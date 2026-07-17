from __future__ import annotations

from datetime import date

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
    page_title="DID Analyse — Probabilidades de Futebol",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_styles()
init_db()
brand_header()
st.caption("DID Analyse · Versão limpa 1.0 · 8 competições · 2670 jogos")
page_intro()
picker_header()


def matrix_probability(matrix, predicate) -> float:
    return sum(float(probability) for score, probability in matrix.items() if predicate(*score))


def total_goals_over(matrix, line: float) -> float:
    return matrix_probability(matrix, lambda home, away: home + away > line)


def render_count_market(prediction, key: str, label: str, lines: list[float], home: str, away: str) -> None:
    info = prediction["counts"].get(key, {})
    if not info.get("available"):
        st.info(
            f"Ainda não existem dados históricos suficientes para apresentar probabilidades de {label.lower()}. "
            f"Cobertura atual: {info.get('coverage', 0)*100:.0f}%."
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
st.caption(f"{len(leagues)} competições disponíveis · {sum(int(row['game_count']) for row in leagues)} jogos carregados")
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

summary_tab, goals_tab, halftime_tab, corners_tab, cards_tab, fouls_tab, offsides_tab = st.tabs(
    ["Resumo", "Golos", "1.ª parte", "Cantos", "Cartões", "Faltas", "Foras de jogo"]
)

with summary_tab:
    section_title("Resultado final", "Probabilidades 1X2 e odds justas do modelo")
    outcomes = [
        (game["home"], prediction["home_win"]),
        ("Empate", prediction["draw"]),
        (game["away"], prediction["away_win"]),
    ]
    outcome_cards(outcomes)

    section_title("Dupla possibilidade", "Combinações dos três desfechos principais")
    probability_list(
        [
            (f"{game['home']} ou empate", prediction["home_win"] + prediction["draw"], ""),
            (f"Empate ou {game['away']}", prediction["draw"] + prediction["away_win"], "blue"),
            ("Sem empate", prediction["home_win"] + prediction["away_win"], "amber"),
        ]
    )

    section_title("Resultados exatos", "Cenários individuais mais prováveis")
    score_cards(
        [(f"{home}–{away}", probability) for (home, away), probability in prediction["exact_scores"][:8]]
    )

    section_title("Leitura rápida", "Indicadores centrais do confronto")
    favorite, favorite_probability = max(outcomes, key=lambda item: item[1])
    top_score, top_score_probability = prediction["exact_scores"][0]
    stat_cards(
        [
            ("Desfecho favorito", favorite, f"{favorite_probability*100:.1f}%"),
            ("Resultado líder", f"{top_score[0]}–{top_score[1]}", f"{top_score_probability*100:.1f}%"),
            ("Golos esperados", f"{prediction['expected_home_goals'] + prediction['expected_away_goals']:.2f}", "total do jogo"),
            ("Amostra", str(prediction["data_matches"]), "jogos utilizados"),
        ]
    )

with goals_tab:
    matrix = prediction["score_matrix"]
    expected_total = prediction["expected_home_goals"] + prediction["expected_away_goals"]
    section_title("Produção ofensiva", "Estimativa de golos para cada equipa")
    stat_cards(
        [
            (game["home"], f"{prediction['expected_home_goals']:.2f}", "golos esperados"),
            (game["away"], f"{prediction['expected_away_goals']:.2f}", "golos esperados"),
            ("Total esperado", f"{expected_total:.2f}", "golos"),
            ("Ambas marcam", f"{prediction['btts_yes']*100:.1f}%", "probabilidade"),
        ]
    )

    section_title("Mais / menos golos", "Linhas principais do total da partida")
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

    section_title("Ambas marcam e equipas a marcar", "Probabilidades derivadas da matriz de resultados")
    home_scores = matrix_probability(matrix, lambda home, away: home >= 1)
    away_scores = matrix_probability(matrix, lambda home, away: away >= 1)
    probability_list(
        [
            ("Ambas marcam — Sim", prediction["btts_yes"], ""),
            ("Ambas marcam — Não", prediction["btts_no"], "blue"),
            (f"{game['home']} marca", home_scores, ""),
            (f"{game['away']} marca", away_scores, "blue"),
            (f"{game['home']} sem sofrer", matrix_probability(matrix, lambda home, away: away == 0), "amber"),
            (f"{game['away']} sem sofrer", matrix_probability(matrix, lambda home, away: home == 0), "amber"),
        ]
    )

    section_title("Golo nos primeiros 5 minutos")
    if prediction["first5"] is None:
        note("Ainda não existem dados suficientes para calcular este mercado com confiança.")
    else:
        probability_list(
            [
                ("Sim", prediction["first5"], ""),
                ("Não", 1 - prediction["first5"], "blue"),
            ]
        )

with halftime_tab:
    section_title("Resultado ao intervalo", "Probabilidades 1X2 na primeira parte")
    outcome_cards(
        [
            (game["home"], prediction["ht_home"]),
            ("Empate", prediction["ht_draw"]),
            (game["away"], prediction["ht_away"]),
        ]
    )
    section_title("Resultados exatos ao intervalo", "Cenários mais prováveis")
    score_cards(
        [(f"{home}–{away}", probability) for (home, away), probability in prediction["ht_exact_scores"]]
    )

with corners_tab:
    render_count_market(prediction, "corners", "Cantos", [8.5, 9.5, 10.5], game["home"], game["away"])

with cards_tab:
    render_count_market(prediction, "yellows", "Cartões amarelos", [3.5, 4.5, 5.5], game["home"], game["away"])

with fouls_tab:
    render_count_market(prediction, "fouls", "Faltas", [21.5, 23.5, 25.5], game["home"], game["away"])

with offsides_tab:
    render_count_market(prediction, "offsides", "Foras de jogo", [2.5, 3.5, 4.5], game["home"], game["away"])

with st.expander("Como são calculadas estas probabilidades?"):
    st.write(
        "O modelo utiliza histórico recente, força ofensiva e defensiva, adversário, contexto casa/fora, "
        "equipas promovidas, mercado de transferências e correção Dixon–Coles. O peso das transferências "
        "diminui à medida que surgem jogos reais da nova época."
    )
    st.write(f"**{game['home']}:** {prediction['home_source']} ({prediction['home_sample']} jogos)")
    st.write(f"**{game['away']}:** {prediction['away_source']} ({prediction['away_sample']} jogos)")
    st.write(f"**Modelo:** {prediction['model_version']}")
    if prediction["home_promoted"] or prediction["away_promoted"]:
        st.warning("O encontro inclui uma equipa promovida; foi aplicado um perfil ajustado e conservador.")

note(
    "As probabilidades são estimativas estatísticas. Lesões, suspensões, onze inicial e alterações táticas de última hora devem ser confirmados antes da interpretação."
)
footer()
