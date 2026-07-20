from __future__ import annotations

from datetime import date, datetime, time
from html import escape
import base64
import hmac
import json
from math import prod
from pathlib import Path

import pandas as pd
import requests

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
  box-shadow: 0 14px 36px rgba(0, 0, 0, .24);
}
.challenge-card.active {
  border-color: rgba(53, 232, 135, .44);
  background: linear-gradient(145deg, rgba(53, 232, 135, .12), rgba(13, 21, 34, .96));
}
.challenge-card.failed {
  border-color: rgba(251, 113, 133, .42);
  background: linear-gradient(145deg, rgba(251, 113, 133, .10), rgba(13, 21, 34, .96));
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
  border: 1px solid rgba(53, 232, 135, .30);
  color: var(--green-dark);
  font-size: .68rem;
  font-weight: 820;
}
.challenge-status.waiting {
  background: var(--blue-soft);
  border-color: rgba(56, 189, 248, .28);
  color: #7dd3fc;
}
.challenge-status.failed {
  background: var(--red-soft);
  border-color: rgba(251, 113, 133, .30);
  color: #fda4af;
}
.challenge-progress {
  height: 7px;
  background: #182334;
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
  border-bottom: 1px solid var(--line);
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
  color: #fda4af;
}
.result-pill {
  display: inline-block;
  border-radius: 999px;
  padding: .28rem .52rem;
  font-size: .67rem;
  font-weight: 820;
  background: var(--blue-soft);
  color: #7dd3fc;
}
.result-pill.won {
  background: var(--green-soft);
  color: var(--green-dark);
}
.result-pill.lost {
  background: #fef2f2;
  color: #fda4af;
}
.result-pill.void {
  background: var(--amber-soft);
  color: #fcd34d;
}
.accumulator-leg {
  padding: .34rem 0;
  border-bottom: 1px dashed var(--line);
  line-height: 1.35;
}
.accumulator-leg:last-child {
  border-bottom: none;
}
.accumulator-leg-number {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  margin-right: .35rem;
  border-radius: 50%;
  background: var(--blue-soft);
  color: var(--blue);
  font-size: .64rem;
  font-weight: 900;
}
.accumulator-leg-meta {
  color: var(--muted);
  font-size: .67rem;
  margin-left: 1.65rem;
}
.accumulator-odd {
  color: var(--green-dark);
  font-weight: 900;
  white-space: nowrap;
}
@media (max-width: 900px) {
  .challenge-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 600px) {
  .challenge-grid { grid-template-columns: 1fr; }
}

.challenge-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .55rem;
}
.challenge-card {
  border-radius: 13px;
  padding: .78rem;
  box-shadow: none;
}
.challenge-target {
  font-size: 1.25rem;
  margin-top: .38rem;
}
.challenge-meta {
  font-size: .66rem;
}
.challenge-status {
  margin-top: .5rem;
  padding: .25rem .46rem;
  font-size: .63rem;
}
.stage-line {
  display: grid;
  grid-template-columns: repeat(15, minmax(20px, 1fr));
  align-items: start;
  gap: .22rem;
  margin: .65rem 0 .9rem;
}
.stage-item {
  text-align: center;
  min-width: 0;
}
.stage-dot {
  width: 24px;
  height: 24px;
  margin: 0 auto;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #172234;
  border: 1px solid var(--line);
  color: #7f91a7;
  font-size: .59rem;
  font-weight: 900;
}
.stage-dot.won {
  background: var(--green-soft);
  border-color: rgba(53, 232, 135, .42);
  color: var(--green-dark);
}
.stage-dot.current {
  background: var(--amber-soft);
  border-color: rgba(251, 191, 36, .65);
  color: #fcd34d;
  box-shadow: 0 0 0 3px rgba(251, 191, 36, .13);
}
.stage-dot.lost {
  background: #fef2f2;
  border-color: rgba(251, 113, 133, .62);
  color: #fda4af;
}
.current-bet-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: .88rem;
}
.current-bet-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: .8rem;
}
.current-bet-title {
  color: var(--text);
  font-size: .94rem;
  font-weight: 900;
}
.current-bet-subtitle {
  color: var(--muted);
  font-size: .68rem;
  margin-top: .14rem;
}
.current-bet-odd {
  color: var(--green-dark);
  font-size: 1.25rem;
  font-weight: 900;
  white-space: nowrap;
}
.current-bet-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0,1fr));
  gap: .45rem;
  margin-top: .72rem;
}
.current-bet-stat {
  background: var(--surface-soft);
  border-radius: 10px;
  padding: .55rem;
}
.current-bet-stat span {
  display: block;
  color: var(--muted);
  font-size: .61rem;
}
.current-bet-stat strong {
  display: block;
  color: var(--text);
  font-size: .86rem;
  margin-top: .12rem;
}
.history-table {
  width: 100%;
  border-collapse: collapse;
}
.history-table th,
.history-table td {
  padding: .62rem .55rem;
  border-bottom: 1px solid var(--line);
  text-align: left;
  font-size: .72rem;
}
.history-table th {
  color: var(--muted);
  font-size: .62rem;
  text-transform: uppercase;
  letter-spacing: .05em;
}
@media (max-width: 760px) {
  .stage-line {
    grid-template-columns: repeat(8, minmax(22px, 1fr));
    row-gap: .5rem;
  }
  .current-bet-stats {
    grid-template-columns: 1fr;
  }
}

