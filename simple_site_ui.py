from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
<style>
:root {
  --bg: #060910;
  --bg-soft: #0a101b;
  --surface: #0d1522;
  --surface-raised: #111c2c;
  --surface-soft: #101a29;
  --text: #f3f7fb;
  --muted: #8c9caf;
  --line: rgba(148, 163, 184, .16);
  --green: #35e887;
  --green-dark: #62f3a0;
  --green-soft: rgba(53, 232, 135, .11);
  --blue: #38bdf8;
  --blue-soft: rgba(56, 189, 248, .11);
  --amber: #fbbf24;
  --amber-soft: rgba(251, 191, 36, .11);
  --red: #fb7185;
  --red-soft: rgba(251, 113, 133, .11);
  --shadow: 0 18px 55px rgba(0, 0, 0, .32);
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background:
    radial-gradient(circle at 12% 0%, rgba(53, 232, 135, .075), transparent 30%),
    radial-gradient(circle at 90% 8%, rgba(56, 189, 248, .065), transparent 28%),
    var(--bg) !important;
  color: var(--text) !important;
}

[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--line);
}

[data-testid="stSidebarCollapsedControl"] {
  display: flex !important;
}

header[data-testid="stHeader"] {
  background: rgba(6, 9, 16, .86) !important;
  backdrop-filter: blur(10px);
}

.block-container {
  max-width: 1080px;
  padding-top: .75rem;
  padding-bottom: 3.25rem;
}

#MainMenu, footer { visibility: hidden; }

.brand-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .8rem;
  margin: .1rem 0 .8rem;
}
.brand-left {
  display: flex;
  align-items: center;
  gap: .68rem;
}
.brand-mark {
  width: 39px;
  height: 39px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, var(--green), var(--blue));
  color: #03120a;
  font-weight: 900;
  letter-spacing: -.05em;
}
.brand-name {
  color: var(--text);
  font-size: 1.02rem;
  font-weight: 900;
  line-height: 1.05;
}
.brand-tagline {
  color: var(--muted);
  font-size: .71rem;
  margin-top: .16rem;
}

.page-intro {
  padding: 1.05rem 1.15rem;
  border: 1px solid var(--line);
  border-left: 3px solid var(--green);
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(17, 28, 44, .96), rgba(10, 17, 28, .96));
  box-shadow: var(--shadow);
  margin-bottom: .85rem;
}
.page-kicker {
  color: var(--green-dark);
  font-size: .66rem;
  font-weight: 850;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.page-title {
  color: var(--text);
  font-size: clamp(1.28rem, 3vw, 1.78rem);
  font-weight: 900;
  letter-spacing: -.035em;
  margin-top: .18rem;
}
.page-copy {
  color: var(--muted);
  max-width: 760px;
  font-size: .83rem;
  line-height: 1.5;
  margin-top: .3rem;
}

.picker-card {
  background: transparent;
  border: 0;
  padding: .25rem 0 .2rem;
  margin-bottom: .15rem;
}
.picker-title {
  color: var(--text);
  font-size: .9rem;
  font-weight: 850;
}
.picker-copy {
  display: none;
}

.match-hero-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1rem 1.1rem;
  box-shadow: var(--shadow);
  margin: .85rem 0;
}
.match-meta-simple {
  text-align: center;
  color: var(--muted);
  font-size: .68rem;
  font-weight: 750;
  text-transform: uppercase;
  letter-spacing: .07em;
}
.match-row-simple {
  display: grid;
  grid-template-columns: minmax(0,1fr) 54px minmax(0,1fr);
  align-items: center;
  gap: .65rem;
  margin-top: .6rem;
}
.match-team-simple {
  color: var(--text);
  font-size: clamp(1.02rem, 2.5vw, 1.48rem);
  font-weight: 900;
  line-height: 1.15;
}
.match-team-simple.home { text-align: right; }
.match-team-simple.away { text-align: left; }
.match-vs-simple {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  margin: auto;
  border-radius: 50%;
  background: var(--surface-soft);
  border: 1px solid var(--line);
  color: var(--muted);
  font-size: .66rem;
  font-weight: 900;
}

.section-title-simple {
  margin: 1rem 0 .5rem;
}
.section-title-simple strong {
  display: block;
  color: var(--text);
  font-size: .98rem;
  font-weight: 900;
}
.section-title-simple span {
  color: var(--muted);
  font-size: .73rem;
}

