from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import json
import math
import re
import unicodedata
from pathlib import Path


VALIDATION_PATH = Path(__file__).resolve().parent / "model_validation.json"


def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _num(value, default=None):
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalise(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _date(value):
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _hist_key(row, side):
    current_id = _get(row, f"{side}_current_team_id")
    if current_id is not None:
        return f"id:{int(current_id)}"
    return f"hist:{_normalise(_get(row, f'{side}_team_name', ''))}"


def _current_key(row, side):
    team_id = _get(row, f"{side}_team_id")
    if team_id is None:
        name = _get(row, f"{side}_name", _get(row, side, ""))
        return f"current:{_normalise(name)}"
    return f"id:{int(team_id)}"


def records_from_rows(current_rows, historical_rows, source_level=1, before_date=None):
    records = []
    cutoff = _date(before_date) if before_date else None

    for row in historical_rows:
        if int(_get(row, "source_level", 1) or 1) != source_level:
            continue
        dt = _date(_get(row, "match_date"))
        if cutoff and dt and dt >= cutoff:
            continue
        records.append({
            "home": _hist_key(row, "home"),
            "away": _hist_key(row, "away"),
            "date": dt,
            "row": row,
            "historical": True,
        })

    if source_level == 1:
        for row in current_rows:
            if _get(row, "status") != "Concluído":
                continue
            if _get(row, "ft_home_goals") is None:
                continue
            dt = _date(_get(row, "match_date"))
            if cutoff and dt and dt >= cutoff:
                continue
            records.append({
                "home": _current_key(row, "home"),
                "away": _current_key(row, "away"),
                "date": dt,
                "row": row,
                "historical": False,
            })

    records.sort(key=lambda x: (x["date"] or datetime(1900, 1, 1)))
    return records


def _column(record, name):
    return _num(_get(record["row"], name))


def _weight(record, reference, half_life_days=150.0):
    if not reference or not record["date"]:
        return 1.0
    age = max(0.0, (reference - record["date"]).days)
    return math.exp(-math.log(2.0) * age / max(1.0, half_life_days))


@dataclass
class CountStrengthModel:
    home_base: float
    away_base: float
    attack: dict
    defence: dict
    weights: dict
    coverage: float
    matches: int

    def expected(self, home_key, away_key):
        ha = self.attack.get(home_key, 1.0)
        hd = self.defence.get(home_key, 1.0)
        aa = self.attack.get(away_key, 1.0)
        ad = self.defence.get(away_key, 1.0)
        return (
            max(0.001, self.home_base * ha * ad),
            max(0.001, self.away_base * aa * hd),
        )


def fit_count_strength(records, home_col, away_col, reference=None, half_life_days=150.0, prior_games=8.0, iterations=50, default_home=1.0, default_away=1.0):
    usable = []
    all_count = 0
    reference_dt = _date(reference) if not isinstance(reference, datetime) else reference
    if reference_dt is None:
        dates = [r["date"] for r in records if r["date"]]
        reference_dt = max(dates) if dates else None

    for record in records:
        all_count += 1
        h = _column(record, home_col)
        a = _column(record, away_col)
        if h is None or a is None:
            continue
        w = _weight(record, reference_dt, half_life_days)
        usable.append((record["home"], record["away"], h, a, w))

    coverage = len(usable) / all_count if all_count else 0.0
    if not usable:
        return CountStrengthModel(default_home, default_away, {}, {}, {}, coverage, 0)

    total_w = sum(x[4] for x in usable) or 1.0
    home_base = sum(h * w for _, _, h, _, w in usable) / total_w
    away_base = sum(a * w for _, _, _, a, w in usable) / total_w
    home_base = max(0.01, home_base)
    away_base = max(0.01, away_base)

    teams = sorted({x[0] for x in usable} | {x[1] for x in usable})
    attack = {team: 1.0 for team in teams}
    defence = {team: 1.0 for team in teams}
    team_weights = defaultdict(float)
    for home, away, _, _, w in usable:
        team_weights[home] += w
        team_weights[away] += w

    for _ in range(iterations):
        new_attack = {}
        new_defence = {}
        for team in teams:
            att_num = prior_games * ((home_base + away_base) / 2.0)
            att_den = prior_games * ((home_base + away_base) / 2.0)
            def_num = prior_games * ((home_base + away_base) / 2.0)
            def_den = prior_games * ((home_base + away_base) / 2.0)
            for home, away, h, a, w in usable:
                if home == team:
                    att_num += w * h
                    att_den += w * home_base * defence.get(away, 1.0)
                    def_num += w * a
                    def_den += w * away_base * attack.get(away, 1.0)
                elif away == team:
                    att_num += w * a
                    att_den += w * away_base * defence.get(home, 1.0)
                    def_num += w * h
                    def_den += w * home_base * attack.get(home, 1.0)
            new_attack[team] = max(0.30, min(2.50, att_num / max(0.01, att_den)))
            new_defence[team] = max(0.35, min(2.70, def_num / max(0.01, def_den)))

        # Identifiability: keep geometric means near one.
        att_geo = math.exp(sum(math.log(v) for v in new_attack.values()) / max(1, len(new_attack)))
        def_geo = math.exp(sum(math.log(v) for v in new_defence.values()) / max(1, len(new_defence)))
        attack = {k: v / att_geo for k, v in new_attack.items()}
        defence = {k: v / def_geo for k, v in new_defence.items()}

    return CountStrengthModel(home_base, away_base, attack, defence, dict(team_weights), coverage, len(usable))


def fit_elo(records, reference=None, half_life_days=300.0, k=22.0, home_adv=62.0):
    ratings = defaultdict(lambda: 1500.0)
    reference_dt = _date(reference) if not isinstance(reference, datetime) else reference
    dates = [r["date"] for r in records if r["date"]]
    if reference_dt is None:
        reference_dt = max(dates) if dates else None

    for record in records:
        hg = _column(record, "ft_home_goals")
        ag = _column(record, "ft_away_goals")
        if hg is None or ag is None:
            continue
        home = record["home"]
        away = record["away"]
        diff = ratings[home] + home_adv - ratings[away]
        expected = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
        actual = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        margin = abs(hg - ag)
        margin_mult = 1.0 if margin <= 1 else math.log(margin + 1.0) * (2.2 / ((abs(diff) * 0.001) + 2.2))
        decay = _weight(record, reference_dt, half_life_days)
        delta = k * decay * margin_mult * (actual - expected)
        ratings[home] += delta
        ratings[away] -= delta
    return dict(ratings)


def _poisson(k, lam):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _dc_tau(h, a, lh, la, rho):
    if h == 0 and a == 0:
        return 1.0 - lh * la * rho
    if h == 0 and a == 1:
        return 1.0 + lh * rho
    if h == 1 and a == 0:
        return 1.0 + la * rho
    if h == 1 and a == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lh, la, rho=-0.08, max_goals=8):
    matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson(h, lh) * _poisson(a, la) * max(0.02, _dc_tau(h, a, lh, la, rho))
            matrix[(h, a)] = p
    norm = sum(matrix.values()) or 1.0
    return {k: v / norm for k, v in matrix.items()}


