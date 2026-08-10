from __future__ import annotations

"""Sincroniza a época 2026/27 e as estatísticas individuais.

Uso:
    python season_sync.py
    python season_sync.py --league "Liga Portugal"
    python season_sync.py --league "Scottish Premiership" --refresh

A ligação à base segue database.get_connection(): SQLite local por defeito e Turso
quando TURSO_DATABASE_URL/TURSO_AUTH_TOKEN estão configurados com permissões de escrita.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from database import BASE_DIR, SEASON, get_connection, init_db
from historical_import import (
    COMPETITIONS,
    HISTORY_SEASON,
    extract_incidents,
    extract_statistics,
    fetch_event_bundle,
    get_json,
    import_league_history,
    match_current_team,
)

CACHE_DIR = BASE_DIR / "data" / "current_season_cache"
TARGET_SEASON = "26/27"
FINISHED = {"finished", "afterpenalties", "afterextra"}


def _season_id(tournament_id: int, refresh: bool = False) -> int:
    data = get_json(
        f"unique-tournament/{tournament_id}/seasons",
        CACHE_DIR,
        refresh=refresh,
    )
    for season in data.get("seasons", []):
        year = str(season.get("year", "")).replace("\\/", "/")
        name = str(season.get("name", "")).replace("\\/", "/")
        if year == TARGET_SEASON or TARGET_SEASON in name:
            return int(season["id"])
    raise RuntimeError(f"Não foi encontrada a época {TARGET_SEASON} no torneio {tournament_id}.")


def _events(tournament_id: int, season_id: int, refresh: bool = False) -> list[dict]:
    found: dict[int, dict] = {}
    # 'last' contém o passado/atual e 'next' o calendário futuro.
    for direction in ("last", "next"):
        for page in range(60):
            try:
                data = get_json(
                    f"unique-tournament/{tournament_id}/season/{season_id}/events/{direction}/{page}",
                    CACHE_DIR,
                    refresh=refresh,
                )
            except Exception:
                if page == 0:
                    continue
                break
            current = data.get("events", [])
            for event in current:
                event_id = event.get("id")
                if event_id:
                    found[int(event_id)] = event
            if not current or not data.get("hasNextPage"):
                break
    return sorted(found.values(), key=lambda e: int(e.get("startTimestamp") or 0))


def _status(event: dict) -> str:
    kind = str((event.get("status") or {}).get("type") or "").lower()
    if kind in FINISHED:
        return "Concluído"
    if kind in {"inprogress", "live", "halftime"}:
        return "Em curso"
    if kind in {"postponed"}:
        return "Adiado"
    if kind in {"canceled", "cancelled"}:
        return "Cancelado"
    return "Agendado"


def _score(event: dict, side: str, key: str, default=None):
    value = (event.get(f"{side}Score") or {}).get(key)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _stat(stats: dict, period: str, key: str, side: int, default=None):
    value = stats.get(period, {}).get(key)
    if not value:
        return default
    return value[side]


def _league_id(conn, name: str, country: str = "") -> int:
    row = conn.execute("SELECT id FROM leagues WHERE name=?", (name,)).fetchone()
    if row:
        return int(row["id"])
    conn.execute(
        "INSERT INTO leagues(name,country,season) VALUES(?,?,?)",
        (name, country or "—", SEASON),
    )
    return int(conn.execute("SELECT id FROM leagues WHERE name=?", (name,)).fetchone()["id"])


def _ensure_team(conn, league_id: int, team: dict) -> int:
    ext_id = team.get("id")
    name = str(team.get("name") or team.get("shortName") or "Equipa").strip()
    team_id = match_current_team(conn, league_id, ext_id, name)
    if team_id:
        return int(team_id)

    conn.execute("INSERT OR IGNORE INTO teams(league_id,name) VALUES(?,?)", (league_id, name))
    row = conn.execute("SELECT id FROM teams WHERE league_id=? AND name=?", (league_id, name)).fetchone()
    team_id = int(row["id"])
    if ext_id:
        conn.execute(
            """
            INSERT INTO team_external_ids(team_id,league_id,external_team_id,source,external_name)
            VALUES(?,?,?,?,?)
            ON CONFLICT(league_id,external_team_id)
            DO UPDATE SET team_id=excluded.team_id,external_name=excluded.external_name
            """,
            (team_id, league_id, int(ext_id), "SofaScore", name),
        )
    return team_id


def _event_datetime(event: dict) -> tuple[str, str]:
    stamp = event.get("startTimestamp")
    if not stamp:
        return "", ""
    dt = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(ZoneInfo("Europe/Lisbon"))
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _referee_id(conn, name: str | None):
    if not name:
        return None
    conn.execute("INSERT OR IGNORE INTO referees(name) VALUES(?)", (str(name),))
    row = conn.execute("SELECT id FROM referees WHERE name=?", (str(name),)).fetchone()
    return int(row["id"]) if row else None


def _upsert_match(conn, league_id: int, event: dict, detailed: dict | None = None) -> int:
    detailed = detailed or event
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    home_id = _ensure_team(conn, league_id, home)
    away_id = _ensure_team(conn, league_id, away)
    event_id = int(event["id"])
    match_date, match_time = _event_datetime(event)
    round_number = int((event.get("roundInfo") or {}).get("round") or 0)
    status = _status(event)

    venue = detailed.get("venue") or event.get("venue") or {}
    stadium = ((venue.get("stadium") or {}).get("name") or venue.get("name") or "")
    referee = detailed.get("referee") or event.get("referee") or {}
    referee_id = _referee_id(conn, referee.get("name") if isinstance(referee, dict) else None)

    row = conn.execute("SELECT id FROM matches WHERE sofascore_event_id=?", (event_id,)).fetchone()
    if not row:
        row = conn.execute(
            """
            SELECT id FROM matches
            WHERE league_id=? AND season=? AND home_team_id=? AND away_team_id=?
            ORDER BY CASE WHEN round_number=? THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (league_id, SEASON, home_id, away_id, round_number),
        ).fetchone()

    values = (
        league_id, SEASON, round_number, match_date, match_time, home_id, away_id,
        stadium, status, referee_id, event_id, "SofaScore", str(event_id), 0,
    )
    if row:
        match_id = int(row["id"])
        conn.execute(
            """
            UPDATE matches SET
                league_id=?,season=?,round_number=?,match_date=?,match_time=?,
                home_team_id=?,away_team_id=?,stadium=?,status=?,referee_id=?,
                sofascore_event_id=?,source=?,source_match_number=?,schedule_provisional=?,
                updated_at=CURRENT_TIMESTAMP
            WHERE id=?
            """,
            values + (match_id,),
        )
    else:
        conn.execute(
            """
            INSERT INTO matches(
                league_id,season,round_number,match_date,match_time,home_team_id,away_team_id,
                stadium,status,referee_id,sofascore_event_id,source,source_match_number,schedule_provisional
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            values,
        )
        match_id = int(conn.execute("SELECT id FROM matches WHERE sofascore_event_id=?", (event_id,)).fetchone()["id"])
    return match_id


def _update_finished_match(conn, match_id: int, event: dict, detailed: dict, stats: dict, cards: dict, goal_minutes: str):
    ht_h = _score(event, "home", "period1", 0)
    ht_a = _score(event, "away", "period1", 0)
    ft_h = _score(event, "home", "normaltime", _score(event, "home", "current", 0))
    ft_a = _score(event, "away", "normaltime", _score(event, "away", "current", 0))
    sh_h = max(0, (ft_h or 0) - (ht_h or 0))
    sh_a = max(0, (ft_a or 0) - (ht_a or 0))

    values = {}
    for prefix, period in (("fh", "first"), ("sh", "second"), ("", "all")):
        for key in ("xg", "shots", "shots_on_target", "corners", "fouls", "offsides"):
            values[f"{prefix}_home_{key}".strip("_")] = _stat(stats, period, key, 0)
            values[f"{prefix}_away_{key}".strip("_")] = _stat(stats, period, key, 1)

    for half, prefix in (("first", "fh"), ("second", "sh")):
        for side in ("home", "away"):
            values[f"{prefix}_{side}_yellow"] = cards[half][f"{side}_yellow"]
            values[f"{prefix}_{side}_red"] = cards[half][f"{side}_red"]
    values["home_yellow"] = values["fh_home_yellow"] + values["sh_home_yellow"]
    values["away_yellow"] = values["fh_away_yellow"] + values["sh_away_yellow"]
    values["home_red"] = values["fh_home_red"] + values["sh_home_red"]
    values["away_red"] = values["fh_away_red"] + values["sh_away_red"]

    columns = [
        "ht_home_goals","ht_away_goals","sh_home_goals","sh_away_goals","ft_home_goals","ft_away_goals","goal_minutes",
        "fh_home_xg","fh_away_xg","sh_home_xg","sh_away_xg","home_xg","away_xg",
        "fh_home_shots","fh_away_shots","sh_home_shots","sh_away_shots","home_shots","away_shots",
        "fh_home_shots_on_target","fh_away_shots_on_target","sh_home_shots_on_target","sh_away_shots_on_target","home_shots_on_target","away_shots_on_target",
        "fh_home_corners","fh_away_corners","sh_home_corners","sh_away_corners","home_corners","away_corners",
        "fh_home_fouls","fh_away_fouls","sh_home_fouls","sh_away_fouls","home_fouls","away_fouls",
        "fh_home_offsides","fh_away_offsides","sh_home_offsides","sh_away_offsides","home_offsides","away_offsides",
        "fh_home_yellow","fh_away_yellow","sh_home_yellow","sh_away_yellow","home_yellow","away_yellow",
        "fh_home_red","fh_away_red","sh_home_red","sh_away_red","home_red","away_red",
        "stats_split_confirmed","status",
    ]
    vals = [ht_h, ht_a, sh_h, sh_a, ft_h, ft_a, goal_minutes]
    vals += [values.get(c) for c in columns[7:-2]]
    vals += [1 if stats.get("first") or stats.get("second") else 0, "Concluído"]
    assignments = ",".join(f"{col}=?" for col in columns)
    conn.execute(f"UPDATE matches SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?", tuple(vals) + (match_id,))


def _first(stats: dict, *keys, default=None):
    for key in keys:
        value = stats.get(key)
        if value is not None:
            return value
    return default


def _number(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace("%", "").replace(",", "."))
    except Exception:
        return default


def _player_id(conn, team_id: int, row: dict) -> int | None:
    player = row.get("player") or {}
    ext = player.get("id")
    name = str(player.get("name") or player.get("shortName") or "").strip()
    if not name:
        return None
    if ext:
        existing = conn.execute("SELECT id FROM players WHERE sofascore_player_id=?", (int(ext),)).fetchone()
        if existing:
            pid = int(existing["id"])
            conn.execute(
                """
                UPDATE players SET team_id=?,name=?,short_name=?,position=?,shirt_number=?,active=1,updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (team_id, name, player.get("shortName"), player.get("position"), row.get("shirtNumber"), pid),
            )
            return pid
    conn.execute(
        """
        INSERT INTO players(sofascore_player_id,team_id,name,short_name,position,shirt_number)
        VALUES(?,?,?,?,?,?)
        """,
        (int(ext) if ext else None, team_id, name, player.get("shortName"), player.get("position"), row.get("shirtNumber")),
    )
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])


