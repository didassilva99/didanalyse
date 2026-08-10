from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
import json
import math
import re
import sqlite3
import time
import unicodedata
import urllib.error
import urllib.request

HISTORY_SEASON = "2025/26"
BASE_URLS = (
    "https://api.sofascore.com/api/v1",
    "https://www.sofascore.com/api/v1",
)

# IDs públicos das competições no SofaScore.
COMPETITIONS = {
    "Premier League": {"top": 17, "second": 18, "second_name": "Championship"},
    "Ligue 1": {"top": 34, "second": 182, "second_name": "Ligue 2"},
    "Serie A": {"top": 23, "second": 53, "second_name": "Serie B"},
    "LaLiga": {"top": 8, "second": 54, "second_name": "LaLiga 2"},
    "Liga Portugal": {"top": 238, "second": 239, "second_name": "Liga Portugal 2"},
    "Süper Lig": {"top": 52, "second": 98, "second_name": "1. Lig"},
    "Eredivisie": {"top": 37, "second": 131, "second_name": "Eerste Divisie"},
    "Bundesliga": {"top": 35, "second": 44, "second_name": "2. Bundesliga"},
    "Pro League": {"top": 38, "second": 9, "second_name": "Challenger Pro League"},
    "Scottish Premiership": {"top": 36, "second": 206, "second_name": "Scottish Championship"},
}

STAT_ALIASES = {
    "expected goals": "xg",
    "expected goals (xg)": "xg",
    "total shots": "shots",
    "shots total": "shots",
    "shots on target": "shots_on_target",
    "corner kicks": "corners",
    "corners": "corners",
    "fouls": "fouls",
    "fouls committed": "fouls",
    "offsides": "offsides",
    "yellow cards": "yellow",
    "red cards": "red",
}

CLUB_WORDS = {
    "fc", "cf", "sc", "ac", "afc", "sv", "fk", "rc", "rsc", "kv", "kvc",
    "club", "calcio", "futbol", "football", "de", "the", "sk", "as", "us",
}


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _club_key(value: str) -> str:
    tokens = [x for x in _normalise(value).split() if x not in CLUB_WORDS]
    return " ".join(tokens)