def fit_rho(records, model, reference=None):
    best_rho = -0.08
    best_ll = float("-inf")
    candidates = [x / 100.0 for x in range(-18, 7, 2)]
    reference_dt = _date(reference) if not isinstance(reference, datetime) else reference
    dates = [r["date"] for r in records if r["date"]]
    if reference_dt is None:
        reference_dt = max(dates) if dates else None
    for rho in candidates:
        ll = 0.0
        for record in records:
            h = _column(record, "ft_home_goals")
            a = _column(record, "ft_away_goals")
            if h is None or a is None or h > 8 or a > 8:
                continue
            lh, la = model.expected(record["home"], record["away"])
            p = _poisson(int(h), lh) * _poisson(int(a), la) * max(0.02, _dc_tau(int(h), int(a), lh, la, rho))
            ll += _weight(record, reference_dt, 150.0) * math.log(max(1e-12, p))
        if ll > best_ll:
            best_ll, best_rho = ll, rho
    return best_rho


def _outcome_probs(matrix):
    return (
        sum(p for (h, a), p in matrix.items() if h > a),
        sum(p for (h, a), p in matrix.items() if h == a),
        sum(p for (h, a), p in matrix.items() if h < a),
    )


def _rescale_outcomes(matrix, target):
    raw = _outcome_probs(matrix)
    adjusted = {}
    for score, p in matrix.items():
        h, a = score
        idx = 0 if h > a else 1 if h == a else 2
        adjusted[score] = p * target[idx] / max(1e-12, raw[idx])
    norm = sum(adjusted.values()) or 1.0
    return {k: v / norm for k, v in adjusted.items()}


