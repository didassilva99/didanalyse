from __future__ import annotations

from datetime import date, datetime, time
from html import escape
import base64
import hmac
import json
from pathlib import Path

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
st.caption("DidAnalyze · Versão 1.5 · Painel privado de desafios")

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
            used_odd = float(bet.get("odd_escolhida") or target_odd)
            bank *= used_odd
            won += 1
        elif result == "lost":
            bank = 0.0
            lost = True
            break
        elif result == "void":
            pending = True
            break
        else:
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
        selected_odd = bet.get("odd_escolhida")
        used_odd = float(selected_odd or target_odd)

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

        if not sequence_open:
            running_bank *= target_odd
            continue

        if result == "won":
            running_bank = potential_return
        elif result == "lost":
            running_bank = 0.0
            sequence_open = False
        elif result in {"pending", "void"} and bet:
            sequence_open = False
        else:
            running_bank = potential_return

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

        game = escape(str(bet.get("jogo") or "Por definir"))
        selection = escape(str(bet.get("selecao") or "Por definir"))
        selected_odd = bet.get("odd_escolhida")
        selected_odd_text = odd_text(selected_odd) if selected_odd not in (None, "") else "—"
        projection_mark = " · projeção" if item["is_projected"] else ""

        rows.append(
            f"""
<tr>
  <td><div class="challenge-step {step_class}">{stage}</div></td>
  <td><strong>{euro(item['stake'])}</strong>{projection_mark}</td>
  <td><strong>{euro(item['potential_return'])}</strong>{projection_mark}</td>
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
      <th>Retorno</th>
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

    summaries = all_challenge_summaries(data)
    active = sum(item["status"] == "Em curso" for item in summaries)
    completed = sum(item["status"] == "Concluído" for item in summaries)
    failed = sum(item["status"] == "Falhado" for item in summaries)
    current_total = sum(float(item["current_bank"]) for item in summaries)

    stat_cards(
        [
            ("Desafios ativos", str(active), "sequências em curso"),
            ("Concluídos", str(completed), "15 etapas ganhas"),
            ("Falhados", str(failed), "sequências encerradas"),
            ("Banca atual total", euro(current_total), "soma dos 20 desafios"),
        ]
    )

    group_labels = [f"Odd {odd_text(group.get('odd', 0))}" for group in groups]
    selected_label = st.radio(
        "Escolher grupo de desafios",
        group_labels,
        horizontal=True,
    )
    selected_group = groups[group_labels.index(selected_label)]
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
    summary = challenge_summary(selected_challenge, target_odd, start_bank, max_stages)

    section_title(
        f"{selected_name} · odd {odd_text(target_odd)}",
        (
            f"{summary['status']} · {summary['won']} de {max_stages} etapas ganhas · "
            f"Banca atual: {euro(summary['current_bank'])}"
        ),
    )

    render_challenge_table(selected_challenge, target_odd, start_bank, max_stages)

    st.info(
        "Os jogos e resultados são geridos no painel privado «Administração». "
        "O público apenas consegue consultar os desafios."
    )

    with st.expander("Como funciona o acumulado?"):
        st.write(
            f"Cada desafio começa com {euro(start_bank)}. Num desafio de odd "
            f"{odd_text(target_odd)}, o retorno da primeira etapa é calculado pela "
            "odd realmente registada. Todo o retorno passa para a etapa seguinte."
        )
        st.write(
            f"Com 15 ganhos consecutivos exatamente na odd {odd_text(target_odd)}, "
            f"o valor teórico final é {euro(final_target)}."
        )

    note(
        "Os valores apresentados são projeções matemáticas e não garantem ganhos. "
        "Uma aposta perdida encerra a sequência desse desafio."
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
    Adiciona jogos, atualiza resultados, controla as etapas e publica as
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

    date_default = date.today()
    if existing.get("data"):
        try:
            date_default = date.fromisoformat(str(existing["data"]))
        except ValueError:
            pass

    time_default = time(15, 0)
    if existing.get("hora"):
        try:
            time_default = time.fromisoformat(str(existing["hora"]))
        except ValueError:
            pass

    current_result = str(existing.get("resultado") or "pendente").lower()
    if current_result not in RESULT_OPTIONS:
        current_result = "pendente"

    st.markdown("### Registar ou corrigir aposta")
    with st.form("challenge_bet_form"):
        col1, col2 = st.columns(2)
        with col1:
            competition = st.text_input(
                "Competição",
                value=str(existing.get("competicao") or ""),
                placeholder="Ex.: Liga Portugal",
            )
            game = st.text_input(
                "Jogo",
                value=str(existing.get("jogo") or ""),
                placeholder="Ex.: Benfica x Porto",
            )
            selection = st.text_input(
                "Seleção",
                value=str(existing.get("selecao") or ""),
                placeholder="Ex.: Mais de 1,5 golos",
            )
            bookmaker = st.text_input(
                "Casa de apostas",
                value=str(existing.get("casa_apostas") or ""),
                placeholder="Opcional",
            )

        with col2:
            game_date = st.date_input("Data do jogo", value=date_default)
            game_time = st.time_input("Hora do jogo", value=time_default)
            selected_odd = st.number_input(
                "Odd escolhida",
                min_value=1.01,
                max_value=100.0,
                value=float(existing.get("odd_escolhida") or odd),
                step=0.01,
                format="%.2f",
            )
            result = st.selectbox(
                "Resultado",
                RESULT_OPTIONS,
                index=RESULT_OPTIONS.index(current_result),
            )

        note_text = st.text_area(
            "Nota",
            value=str(existing.get("nota") or ""),
            placeholder="Informação opcional sobre a escolha.",
        )

        save = st.form_submit_button(
            "Guardar alteração no painel",
            type="primary",
            use_container_width=True,
        )

    if save:
        is_existing = stage in bets

        if not game.strip() or not selection.strip():
            st.error("Preenche o jogo e a seleção.")
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
            new_bet = {
                "etapa": int(stage),
                "competicao": competition.strip(),
                "jogo": game.strip(),
                "selecao": selection.strip(),
                "casa_apostas": bookmaker.strip(),
                "data": game_date.isoformat(),
                "hora": game_time.strftime("%H:%M"),
                "odd_escolhida": round(float(selected_odd), 2),
                "resultado": result,
                "nota": note_text.strip(),
                "atualizado_em": datetime.now().isoformat(timespec="seconds"),
            }
            upsert_bet(challenge, new_bet)
            data["ultima_atualizacao"] = datetime.now().strftime("%d/%m/%Y %H:%M")
            st.session_state["admin_challenges_data"] = data
            st.success(
                "Alteração guardada nesta sessão. Publica no GitHub para atualizar o site."
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


st.markdown('<div class="challenge-nav">', unsafe_allow_html=True)
active_area = st.radio(
    "Área",
    ["⚽ Prognósticos", "🎯 Desafios Sequenciais", "🔐 Administração"],
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown("</div>", unsafe_allow_html=True)

if active_area == "🎯 Desafios Sequenciais":
    render_challenges_page()
    st.stop()

if active_area == "🔐 Administração":
    render_admin_page()
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
