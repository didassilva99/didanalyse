from __future__ import annotations

from datetime import date
from html import escape
import json
from math import prod
from pathlib import Path

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
    page_title="DidAnalyze — Probabilidades de Futebol",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_styles()
init_db()
brand_header()
st.caption("DidAnalyze · Versão 1.4 · Desafios acumulados até 15 etapas")

st.markdown(
    """
<style>
.challenge-nav [data-testid="stRadio"] > div {
  gap: .45rem;
}
.challenge-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .72rem;
  margin: .8rem 0 1.15rem;
}
.challenge-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem;
  box-shadow: 0 8px 24px rgba(15, 23, 42, .05);
}
.challenge-card.active {
  border-color: #86efac;
  background: linear-gradient(180deg, #f0fdf4, #ffffff);
}
.challenge-card.failed {
  border-color: #fecaca;
  background: linear-gradient(180deg, #fef2f2, #ffffff);
}
.challenge-kicker {
  color: var(--muted);
  font-size: .68rem;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.challenge-name {
  color: var(--text);
  font-size: 1.02rem;
  font-weight: 900;
  margin-top: .2rem;
}
.challenge-target {
  color: var(--green-dark);
  font-size: 1.55rem;
  font-weight: 900;
  letter-spacing: -.04em;
  margin-top: .55rem;
}
.challenge-meta {
  color: var(--muted);
  font-size: .72rem;
  margin-top: .15rem;
}
.challenge-status {
  display: inline-block;
  margin-top: .68rem;
  border-radius: 999px;
  padding: .3rem .55rem;
  background: var(--green-soft);
  border: 1px solid #bbf7d0;
  color: var(--green-dark);
  font-size: .68rem;
  font-weight: 820;
}
.challenge-status.waiting {
  background: var(--blue-soft);
  border-color: #bfdbfe;
  color: #1d4ed8;
}
.challenge-status.failed {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}
.challenge-progress {
  height: 7px;
  background: #e9eef5;
  border-radius: 999px;
  overflow: hidden;
  margin-top: .65rem;
}
.challenge-progress > span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, var(--green), #4ade80);
  border-radius: inherit;
}
.challenge-table-wrap {
  overflow-x: auto;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  margin-top: .65rem;
}
.challenge-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}
.challenge-table th {
  text-align: left;
  color: var(--muted);
  background: var(--surface-soft);
  font-size: .68rem;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: .75rem .8rem;
  border-bottom: 1px solid var(--line);
}
.challenge-table td {
  color: var(--text);
  font-size: .78rem;
  padding: .82rem .8rem;
  border-bottom: 1px solid #eef2f7;
  vertical-align: middle;
}
.challenge-table tr:last-child td {
  border-bottom: none;
}
.challenge-step {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--blue-soft);
  color: var(--blue);
  font-weight: 900;
}
.challenge-step.won {
  background: var(--green-soft);
  color: var(--green-dark);
}
.challenge-step.lost {
  background: #fef2f2;
  color: #991b1b;
}
.result-pill {
  display: inline-block;
  border-radius: 999px;
  padding: .28rem .52rem;
  font-size: .67rem;
  font-weight: 820;
  background: var(--blue-soft);
  color: #1d4ed8;
}
.result-pill.won {
  background: var(--green-soft);
  color: var(--green-dark);
}
.result-pill.lost {
  background: #fef2f2;
  color: #991b1b;
}
.result-pill.void {
  background: var(--amber-soft);
  color: #92400e;
}
@media (max-width: 900px) {
  .challenge-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 600px) {
  .challenge-grid { grid-template-columns: 1fr; }
}
</style>
    """,
    unsafe_allow_html=True,
)