def _save_lineups(conn, match_id: int, home_team_id: int, away_team_id: int, event_id: int, refresh: bool = False) -> int:
    try:
        payload = get_json(f"event/{event_id}/lineups", CACHE_DIR, refresh=refresh)
    except Exception:
        return 0

    saved = 0
    for side, team_id in (("home", home_team_id), ("away", away_team_id)):
        block = payload.get(side) or {}
        for row in block.get("players", []):
            pid = _player_id(conn, team_id, row)
            if not pid:
                continue
            st = row.get("statistics") or {}
            substitute = 1 if row.get("substitute") else 0
            started = 0 if substitute else 1
            minutes = _number(_first(st, "minutesPlayed", "minutes", default=0), 0)
            normalized = {
                "rating": _number(_first(st, "rating")),
                "goals": _number(_first(st, "goals", default=0), 0),
                "assists": _number(_first(st, "goalAssist", "assists", default=0), 0),
                "xg": _number(_first(st, "expectedGoals", "xg")),
                "xa": _number(_first(st, "expectedAssists", "xa")),
                "shots": _number(_first(st, "totalShots", "totalScoringAttempt")),
                "shots_on_target": _number(_first(st, "onTargetScoringAttempt", "shotsOnTarget")),
                "key_passes": _number(_first(st, "keyPass", "keyPasses")),
                "passes_total": _number(_first(st, "totalPass", "passes")),
                "passes_accurate": _number(_first(st, "accuratePass", "accuratePasses")),
                "touches": _number(_first(st, "touches")),
                "tackles": _number(_first(st, "totalTackle", "tackles")),
                "interceptions": _number(_first(st, "interceptionWon", "interceptions")),
                "clearances": _number(_first(st, "totalClearance", "clearances")),
                "blocks": _number(_first(st, "blockedScoringAttempt", "blocks")),
                "duels": _number(_first(st, "totalContest", "duels")),
                "duels_won": _number(_first(st, "wonContest", "duelsWon")),
                "aerial_duels": _number(_first(st, "aerialWon"), 0) + _number(_first(st, "aerialLost"), 0),
                "aerial_duels_won": _number(_first(st, "aerialWon")),
                "fouls": _number(_first(st, "fouls", "foulsCommitted")),
                "fouled": _number(_first(st, "wasFouled")),
                "offsides": _number(_first(st, "totalOffside", "offsides")),
                "yellow_cards": _number(_first(st, "yellowCards", default=0), 0),
                "red_cards": _number(_first(st, "redCards", default=0), 0),
                "saves": _number(_first(st, "saves", "totalKeeperSweeper")),
                "goals_prevented": _number(_first(st, "goalsPrevented")),
                "possession_lost": _number(_first(st, "possessionLostCtrl", "possessionLost")),
                "dispossessed": _number(_first(st, "dispossessed")),
            }
            cols = [
                "match_id","player_id","team_id","season","started","substitute","minutes",
                *normalized.keys(),"stats_json","source",
            ]
            vals = [
                match_id,pid,team_id,SEASON,started,substitute,minutes,
                *normalized.values(),json.dumps(st, ensure_ascii=False, separators=(",", ":")),"SofaScore",
            ]
            placeholders = ",".join("?" for _ in cols)
            updates = ",".join(f"{c}=excluded.{c}" for c in cols if c not in {"match_id","player_id"})
            conn.execute(
                f"""
                INSERT INTO player_match_stats({','.join(cols)}) VALUES({placeholders})
                ON CONFLICT(match_id,player_id) DO UPDATE SET {updates},updated_at=CURRENT_TIMESTAMP
                """,
                tuple(vals),
            )
            saved += 1
    return saved


