from __future__ import annotations

from datetime import date
from html import escape

import pandas as pd

import streamlit as st

from database import SEASON, get_connection, init_db
from model_engine import build_prediction_v3, over_probability
from simple_site_ui import (
    brand_header,
    confidence_badge,
    footer,
    inject_styles,
    match_hero,
    note,
    outcome_cards,
    page_intro,
    picker_header,
    probability_list,
    score_cards,
    section_title,
    stat_cards,
)



HISTORY_SEASON = "2025/26"


def transfer_score(connection, team_id: int) -> dict:
    row = connection.execute(
        """
        SELECT *
        FROM transfer_team_scores
        WHERE team_id=? AND season=?
        """,
        (team_id, SEASON),
    ).fetchone()

    if row is None:
        return {
            "attack_delta": 0.0,
            "midfield_delta": 0.0,
            "defence_delta": 0.0,
            "goalkeeper_delta": 0.0,
            "overall_delta": 0.0,
            "arrivals": 0,
            "departures": 0,
        }

    return dict(row)


st.set_page_config(
    page_title="DidAnalyze",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_styles()
init_db()
brand_header()

def _player_table_available() -> bool:
    try:
        with get_connection() as conn:
            conn.execute("SELECT 1 FROM player_match_stats LIMIT 1").fetchone()
        return True
    except Exception:
        return False


def render_players_page() -> None:
    section_title("Jogadores", "Médias e acumulados individuais da época 2026/27")

    if not _player_table_available():
        st.info(
            "A estrutura de jogadores ainda não foi criada na base pública. "
            "Executa season_sync.py com acesso de escrita à base e volta a publicar/sincronizar."
        )
        return

    with get_connection() as conn:
        leagues = conn.execute(
            """
            SELECT DISTINCT l.id,l.name,l.country
            FROM leagues l
            JOIN teams t ON t.league_id=l.id
            JOIN player_match_stats pms ON pms.team_id=t.id AND pms.season=?
            ORDER BY l.name
            """,
            (SEASON,),
        ).fetchall()

    if not leagues:
        st.info("Ainda não existem estatísticas individuais carregadas para 2026/27.")
        return

    league_labels = [f"{row['name']} · {row['country']}" for row in leagues]
    league_label = st.selectbox("Competição", league_labels, key="players_league")
    league = leagues[league_labels.index(league_label)]
    league_id = int(league["id"])

    with get_connection() as conn:
        teams = conn.execute(
            """
            SELECT DISTINCT t.id,t.name
            FROM teams t
            JOIN player_match_stats pms ON pms.team_id=t.id AND pms.season=?
            WHERE t.league_id=?
            ORDER BY t.name
            """,
            (SEASON, league_id),
        ).fetchall()

    team_options = ["Todas as equipas"] + [row["name"] for row in teams]
    team_name = st.selectbox("Equipa", team_options, key="players_team")
    team_id = None
    if team_name != "Todas as equipas":
        team_id = int(next(row["id"] for row in teams if row["name"] == team_name))

    params = [SEASON, league_id]
    team_sql = ""
    if team_id is not None:
        team_sql = " AND pms.team_id=?"
        params.append(team_id)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT
                p.id AS player_id,
                p.name,
                COALESCE(p.position,'—') AS position,
                t.name AS team,
                COUNT(DISTINCT pms.match_id) AS apps,
                SUM(COALESCE(pms.started,0)) AS starts,
                ROUND(SUM(COALESCE(pms.minutes,0)),0) AS minutes,
                ROUND(AVG(CASE WHEN pms.rating IS NOT NULL THEN pms.rating END),2) AS avg_rating,
                SUM(COALESCE(pms.goals,0)) AS goals,
                SUM(COALESCE(pms.assists,0)) AS assists,
                ROUND(SUM(COALESCE(pms.xg,0)),2) AS xg,
                ROUND(SUM(COALESCE(pms.xa,0)),2) AS xa,
                SUM(COALESCE(pms.shots,0)) AS shots,
                SUM(COALESCE(pms.shots_on_target,0)) AS shots_on_target,
                SUM(COALESCE(pms.key_passes,0)) AS key_passes,
                SUM(COALESCE(pms.passes_total,0)) AS passes_total,
                SUM(COALESCE(pms.passes_accurate,0)) AS passes_accurate,
                SUM(COALESCE(pms.tackles,0)) AS tackles,
                SUM(COALESCE(pms.interceptions,0)) AS interceptions,
                SUM(COALESCE(pms.saves,0)) AS saves
            FROM player_match_stats pms
            JOIN players p ON p.id=pms.player_id
            JOIN teams t ON t.id=pms.team_id
            WHERE pms.season=? AND t.league_id=? {team_sql}
            GROUP BY p.id,p.name,p.position,t.name
            ORDER BY CASE WHEN avg_rating IS NULL THEN 1 ELSE 0 END, avg_rating DESC, minutes DESC
            """,
            tuple(params),
        ).fetchall()

    if not rows:
        st.info("Não há jogadores com estatísticas nesta seleção.")
        return

    data = pd.DataFrame([dict(row) for row in rows])
    numeric = [
        "apps", "starts", "minutes", "avg_rating", "goals", "assists", "xg", "xa",
        "shots", "shots_on_target", "key_passes", "passes_total", "passes_accurate",
        "tackles", "interceptions", "saves",
    ]
    for column in numeric:
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0)

    data["g+a"] = data["goals"] + data["assists"]
    data["passes_%"] = data.apply(
        lambda row: (100.0 * row["passes_accurate"] / row["passes_total"]) if row["passes_total"] else 0.0,
        axis=1,
    )
    for source, target in [
        ("shots", "remates/90"),
        ("key_passes", "passes-chave/90"),
        ("tackles", "desarmes/90"),
        ("interceptions", "interceções/90"),
        ("saves", "defesas/90"),
    ]:
        data[target] = data.apply(
            lambda row, source=source: (90.0 * row[source] / row["minutes"]) if row["minutes"] else 0.0,
            axis=1,
        )

    rated = data[data["avg_rating"] > 0].copy()
    best = rated.iloc[0] if not rated.empty else data.iloc[0]
    scorer = data.sort_values(["goals", "minutes"], ascending=[False, False]).iloc[0]
    creator = data.sort_values(["assists", "key_passes"], ascending=[False, False]).iloc[0]
    most_used = data.sort_values("minutes", ascending=False).iloc[0]
    stat_cards(
        [
            ("Melhor média", str(best["name"]), f"{best['avg_rating']:.2f}" if best["avg_rating"] else "—"),
            ("Mais golos", str(scorer["name"]), f"{int(scorer['goals'])}"),
            ("Mais assistências", str(creator["name"]), f"{int(creator['assists'])}"),
            ("Mais minutos", str(most_used["name"]), f"{int(most_used['minutes'])}"),
        ]
    )

    section_title("Ranking da época", "Média por jogo e produção por 90 minutos")
    display = data[[
        "name", "team", "position", "apps", "starts", "minutes", "avg_rating",
        "goals", "assists", "g+a", "xg", "xa", "remates/90", "passes-chave/90",
        "passes_%", "desarmes/90", "interceções/90", "defesas/90",
    ]].copy()
    display.columns = [
        "Jogador", "Equipa", "Pos.", "Jogos", "Titular", "Min.", "Nota média",
        "Golos", "Assist.", "G+A", "xG", "xA", "Remates/90", "Passes-chave/90",
        "Passes %", "Desarmes/90", "Interceções/90", "Defesas/90",
    ]
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Nota média": st.column_config.NumberColumn(format="%.2f"),
            "xG": st.column_config.NumberColumn(format="%.2f"),
            "xA": st.column_config.NumberColumn(format="%.2f"),
            "Remates/90": st.column_config.NumberColumn(format="%.2f"),
            "Passes-chave/90": st.column_config.NumberColumn(format="%.2f"),
            "Passes %": st.column_config.NumberColumn(format="%.1f%%"),
            "Desarmes/90": st.column_config.NumberColumn(format="%.2f"),
            "Interceções/90": st.column_config.NumberColumn(format="%.2f"),
            "Defesas/90": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    section_title("Evolução de um jogador", "Nota jogo a jogo")
    player_names = data.sort_values("name")["name"].tolist()
    selected_name = st.selectbox("Jogador", player_names, key="player_detail")
    selected_id = int(data.loc[data["name"] == selected_name, "player_id"].iloc[0])
    with get_connection() as conn:
        form = conn.execute(
            """
            SELECT m.match_date,
                   th.name AS home, ta.name AS away,
                   pms.minutes,pms.rating,pms.goals,pms.assists
            FROM player_match_stats pms
            JOIN matches m ON m.id=pms.match_id
            JOIN teams th ON th.id=m.home_team_id
            JOIN teams ta ON ta.id=m.away_team_id
            WHERE pms.player_id=? AND pms.season=?
            ORDER BY m.match_date,m.match_time
            """,
            (selected_id, SEASON),
        ).fetchall()
    if form:
        form_df = pd.DataFrame([dict(row) for row in form])
        form_df["Jogo"] = form_df["home"] + " × " + form_df["away"]
        form_df["rating"] = pd.to_numeric(form_df["rating"], errors="coerce")
        chart_df = form_df.dropna(subset=["rating"])[["match_date", "rating"]].set_index("match_date")
        if not chart_df.empty:
            st.line_chart(chart_df, y="rating")
        st.dataframe(
            form_df[["match_date", "Jogo", "minutes", "rating", "goals", "assists"]].rename(
                columns={"match_date":"Data","minutes":"Min.","rating":"Nota","goals":"Golos","assists":"Assist."}
            ),
            use_container_width=True,
            hide_index=True,
        )


active_area = st.radio(
    "Área pública",
    ["Prognósticos", "Jogadores"],
    horizontal=True,
    label_visibility="collapsed",
)

if active_area == "Jogadores":
    render_players_page()
    footer()
    st.stop()

page_intro()
picker_header()
def matrix_probability(matrix, predicate) -> float:
    return sum(float(probability) for score, probability in matrix.items() if predicate(*score))


def total_goals_over(matrix, line: float) -> float:
    return matrix_probability(matrix, lambda home, away: home + away > line)


def render_count_market(prediction, key: str, label: str, lines: list[float], home: str, away: str) -> None:
    info = prediction["counts"].get(key, {})
    if not info.get("available"):
        coverage = float(info.get("coverage", 0) or 0)
        if key == "offsides" and coverage == 0:
            st.warning(
                "A base histórica 2025/26 não contém registos de foras de jogo "
                "(cobertura: 0%). Por esse motivo, o modelo não apresenta "
                "probabilidades neste mercado, evitando mostrar estimativas inventadas. "
                "As probabilidades ficarão disponíveis quando forem carregados dados "
                "de foras de jogo por equipa."
            )
        else:
            st.info(
                f"Ainda não existem dados históricos suficientes para apresentar "
                f"probabilidades de {label.lower()}. "
                f"Cobertura atual: {coverage*100:.0f}%."
            )
        return

    stat_cards(
        [
            (home, f"{info['home']:.1f}", f"{label.lower()} esperados"),
            (away, f"{info['away']:.1f}", f"{label.lower()} esperados"),
            ("Total esperado", f"{info['total']:.1f}", label),
            ("Cobertura", f"{info.get('coverage', 0)*100:.0f}%", "dados disponíveis"),
        ]
    )
    section_title("Linhas de mercado", "Probabilidade de mais e menos")
    rows = []
    for line in lines:
        over = over_probability(info["total"], line, info.get("dispersion"))
        rows.extend(
            [
                (f"Mais de {str(line).replace('.', ',')}", over, ""),
                (f"Menos de {str(line).replace('.', ',')}", 1 - over, "blue"),
            ]
        )
    probability_list(rows)

    adjustments = []
    if info.get("referee_sample"):
        adjustments.append(f"árbitro: {info['referee_sample']} jogos")
    if info.get("weather_sample"):
        adjustments.append(f"clima: {info['weather_sample']} jogos comparáveis")
    if adjustments:
        st.caption("Ajustes considerados · " + " · ".join(adjustments))


with get_connection() as conn:
    # Mostra todas as competições que têm jogos carregados para 2026/27.
    # Não depende de um texto exato no campo status, evitando esconder ligas
    # caso uma fonte use uma designação diferente de "Agendado".
    leagues = conn.execute(
        """
        SELECT l.id,l.name,l.country,
               MIN(m.match_date) AS next_date,
               COUNT(m.id) AS game_count
        FROM leagues l
        JOIN matches m ON m.league_id=l.id
        WHERE m.season=?
        GROUP BY l.id,l.name,l.country
        HAVING COUNT(m.id) > 0
        ORDER BY
          CASE l.name
            WHEN 'Liga Portugal' THEN 1
            WHEN 'Premier League' THEN 2
            WHEN 'LaLiga' THEN 3
            WHEN 'Serie A' THEN 4
            WHEN 'Bundesliga' THEN 5
            WHEN 'Ligue 1' THEN 6
            WHEN 'Eredivisie' THEN 7
            WHEN 'Süper Lig' THEN 8
            WHEN 'Pro League' THEN 9
            ELSE 10
          END,
          l.name
        """,
        (SEASON,),
    ).fetchall()

if not leagues:
    st.warning("Ainda não existem jogos agendados disponíveis.")
    st.stop()

league_labels = [f"{row['name']} · {row['country']}" for row in leagues]
default_league_index = next(
    (index for index, row in enumerate(leagues) if "Portugal" in str(row["name"]) or "Portugal" in str(row["country"])),
    0,
)

selector_1, selector_2, selector_3 = st.columns([1.15, .72, 1.75])
league_label = selector_1.selectbox("Competição", league_labels, index=default_league_index)
league = leagues[league_labels.index(league_label)]
league_id = int(league["id"])

with get_connection() as conn:
    rounds = conn.execute(
        """
        SELECT round_number,MIN(match_date) AS first_date
        FROM matches
        WHERE league_id=? AND season=? AND COALESCE(status,'') <> 'Concluído'
        GROUP BY round_number
        ORDER BY first_date,round_number
        """,
        (league_id, SEASON),
    ).fetchall()

if not rounds:
    st.info("Não existem jogos agendados nesta competição.")
    st.stop()

round_values = [int(row["round_number"] or 0) for row in rounds]
today = date.today().isoformat()
default_round_index = next(
    (index for index, row in enumerate(rounds) if str(row["first_date"] or "") >= today),
    0,
)
round_number = selector_2.selectbox("Jornada", round_values, index=default_round_index)

with get_connection() as conn:
    games = conn.execute(
        """
        SELECT m.*,th.name AS home,ta.name AS away,r.name AS assigned_referee
        FROM matches m
        JOIN teams th ON th.id=m.home_team_id
        JOIN teams ta ON ta.id=m.away_team_id
        LEFT JOIN referees r ON r.id=m.referee_id
        WHERE m.league_id=? AND m.season=?
          AND COALESCE(m.status,'') <> 'Concluído'
          AND m.round_number=?
        ORDER BY m.match_date,m.match_time,th.name
        """,
        (league_id, SEASON, round_number),
    ).fetchall()

if not games:
    st.info("Não existem jogos agendados nesta jornada.")
    st.stop()

game_labels = [
    f"{game['home']}  ×  {game['away']} · {game['match_date']} {game['match_time'] or ''}".strip()
    for game in games
]
game_label = selector_3.selectbox("Jogo", game_labels)
game = games[game_labels.index(game_label)]

with get_connection() as conn:
    current_rows = conn.execute(
        """
        SELECT m.*,r.name AS referee_name
        FROM matches m
        LEFT JOIN referees r ON r.id=m.referee_id
        WHERE m.league_id=? AND m.season=?
        """,
        (league_id, SEASON),
    ).fetchall()
    historical_rows = conn.execute(
        "SELECT * FROM historical_matches WHERE target_league_id=? AND season=?",
        (league_id, HISTORY_SEASON),
    ).fetchall()
    home_transfer = transfer_score(conn, int(game["home_team_id"]))
    away_transfer = transfer_score(conn, int(game["away_team_id"]))

prediction = build_prediction_v3(
    current_rows=current_rows,
    historical_rows=historical_rows,
    home_team_id=game["home_team_id"],
    away_team_id=game["away_team_id"],
    home_name=game["home"],
    away_name=game["away"],
    league_name=league["name"],
    match_date=game["match_date"],
    referee_name=game["assigned_referee"],
    rain=None,
    temperature=None,
    home_transfer=home_transfer,
    away_transfer=away_transfer,
)

meta = f"{league['name']} · Jornada {round_number} · {game['match_date']}"
if game["match_time"]:
    meta += f" · {game['match_time']}"
match_hero(game["home"], game["away"], meta)

if prediction is None:
    st.warning("Não existem dados suficientes para produzir esta previsão.")
    st.stop()

score = int(prediction["confidence_score"])
confidence_badge(score)
if game["assigned_referee"]:
    st.caption(f"Árbitro associado: {game['assigned_referee']}")


outcomes = [
    (game["home"], prediction["home_win"]),
    ("Empate", prediction["draw"]),
    (game["away"], prediction["away_win"]),
]
favorite, favorite_probability = max(outcomes, key=lambda item: item[1])
top_score, top_score_probability = prediction["exact_scores"][0]
matrix = prediction["score_matrix"]
expected_total = prediction["expected_home_goals"] + prediction["expected_away_goals"]
home_scores = matrix_probability(matrix, lambda home, away: home >= 1)
away_scores = matrix_probability(matrix, lambda home, away: away >= 1)

section_title("Resumo")
stat_cards(
    [
        ("Favorito", favorite, f"{favorite_probability*100:.1f}%"),
        (
            "Resultado provável",
            f"{top_score[0]}–{top_score[1]}",
            f"{top_score_probability*100:.1f}%",
        ),
        ("Golos esperados", f"{expected_total:.2f}", "total"),
        ("Confiança", f"{score}/100", f"{prediction['data_matches']} jogos"),
    ]
)

section_title("Mercados principais")

st.markdown("##### Resultado final")
outcome_cards(outcomes)

main_left, main_right = st.columns(2)
with main_left:
    st.markdown("##### Dupla possibilidade")
    probability_list(
        [
            (
                f"{game['home']} ou empate",
                prediction["home_win"] + prediction["draw"],
                "",
            ),
            (
                f"Empate ou {game['away']}",
                prediction["draw"] + prediction["away_win"],
                "blue",
            ),
            (
                "Sem empate",
                prediction["home_win"] + prediction["away_win"],
                "amber",
            ),
        ]
    )

with main_right:
    st.markdown("##### Golos principais")
    probability_list(
        [
            ("Mais de 2,5 golos", prediction["over_25"], ""),
            ("Menos de 2,5 golos", 1 - prediction["over_25"], "blue"),
            ("Ambas marcam — Sim", prediction["btts_yes"], ""),
            ("Ambas marcam — Não", prediction["btts_no"], "blue"),
        ]
    )

section_title("Mais mercados")

with st.expander("Golos e resultados exatos"):
    section_title("Resultados exatos", "6 mais prováveis")
    score_cards(
        [
            (f"{home}–{away}", probability)
            for (home, away), probability in prediction["exact_scores"][:6]
        ]
    )

    section_title("Golos esperados")
    stat_cards(
        [
            (
                game["home"],
                f"{prediction['expected_home_goals']:.2f}",
                "golos esperados",
            ),
            (
                game["away"],
                f"{prediction['expected_away_goals']:.2f}",
                "golos esperados",
            ),
            ("Total", f"{expected_total:.2f}", "golos"),
            ("Ambas marcam", f"{prediction['btts_yes']*100:.1f}%", "probabilidade"),
        ]
    )

    section_title("Linhas de golos")
    goal_rows = []
    for line in [0.5, 1.5, 2.5, 3.5, 4.5]:
        over = prediction["over_25"] if line == 2.5 else total_goals_over(matrix, line)
        goal_rows.extend(
            [
                (f"Mais de {str(line).replace('.', ',')}", over, ""),
                (f"Menos de {str(line).replace('.', ',')}", 1 - over, "blue"),
            ]
        )
    probability_list(goal_rows)

    section_title("Equipas a marcar")
    probability_list(
        [
            (f"{game['home']} marca", home_scores, ""),
            (f"{game['away']} marca", away_scores, "blue"),
            (
                f"{game['home']} sem sofrer",
                matrix_probability(matrix, lambda home, away: away == 0),
                "amber",
            ),
            (
                f"{game['away']} sem sofrer",
                matrix_probability(matrix, lambda home, away: home == 0),
                "amber",
            ),
        ]
    )

    section_title("Golo nos primeiros 5 minutos")
    if prediction["first5"] is None:
        st.caption("Ainda não existem dados suficientes para este mercado.")
    else:
        probability_list(
            [
                ("Sim", prediction["first5"], ""),
                ("Não", 1 - prediction["first5"], "blue"),
            ]
        )

with st.expander("Primeira parte"):
    section_title("Resultado ao intervalo")
    outcome_cards(
        [
            (game["home"], prediction["ht_home"]),
            ("Empate", prediction["ht_draw"]),
            (game["away"], prediction["ht_away"]),
        ]
    )
    section_title("Resultados exatos ao intervalo")
    score_cards(
        [
            (f"{home}–{away}", probability)
            for (home, away), probability in prediction["ht_exact_scores"]
        ]
    )

with st.expander("Cantos"):
    render_count_market(
        prediction,
        "corners",
        "Cantos",
        [8.5, 9.5, 10.5],
        game["home"],
        game["away"],
    )

with st.expander("Cartões e faltas"):
    section_title("Cartões amarelos")
    render_count_market(
        prediction,
        "yellows",
        "Cartões amarelos",
        [3.5, 4.5, 5.5],
        game["home"],
        game["away"],
    )
    st.divider()
    section_title("Faltas")
    render_count_market(
        prediction,
        "fouls",
        "Faltas",
        [21.5, 23.5, 25.5],
        game["home"],
        game["away"],
    )

with st.expander("Foras de jogo"):
    render_count_market(
        prediction,
        "offsides",
        "Foras de jogo",
        [2.5, 3.5, 4.5],
        game["home"],
        game["away"],
    )

with st.expander("Metodologia e confiança"):
    confidence_badge(score)
    st.write(
        "O modelo utiliza histórico recente, força ofensiva e defensiva, "
        "adversário, contexto casa/fora, equipas promovidas, mercado de "
        "transferências e correção Dixon–Coles."
    )
    st.write(
        f"**{game['home']}:** {prediction['home_source']} "
        f"({prediction['home_sample']} jogos)"
    )
    st.write(
        f"**{game['away']}:** {prediction['away_source']} "
        f"({prediction['away_sample']} jogos)"
    )
    st.write(f"**Modelo:** {prediction['model_version']}")
    if prediction["home_promoted"] or prediction["away_promoted"]:
        st.warning(
            "O encontro inclui uma equipa promovida; foi aplicado um perfil "
            "ajustado e conservador."
        )

note(
    "Estimativa estatística. Confirmar lesões, suspensões e onze inicial."
)
footer()