.outcome-grid-simple {
  display: grid;
  grid-template-columns: repeat(3, minmax(0,1fr));
  gap: .58rem;
}
.outcome-card-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: .78rem .82rem;
  min-height: 98px;
}
.outcome-card-simple.highlight {
  border-color: rgba(53, 232, 135, .52);
  background: linear-gradient(145deg, rgba(53, 232, 135, .13), rgba(13, 21, 34, .96));
}
.outcome-label-simple {
  color: var(--muted);
  font-size: .7rem;
  font-weight: 740;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.outcome-value-simple {
  color: var(--text);
  font-size: 1.52rem;
  font-weight: 900;
  letter-spacing: -.04em;
  margin-top: .16rem;
}
.outcome-fair-simple {
  color: var(--muted);
  font-size: .67rem;
  margin-top: .15rem;
}
.outcome-card-simple.highlight .outcome-value-simple {
  color: var(--green-dark);
}

.stat-grid-simple {
  display: grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  gap: .56rem;
}
.stat-card-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: .72rem .76rem;
}
.stat-label-simple {
  color: var(--muted);
  font-size: .66rem;
  font-weight: 740;
}
.stat-value-simple {
  color: var(--text);
  font-size: 1.1rem;
  font-weight: 900;
  margin-top: .12rem;
  letter-spacing: -.025em;
}
.stat-note-simple {
  color: var(--muted);
  font-size: .63rem;
  margin-top: .1rem;
}

.score-grid-simple {
  display: grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  gap: .5rem;
}
.score-card-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: .62rem;
  text-align: center;
}
.score-score-simple {
  color: var(--text);
  font-size: 1rem;
  font-weight: 900;
}
.score-prob-simple {
  color: var(--green-dark);
  font-size: .72rem;
  font-weight: 800;
  margin-top: .1rem;
}

.prob-list-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 13px;
  padding: .24rem .8rem;
}
.prob-row-simple {
  padding: .62rem 0;
  border-bottom: 1px solid var(--line);
}
.prob-row-simple:last-child { border-bottom: none; }
.prob-head-simple {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  color: var(--text);
  font-size: .75rem;
  font-weight: 760;
}
.prob-value-simple {
  color: var(--green-dark);
  font-weight: 900;
}
.prob-track-simple {
  height: 5px;
  background: #182334;
  border-radius: 999px;
  overflow: hidden;
  margin-top: .3rem;
}
.prob-fill-simple {
  height: 100%;
  border-radius: inherit;
  background: var(--green);
}
.prob-fill-simple.blue { background: var(--blue); }
.prob-fill-simple.amber { background: var(--amber); }

.note-simple {
  border: 1px solid rgba(56, 189, 248, .24);
  background: var(--blue-soft);
  color: #bae6fd;
  border-radius: 12px;
  padding: .68rem .75rem;
  font-size: .73rem;
  line-height: 1.48;
}
.confidence-simple {
  display: inline-flex;
  align-items: center;
  gap: .3rem;
  border-radius: 999px;
  padding: .32rem .55rem;
  font-size: .67rem;
  font-weight: 820;
}
.confidence-simple.good {
  background: var(--green-soft);
  color: var(--green-dark);
  border: 1px solid #bbf7d0;
}
.confidence-simple.medium {
  background: var(--amber-soft);
  color: #92400e;
  border: 1px solid #fde68a;
}
.confidence-simple.low {
  background: var(--red-soft);
  color: #991b1b;
  border: 1px solid #fecaca;
}

div[data-baseweb="select"] > div {
  background: var(--surface-raised) !important;
  border-color: var(--line) !important;
  color: var(--text) !important;
  border-radius: 10px !important;
}

details[data-testid="stExpander"] {
  background: var(--surface);
  border: 1px solid var(--line) !important;
  border-radius: 12px !important;
  box-shadow: none !important;
  margin-bottom: .45rem;
}
details[data-testid="stExpander"] summary {
  font-weight: 800;
  color: var(--text);
}

div[role="radiogroup"] {
  gap: .35rem;
}
div[role="radiogroup"] label {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: .08rem .45rem;
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
  border-radius: 10px;
  font-weight: 780;
}

.site-footer-simple {
  color: var(--muted);
  font-size: .67rem;
  text-align: center;
  padding: 1.6rem .5rem .35rem;
}