def sync_league(league_name: str, refresh: bool = False) -> dict:
    config = COMPETITIONS[league_name]
    tournament_id = int(config["top"])
    season_id = _season_id(tournament_id, refresh=refresh)
    events = _events(tournament_id, season_id, refresh=refresh)
    if not events:
        raise RuntimeError("Nenhum jogo encontrado.")

    country = {
        "Premier League":"Inglaterra", "Ligue 1":"França", "Serie A":"Itália", "LaLiga":"Espanha",
        "Liga Portugal":"Portugal", "Süper Lig":"Turquia", "Eredivisie":"Países Baixos",
        "Bundesliga":"Alemanha", "Pro League":"Bélgica", "Scottish Premiership":"Escócia",
    }.get(league_name, "—")

    result = {"league": league_name, "events": len(events), "finished": 0, "player_rows": 0, "errors": []}
    with get_connection() as conn:
        league_id = _league_id(conn, league_name, country)
        for event in events:
            try:
                kind = str((event.get("status") or {}).get("type") or "").lower()
                detailed = event
                stats = {"all": {}, "first": {}, "second": {}}
                cards = {
                    "first":{"home_yellow":0,"away_yellow":0,"home_red":0,"away_red":0},
                    "second":{"home_yellow":0,"away_yellow":0,"home_red":0,"away_red":0},
                }
                goal_minutes = ""
                if kind in FINISHED:
                    detailed, stats, cards, goal_minutes = fetch_event_bundle(event, CACHE_DIR, refresh=refresh)
                match_id = _upsert_match(conn, league_id, event, detailed)
                if kind in FINISHED:
                    _update_finished_match(conn, match_id, event, detailed, stats, cards, goal_minutes)
                    match = conn.execute("SELECT home_team_id,away_team_id FROM matches WHERE id=?", (match_id,)).fetchone()
                    result["player_rows"] += _save_lineups(
                        conn, match_id, int(match["home_team_id"]), int(match["away_team_id"]), int(event["id"]), refresh=refresh
                    )
                    result["finished"] += 1
                conn.commit()
            except Exception as exc:
                result["errors"].append(f"{event.get('id')}: {type(exc).__name__}: {exc}")
        conn.commit()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza DidAnalyze com resultados/estatísticas 2026/27.")
    parser.add_argument("--league", action="append", help="Liga a sincronizar; pode ser repetido.")
    parser.add_argument("--refresh", action="store_true", help="Ignora a cache e volta a consultar a fonte.")
    args = parser.parse_args()

    init_db()
    names = args.league or list(COMPETITIONS.keys())
    unknown = [name for name in names if name not in COMPETITIONS]
    if unknown:
        print("Ligas desconhecidas:", ", ".join(unknown))
        return 2

    total_errors = 0
    print(f"DidAnalyze · sincronização {SEASON}")
    for name in names:
        try:
            result = sync_league(name, refresh=args.refresh)
            total_errors += len(result["errors"])
            print(
                f"✓ {name}: {result['events']} jogos no calendário · "
                f"{result['finished']} concluídos · {result['player_rows']} linhas de jogadores"
            )
            for error in result["errors"][:5]:
                print("  !", error)
            if len(result["errors"]) > 5:
                print(f"  ! +{len(result['errors'])-5} erros")

            # A Escócia é nova no DidAnalyze: na primeira sincronização carrega
            # automaticamente 2025/26 para o modelo não começar sem histórico.
            if name == "Scottish Premiership":
                with get_connection() as conn:
                    lid = conn.execute("SELECT id FROM leagues WHERE name=?", (name,)).fetchone()
                    hist_n = 0 if not lid else conn.execute(
                        "SELECT COUNT(*) AS n FROM historical_matches WHERE target_league_id=? AND season=?",
                        (int(lid["id"]), HISTORY_SEASON),
                    ).fetchone()["n"]
                    if int(hist_n or 0) < 50:
                        print("  ↳ A carregar histórico 2025/26 da Escócia (primeira execução)...")
                        hist = import_league_history(
                            conn, name, BASE_DIR / "data" / "historical_cache",
                            refresh=args.refresh, max_workers=4,
                        )
                        print(f"  ✓ Histórico Escócia: {hist['imported']} jogos importados")
        except Exception as exc:
            total_errors += 1
            print(f"✗ {name}: {type(exc).__name__}: {exc}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