def _blend_probability(raw, base, alpha):
    return max(0.001, min(0.999, alpha * raw + (1.0 - alpha) * base))


def _load_validation():
    try:
        return json.loads(VALIDATION_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _team_source(top_records, second_records, key):
    top_n = sum(1 for r in top_records if r["home"] == key or r["away"] == key)
    second_n = sum(1 for r in second_records if r["home"] == key or r["away"] == key)
    if top_n:
        return "1.ª divisão 2025/26", top_n, False
    if second_n:
        return "2.ª divisão 2025/26 com ajuste de promoção", second_n, True
    return "Perfil conservador estimado de equipa promovida", 0, True


def _promoted_strength(second_model, second_elo, key, metric="goals"):
    if key not in second_model.attack and key not in second_model.defence:
        if metric == "discipline":
            return 1.0, 1.0, 1420.0
        return 0.82, 1.18, 1420.0
    attack = second_model.attack.get(key, 1.0)
    defence = second_model.defence.get(key, 1.0)
    if metric == "discipline":
        converted_attack = max(0.75, min(1.35, 1.0 + 0.55 * (attack - 1.0)))
        converted_defence = max(0.75, min(1.35, 1.0 + 0.55 * (defence - 1.0)))
    elif metric == "performance":
        converted_attack = max(0.72, min(1.28, 0.90 + 0.60 * (attack - 1.0)))
        converted_defence = max(0.78, min(1.35, 1.10 + 0.60 * (defence - 1.0)))
    else:
        converted_attack = max(0.62, min(1.18, 0.82 + 0.60 * (attack - 1.0)))
        converted_defence = max(0.88, min(1.55, 1.18 + 0.60 * (defence - 1.0)))
    elo = 1420.0 + 0.72 * (second_elo.get(key, 1500.0) - 1500.0)
    return converted_attack, converted_defence, elo


def _expected_for_keys(top_model, second_model, top_elo, second_elo, home_key, away_key, metric="goals"):
    home_promoted = home_key not in top_model.attack
    away_promoted = away_key not in top_model.attack

    ha = top_model.attack.get(home_key)
    hd = top_model.defence.get(home_key)
    aa = top_model.attack.get(away_key)
    ad = top_model.defence.get(away_key)
    helo = top_elo.get(home_key)
    aelo = top_elo.get(away_key)

    if home_promoted:
        ha, hd, helo = _promoted_strength(second_model, second_elo, home_key, metric)
    if away_promoted:
        aa, ad, aelo = _promoted_strength(second_model, second_elo, away_key, metric)

    if metric == "discipline":
        default_attack, default_defence = 1.0, 1.0
    elif metric == "performance":
        default_attack, default_defence = 0.90, 1.10
    else:
        default_attack, default_defence = 0.82, 1.18
    ha = ha if ha is not None else default_attack
    hd = hd if hd is not None else default_defence
    aa = aa if aa is not None else default_attack
    ad = ad if ad is not None else default_defence
    helo = helo if helo is not None else 1420.0
    aelo = aelo if aelo is not None else 1420.0

    home_exp = top_model.home_base * ha * ad
    away_exp = top_model.away_base * aa * hd
    if metric == "goals":
        elo_diff = max(-350.0, min(350.0, helo + 62.0 - aelo))
        home_exp *= math.exp(elo_diff / 2200.0)
        away_exp *= math.exp(-elo_diff / 2200.0)
    return max(0.001, home_exp), max(0.001, away_exp), home_promoted, away_promoted


def _negative_binomial_pmf(k, mean, dispersion):
    if mean <= 0:
        return 1.0 if k == 0 else 0.0
    if dispersion is None or dispersion > 1e6:
        return _poisson(k, mean)
    r = max(0.05, dispersion)
    p = r / (r + mean)
    return math.exp(
        math.lgamma(k + r) - math.lgamma(r) - math.lgamma(k + 1)
        + r * math.log(p) + k * math.log(1.0 - p)
    )


def _dispersion(records, home_col, away_col):
    totals = []
    for r in records:
        h = _column(r, home_col)
        a = _column(r, away_col)
        if h is not None and a is not None:
            totals.append(h + a)
    if len(totals) < 20:
        return None
    mean = sum(totals) / len(totals)
    var = sum((x - mean) ** 2 for x in totals) / max(1, len(totals) - 1)
    if var <= mean * 1.03:
        return None
    return max(0.2, min(200.0, mean * mean / (var - mean)))


def over_probability(mean, line, dispersion=None, max_count=80):
    threshold = math.floor(line) + 1
    cumulative = sum(_negative_binomial_pmf(k, mean, dispersion) for k in range(threshold))
    return max(0.0, min(1.0, 1.0 - cumulative))


def _coverage(records, home_col, away_col):
    if not records:
        return 0.0
    n = sum(1 for r in records if _column(r, home_col) is not None and _column(r, away_col) is not None)
    return n / len(records)


def _referee_adjustment(current_rows, historical_rows, referee_name, metric_home, metric_away, league_mean):
    if not referee_name or league_mean <= 0:
        return 1.0, 0
    target = _normalise(referee_name)
    values = []
    for row in historical_rows:
        if _normalise(_get(row, "referee_name", "")) != target:
            continue
        h = _num(_get(row, metric_home))
        a = _num(_get(row, metric_away))
        if h is not None and a is not None:
            values.append(h + a)
    for row in current_rows:
        # Prognostics query can include referee_name alias for concluded matches.
        if _normalise(_get(row, "referee_name", "")) != target:
            continue
        h = _num(_get(row, metric_home))
        a = _num(_get(row, metric_away))
        if h is not None and a is not None:
            values.append(h + a)
    n = len(values)
    if n < 3:
        return 1.0, n
    avg = sum(values) / n
    factor = (avg * n + league_mean * 8.0) / ((n + 8.0) * league_mean)
    return max(0.82, min(1.22, factor)), n


def _weather_adjustment(current_rows, rain, temperature, metric_home, metric_away):
    if rain is None and temperature is None:
        return 1.0, 0, "Sem ajuste meteorológico"
    completed = []
    for row in current_rows:
        if _get(row, "status") != "Concluído":
            continue
        h = _num(_get(row, metric_home))
        a = _num(_get(row, metric_away))
        if h is None or a is None:
            continue
        completed.append((row, h + a))
    if len(completed) < 20:
        return 1.0, len(completed), "Sem amostra suficiente para clima"
    all_avg = sum(v for _, v in completed) / len(completed)
    factors = []
    samples = 0
    if rain is not None:
        subset = [v for row, v in completed if int(_get(row, "rain", 0) or 0) == int(bool(rain))]
        if len(subset) >= 8:
            factors.append((sum(subset) / len(subset)) / max(0.01, all_avg))
            samples += len(subset)
    if temperature is not None:
        temp_subset = [
            v for row, v in completed
            if _num(_get(row, "temperature")) is not None
            and abs(_num(_get(row, "temperature")) - float(temperature)) <= 4.0
        ]
        if len(temp_subset) >= 8:
            factors.append((sum(temp_subset) / len(temp_subset)) / max(0.01, all_avg))
            samples += len(temp_subset)
    if not factors:
        return 1.0, samples, "Sem amostra comparável para clima"
    raw = sum(factors) / len(factors)
    shrink = samples / (samples + 20.0)
    factor = 1.0 + shrink * (raw - 1.0)
    return max(0.88, min(1.12, factor)), samples, "Ajuste meteorológico com shrinkage"


def build_prediction_v3(current_rows, historical_rows, home_team_id, away_team_id, home_name, away_name, league_name, match_date=None, referee_name=None, rain=None, temperature=None, home_transfer=None, away_transfer=None):
    top_records = records_from_rows(current_rows, historical_rows, 1, before_date=match_date)
    second_records = records_from_rows([], historical_rows, 2, before_date=match_date)
    if not top_records:
        return None

    home_key = f"id:{int(home_team_id)}"
    away_key = f"id:{int(away_team_id)}"
    ref_date = _date(match_date) or max((r["date"] for r in top_records if r["date"]), default=None)

    goal_model = fit_count_strength(top_records, "ft_home_goals", "ft_away_goals", ref_date, 150.0, 8.0, default_home=1.35, default_away=1.10)
    second_goal_model = fit_count_strength(second_records, "ft_home_goals", "ft_away_goals", ref_date, 180.0, 8.0, default_home=1.30, default_away=1.05)
    top_elo = fit_elo(top_records, ref_date)
    second_elo = fit_elo(second_records, ref_date)

    lh, la, home_promoted, away_promoted = _expected_for_keys(
        goal_model, second_goal_model, top_elo, second_elo, home_key, away_key, "goals"
    )

    # Transfer-market adjustment. It is deliberately capped and fades as real
    # 2026/27 matches accumulate. Fees are only a proxy for expected impact.
    home_transfer = home_transfer or {}
    away_transfer = away_transfer or {}
    home_current_games = sum(
        1 for row in current_rows
        if _get(row, "status") == "Concluído"
        and int(_get(row, "home_team_id", -1)) == int(home_team_id)
        or _get(row, "status") == "Concluído"
        and int(_get(row, "away_team_id", -1)) == int(home_team_id)
    )
    away_current_games = sum(
        1 for row in current_rows
        if _get(row, "status") == "Concluído"
        and int(_get(row, "home_team_id", -1)) == int(away_team_id)
        or _get(row, "status") == "Concluído"
        and int(_get(row, "away_team_id", -1)) == int(away_team_id)
    )
    home_transfer_weight = max(0.0, 1.0 - home_current_games / 15.0)
    away_transfer_weight = max(0.0, 1.0 - away_current_games / 15.0)

    def transfer_components(data):
        attack = float(data.get("attack_delta", 0.0) or 0.0) + 0.40 * float(data.get("midfield_delta", 0.0) or 0.0)
        defence = float(data.get("defence_delta", 0.0) or 0.0) + 0.55 * float(data.get("goalkeeper_delta", 0.0) or 0.0) + 0.20 * float(data.get("midfield_delta", 0.0) or 0.0)
        return max(-0.12, min(0.12, attack)), max(-0.12, min(0.12, defence))

    h_att, h_def = transfer_components(home_transfer)
    a_att, a_def = transfer_components(away_transfer)
    home_transfer_factor = max(0.86, min(1.14, math.exp(home_transfer_weight * h_att - away_transfer_weight * a_def)))
    away_transfer_factor = max(0.86, min(1.14, math.exp(away_transfer_weight * a_att - home_transfer_weight * h_def)))
    lh *= home_transfer_factor
    la *= away_transfer_factor

    # Shot-on-target signal reduces the influence of unusual finishing.
    sot_cov = _coverage(top_records, "home_shots_on_target", "away_shots_on_target")
    if sot_cov >= 0.70:
        sot_model = fit_count_strength(top_records, "home_shots_on_target", "away_shots_on_target", ref_date, 150.0, 8.0, default_home=4.8, default_away=3.8)
        second_sot = fit_count_strength(second_records, "home_shots_on_target", "away_shots_on_target", ref_date, 180.0, 8.0, default_home=4.5, default_away=3.6)
        sh, sa, _, _ = _expected_for_keys(sot_model, second_sot, top_elo, second_elo, home_key, away_key, "performance")
        total_goals = sum((_column(r, "ft_home_goals") or 0) + (_column(r, "ft_away_goals") or 0) for r in top_records)
        total_sot = sum((_column(r, "home_shots_on_target") or 0) + (_column(r, "away_shots_on_target") or 0) for r in top_records)
        conversion = total_goals / max(1.0, total_sot)
        lh = 0.82 * lh + 0.18 * sh * conversion
        la = 0.82 * la + 0.18 * sa * conversion

    rho = fit_rho(top_records, goal_model, ref_date)
    raw_matrix = score_matrix(lh, la, rho)
    raw_h, raw_d, raw_a = _outcome_probs(raw_matrix)

    validations = _load_validation().get(league_name, {})
    alpha = float(validations.get("alpha_1x2", 0.88))
    base = validations.get("outcome_base") or [0.44, 0.27, 0.29]
    calibrated = [alpha * raw_h + (1-alpha) * base[0], alpha * raw_d + (1-alpha) * base[1], alpha * raw_a + (1-alpha) * base[2]]
    total = sum(calibrated) or 1.0
    calibrated = [x / total for x in calibrated]
    matrix = _rescale_outcomes(raw_matrix, calibrated)

    over_raw = sum(p for (h, a), p in matrix.items() if h + a >= 3)
    btts_raw = sum(p for (h, a), p in matrix.items() if h > 0 and a > 0)
    alpha_over = float(validations.get("alpha_over", 0.90))
    alpha_btts = float(validations.get("alpha_btts", 0.90))
    over_base = float(validations.get("over_base", 0.50))
    btts_base = float(validations.get("btts_base", 0.50))
    over_25 = _blend_probability(over_raw, over_base, alpha_over)
    btts = _blend_probability(btts_raw, btts_base, alpha_btts)

    # Half-time model.
    ht_model = fit_count_strength(top_records, "ht_home_goals", "ht_away_goals", ref_date, 150.0, 10.0, default_home=0.62, default_away=0.48)
    second_ht = fit_count_strength(second_records, "ht_home_goals", "ht_away_goals", ref_date, 180.0, 10.0, default_home=0.58, default_away=0.45)
    hth, hta, _, _ = _expected_for_keys(ht_model, second_ht, top_elo, second_elo, home_key, away_key, "goals")
    ht_matrix = score_matrix(hth, hta, rho=-0.05, max_goals=5)
    ht_probs = _outcome_probs(ht_matrix)

    count_specs = {
        "corners": ("home_corners", "away_corners", 5.0, 4.5, "performance"),
        "fouls": ("home_fouls", "away_fouls", 12.0, 12.0, "discipline"),
        "yellows": ("home_yellow", "away_yellow", 2.2, 2.3, "discipline"),
        "offsides": ("home_offsides", "away_offsides", 1.8, 1.7, "performance"),
    }
    counts = {}
    for name, (hc, ac, dh, da, cls) in count_specs.items():
        cov = _coverage(top_records, hc, ac)
        if cov < 0.35:
            counts[name] = {"available": False, "coverage": cov}
            continue
        top_m = fit_count_strength(top_records, hc, ac, ref_date, 150.0, 8.0, default_home=dh, default_away=da)
        second_m = fit_count_strength(second_records, hc, ac, ref_date, 180.0, 8.0, default_home=dh, default_away=da)
        eh, ea, _, _ = _expected_for_keys(top_m, second_m, top_elo, second_elo, home_key, away_key, cls)
        expected_total = eh + ea
        ref_factor, ref_n = _referee_adjustment(current_rows, historical_rows, referee_name, hc, ac, top_m.home_base + top_m.away_base)
        weather_factor, weather_n, weather_label = _weather_adjustment(current_rows, rain, temperature, hc, ac)
        expected_total *= ref_factor * weather_factor
        scale = expected_total / max(0.01, eh + ea)
        eh *= scale
        ea *= scale
        dispersion = _dispersion(top_records, hc, ac)
        counts[name] = {
            "available": True,
            "coverage": cov,
            "home": eh,
            "away": ea,
            "total": expected_total,
            "dispersion": dispersion,
            "referee_sample": ref_n,
            "weather_sample": weather_n,
            "weather_label": weather_label,
        }

    goal_minutes_cov = sum(1 for r in top_records if str(_get(r["row"], "goal_minutes", "") or "").strip()) / len(top_records)
    first5 = None
    if goal_minutes_cov >= 0.30:
        total_early = 0
        usable = 0
        team_early = defaultdict(lambda: [0, 0])
        for r in top_records:
            text = str(_get(r["row"], "goal_minutes", "") or "").strip()
            if not text:
                continue
            minutes = []
            for token in re.split(r"[,;\s]+", text):
                m = re.fullmatch(r"(\d+)(?:\+(\d+))?", token)
                if m:
                    minutes.append(int(m.group(1)) + int(m.group(2) or 0))
            early = any(m <= 5 for m in minutes)
            usable += 1
            total_early += int(early)
            for team in (r["home"], r["away"]):
                team_early[team][0] += int(early)
                team_early[team][1] += 1
        league_rate = (total_early + 2.0) / (usable + 28.0)
        rates = []
        for key in (home_key, away_key):
            e, n = team_early[key]
            if n:
                rates.append((e + league_rate * 8.0) / (n + 8.0))
        first5 = max(0.01, min(0.22, (league_rate + (sum(rates) / len(rates) if rates else league_rate)) / 2.0))

    home_source = _team_source(top_records, second_records, home_key)
    away_source = _team_source(top_records, second_records, away_key)
    validation_skill = float(validations.get("brier_improvement_pct", 0.0))
    min_sample = min(home_source[1], away_source[1])
    confidence_score = 45
    confidence_score += min(25, min_sample)
    confidence_score += max(-12, min(12, validation_skill * 2.0))
    if home_promoted or away_promoted:
        confidence_score -= 10
    if (home_source[1] == 0 and home_promoted) or (away_source[1] == 0 and away_promoted):
        confidence_score -= 8
    confidence_score = int(max(15, min(90, confidence_score)))

    return {
        "home_win": calibrated[0], "draw": calibrated[1], "away_win": calibrated[2],
        "raw_home_win": raw_h, "raw_draw": raw_d, "raw_away_win": raw_a,
        "expected_home_goals": lh, "expected_away_goals": la,
        "score_matrix": matrix,
        "exact_scores": sorted(matrix.items(), key=lambda x: x[1], reverse=True)[:7],
        "over_25": over_25, "under_25": 1-over_25,
        "btts_yes": btts, "btts_no": 1-btts,
        "ht_home": ht_probs[0], "ht_draw": ht_probs[1], "ht_away": ht_probs[2],
        "ht_exact_scores": sorted(ht_matrix.items(), key=lambda x: x[1], reverse=True)[:4],
        "counts": counts,
        "first5": first5,
        "first5_coverage": goal_minutes_cov,
        "rho": rho,
        "home_source": home_source[0], "away_source": away_source[0],
        "home_sample": home_source[1], "away_sample": away_source[1],
        "home_promoted": home_promoted, "away_promoted": away_promoted,
        "confidence_score": confidence_score,
        "validation": validations,
        "data_matches": len(top_records),
        "transfer_adjustment": {
            "home_factor": home_transfer_factor, "away_factor": away_transfer_factor,
            "home_weight": home_transfer_weight, "away_weight": away_transfer_weight,
            "home_arrivals": int(home_transfer.get("arrivals", 0) or 0),
            "home_departures": int(home_transfer.get("departures", 0) or 0),
            "away_arrivals": int(away_transfer.get("arrivals", 0) or 0),
            "away_departures": int(away_transfer.get("departures", 0) or 0),
        },
        "model_version": "V4 — força dinâmica + transferências + recência + adversário + Dixon-Coles + calibração",
    }