@media (max-width: 760px) {
  .block-container {
    padding-left: .72rem;
    padding-right: .72rem;
  }
  .page-intro {
    padding: .92rem;
  }
  .match-row-simple {
    grid-template-columns: minmax(0,1fr) 44px minmax(0,1fr);
    gap: .28rem;
  }
  .match-vs-simple {
    width: 36px;
    height: 36px;
  }
  .outcome-grid-simple {
    grid-template-columns: 1fr;
  }
  .stat-grid-simple {
    grid-template-columns: repeat(2, minmax(0,1fr));
  }
  .score-grid-simple {
    grid-template-columns: repeat(2, minmax(0,1fr));
  }
}

/* Controlos nativos do Streamlit */
.stApp, .stApp p, .stApp label, .stApp span {
  color: var(--text);
}

[data-testid="stSidebar"] {
  background:
    linear-gradient(180deg, rgba(13, 21, 34, .98), rgba(6, 9, 16, .98)) !important;
  box-shadow: 16px 0 45px rgba(0, 0, 0, .22);
}

[data-testid="stSidebar"] * {
  color: var(--text);
}

[data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button {
  background: var(--surface-raised) !important;
  border: 1px solid var(--line) !important;
  color: var(--text) !important;
  box-shadow: 0 8px 25px rgba(0, 0, 0, .28);
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stDateInput"] input,
[data-testid="stTimeInput"] input {
  background: var(--surface-raised) !important;
  border-color: var(--line) !important;
  color: var(--text) !important;
  caret-color: var(--green);
}

div[data-baseweb="popover"],
div[data-baseweb="menu"],
ul[role="listbox"] {
  background: #111c2c !important;
  border: 1px solid var(--line) !important;
}

li[role="option"] {
  color: var(--text) !important;
}

li[role="option"]:hover,
li[aria-selected="true"] {
  background: rgba(53, 232, 135, .11) !important;
}

.stButton > button,
.stDownloadButton > button,
.stFormSubmitButton > button {
  background: linear-gradient(135deg, rgba(53, 232, 135, .16), rgba(56, 189, 248, .11));
  border: 1px solid rgba(53, 232, 135, .28);
  color: var(--text);
  box-shadow: 0 8px 24px rgba(0, 0, 0, .18);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
.stFormSubmitButton > button:hover {
  transform: translateY(-1px);
  border-color: rgba(53, 232, 135, .62);
  box-shadow: 0 12px 30px rgba(0, 0, 0, .28), 0 0 24px rgba(53, 232, 135, .08);
}

button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
  background: linear-gradient(135deg, var(--green), #26c6da) !important;
  color: #03120a !important;
  border-color: transparent !important;
}

div[role="radiogroup"] label {
  background: rgba(13, 21, 34, .88);
  border-color: var(--line);
  color: var(--muted);
  transition: all .18s ease;
}

div[role="radiogroup"] label:hover {
  border-color: rgba(53, 232, 135, .38);
  color: var(--text);
}

div[role="radiogroup"] label:has(input:checked) {
  background: linear-gradient(135deg, rgba(53, 232, 135, .16), rgba(56, 189, 248, .10));
  border-color: rgba(53, 232, 135, .48);
  color: var(--text);
  box-shadow: 0 0 20px rgba(53, 232, 135, .06);
}

details[data-testid="stExpander"] {
  background: linear-gradient(145deg, rgba(17, 28, 44, .96), rgba(10, 17, 28, .96));
  border-color: var(--line) !important;
}

details[data-testid="stExpander"][open] {
  border-color: rgba(53, 232, 135, .26) !important;
  box-shadow: 0 12px 35px rgba(0, 0, 0, .18);
}

[data-testid="stAlert"] {
  background: var(--surface-raised) !important;
  border: 1px solid var(--line) !important;
  color: var(--text) !important;
}

hr {
  border-color: var(--line) !important;
}

.brand-mark {
  box-shadow: 0 0 26px rgba(53, 232, 135, .18);
}

.page-intro,
.match-hero-simple,
.outcome-card-simple,
.stat-card-simple,
.score-card-simple,
.prob-list-simple {
  backdrop-filter: blur(12px);
}

.outcome-card-simple,
.stat-card-simple,
.score-card-simple {
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

.outcome-card-simple:hover,
.stat-card-simple:hover,
.score-card-simple:hover {
  transform: translateY(-2px);
  border-color: rgba(56, 189, 248, .26);
  box-shadow: 0 14px 32px rgba(0, 0, 0, .24);
}

.prob-track-simple {
  background: #1a2638;
}

.prob-fill-simple {
  box-shadow: 0 0 14px rgba(53, 232, 135, .24);
}

.site-footer-simple {
  opacity: .72;
}
</style>

        """,
        unsafe_allow_html=True,
    )


def brand_header() -> None:
    st.markdown(
        """
<div class="brand-bar">
  <div class="brand-left">
    <div class="brand-mark">DA</div>
    <div>
      <div class="brand-name">DidAnalyze</div>
      <div class="brand-tagline">Football intelligence · probabilities & challenges</div>
    </div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def page_intro() -> None:
    st.markdown(
        """
<div class="page-intro">
  <div class="page-kicker">Análise pré-jogo</div>
  <div class="page-title">Decisões mais claras. Dados mais fortes.</div>
  <div class="page-copy">
    Escolhe um encontro, consulta primeiro os mercados principais e abre apenas
    os detalhes de que precisas.
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def picker_header() -> None:
    st.markdown(
        """
<div class="picker-card">
  <div class="picker-title">Escolher jogo</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def match_hero(home: str, away: str, meta: str) -> None:
    st.markdown(
        f"""
<div class="match-hero-simple">
  <div class="match-meta-simple">{escape(meta)}</div>
  <div class="match-row-simple">
    <div class="match-team-simple home">{escape(home)}</div>
    <div class="match-vs-simple">VS</div>
    <div class="match-team-simple away">{escape(away)}</div>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="section-title-simple"><strong>{escape(title)}</strong><span>{escape(subtitle)}</span></div>',
        unsafe_allow_html=True,
    )


def outcome_cards(items: Sequence[tuple[str, float]]) -> None:
    best = max(range(len(items)), key=lambda index: items[index][1])
    html = ['<div class="outcome-grid-simple">']
    for index, (label, probability) in enumerate(items):
        probability = max(0.0, min(1.0, float(probability)))
        fair = 1.0 / probability if probability > 0 else 0.0
        highlight = " highlight" if index == best else ""
        html.append(
            f'<div class="outcome-card-simple{highlight}">'
            f'<div class="outcome-label-simple">{escape(label)}</div>'
            f'<div class="outcome-value-simple">{probability*100:.1f}%</div>'
            f'<div class="outcome-fair-simple">Odd justa {fair:.2f}</div>'
            '</div>'
        )
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def stat_cards(items: Sequence[tuple[str, str, str]]) -> None:
    html = ['<div class="stat-grid-simple">']
    for label, value, note_text in items:
        html.append(
            '<div class="stat-card-simple">'
            f'<div class="stat-label-simple">{escape(label)}</div>'
            f'<div class="stat-value-simple">{escape(value)}</div>'
            f'<div class="stat-note-simple">{escape(note_text)}</div>'
            '</div>'
        )
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def score_cards(items: Sequence[tuple[str, float]]) -> None:
    html = ['<div class="score-grid-simple">']
    for score, probability in items:
        html.append(
            '<div class="score-card-simple">'
            f'<div class="score-score-simple">{escape(score)}</div>'
            f'<div class="score-prob-simple">{float(probability)*100:.1f}%</div>'
            '</div>'
        )
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def probability_list(
    items: Iterable[tuple[str, float, str]],
) -> None:
    html = ['<div class="prob-list-simple">']
    for label, probability, tone in items:
        pct = max(0.0, min(100.0, float(probability) * 100.0))
        tone_class = f' {tone}' if tone in {'blue', 'amber'} else ''
        html.append(
            '<div class="prob-row-simple">'
            '<div class="prob-head-simple">'
            f'<span>{escape(label)}</span><span class="prob-value-simple">{pct:.1f}%</span>'
            '</div>'
            '<div class="prob-track-simple">'
            f'<div class="prob-fill-simple{tone_class}" style="width:{pct:.1f}%"></div>'
            '</div>'
            '</div>'
        )
    html.append('</div>')
    st.markdown(''.join(html), unsafe_allow_html=True)


def confidence_badge(score: int) -> None:
    if score >= 72:
        label, tone = "Confiança boa", "good"
    elif score >= 55:
        label, tone = "Confiança média", "medium"
    else:
        label, tone = "Confiança baixa", "low"
    st.markdown(
        f'<span class="confidence-simple {tone}">{escape(label)} · {int(score)}/100</span>',
        unsafe_allow_html=True,
    )


def note(text: str) -> None:
    st.markdown(
        f'<div class="note-simple">{escape(text)}</div>',
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        '<div class="site-footer-simple">DidAnalyze · Modelo estatístico · v1.7 · As probabilidades não garantem resultados.</div>',
        unsafe_allow_html=True,
    )