def _num(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", ".")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


def _cache_path(cache_dir: Path, path: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", path.strip("/"))
    return cache_dir / f"{safe}.json"


def get_json(path: str, cache_dir: Path, refresh: bool = False, retries: int = 3):
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(cache_dir, path)
    if cache.exists() and not refresh:
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    last_error = None
    for attempt in range(retries):
        for base in BASE_URLS:
            request = urllib.request.Request(
                f"{base}/{path.lstrip('/')}",
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AnaliseApostas/2.0",
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": "https://www.sofascore.com/",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=35) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                cache.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429:
                    time.sleep(2 + attempt * 2)
                elif exc.code in {404, 410}:
                    raise
            except Exception as exc:
                last_error = exc
        time.sleep(1 + attempt)
    raise RuntimeError(f"Falha ao obter {path}: {last_error}")


def season_id(tournament_id: int, cache_dir: Path) -> int:
    data = get_json(f"unique-tournament/{tournament_id}/seasons", cache_dir)
    for season in data.get("seasons", []):
        year = str(season.get("year", "")).replace("\\/", "/")
        name = str(season.get("name", "")).replace("\\/", "/")
        if year == "25/26" or "25/26" in name:
            return int(season["id"])
    raise RuntimeError(f"Não foi encontrada a época 25/26 para o torneio {tournament_id}.")


def tournament_events(tournament_id: int, season: int, cache_dir: Path):
    events = []
    seen = set()
    page = 0
    while page < 60:
        data = get_json(
            f"unique-tournament/{tournament_id}/season/{season}/events/last/{page}",
            cache_dir,
        )
        current = data.get("events", [])
        for event in current:
            event_id = event.get("id")
            if event_id and event_id not in seen:
                seen.add(event_id)
                events.append(event)
        if not data.get("hasNextPage") or not current:
            break
        page += 1
    return events


def _period_key(value: str):
    text = _normalise(value)
    if text in {"all", "match", "full time", "ft"}:
        return "all"
    if text in {"1st", "first half", "first", "1 half"}:
        return "first"
    if text in {"2nd", "second half", "second", "2 half"}:
        return "second"
    return None


def extract_statistics(payload):
    result = {"all": {}, "first": {}, "second": {}}
    for section in payload.get("statistics", []):
        period = _period_key(section.get("period", ""))
        if not period:
            continue
        for group in section.get("groups", []):
            for item in group.get("statisticsItems", []):
                name = _normalise(item.get("name", ""))
                key = STAT_ALIASES.get(name)
                if not key:
                    continue
                home = _num(item.get("homeValue"))
                away = _num(item.get("awayValue"))
                if home is None:
                    home = _num(item.get("home"))
                if away is None:
                    away = _num(item.get("away"))
                result[period][key] = (home, away)
    return result


def _minute_token(incident):
    minute = incident.get("time")
    if minute is None:
        return None
    added = incident.get("addedTime") or 0
    try:
        minute = int(minute)
        added = int(added)
    except Exception:
        return None
    return f"{minute}+{added}" if added else str(minute)


def extract_incidents(payload):
    cards = {
        "first": {"home_yellow": 0, "away_yellow": 0, "home_red": 0, "away_red": 0},
        "second": {"home_yellow": 0, "away_yellow": 0, "home_red": 0, "away_red": 0},
    }
    goal_minutes = []
    for incident in payload.get("incidents", []):
        incident_type = incident.get("incidentType")
        minute = incident.get("time")
        added = incident.get("addedTime") or 0
        try:
            effective_minute = int(minute or 0) + int(added or 0)
        except Exception:
            effective_minute = 0
        half = "first" if int(minute or 0) <= 45 else "second"
        is_home = bool(incident.get("isHome"))
        side = "home" if is_home else "away"

        if incident_type == "goal":
            token = _minute_token(incident)
            if token:
                goal_minutes.append((effective_minute, token))
        elif incident_type == "card":
            kind = _normalise(incident.get("incidentClass", ""))
            if kind in {"yellow", "yellow card"}:
                cards[half][f"{side}_yellow"] += 1
            elif kind in {"red", "red card"}:
                cards[half][f"{side}_red"] += 1
            elif kind in {"yellow red", "yellowred", "second yellow"}:
                cards[half][f"{side}_yellow"] += 1
                cards[half][f"{side}_red"] += 1
    goal_minutes.sort(key=lambda x: x[0])
    return cards, ", ".join(token for _, token in goal_minutes)


def _score(event, side: str, key: str, default=None):
    value = (event.get(f"{side}Score") or {}).get(key)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _stat(stats, period, key, side_index, default=None):
    value = stats.get(period, {}).get(key)
    if not value:
        return default
    return value[side_index]


def _event_detail(event_id: int, cache_dir: Path):
    data = get_json(f"event/{event_id}", cache_dir)
    return data.get("event", data)


def fetch_event_bundle(event, cache_dir: Path, refresh=False):
    event_id = int(event["id"])
    try:
        stats_payload = get_json(f"event/{event_id}/statistics", cache_dir, refresh=refresh)
    except Exception:
        stats_payload = {"statistics": []}
    try:
        incidents_payload = get_json(f"event/{event_id}/incidents", cache_dir, refresh=refresh)
    except Exception:
        incidents_payload = {"incidents": []}

    detailed = event
    if not event.get("referee") or not event.get("venue"):
        try:
            detailed = _event_detail(event_id, cache_dir)
        except Exception:
            detailed = event

    stats = extract_statistics(stats_payload)
    cards, goal_minutes = extract_incidents(incidents_payload)
    return detailed, stats, cards, goal_minutes


def _current_teams(conn, league_id):
    return conn.execute(
        "SELECT id,name FROM teams WHERE league_id=? ORDER BY name", (league_id,)
    ).fetchall()


def match_current_team(conn, league_id, external_id, name):
    if external_id:
        mapped = conn.execute(
            "SELECT team_id FROM team_external_ids WHERE external_team_id=? AND league_id=?",
            (int(external_id), league_id),
        ).fetchone()
        if mapped:
            return mapped["team_id"]

    teams = _current_teams(conn, league_id)
    normal = _normalise(name)
    key = _club_key(name)
    exact = [row for row in teams if _normalise(row["name"]) == normal]
    if not exact:
        exact = [row for row in teams if _club_key(row["name"]) == key and key]
    if exact:
        team_id = exact[0]["id"]
    else:
        best = None
        best_score = 0.0
        for row in teams:
            score = max(
                SequenceMatcher(None, normal, _normalise(row["name"])).ratio(),
                SequenceMatcher(None, key, _club_key(row["name"])).ratio() if key else 0,
            )
            if score > best_score:
                best, best_score = row, score
        team_id = best["id"] if best is not None and best_score >= 0.84 else None

    if team_id and external_id:
        conn.execute(
            """
            INSERT INTO team_external_ids(team_id,league_id,external_team_id,source,external_name)
            VALUES(?,?,?,?,?)
            ON CONFLICT(league_id,external_team_id)
            DO UPDATE SET team_id=excluded.team_id, external_name=excluded.external_name
            """,
            (team_id, league_id, int(external_id), "SofaScore", str(name)),
        )
    return team_id


def _insert_historical_match(
    conn, league_id, source_level, tournament_id, source_season_id,
    event, detailed, stats, cards, goal_minutes,
):
    home = event.get("homeTeam") or {}
    away = event.get("awayTeam") or {}
    home_ext = home.get("id")
    away_ext = away.get("id")
    home_current = match_current_team(conn, league_id, home_ext, home.get("name", ""))
    away_current = match_current_team(conn, league_id, away_ext, away.get("name", ""))

    timestamp = event.get("startTimestamp")
    match_date = ""
    match_time = ""
    if timestamp:
        dt = datetime.fromtimestamp(int(timestamp), timezone.utc).astimezone()
        match_date = dt.strftime("%Y-%m-%d")
        match_time = dt.strftime("%H:%M")

    referee = (detailed.get("referee") or {}).get("name")
    venue = detailed.get("venue") or {}
    stadium = ((venue.get("stadium") or {}).get("name") or venue.get("name") or "")

    fh_home_goals = _score(event, "home", "period1", 0)
    fh_away_goals = _score(event, "away", "period1", 0)
    ft_home_goals = _score(event, "home", "normaltime", _score(event, "home", "current", 0))
    ft_away_goals = _score(event, "away", "normaltime", _score(event, "away", "current", 0))
    sh_home_goals = max(0, (ft_home_goals or 0) - (fh_home_goals or 0))
    sh_away_goals = max(0, (ft_away_goals or 0) - (fh_away_goals or 0))

    def value(period, key, side, fallback=None):
        current = _stat(stats, period, key, side, None)
        return fallback if current is None else current

    # Se não houver separação por parte, os totais continuam disponíveis.
    vals = {}
    for prefix, period in (("fh", "first"), ("sh", "second"), ("", "all")):
        for key in ("xg", "shots", "shots_on_target", "corners", "fouls", "offsides"):
            vals[f"{prefix}_home_{key}".strip("_")] = value(period, key, 0)
            vals[f"{prefix}_away_{key}".strip("_")] = value(period, key, 1)

    for half, prefix in (("first", "fh"), ("second", "sh")):
        vals[f"{prefix}_home_yellow"] = cards[half]["home_yellow"]
        vals[f"{prefix}_away_yellow"] = cards[half]["away_yellow"]
        vals[f"{prefix}_home_red"] = cards[half]["home_red"]
        vals[f"{prefix}_away_red"] = cards[half]["away_red"]
    vals["home_yellow"] = vals["fh_home_yellow"] + vals["sh_home_yellow"]
    vals["away_yellow"] = vals["fh_away_yellow"] + vals["sh_away_yellow"]
    vals["home_red"] = vals["fh_home_red"] + vals["sh_home_red"]
    vals["away_red"] = vals["fh_away_red"] + vals["sh_away_red"]

    columns = [
        "target_league_id", "source_level", "source_tournament_id", "source_season_id",
        "source_event_id", "season", "round_number", "match_date", "match_time",
        "home_team_name", "away_team_name", "home_external_id", "away_external_id",
        "home_current_team_id", "away_current_team_id", "referee_name", "stadium",
        "ht_home_goals", "ht_away_goals", "sh_home_goals", "sh_away_goals",
        "ft_home_goals", "ft_away_goals", "goal_minutes",
        "fh_home_xg", "fh_away_xg", "sh_home_xg", "sh_away_xg", "home_xg", "away_xg",
        "fh_home_shots", "fh_away_shots", "sh_home_shots", "sh_away_shots", "home_shots", "away_shots",
        "fh_home_shots_on_target", "fh_away_shots_on_target", "sh_home_shots_on_target", "sh_away_shots_on_target", "home_shots_on_target", "away_shots_on_target",
        "fh_home_corners", "fh_away_corners", "sh_home_corners", "sh_away_corners", "home_corners", "away_corners",
        "fh_home_fouls", "fh_away_fouls", "sh_home_fouls", "sh_away_fouls", "home_fouls", "away_fouls",
        "fh_home_offsides", "fh_away_offsides", "sh_home_offsides", "sh_away_offsides", "home_offsides", "away_offsides",
        "fh_home_yellow", "fh_away_yellow", "sh_home_yellow", "sh_away_yellow", "home_yellow", "away_yellow",
        "fh_home_red", "fh_away_red", "sh_home_red", "sh_away_red", "home_red", "away_red",
        "stats_split_available", "source",
    ]
    values = [
        league_id, source_level, tournament_id, source_season_id,
        int(event["id"]), HISTORY_SEASON, int((event.get("roundInfo") or {}).get("round") or 0),
        match_date, match_time, home.get("name", ""), away.get("name", ""), home_ext, away_ext,
        home_current, away_current, referee, stadium,
        fh_home_goals, fh_away_goals, sh_home_goals, sh_away_goals,
        ft_home_goals, ft_away_goals, goal_minutes,
        vals.get("fh_home_xg"), vals.get("fh_away_xg"), vals.get("sh_home_xg"), vals.get("sh_away_xg"), vals.get("home_xg"), vals.get("away_xg"),
        vals.get("fh_home_shots"), vals.get("fh_away_shots"), vals.get("sh_home_shots"), vals.get("sh_away_shots"), vals.get("home_shots"), vals.get("away_shots"),
        vals.get("fh_home_shots_on_target"), vals.get("fh_away_shots_on_target"), vals.get("sh_home_shots_on_target"), vals.get("sh_away_shots_on_target"), vals.get("home_shots_on_target"), vals.get("away_shots_on_target"),
        vals.get("fh_home_corners"), vals.get("fh_away_corners"), vals.get("sh_home_corners"), vals.get("sh_away_corners"), vals.get("home_corners"), vals.get("away_corners"),
        vals.get("fh_home_fouls"), vals.get("fh_away_fouls"), vals.get("sh_home_fouls"), vals.get("sh_away_fouls"), vals.get("home_fouls"), vals.get("away_fouls"),
        vals.get("fh_home_offsides"), vals.get("fh_away_offsides"), vals.get("sh_home_offsides"), vals.get("sh_away_offsides"), vals.get("home_offsides"), vals.get("away_offsides"),
        vals.get("fh_home_yellow"), vals.get("fh_away_yellow"), vals.get("sh_home_yellow"), vals.get("sh_away_yellow"), vals.get("home_yellow"), vals.get("away_yellow"),
        vals.get("fh_home_red"), vals.get("fh_away_red"), vals.get("sh_home_red"), vals.get("sh_away_red"), vals.get("home_red"), vals.get("away_red"),
        1 if stats.get("first") or stats.get("second") else 0, "SofaScore",
    ]

    placeholders = ",".join("?" for _ in columns)
    updates = ",".join(f"{col}=excluded.{col}" for col in columns if col != "source_event_id")
    conn.execute(
        f"""
        INSERT INTO historical_matches({','.join(columns)}) VALUES({placeholders})
        ON CONFLICT(source_event_id) DO UPDATE SET {updates}, updated_at=CURRENT_TIMESTAMP
        """,
        values,
    )
    return home_current, away_current


def _finished_events(events):
    result = []
    for event in events:
        status = (event.get("status") or {}).get("type")
        if status in {"finished", "afterpenalties", "afterextra"}:
            result.append(event)
    return result


def import_league_history(
    conn: sqlite3.Connection,
    league_name: str,
    cache_dir: Path,
    progress=None,
    refresh: bool = False,
    max_workers: int = 4,
):
    config = COMPETITIONS[league_name]
    league = conn.execute("SELECT id FROM leagues WHERE name=?", (league_name,)).fetchone()
    if not league:
        raise RuntimeError(f"Liga não encontrada: {league_name}")
    league_id = int(league["id"])

    top_season_id = season_id(config["top"], cache_dir)
    top_events = _finished_events(tournament_events(config["top"], top_season_id, cache_dir))

    current_team_ids = {row["id"] for row in _current_teams(conn, league_id)}
    top_mapped = set()
    for event in top_events:
        for side in ("homeTeam", "awayTeam"):
            team = event.get(side) or {}
            mapped = match_current_team(conn, league_id, team.get("id"), team.get("name", ""))
            if mapped:
                top_mapped.add(mapped)
    promoted_ids = current_team_ids - top_mapped

    second_season_id = season_id(config["second"], cache_dir)
    all_second_events = _finished_events(tournament_events(config["second"], second_season_id, cache_dir))
    selected_second_events = []
    for event in all_second_events:
        keep = False
        for side in ("homeTeam", "awayTeam"):
            team = event.get(side) or {}
            mapped = match_current_team(conn, league_id, team.get("id"), team.get("name", ""))
            if mapped in promoted_ids:
                keep = True
        if keep:
            selected_second_events.append(event)

    jobs = [(1, config["top"], top_season_id, event) for event in top_events]
    jobs += [(2, config["second"], second_season_id, event) for event in selected_second_events]

    done = 0
    errors = []
    imported = 0
    if progress:
        progress(0, len(jobs), f"Encontrados {len(top_events)} jogos da primeira divisão e {len(selected_second_events)} jogos relevantes da segunda divisão.")

    def fetch(job):
        level, tournament_id, source_sid, event = job
        bundle = fetch_event_bundle(event, cache_dir, refresh=refresh)
        return level, tournament_id, source_sid, event, bundle

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 6))) as executor:
        futures = {executor.submit(fetch, job): job for job in jobs}
        for future in as_completed(futures):
            level, tournament_id, source_sid, event = futures[future]
            try:
                detailed, stats, cards, goal_minutes = future.result()
                _insert_historical_match(
                    conn, league_id, level, tournament_id, source_sid,
                    event, detailed, stats, cards, goal_minutes,
                )
                imported += 1
                if imported % 15 == 0:
                    conn.commit()
            except Exception as exc:
                errors.append(f"{event.get('id')}: {exc}")
            done += 1
            if progress:
                progress(done, len(jobs), f"{league_name}: {done}/{len(jobs)} jogos processados")
    conn.commit()

    conn.execute(
        """
        INSERT INTO historical_imports(target_league_id,season,top_tournament_id,second_tournament_id,
            imported_matches,error_count,last_error,updated_at)
        VALUES(?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(target_league_id,season) DO UPDATE SET
            imported_matches=excluded.imported_matches,error_count=excluded.error_count,
            last_error=excluded.last_error,updated_at=CURRENT_TIMESTAMP
        """,
        (
            league_id, HISTORY_SEASON, config["top"], config["second"], imported,
            len(errors), errors[-1] if errors else None,
        ),
    )
    conn.commit()

    promoted = [row["name"] for row in _current_teams(conn, league_id) if row["id"] in promoted_ids]
    return {
        "league": league_name,
        "top_matches": len(top_events),
        "second_matches": len(selected_second_events),
        "imported": imported,
        "errors": errors,
        "promoted": promoted,
    }


def history_summary(conn):
    return conn.execute(
        """
        SELECT l.name AS league,
               SUM(CASE WHEN h.source_level=1 THEN 1 ELSE 0 END) AS top_matches,
               SUM(CASE WHEN h.source_level=2 THEN 1 ELSE 0 END) AS second_matches,
               COUNT(DISTINCT CASE WHEN h.source_level=1 THEN h.home_current_team_id END)
                 + COUNT(DISTINCT CASE WHEN h.source_level=1 THEN h.away_current_team_id END) AS mapped_top_sides,
               MAX(h.updated_at) AS updated_at
        FROM leagues l
        LEFT JOIN historical_matches h ON h.target_league_id=l.id AND h.season=?
        GROUP BY l.id ORDER BY l.name
        """,
        (HISTORY_SEASON,),
    ).fetchall()
