from __future__ import annotations

from html import escape
from typing import Iterable, Sequence

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
<style>
:root {
  --bg: #f4f7fb;
  --surface: #ffffff;
  --surface-soft: #f8fafc;
  --text: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --green: #16a34a;
  --green-dark: #15803d;
  --green-soft: #ecfdf3;
  --blue: #2563eb;
  --blue-soft: #eff6ff;
  --amber: #d97706;
  --amber-soft: #fffbeb;
  --red: #dc2626;
  --shadow: 0 12px 34px rgba(15, 23, 42, .08);
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: var(--bg) !important;
  color: var(--text) !important;
}

[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {
  display: none !important;
}

header[data-testid="stHeader"] {
  background: transparent !important;
}

.block-container {
  max-width: 1180px;
  padding-top: 1.15rem;
  padding-bottom: 4rem;
}

#MainMenu, footer { visibility: hidden; }

.brand-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin: .15rem 0 1.25rem;
}
.brand-left { display: flex; align-items: center; gap: .8rem; }
.brand-mark {
  width: 44px; height: 44px; border-radius: 13px;
  display: grid; place-items: center;
  background: linear-gradient(135deg, var(--green), #22c55e);
  color: white; font-weight: 900; letter-spacing: -.04em;
  box-shadow: 0 8px 24px rgba(22, 163, 74, .24);
}
.brand-name { color: var(--text); font-size: 1.06rem; font-weight: 850; line-height: 1.1; }
.brand-tagline { color: var(--muted); font-size: .76rem; margin-top: .18rem; }
.brand-status {
  padding: .42rem .68rem; border: 1px solid #bbf7d0; border-radius: 999px;
  color: var(--green-dark); background: var(--green-soft); font-size: .73rem; font-weight: 750;
}

.page-intro {
  padding: 1.45rem 1.5rem;
  border-radius: 20px;
  background: linear-gradient(135deg, #0f172a, #172554);
  color: white;
  box-shadow: var(--shadow);
  margin-bottom: 1rem;
  position: relative;
  overflow: hidden;
}
.page-intro:after {
  content: ""; position: absolute; width: 220px; height: 220px;
  border: 1px solid rgba(255,255,255,.10); border-radius: 50%;
  right: -85px; top: -125px;
}
.page-kicker { color: #86efac; font-size: .7rem; font-weight: 850; letter-spacing: .14em; text-transform: uppercase; }
.page-title { font-size: clamp(1.55rem, 4vw, 2.35rem); font-weight: 900; letter-spacing: -.045em; margin-top: .25rem; }
.page-copy { color: #cbd5e1; max-width: 720px; font-size: .94rem; line-height: 1.55; margin-top: .42rem; }

.picker-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 1rem 1.05rem .65rem;
  box-shadow: 0 8px 26px rgba(15,23,42,.06);
  margin-bottom: 1rem;
}
.picker-title { color: var(--text); font-size: .9rem; font-weight: 820; margin-bottom: .08rem; }
.picker-copy { color: var(--muted); font-size: .78rem; margin-bottom: .5rem; }

.match-hero-simple {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 1.25rem 1.35rem;
  box-shadow: var(--shadow);
  margin: 1rem 0;
}
.match-meta-simple { text-align: center; color: var(--muted); font-size: .75rem; font-weight: 750; text-transform: uppercase; letter-spacing: .08em; }
.match-row-simple {
  display: grid; grid-template-columns: minmax(0,1fr) 64px minmax(0,1fr);
  align-items: center; gap: .75rem; margin-top: .8rem;
}
.match-team-simple { color: var(--text); font-size: clamp(1.08rem, 3vw, 1.65rem); font-weight: 900; line-height: 1.18; }
.match-team-simple.home { text-align: right; }
.match-team-simple.away { text-align: left; }
.match-vs-simple {
  width: 48px; height: 48px; display: grid; place-items: center; margin: auto;
  border-radius: 50%; background: var(--green-soft); border: 1px solid #bbf7d0;
  color: var(--green-dark); font-size: .72rem; font-weight: 900;
}

.section-title-simple { margin: 1.15rem 0 .58rem; }
.section-title-simple strong { display: block; color: var(--text); font-size: 1.03rem; font-weight: 880; }
.section-title-simple span { color: var(--muted); font-size: .78rem; }

.outcome-grid-simple { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: .72rem; }
.outcome-card-simple {
  background: var(--surface); border: 1px solid var(--line); border-radius: 15px;
  padding: .95rem 1rem; min-height: 116px;
}
.outcome-card-simple.highlight {
  border-color: #86efac; background: linear-gradient(180deg, #f0fdf4, #ffffff);
  box-shadow: 0 9px 25px rgba(22, 163, 74, .10);
}
.outcome-label-simple { color: var(--muted); font-size: .76rem; font-weight: 740; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.outcome-value-simple { color: var(--text); font-size: 1.75rem; font-weight: 900; letter-spacing: -.045em; margin-top: .22rem; }
.outcome-fair-simple { color: var(--muted); font-size: .73rem; margin-top: .22rem; }
.outcome-card-simple.highlight .outcome-value-simple { color: var(--green-dark); }

.stat-grid-simple { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .68rem; }
.stat-card-simple { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: .86rem .9rem; }
.stat-label-simple { color: var(--muted); font-size: .7rem; font-weight: 740; }
.stat-value-simple { color: var(--text); font-size: 1.25rem; font-weight: 890; margin-top: .15rem; letter-spacing: -.03em; }
.stat-note-simple { color: var(--muted); font-size: .68rem; margin-top: .14rem; }

.score-grid-simple { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .58rem; }
.score-card-simple { background: var(--surface); border: 1px solid var(--line); border-radius: 13px; padding: .72rem; text-align: center; }
.score-score-simple { color: var(--text); font-size: 1.08rem; font-weight: 900; }
.score-prob-simple { color: var(--green-dark); font-size: .78rem; font-weight: 780; margin-top: .12rem; }

.prob-list-simple { background: var(--surface); border: 1px solid var(--line); border-radius: 15px; padding: .35rem .95rem; }
.prob-row-simple { padding: .72rem 0; border-bottom: 1px solid #eef2f7; }
.prob-row-simple:last-child { border-bottom: none; }
.prob-head-simple { display: flex; justify-content: space-between; gap: 1rem; color: var(--text); font-size: .8rem; font-weight: 760; }
.prob-value-simple { color: var(--green-dark); font-weight: 860; }
.prob-track-simple { height: 6px; background: #edf2f7; border-radius: 999px; overflow: hidden; margin-top: .35rem; }
.prob-fill-simple { height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--green), #4ade80); }
.prob-fill-simple.blue { background: linear-gradient(90deg, #2563eb, #60a5fa); }
.prob-fill-simple.amber { background: linear-gradient(90deg, #d97706, #fbbf24); }

.note-simple { border: 1px solid #dbeafe; background: var(--blue-soft); color: #1e3a8a; border-radius: 13px; padding: .76rem .85rem; font-size: .78rem; line-height: 1.5; }
.confidence-simple { display: inline-flex; align-items: center; gap: .35rem; border-radius: 999px; padding: .38rem .65rem; font-size: .72rem; font-weight: 800; }
.confidence-simple.good { background: var(--green-soft); color: var(--green-dark); border: 1px solid #bbf7d0; }
.confidence-simple.medium { background: var(--amber-soft); color: #92400e; border: 1px solid #fde68a; }
.confidence-simple.low { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }

.stTabs [data-baseweb="tab-list"] {
  background: var(--surface); border: 1px solid var(--line); border-radius: 13px;
  padding: .28rem; gap: .2rem; overflow-x: auto;
}
.stTabs [data-baseweb="tab"] { border-radius: 9px; color: var(--muted); padding-left: .85rem; padding-right: .85rem; }
.stTabs [aria-selected="true"] { background: var(--green-soft) !important; color: var(--green-dark) !important; }
.stTabs [data-baseweb="tab-highlight"] { display: none; }

[data-testid="stMetric"] {
  background: var(--surface); border: 1px solid var(--line); border-radius: 14px;
  padding: .8rem .9rem; min-height: 104px;
}
[data-testid="stMetricLabel"] { color: var(--muted); font-weight: 720; }
[data-testid="stMetricValue"] { color: var(--text); font-weight: 900; letter-spacing: -.035em; }

div[data-baseweb="select"] > div {
  background: white !important; border-color: var(--line) !important; border-radius: 11px !important;
}

details[data-testid="stExpander"] { background: var(--surface); border-color: var(--line) !important; border-radius: 13px !important; }

.site-footer-simple { color: var(--muted); font-size: .71rem; text-align: center; padding: 2rem .5rem .5rem; }

@media (max-width: 760px) {
  .block-container { padding-left: .8rem; padding-right: .8rem; }
  .brand-status { display: none; }
  .page-intro { padding: 1.15rem; border-radius: 16px; }
  .match-row-simple { grid-template-columns: minmax(0,1fr) 48px minmax(0,1fr); gap: .35rem; }
  .match-vs-simple { width: 40px; height: 40px; }
  .outcome-grid-simple { grid-template-columns: 1fr; }
  .stat-grid-simple { grid-template-columns: repeat(2, minmax(0,1fr)); }
  .score-grid-simple { grid-template-columns: repeat(2, minmax(0,1fr)); }
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
      <div class="brand-name">DID Analyse</div>
      <div class="brand-tagline">Probabilidades e inteligência de jogo</div>
    </div>
  </div>
  <div class="brand-status">● Dados online</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def page_intro() -> None:
    st.markdown(
        """
<div class="page-intro">
  <div class="page-kicker">Análise pré-jogo</div>
  <div class="page-title">Escolhe um jogo. Vê todas as probabilidades.</div>
  <div class="page-copy">Resultado, golos, intervalo, cantos, cartões, faltas e foras de jogo numa leitura simples e transparente.</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def picker_header() -> None:
    st.markdown(
        """
<div class="picker-card">
  <div class="picker-title">Selecionar jogo</div>
  <div class="picker-copy">Escolhe a competição, a jornada e o encontro que pretendes analisar.</div>
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
    for label, value, note in items:
        html.append(
            '<div class="stat-card-simple">'
            f'<div class="stat-label-simple">{escape(label)}</div>'
            f'<div class="stat-value-simple">{escape(value)}</div>'
            f'<div class="stat-note-simple">{escape(note)}</div>'
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
        '<div class="site-footer-simple">DID Analyse · Probabilidades produzidas por modelo estatístico. Não constituem garantia de resultado.</div>',
        unsafe_allow_html=True,
    )