CHALLENGES_PATH = Path(__file__).resolve().parent / "desafios.json"


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def odd_text(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def load_challenges() -> dict:
    try:
        with CHALLENGES_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        st.error("O ficheiro desafios.json não foi encontrado na raiz do projeto.")
        st.stop()
    except json.JSONDecodeError as error:
        st.error(f"O ficheiro desafios.json tem um erro de formatação: {error}")
        st.stop()

    if not isinstance(data.get("grupos"), list):
        st.error("O ficheiro desafios.json não contém os grupos de odds.")
        st.stop()

    return data


def result_key(value: str) -> str:
    value = str(value or "pendente").strip().lower()
    aliases = {
        "ganho": "won",
        "ganha": "won",
        "vencido": "won",
        "vencida": "won",
        "perdido": "lost",
        "perdida": "lost",
        "falhado": "lost",
        "falhada": "lost",
        "anulado": "void",
        "anulada": "void",
        "pendente": "pending",
    }
    return aliases.get(value, "pending")


def challenge_bets(challenge: dict) -> dict[int, dict]:
    bets = {}
    for bet in challenge.get("apostas", []):
        try:
            stage = int(bet.get("etapa"))
        except (TypeError, ValueError):
            continue
        if 1 <= stage <= 15:
            bets[stage] = bet
    return bets


def challenge_summary(challenge: dict, target_odd: float, start_bank: float, max_stages: int) -> dict:
    bets = challenge_bets(challenge)
    bank = float(start_bank)
    won = 0
    lost = False
    has_bet = bool(bets)

    for stage in range(1, max_stages + 1):
        bet = bets.get(stage)
        if not bet:
            break

        result = result_key(bet.get("resultado"))
        if result == "won":
            used_odd = float(bet.get("odd_escolhida") or target_odd)
            bank *= used_odd
            won += 1
        elif result == "lost":
            bank = 0.0
            lost = True
            break
        elif result in {"pending", "void"}:
            break

    if won >= max_stages:
        status = "Concluído"
        status_class = ""
        card_class = "active"
        current_stage = max_stages
    elif lost:
        status = "Falhado"
        status_class = "failed"
        card_class = "failed"
        current_stage = min(won + 1, max_stages)
    elif has_bet:
        status = "Em curso"
        status_class = ""
        card_class = "active"
        current_stage = min(won + 1, max_stages)
    else:
        status = "Por iniciar"
        status_class = "waiting"
        card_class = ""
        current_stage = 1

    final_target = float(start_bank) * (float(target_odd) ** max_stages)
    progress = min(100.0, won / max_stages * 100.0)

    return {
        "won": won,
        "status": status,
        "status_class": status_class,
        "card_class": card_class,
        "current_stage": current_stage,
        "current_bank": bank,
        "final_target": final_target,
        "progress": progress,
        "bets": bets,
    }


def render_challenge_table(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> None:
    summary = challenge_summary(challenge, target_odd, start_bank, max_stages)
    bets = summary["bets"]

    labels = {
        "won": ("Ganho", "won"),
        "lost": ("Perdido", "lost"),
        "void": ("Anulado", "void"),
        "pending": ("Pendente", ""),
    }

    rows = []
    for stage in range(1, max_stages + 1):
        projected_stake = start_bank * (target_odd ** (stage - 1))
        projected_return = start_bank * (target_odd ** stage)
        bet = bets.get(stage, {})

        result = result_key(bet.get("resultado"))
        result_label, result_class = labels[result]
        step_class = result_class if result_class in {"won", "lost"} else ""

        game = escape(str(bet.get("jogo") or "Por definir"))
        selection = escape(str(bet.get("selecao") or "Por definir"))
        selected_odd = bet.get("odd_escolhida")
        selected_odd_text = odd_text(selected_odd) if selected_odd not in (None, "") else "—"

        rows.append(
            f"""
<tr>
  <td><div class="challenge-step {step_class}">{stage}</div></td>
  <td><strong>{euro(projected_stake)}</strong></td>
  <td><strong>{euro(projected_return)}</strong></td>
  <td>{game}</td>
  <td>{selection}</td>
  <td><strong>{selected_odd_text}</strong></td>
  <td><span class="result-pill {result_class}">{result_label}</span></td>
</tr>
            """
        )

    st.markdown(
        f"""
<div class="challenge-table-wrap">
<table class="challenge-table">
  <thead>
    <tr>
      <th>Etapa</th>
      <th>Valor a apostar</th>
      <th>Retorno acumulado</th>
      <th>Jogo</th>
      <th>Seleção</th>
      <th>Odd registada</th>
      <th>Resultado</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_challenges_page() -> None:
    data = load_challenges()
    groups = data["grupos"]
    start_bank = float(data.get("banca_inicial", 1.0))
    max_stages = int(data.get("max_etapas", 15))

    st.markdown(
        """
<div class="page-intro">
  <div class="page-kicker">Desafios acumulados</div>
  <div class="page-title">Cinco odds. Quatro desafios por odd. Quinze etapas.</div>
  <div class="page-copy">
    Cada desafio começa com 1 € e reinveste todo o retorno na etapa seguinte.
    O objetivo é completar 15 resultados consecutivos dentro da mesma odd.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    total_challenges = sum(len(group.get("desafios", [])) for group in groups)
    total_initial = total_challenges * start_bank

    stat_cards(
        [
            ("Tipos de odd", str(len(groups)), "de 1,20 a 1,60"),
            ("Desafios", str(total_challenges), "4 por cada odd"),
            ("Etapas máximas", str(max_stages), "por desafio"),
            ("Investimento inicial", euro(total_initial), f"{euro(start_bank)} por desafio"),
        ]
    )

    group_labels = [f"Odd {odd_text(group.get('odd', 0))}" for group in groups]
    selected_label = st.radio(
        "Escolher grupo de desafios",
        group_labels,
        horizontal=True,
    )
    selected_index = group_labels.index(selected_label)
    selected_group = groups[selected_index]
    target_odd = float(selected_group.get("odd", 0))
    challenges = selected_group.get("desafios", [])
    final_target = start_bank * (target_odd ** max_stages)

    section_title(
        f"Desafios de odd {odd_text(target_odd)}",
        f"Cada desafio começa em {euro(start_bank)} e poderá atingir {euro(final_target)} após {max_stages} ganhos.",
    )

    cards = []
    for challenge in challenges:
        summary = challenge_summary(challenge, target_odd, start_bank, max_stages)
        cards.append(
            f"""
<div class="challenge-card {summary['card_class']}">
  <div class="challenge-kicker">Odd fixa {odd_text(target_odd)}</div>
  <div class="challenge-name">{escape(str(challenge.get('nome', 'Desafio')))}</div>
  <div class="challenge-target">{euro(summary['current_bank'])}</div>
  <div class="challenge-meta">Banca atual</div>
  <div class="challenge-progress"><span style="width:{summary['progress']:.1f}%"></span></div>
  <div class="challenge-meta">{summary['won']} de {max_stages} etapas ganhas</div>
  <div class="challenge-meta">Próxima etapa: {summary['current_stage']}</div>
  <div class="challenge-status {summary['status_class']}">{summary['status']}</div>
</div>
            """
        )

    st.markdown(
        '<div class="challenge-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )

    selected_name = st.selectbox(
        "Ver detalhes do desafio",
        [str(challenge.get("nome", "Desafio")) for challenge in challenges],
        key=f"challenge_{target_odd}",
    )
    selected_challenge = next(
        challenge
        for challenge in challenges
        if str(challenge.get("nome", "Desafio")) == selected_name
    )
    summary = challenge_summary(
        selected_challenge,
        target_odd,
        start_bank,
        max_stages,
    )

    section_title(
        f"{selected_name} · odd {odd_text(target_odd)}",
        (
            f"{summary['status']} · {summary['won']} de {max_stages} etapas ganhas · "
            f"Banca atual: {euro(summary['current_bank'])}"
        ),
    )

    render_challenge_table(
        selected_challenge,
        target_odd,
        start_bank,
        max_stages,
    )

    st.info(
        "Os jogos ainda estão por definir. Antes de cada jornada, adiciona apenas "
        "a próxima aposta de cada desafio no ficheiro desafios.json."
    )

    with st.expander("Como funciona o acumulado?"):
        st.write(
            f"Cada desafio começa com {euro(start_bank)}. Num desafio de odd "
            f"{odd_text(target_odd)}, o retorno previsto da primeira etapa é "
            f"{euro(start_bank * target_odd)}. Esse valor passa integralmente para "
            "a segunda etapa, repetindo-se até ao máximo de 15 ganhos."
        )
        st.write(
            f"Com 15 ganhos consecutivos na odd {odd_text(target_odd)}, o valor "
            f"teórico final é {euro(final_target)}."
        )

    note(
        "Os valores apresentados são projeções matemáticas e não garantem ganhos. "
        "Uma aposta perdida encerra a sequência desse desafio."
    )
    footer()


st.markdown('<div class="challenge-nav">', unsafe_allow_html=True)
active_area = st.radio(
    "Área",
    ["⚽ Prognósticos", "🎯 Desafios Sequenciais"],
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown("</div>", unsafe_allow_html=True)

if active_area == "🎯 Desafios Sequenciais":
    render_challenges_page()
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

# Todos os mercados são mostrados numa única página.
# Isto evita que um visitante não repare nos separadores do Streamlit.

section_title("1. Resultado final", "Probabilidades 1X2 e odds justas do modelo")
outcomes = [
    (game["home"], prediction["home_win"]),
    ("Empate", prediction["draw"]),
    (game["away"], prediction["away_win"]),
]
outcome_cards(outcomes)

section_title("2. Dupla possibilidade", "Combinações dos três desfechos principais")
probability_list(
    [
        (f"{game['home']} ou empate", prediction["home_win"] + prediction["draw"], ""),
        (f"Empate ou {game['away']}", prediction["draw"] + prediction["away_win"], "blue"),
        ("Sem empate", prediction["home_win"] + prediction["away_win"], "amber"),
    ]
)

section_title("3. Resultados exatos", "Os oito cenários individuais mais prováveis")
score_cards(
    [
        (f"{home}–{away}", probability)
        for (home, away), probability in prediction["exact_scores"][:8]
    ]
)

section_title("4. Leitura rápida", "Indicadores centrais do confronto")
favorite, favorite_probability = max(outcomes, key=lambda item: item[1])
top_score, top_score_probability = prediction["exact_scores"][0]
stat_cards(
    [
        ("Desfecho favorito", favorite, f"{favorite_probability*100:.1f}%"),
        (
            "Resultado líder",
            f"{top_score[0]}–{top_score[1]}",
            f"{top_score_probability*100:.1f}%",
        ),
        (
            "Golos esperados",
            f"{prediction['expected_home_goals'] + prediction['expected_away_goals']:.2f}",
            "total do jogo",
        ),
        ("Amostra", str(prediction["data_matches"]), "jogos utilizados"),
    ]
)

st.divider()

matrix = prediction["score_matrix"]
expected_total = prediction["expected_home_goals"] + prediction["expected_away_goals"]

section_title("5. Golos esperados", "Produção ofensiva estimada de cada equipa")
stat_cards(
    [
        (game["home"], f"{prediction['expected_home_goals']:.2f}", "golos esperados"),
        (game["away"], f"{prediction['expected_away_goals']:.2f}", "golos esperados"),
        ("Total esperado", f"{expected_total:.2f}", "golos"),
        ("Ambas marcam", f"{prediction['btts_yes']*100:.1f}%", "probabilidade"),
    ]
)

section_title("6. Mais / menos golos", "Linhas principais do total da partida")
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

section_title("7. Ambas marcam e equipas a marcar", "Probabilidades derivadas dos resultados possíveis")
home_scores = matrix_probability(matrix, lambda home, away: home >= 1)
away_scores = matrix_probability(matrix, lambda home, away: away >= 1)
probability_list(
    [
        ("Ambas marcam — Sim", prediction["btts_yes"], ""),
        ("Ambas marcam — Não", prediction["btts_no"], "blue"),
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

section_title("8. Golo nos primeiros 5 minutos")
if prediction["first5"] is None:
    note("Ainda não existem dados suficientes para calcular este mercado com confiança.")
else:
    probability_list(
        [
            ("Sim", prediction["first5"], ""),
            ("Não", 1 - prediction["first5"], "blue"),
        ]
    )

st.divider()

section_title("9. Resultado ao intervalo", "Probabilidades 1X2 na primeira parte")
outcome_cards(
    [
        (game["home"], prediction["ht_home"]),
        ("Empate", prediction["ht_draw"]),
        (game["away"], prediction["ht_away"]),
    ]
)

section_title("10. Resultados exatos ao intervalo", "Cenários mais prováveis")
score_cards(
    [
        (f"{home}–{away}", probability)
        for (home, away), probability in prediction["ht_exact_scores"]
    ]
)

st.divider()

section_title("11. Cantos", "Estimativas e linhas de mais/menos")
render_count_market(
    prediction,
    "corners",
    "Cantos",
    [8.5, 9.5, 10.5],
    game["home"],
    game["away"],
)

st.divider()

section_title("12. Cartões amarelos", "Estimativas e linhas de mais/menos")
render_count_market(
    prediction,
    "yellows",
    "Cartões amarelos",
    [3.5, 4.5, 5.5],
    game["home"],
    game["away"],
)

st.divider()

section_title("13. Faltas", "Estimativas e linhas de mais/menos")
render_count_market(
    prediction,
    "fouls",
    "Faltas",
    [21.5, 23.5, 25.5],
    game["home"],
    game["away"],
)

st.divider()

section_title("14. Foras de jogo", "Estimativas e linhas de mais/menos")
render_count_market(
    prediction,
    "offsides",
    "Foras de jogo",
    [2.5, 3.5, 4.5],
    game["home"],
    game["away"],
)

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