.challenge-card {
  background: linear-gradient(145deg, rgba(17, 28, 44, .97), rgba(10, 17, 28, .97));
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.challenge-card:hover {
  transform: translateY(-2px);
  border-color: rgba(56, 189, 248, .25);
  box-shadow: 0 16px 38px rgba(0, 0, 0, .30);
}
.challenge-progress > span {
  box-shadow: 0 0 16px rgba(53, 232, 135, .28);
}
.challenge-table-wrap,
.current-bet-card {
  background: linear-gradient(145deg, rgba(17, 28, 44, .97), rgba(10, 17, 28, .97));
  box-shadow: 0 14px 36px rgba(0, 0, 0, .18);
}
.current-bet-odd,
.challenge-target,
.accumulator-odd {
  text-shadow: 0 0 18px rgba(53, 232, 135, .16);
}
.current-bet-stat {
  border: 1px solid var(--line);
}
.stage-dot.current {
  box-shadow: 0 0 0 3px rgba(251, 191, 36, .10), 0 0 20px rgba(251, 191, 36, .12);
}
</style>
    """,
    unsafe_allow_html=True,
)

CHALLENGES_PATH = Path(__file__).resolve().parent / "desafios.json"
RESULT_OPTIONS = ["pendente", "ganho", "perdido", "anulado"]


def euro(value: float) -> str:
    return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def odd_text(value: float) -> str:
    return f"{float(value):.2f}".replace(".", ",")


def clone_data(data: dict) -> dict:
    return json.loads(json.dumps(data, ensure_ascii=False))


def load_challenges_file() -> dict:
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


def load_challenges() -> dict:
    preview = st.session_state.get("admin_challenges_data")
    if isinstance(preview, dict):
        return preview
    return load_challenges_file()


def secret_value(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        return ""
    return str(value or "").strip()


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
    bets: dict[int, dict] = {}
    for bet in challenge.get("apostas", []):
        try:
            stage = int(bet.get("etapa"))
        except (TypeError, ValueError):
            continue
        if 1 <= stage <= 15:
            bets[stage] = bet
    return bets


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return float(default)


def normalize_selections(bet: dict) -> list[dict]:
    """Lê acumuladores novos e converte apostas antigas de uma seleção."""
    raw = bet.get("selecoes")
    selections: list[dict] = []

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            selections.append(
                {
                    "competicao": str(item.get("competicao") or "").strip(),
                    "jogo": str(item.get("jogo") or "").strip(),
                    "selecao": str(item.get("selecao") or "").strip(),
                    "data": str(item.get("data") or "").strip(),
                    "hora": str(item.get("hora") or "").strip(),
                    "odd": safe_float(item.get("odd"), 0.0),
                }
            )

    if selections:
        return selections

    # Compatibilidade com a versão anterior, que guardava apenas uma seleção.
    if str(bet.get("jogo") or "").strip() or str(bet.get("selecao") or "").strip():
        return [
            {
                "competicao": str(bet.get("competicao") or "").strip(),
                "jogo": str(bet.get("jogo") or "").strip(),
                "selecao": str(bet.get("selecao") or "").strip(),
                "data": str(bet.get("data") or "").strip(),
                "hora": str(bet.get("hora") or "").strip(),
                "odd": safe_float(bet.get("odd_escolhida"), 0.0),
            }
        ]

    return []


def combined_odd(bet: dict, target_odd: float) -> float:
    selections = normalize_selections(bet)
    valid_odds = [
        safe_float(item.get("odd"), 0.0)
        for item in selections
        if safe_float(item.get("odd"), 0.0) > 1.0
    ]

    if valid_odds:
        return float(prod(valid_odds))

    legacy = safe_float(
        bet.get("odd_combinada") or bet.get("odd_escolhida"),
        0.0,
    )
    return legacy if legacy > 1.0 else float(target_odd)


def editor_rows_for_bet(bet: dict, target_odd: float) -> list[dict]:
    selections = normalize_selections(bet)
    if not selections:
        selections = [
            {
                "competicao": "",
                "jogo": "",
                "selecao": "",
                "data": date.today().isoformat(),
                "hora": "15:00",
                "odd": round(float(target_odd), 2),
            }
        ]

    return [
        {
            "Competição": item.get("competicao", ""),
            "Jogo": item.get("jogo", ""),
            "Seleção / mercado": item.get("selecao", ""),
            "Data": item.get("data", ""),
            "Hora": item.get("hora", ""),
            "Odd": safe_float(item.get("odd"), target_odd),
        }
        for item in selections
    ]


def selections_from_editor(editor_data) -> tuple[list[dict], list[str]]:
    if hasattr(editor_data, "to_dict"):
        records = editor_data.to_dict(orient="records")
    else:
        records = list(editor_data or [])

    selections: list[dict] = []
    errors: list[str] = []

    for index, row in enumerate(records, start=1):
        competition = str(row.get("Competição") or "").strip()
        game = str(row.get("Jogo") or "").strip()
        market = str(row.get("Seleção / mercado") or "").strip()
        game_date = str(row.get("Data") or "").strip()
        game_time = str(row.get("Hora") or "").strip()
        odd = safe_float(row.get("Odd"), 0.0)

        # Ignora uma linha totalmente vazia criada pelo editor.
        if not any([competition, game, market, game_date, game_time]) and odd <= 0:
            continue

        if not game:
            errors.append(f"Seleção {index}: falta o jogo.")
        if not market:
            errors.append(f"Seleção {index}: falta a seleção ou mercado.")
        if odd <= 1.0:
            errors.append(f"Seleção {index}: a odd tem de ser superior a 1,00.")

        selections.append(
            {
                "competicao": competition,
                "jogo": game,
                "selecao": market,
                "data": game_date,
                "hora": game_time,
                "odd": round(float(odd), 3),
            }
        )

    if not selections:
        errors.append("Adiciona pelo menos uma seleção ao acumulador.")

    return selections, errors


def accumulator_html(bet: dict) -> str:
    selections = normalize_selections(bet)
    if not selections:
        return "Por definir"

    lines = []
    for index, item in enumerate(selections, start=1):
        game = escape(str(item.get("jogo") or "Jogo por definir"))
        market = escape(str(item.get("selecao") or "Seleção por definir"))
        competition = escape(str(item.get("competicao") or ""))
        date_value = escape(str(item.get("data") or ""))
        time_value = escape(str(item.get("hora") or ""))
        odd = safe_float(item.get("odd"), 0.0)

        meta_parts = [part for part in [competition, date_value, time_value] if part]
        meta = " · ".join(meta_parts)
        meta_html = (
            f'<div class="accumulator-leg-meta">{meta}</div>'
            if meta
            else ""
        )
        odd_html = (
            f' <span class="accumulator-odd">@ {odd_text(odd)}</span>'
            if odd > 1.0
            else ""
        )

        lines.append(
            f"""
<div class="accumulator-leg">
  <span class="accumulator-leg-number">{index}</span>
  <strong>{game}</strong> — {market}{odd_html}
  {meta_html}
</div>
            """
        )

    return "".join(lines)


def challenge_summary(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> dict:
    bets = challenge_bets(challenge)
    bank = float(start_bank)
    won = 0
    lost = False
    pending = False

    for stage in range(1, max_stages + 1):
        bet = bets.get(stage)
        if not bet:
            break

        result = result_key(bet.get("resultado"))
        if result == "won":
            bank *= combined_odd(bet, target_odd)
            won += 1
        elif result == "lost":
            bank = 0.0
            lost = True
            break
        elif result in {"void", "pending"}:
            pending = True
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
    elif bets or pending:
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
        "lost": lost,
        "status": status,
        "status_class": status_class,
        "card_class": card_class,
        "current_stage": current_stage,
        "current_bank": bank,
        "final_target": final_target,
        "progress": progress,
        "bets": bets,
    }


def stage_financials(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> list[dict]:
    bets = challenge_bets(challenge)
    rows: list[dict] = []
    running_bank = float(start_bank)
    sequence_open = True

    for stage in range(1, max_stages + 1):
        bet = bets.get(stage, {})
        used_odd = combined_odd(bet, target_odd)
        stake = running_bank
        potential_return = stake * used_odd
        result = result_key(bet.get("resultado"))

        rows.append(
            {
                "stage": stage,
                "stake": stake,
                "potential_return": potential_return,
                "bet": bet,
                "result": result,
                "used_odd": used_odd,
                "is_projected": not bool(bet),
            }
        )

        if result == "won":
            running_bank = potential_return
        elif result == "lost":
            running_bank = 0.0
            sequence_open = False
        elif result == "pending" and bet:
            # Para projetar as etapas seguintes, assume o retorno potencial.
            running_bank = potential_return
            sequence_open = False
        elif result == "void" and bet:
            # Uma anulada mantém a banca; a mesma etapa deverá ser substituída.
            running_bank = stake
            sequence_open = False
        elif sequence_open:
            running_bank = potential_return
        elif running_bank > 0:
            running_bank *= float(target_odd)

    return rows


def render_challenge_table(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> None:
    labels = {
        "won": ("Ganho", "won"),
        "lost": ("Perdido", "lost"),
        "void": ("Anulado", "void"),
        "pending": ("Pendente", ""),
    }

    rows = []
    for item in stage_financials(challenge, target_odd, start_bank, max_stages):
        stage = item["stage"]
        bet = item["bet"]
        result = item["result"]
        result_label, result_class = labels[result]
        step_class = result_class if result_class in {"won", "lost"} else ""
        projection_mark = " · projeção" if item["is_projected"] else ""
        selections_count = len(normalize_selections(bet))
        count_text = (
            f"{selections_count} seleção"
            if selections_count == 1
            else f"{selections_count} seleções"
        ) if selections_count else "Por definir"

        rows.append(
            f"""
<tr>
  <td><div class="challenge-step {step_class}">{stage}</div></td>
  <td><strong>{euro(item['stake'])}</strong>{projection_mark}</td>
  <td><strong>{euro(item['potential_return'])}</strong>{projection_mark}</td>
  <td>{accumulator_html(bet)}<div class="accumulator-leg-meta">{count_text}</div></td>
  <td><strong>{odd_text(item['used_odd'])}</strong>{projection_mark}</td>
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
      <th>Retorno</th>
      <th>Acumulador</th>
      <th>Odd combinada</th>
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


def all_challenge_summaries(data: dict) -> list[dict]:
    start_bank = float(data.get("banca_inicial", 1.0))
    max_stages = int(data.get("max_etapas", 15))
    summaries = []

    for group in data.get("grupos", []):
        odd = float(group.get("odd", 0))
        for challenge in group.get("desafios", []):
            summary = challenge_summary(challenge, odd, start_bank, max_stages)
            summary.update(
                {
                    "odd": odd,
                    "name": str(challenge.get("nome", "Desafio")),
                }
            )
            summaries.append(summary)

    return summaries



def render_stage_line(summary: dict, max_stages: int) -> None:
    dots = []
    for stage in range(1, max_stages + 1):
        tone = ""
        if stage <= summary["won"]:
            tone = "won"
        elif summary["lost"] and stage == summary["current_stage"]:
            tone = "lost"
        elif (
            summary["status"] not in {"Concluído", "Falhado"}
            and stage == summary["current_stage"]
        ):
            tone = "current"

        dots.append(
            f'<div class="stage-item">'
            f'<div class="stage-dot {tone}">{stage}</div>'
            f'</div>'
        )

    st.markdown(
        '<div class="stage-line">' + "".join(dots) + "</div>",
        unsafe_allow_html=True,
    )


def render_current_accumulator(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> None:
    summary = challenge_summary(challenge, target_odd, start_bank, max_stages)
    financials = stage_financials(challenge, target_odd, start_bank, max_stages)

    if summary["status"] == "Concluído":
        st.success(
            f"Desafio concluído: 15 etapas ganhas e banca final de "
            f"{euro(summary['current_bank'])}."
        )
        return

    stage_index = max(0, min(max_stages - 1, summary["current_stage"] - 1))
    item = financials[stage_index]
    bet = item["bet"]

    if summary["lost"]:
        st.error(
            f"O desafio terminou na etapa {summary['current_stage']}. "
            "O histórico permanece disponível abaixo."
        )
        return

    if not bet:
        st.info(
            f"A aposta da etapa {summary['current_stage']} ainda não foi publicada."
        )
        return

    selections = normalize_selections(bet)
    result = result_key(bet.get("resultado"))
    status_labels = {
        "pending": "Pendente",
        "won": "Ganho",
        "lost": "Perdido",
        "void": "Anulado",
    }

    st.markdown(
        f"""
<div class="current-bet-card">
  <div class="current-bet-head">
    <div>
      <div class="current-bet-title">Etapa {item['stage']} · {len(selections)} seleções</div>
      <div class="current-bet-subtitle">Estado: {status_labels[result]}</div>
    </div>
    <div class="current-bet-odd">{odd_text(item['used_odd'])}</div>
  </div>
  <div class="current-bet-stats">
    <div class="current-bet-stat">
      <span>Valor apostado</span>
      <strong>{euro(item['stake'])}</strong>
    </div>
    <div class="current-bet-stat">
      <span>Retorno possível</span>
      <strong>{euro(item['potential_return'])}</strong>
    </div>
    <div class="current-bet-stat">
      <span>Odd objetivo</span>
      <strong>{odd_text(target_odd)}</strong>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Ver seleções do acumulador"):
        st.markdown(accumulator_html(bet), unsafe_allow_html=True)


def render_challenge_history(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> None:
    actual = [
        item
        for item in stage_financials(challenge, target_odd, start_bank, max_stages)
        if item["bet"]
    ]

    if not actual:
        st.caption("Este desafio ainda não tem etapas registadas.")
        return

    status_labels = {
        "pending": ("Pendente", ""),
        "won": ("Ganho", "won"),
        "lost": ("Perdido", "lost"),
        "void": ("Anulado", "void"),
    }
    rows = []

    for item in actual:
        label, css_class = status_labels[item["result"]]
        count = len(normalize_selections(item["bet"]))
        rows.append(
            f"""
<tr>
  <td><strong>{item['stage']}</strong></td>
  <td>{count}</td>
  <td>{odd_text(item['used_odd'])}</td>
  <td>{euro(item['stake'])}</td>
  <td>{euro(item['potential_return'])}</td>
  <td><span class="result-pill {css_class}">{label}</span></td>
</tr>
            """
        )

    st.markdown(
        f"""
<div class="challenge-table-wrap">
<table class="history-table">
  <thead>
    <tr>
      <th>Etapa</th>
      <th>Seleções</th>
      <th>Odd</th>
      <th>Aposta</th>
      <th>Retorno</th>
      <th>Estado</th>
    </tr>
  </thead>
  <tbody>{''.join(rows)}</tbody>
</table>
</div>
        """,
        unsafe_allow_html=True,
    )

    for item in actual:
        with st.expander(f"Etapa {item['stage']} · ver seleções"):
            st.markdown(
                accumulator_html(item["bet"]),
                unsafe_allow_html=True,
            )


def render_challenge_projection(
    challenge: dict,
    target_odd: float,
    start_bank: float,
    max_stages: int,
) -> None:
    rows = []
    for item in stage_financials(challenge, target_odd, start_bank, max_stages):
        rows.append(
            f"""
<tr>
  <td>{item['stage']}</td>
  <td>{euro(item['stake'])}</td>
  <td>{odd_text(item['used_odd'])}</td>
  <td><strong>{euro(item['potential_return'])}</strong></td>
</tr>
            """
        )

    st.markdown(
        f"""
<div class="challenge-table-wrap">
<table class="history-table">
  <thead>
    <tr>
      <th>Etapa</th>
      <th>Valor</th>
      <th>Odd</th>
      <th>Retorno projetado</th>
    </tr>
  </thead>
  <tbody>{''.join(rows)}</tbody>
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
  <div class="page-kicker">Desafios</div>
  <div class="page-title">Uma etapa de cada vez.</div>
  <div class="page-copy">
    Escolhe a odd, acompanha a etapa atual e abre o histórico apenas quando
    precisares de mais detalhe.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    summaries = all_challenge_summaries(data)
    active = sum(item["status"] == "Em curso" for item in summaries)
    completed = sum(item["status"] == "Concluído" for item in summaries)
    failed = sum(item["status"] == "Falhado" for item in summaries)
    current_total = sum(float(item["current_bank"]) for item in summaries)

    stat_cards(
        [
            ("Ativos", str(active), "em curso"),
            ("Concluídos", str(completed), "15 etapas"),
            ("Falhados", str(failed), "encerrados"),
            ("Banca atual", euro(current_total), "total"),
        ]
    )

    group_labels = [f"{odd_text(group.get('odd', 0))}" for group in groups]
    selected_label = st.radio(
        "Odd do desafio",
        group_labels,
        horizontal=True,
    )
    selected_group = groups[group_labels.index(selected_label)]
    target_odd = float(selected_group.get("odd", 0))
    challenges = selected_group.get("desafios", [])
    final_target = start_bank * (target_odd ** max_stages)

    section_title(
        f"Odd {odd_text(target_odd)}",
        f"Quatro desafios independentes · objetivo teórico {euro(final_target)}",
    )

    cards = []
    for challenge in challenges:
        summary = challenge_summary(challenge, target_odd, start_bank, max_stages)
        cards.append(
            f"""
<div class="challenge-card {summary['card_class']}">
  <div class="challenge-name">{escape(str(challenge.get('nome', 'Desafio')))}</div>
  <div class="challenge-target">{euro(summary['current_bank'])}</div>
  <div class="challenge-meta">Banca atual</div>
  <div class="challenge-progress"><span style="width:{summary['progress']:.1f}%"></span></div>
  <div class="challenge-meta">Etapa {summary['current_stage']} de {max_stages}</div>
  <div class="challenge-status {summary['status_class']}">{summary['status']}</div>
</div>
            """
        )

    st.markdown(
        '<div class="challenge-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )

    selected_name = st.selectbox(
        "Abrir desafio",
        [str(challenge.get("nome", "Desafio")) for challenge in challenges],
        key=f"challenge_clean_{target_odd}",
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
        "Resumo do progresso",
    )
    stat_cards(
        [
            ("Estado", summary["status"], "situação atual"),
            ("Etapa", f"{summary['current_stage']}/{max_stages}", "progresso"),
            ("Banca atual", euro(summary["current_bank"]), "acumulado"),
            ("Objetivo", euro(summary["final_target"]), "15 ganhos"),
        ]
    )

    render_stage_line(summary, max_stages)

    section_title("Aposta atual", "O acumulador da etapa em curso")
    render_current_accumulator(
        selected_challenge,
        target_odd,
        start_bank,
        max_stages,
    )

    with st.expander("Histórico das etapas"):
        render_challenge_history(
            selected_challenge,
            target_odd,
            start_bank,
            max_stages,
        )

    with st.expander("Projeção completa até à etapa 15"):
        render_challenge_projection(
            selected_challenge,
            target_odd,
            start_bank,
            max_stages,
        )

    with st.expander("Como funciona o desafio?"):
        st.write(
            f"Cada desafio começa com {euro(start_bank)}. Todo o retorno da etapa "
            "ganha é reinvestido na etapa seguinte. Uma aposta perdida encerra "
            "apenas esse desafio."
        )

    note(
        "Os valores são projeções matemáticas. As odds e os resultados não são garantidos."
    )
    footer()

def admin_login() -> bool:
    configured_password = secret_value("ADMIN_PASSWORD")

    if not configured_password:
        st.warning(
            "O painel privado ainda não tem palavra-passe configurada. "
            "Adiciona ADMIN_PASSWORD nos Secrets do Streamlit."
        )
        with st.expander("Ver exemplo dos Secrets"):
            st.code(
                'ADMIN_PASSWORD = "escreve-aqui-uma-palavra-passe-forte"',
                language="toml",
            )
        return False

    if st.session_state.get("admin_authenticated"):
        return True

    st.markdown("### 🔐 Entrada reservada")
    with st.form("admin_login_form"):
        password = st.text_input("Palavra-passe", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)

    if submitted:
        if hmac.compare_digest(password, configured_password):
            st.session_state["admin_authenticated"] = True
            st.session_state["admin_challenges_data"] = clone_data(load_challenges_file())
            st.rerun()
        else:
            st.error("Palavra-passe incorreta.")

    return False


def get_group_and_challenge(
    data: dict,
    odd: float,
    challenge_name: str,
) -> tuple[dict, dict]:
    group = next(
        group
        for group in data["grupos"]
        if abs(float(group.get("odd", 0)) - float(odd)) < 0.001
    )
    challenge = next(
        challenge
        for challenge in group["desafios"]
        if str(challenge.get("nome")) == challenge_name
    )
    return group, challenge


def previous_stages_are_won(challenge: dict, stage: int) -> bool:
    bets = challenge_bets(challenge)
    for previous in range(1, stage):
        bet = bets.get(previous)
        if not bet or result_key(bet.get("resultado")) != "won":
            return False
    return True


def upsert_bet(challenge: dict, new_bet: dict) -> None:
    stage = int(new_bet["etapa"])
    updated = [
        bet
        for bet in challenge.get("apostas", [])
        if int(bet.get("etapa", 0)) != stage
    ]
    updated.append(new_bet)
    challenge["apostas"] = sorted(updated, key=lambda item: int(item["etapa"]))


def github_settings() -> tuple[str, str, str, str]:
    return (
        secret_value("GITHUB_TOKEN"),
        secret_value("GITHUB_REPO"),
        secret_value("GITHUB_BRANCH") or "main",
        secret_value("GITHUB_FILE_PATH") or "desafios.json",
    )


def publish_to_github(data: dict) -> tuple[bool, str]:
    token, repository, branch, file_path = github_settings()

    if not token or not repository:
        return (
            False,
            "Faltam GITHUB_TOKEN e/ou GITHUB_REPO nos Secrets do Streamlit.",
        )

    api_url = f"https://api.github.com/repos/{repository}/contents/{file_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        current = requests.get(
            api_url,
            headers=headers,
            params={"ref": branch},
            timeout=20,
        )
    except requests.RequestException as error:
        return False, f"Não foi possível contactar o GitHub: {error}"

    if current.status_code != 200:
        return (
            False,
            f"Não foi possível ler o ficheiro no GitHub ({current.status_code}). "
            "Confirma o repositório, o ramo e as permissões do token.",
        )

    sha = current.json().get("sha")
    payload_data = clone_data(data)
    payload_data["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    encoded = base64.b64encode(
        json.dumps(payload_data, ensure_ascii=False, indent=2).encode("utf-8")
    ).decode("ascii")

    payload = {
        "message": "Atualizar desafios pelo painel DidAnalyze",
        "content": encoded,
        "branch": branch,
        "sha": sha,
    }

    try:
        response = requests.put(
            api_url,
            headers=headers,
            json=payload,
            timeout=25,
        )
    except requests.RequestException as error:
        return False, f"Não foi possível publicar no GitHub: {error}"

    if response.status_code not in {200, 201}:
        detail = response.json().get("message", "Erro desconhecido")
        return False, f"Publicação recusada pelo GitHub: {detail}"

    st.session_state["admin_challenges_data"] = payload_data
    return True, "Alterações publicadas. O Streamlit deverá atualizar o site após o novo commit."


def admin_dashboard(data: dict) -> None:
    summaries = all_challenge_summaries(data)
    active = sum(item["status"] == "Em curso" for item in summaries)
    completed = sum(item["status"] == "Concluído" for item in summaries)
    failed = sum(item["status"] == "Falhado" for item in summaries)
    current_total = sum(float(item["current_bank"]) for item in summaries)

    stat_cards(
        [
            ("Em curso", str(active), "desafios ativos"),
            ("Concluídos", str(completed), "sequências completas"),
            ("Falhados", str(failed), "sequências encerradas"),
            ("Banca atual", euro(current_total), "total calculado"),
        ]
    )


def render_admin_page() -> None:
    st.markdown(
        """
<div class="page-intro">
  <div class="page-kicker">Área reservada</div>
  <div class="page-title">Administração dos desafios</div>
  <div class="page-copy">
    Cria acumuladores com várias seleções, atualiza resultados e publica as
    alterações sem expor ferramentas de edição ao público.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if not admin_login():
        return

    if "admin_challenges_data" not in st.session_state:
        st.session_state["admin_challenges_data"] = clone_data(load_challenges_file())

    data = st.session_state["admin_challenges_data"]
    start_bank = float(data.get("banca_inicial", 1.0))
    max_stages = int(data.get("max_etapas", 15))

    top_left, top_right = st.columns([4, 1])
    with top_left:
        st.success("Sessão privada iniciada.")
    with top_right:
        if st.button("Terminar sessão", use_container_width=True):
            st.session_state.pop("admin_authenticated", None)
            st.session_state.pop("admin_challenges_data", None)
            st.rerun()

    admin_dashboard(data)
    st.divider()

    odds = [float(group.get("odd", 0)) for group in data["grupos"]]
    odd = st.selectbox(
        "Grupo de odd",
        odds,
        format_func=lambda value: f"Odd {odd_text(value)}",
    )
    selected_group = next(
        group for group in data["grupos"]
        if abs(float(group.get("odd", 0)) - odd) < 0.001
    )

    challenge_names = [
        str(challenge.get("nome", "Desafio"))
        for challenge in selected_group.get("desafios", [])
    ]
    challenge_name = st.selectbox("Desafio", challenge_names)
    _, challenge = get_group_and_challenge(data, odd, challenge_name)
    summary = challenge_summary(challenge, odd, start_bank, max_stages)
    bets = challenge_bets(challenge)

    stat_cards(
        [
            ("Estado", summary["status"], f"{summary['won']} etapas ganhas"),
            ("Banca atual", euro(summary["current_bank"]), "valor acumulado"),
            ("Próxima etapa", str(summary["current_stage"]), f"máximo de {max_stages}"),
            ("Objetivo final", euro(summary["final_target"]), f"odd {odd_text(odd)}"),
        ]
    )

    existing_stages = sorted(bets)
    default_stage = summary["current_stage"]
    stage = st.selectbox(
        "Etapa a editar",
        list(range(1, max_stages + 1)),
        index=max(0, min(max_stages - 1, default_stage - 1)),
    )
    existing = bets.get(stage, {})
    current_result = str(existing.get("resultado") or "pendente").lower()
    if current_result not in RESULT_OPTIONS:
        current_result = "pendente"

    existing_combined = combined_odd(existing, odd) if existing else odd
    existing_count = len(normalize_selections(existing))

    st.markdown("### Registar ou corrigir acumulador")
    st.caption(
        "Cada linha representa uma seleção do mesmo acumulador. "
        "Usa o botão «+» no fim da tabela para juntar mais jogos ou mercados."
    )

    if existing:
        stat_cards(
            [
                (
                    "Seleções atuais",
                    str(existing_count),
                    "dentro desta etapa",
                ),
                (
                    "Odd combinada atual",
                    odd_text(existing_combined),
                    f"objetivo do grupo: {odd_text(odd)}",
                ),
                (
                    "Valor da etapa",
                    euro(stage_financials(challenge, odd, start_bank, max_stages)[stage - 1]["stake"]),
                    "banca a reinvestir",
                ),
                (
                    "Retorno potencial",
                    euro(
                        stage_financials(
                            challenge,
                            odd,
                            start_bank,
                            max_stages,
                        )[stage - 1]["stake"] * existing_combined
                    ),
                    "pela odd combinada",
                ),
            ]
        )

    editor_rows = editor_rows_for_bet(existing, odd)
    editor_frame = pd.DataFrame(editor_rows)

    with st.form(f"challenge_accumulator_form_{odd}_{challenge_name}_{stage}"):
        bookmaker = st.text_input(
            "Casa de apostas",
            value=str(existing.get("casa_apostas") or ""),
            placeholder="Opcional",
        )

        edited_selections = st.data_editor(
            editor_frame,
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "Competição": st.column_config.TextColumn(
                    "Competição",
                    help="Ex.: Liga Portugal",
                ),
                "Jogo": st.column_config.TextColumn(
                    "Jogo",
                    help="Ex.: Benfica x Porto",
                ),
                "Seleção / mercado": st.column_config.TextColumn(
                    "Seleção / mercado",
                    help="Ex.: Mais de 1,5 golos",
                ),
                "Data": st.column_config.TextColumn(
                    "Data",
                    help="Formato recomendado: AAAA-MM-DD",
                ),
                "Hora": st.column_config.TextColumn(
                    "Hora",
                    help="Formato recomendado: HH:MM",
                ),
                "Odd": st.column_config.NumberColumn(
                    "Odd",
                    min_value=1.01,
                    max_value=100.0,
                    step=0.01,
                    format="%.2f",
                ),
            },
            key=f"accumulator_editor_{odd}_{challenge_name}_{stage}",
        )

        result = st.selectbox(
            "Resultado do acumulador completo",
            RESULT_OPTIONS,
            index=RESULT_OPTIONS.index(current_result),
            help=(
                "Marca «ganho» apenas quando todas as seleções vencerem. "
                "Se uma seleção perder, o acumulador é «perdido»."
            ),
        )

        note_text = st.text_area(
            "Nota",
            value=str(existing.get("nota") or ""),
            placeholder="Informação opcional sobre o acumulador.",
        )

        save = st.form_submit_button(
            "Guardar acumulador no painel",
            type="primary",
            use_container_width=True,
        )

    if save:
        is_existing = stage in bets
        selections, selection_errors = selections_from_editor(edited_selections)

        if selection_errors:
            for error in selection_errors:
                st.error(error)
        elif summary["lost"] and not is_existing:
            st.error(
                "Este desafio está falhado. Reinicia o desafio antes de adicionar uma nova etapa."
            )
        elif not is_existing and stage != summary["current_stage"]:
            st.error(
                f"A próxima etapa permitida é a {summary['current_stage']}. "
                "Não é possível saltar etapas."
            )
        elif stage > 1 and not previous_stages_are_won(challenge, stage):
            st.error("Todas as etapas anteriores têm de estar marcadas como ganhas.")
        else:
            calculated_odd = float(prod(item["odd"] for item in selections))
            new_bet = {
                "etapa": int(stage),
                "casa_apostas": bookmaker.strip(),
                "selecoes": selections,
                "odd_combinada": round(calculated_odd, 4),
                "resultado": result,
                "nota": note_text.strip(),
                "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            }
            upsert_bet(challenge, new_bet)
            data["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            st.session_state["admin_challenges_data"] = data

            difference = calculated_odd - float(odd)
            if calculated_odd < float(odd):
                st.warning(
                    f"Acumulador guardado com odd {odd_text(calculated_odd)}, "
                    f"abaixo do objetivo {odd_text(odd)} por {abs(difference):.2f}."
                )
            else:
                st.success(
                    f"Acumulador guardado com {len(selections)} seleções e "
                    f"odd combinada {odd_text(calculated_odd)}. "
                    "Publica no GitHub para atualizar o site."
                )
            st.rerun()

    st.divider()
    st.markdown("### Ferramentas do desafio")

    tool_col1, tool_col2 = st.columns(2)
    with tool_col1:
        delete_confirm = st.checkbox(
            f"Confirmo que quero eliminar a etapa {stage}",
            key=f"delete_confirm_{odd}_{challenge_name}_{stage}",
        )
        if st.button(
            "Eliminar esta etapa",
            disabled=not delete_confirm or stage not in existing_stages,
            use_container_width=True,
        ):
            challenge["apostas"] = [
                bet for bet in challenge.get("apostas", [])
                if int(bet.get("etapa", 0)) != int(stage)
            ]
            st.session_state["admin_challenges_data"] = data
            st.success("Etapa eliminada nesta sessão.")
            st.rerun()

    with tool_col2:
        reset_confirm = st.checkbox(
            "Confirmo que quero reiniciar todo este desafio",
            key=f"reset_confirm_{odd}_{challenge_name}",
        )
        if st.button(
            "Reiniciar desafio em 1 €",
            disabled=not reset_confirm,
            use_container_width=True,
        ):
            challenge["apostas"] = []
            st.session_state["admin_challenges_data"] = data
            st.success("Desafio reiniciado nesta sessão.")
            st.rerun()

    st.divider()
    st.markdown("### Publicar e guardar")

    json_bytes = json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    action_col1, action_col2, action_col3 = st.columns(3)

    with action_col1:
        st.download_button(
            "Descarregar backup JSON",
            data=json_bytes,
            file_name="desafios.json",
            mime="application/json",
            use_container_width=True,
        )

    with action_col2:
        if st.button("Recarregar versão publicada", use_container_width=True):
            st.session_state["admin_challenges_data"] = clone_data(load_challenges_file())
            st.success("Foi reposta a versão atualmente publicada no site.")
            st.rerun()

    with action_col3:
        if st.button(
            "Publicar alterações no site",
            type="primary",
            use_container_width=True,
        ):
            success, message = publish_to_github(data)
            if success:
                st.success(message)
            else:
                st.error(message)

    token, repository, branch, file_path = github_settings()
    if token and repository:
        st.caption(
            f"Publicação automática configurada para {repository} · "
            f"ramo {branch} · ficheiro {file_path}."
        )
    else:
        st.info(
            "A publicação automática ainda não está configurada. "
            "Podes descarregar o JSON e substituí-lo manualmente no GitHub, "
            "ou adicionar GITHUB_TOKEN e GITHUB_REPO aos Secrets."
        )

    with st.expander("Configuração necessária para publicar diretamente"):
        st.code(
            """ADMIN_PASSWORD = "uma-palavra-passe-forte"
GITHUB_TOKEN = "token-criado-no-github"
GITHUB_REPO = "UTILIZADOR/NOME-DO-REPOSITORIO"
GITHUB_BRANCH = "main"
GITHUB_FILE_PATH = "desafios.json"
""",
            language="toml",
        )
        st.write(
            "O token deve ser colocado apenas nos Secrets do Streamlit. "
            "Nunca deve ser escrito no app.py, no GitHub ou enviado a terceiros."
        )

    st.divider()
    section_title(
        "Pré-visualização do desafio",
        "Esta visualização usa as alterações guardadas na sessão, mesmo antes da publicação.",
    )
    render_challenge_table(challenge, odd, start_bank, max_stages)


with st.sidebar:
    st.markdown("#### Área privada")
    st.caption("Acesso reservado ao administrador.")

    if st.session_state.get("show_admin"):
        if st.button("← Voltar ao site", use_container_width=True):
            st.session_state["show_admin"] = False
            st.rerun()
    else:
        if st.button("🔐 Administração", use_container_width=True):
            st.session_state["show_admin"] = True
            st.rerun()

if st.session_state.get("show_admin"):
    render_admin_page()
    st.stop()

st.markdown('<div class="challenge-nav">', unsafe_allow_html=True)
active_area = st.radio(
    "Área pública",
    ["Prognósticos", "Desafios"],
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown("</div>", unsafe_allow_html=True)

if active_area == "Desafios":
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

# Leitura progressiva: primeiro o essencial, depois os detalhes.

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

section_title("Resumo", "Os quatro indicadores essenciais")
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

section_title("Mercados principais", "A leitura mais rápida do encontro")

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

section_title("Mais mercados", "Abre apenas a informação que pretendes consultar")

with st.expander("Golos e resultados exatos"):
    section_title("Resultados exatos", "Os seis cenários mais prováveis")
    score_cards(
        [
            (f"{home}–{away}", probability)
            for (home, away), probability in prediction["exact_scores"][:6]
        ]
    )

    section_title("Golos esperados", "Produção estimada por equipa")
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

    section_title("Linhas de golos", "Mais e menos")
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

    section_title("Equipas a marcar", "Golos e balizas invioladas")
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
    section_title("Resultado ao intervalo", "Probabilidades 1X2")
    outcome_cards(
        [
            (game["home"], prediction["ht_home"]),
            ("Empate", prediction["ht_draw"]),
            (game["away"], prediction["ht_away"]),
        ]
    )
    section_title("Resultados exatos ao intervalo", "Cenários mais prováveis")
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
    "As probabilidades são estimativas estatísticas. Lesões, suspensões, onze inicial e alterações táticas de última hora devem ser confirmados antes da interpretação."
)
footer()
