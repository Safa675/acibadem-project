"""
advanced_analytics.py
12 additional finance→healthcare analytical transfers.
Standalone implementations using NumPy/SciPy — no external library dependencies.

Features:
  1. GARCH Vol Forecast → Lab Instability Forecaster
  2. Stress Scenarios → Clinical Stress Testing
  3. Walk-Forward Validation → Temporal Clinical Validation
  4. Ulcer Index → Patient Suffering Index
  5. Risk Contribution → Organ System Risk Decomposition
  6. Correlation Matrix → Lab Cross-Correlation
  7. Mean-Variance Optimization → Optimal Fusion Weights
  8. Kelly Criterion → Optimal Intervention Sizing
  9. Significance Testing → Clinical Signal Significance
  10. Inverse Volatility Weighting → Stability-Weighted Health Score
  11. Rolling Metrics → Health Trajectory Dashboard
  12. Drawdown Analysis → Maximum Clinical Decline
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Sequence

from .health_index import SeriesPoint


def _health_returns(points: list[SeriesPoint]) -> list[SeriesPoint]:
    """Convert health score series → return series (percentage changes)."""
    if len(points) < 2:
        return []
    returns = []
    for i in range(1, len(points)):
        prev = max(points[i - 1].value, 0.01)
        ret = (points[i].value - points[i - 1].value) / prev
        returns.append(SeriesPoint(date=points[i].date, value=ret))
    return returns


# ============================================================================
# 1. GARCH Volatility Forecast → "Lab Instability Forecaster"
# ============================================================================


@dataclass
class HealthVolForecast:
    patient_id: str
    latest_forecast_vol: float  # predicted next-period vol (%)
    latest_realized_vol: float  # actual recent vol (%)
    instability_regime: str  # "low" | "normal" | "high"
    vol_series: list[dict]  # [{date, forecast_vol, realized_vol, regime}]


def compute_garch_health_vol(
    patient_id: str,
    series: list[SeriesPoint],
    target_vol_pct: float = 15.0,
) -> HealthVolForecast | None:
    """
    EWMA/GARCH volatility forecast for patient health score.
    Predicts whether lab instability will increase or decrease.
    """
    returns = _health_returns(series)
    if len(returns) < 4:
        return None

    # EWMA volatility forecast
    vals = [r.value for r in returns]
    alpha = 0.15
    ewma_var = vals[0] ** 2
    realized_vols = []
    forecast_vols = []
    for i, r in enumerate(vals):
        ewma_var = alpha * r * r + (1 - alpha) * ewma_var
        realized_vols.append(np.std(vals[max(0, i - 5) : i + 1]) * 100)
        forecast_vols.append(np.sqrt(ewma_var) * 100)

    last_fv = forecast_vols[-1]
    regime = "low" if last_fv < 5 else ("high" if last_fv > 20 else "normal")

    vol_data = [
        {
            "date": returns[i].date,
            "forecast_vol": round(forecast_vols[i], 2),
            "realized_vol": round(realized_vols[i], 2),
            "regime": regime,
        }
        for i in range(len(returns))
    ]

    return HealthVolForecast(
        patient_id=patient_id,
        latest_forecast_vol=round(last_fv, 2),
        latest_realized_vol=round(realized_vols[-1], 2),
        instability_regime=regime,
        vol_series=vol_data,
    )


# ============================================================================
# 2. Stress Scenarios → "Clinical Stress Testing"
# ============================================================================


@dataclass
class ClinicalStressResult:
    patient_id: str
    scenarios: list[dict]  # [{name, shock_pct, health_impact_pct, expected_shortfall}]


def run_clinical_stress_test(
    patient_id: str,
    series: list[SeriesPoint],
) -> ClinicalStressResult | None:
    """
    What happens to this patient if they experience the worst historical outcomes?
    Uses the same stress scenario engine as financial portfolios.
    """
    returns = _health_returns(series)
    if len(returns) < 5:
        return None

    # Quantile-based stress scenarios
    vals = [r.value for r in returns]
    arr = np.array(vals)
    # Guard: when all returns are positive, the 5th-percentile tail may be empty
    tail = arr[arr < np.percentile(arr, 5)]
    es_val = (
        float(np.mean(tail)) * 100
        if len(tail) > 0
        else float(np.percentile(arr, 5)) * 100
    )
    scenarios = [
        {
            "name": "Worst Day (actual)",
            "shock_pct": round(float(arr.min()) * 100, 2),
            "health_impact_pct": round(float(arr.min()) * 100, 2),
            "expected_shortfall": round(es_val, 2),
        },
        {
            "name": "99th percentile adverse",
            "shock_pct": round(float(np.percentile(arr, 1)) * 100, 2),
            "health_impact_pct": round(float(np.percentile(arr, 1)) * 100, 2),
            "expected_shortfall": round(es_val, 2),
        },
        {
            "name": "2x historical worst",
            "shock_pct": round(float(arr.min()) * 200, 2),
            "health_impact_pct": round(float(arr.min()) * 200, 2),
            "expected_shortfall": round(es_val * 2, 2),
        },
    ]
    return ClinicalStressResult(patient_id=patient_id, scenarios=scenarios)


# ============================================================================
# 3. Walk-Forward Validation → "Temporal Clinical Validation"
# ============================================================================


@dataclass
class WalkForwardClinicalResult:
    splits: list[
        dict
    ]  # [{split, train_start, train_end, test_start, test_end, train_sharpe, test_sharpe}]
    avg_test_sharpe: float
    is_robust: bool  # test Sharpe > 0 across all splits


def run_walk_forward_clinical(
    series: list[SeriesPoint],
    splits: int = 3,
) -> WalkForwardClinicalResult | None:
    """Walk-forward validation of health scoring consistency over time."""
    returns = _health_returns(series)
    if len(returns) < 10:
        return None

    # Expanding-window walk-forward split
    n = len(returns)
    chunk = n // (splits + 1)
    split_data = []
    for s in range(splits):
        train_end = chunk * (s + 1)
        test_end = min(chunk * (s + 2), n)
        train = [r.value for r in returns[:train_end]]
        test = [r.value for r in returns[train_end:test_end]]
        train_sharpe = np.mean(train) / max(np.std(train), 1e-8) * np.sqrt(252)
        test_sharpe = (
            np.mean(test) / max(np.std(test), 1e-8) * np.sqrt(252) if test else 0
        )
        split_data.append(
            {
                "split": s + 1,
                "train_start": returns[0].date,
                "train_end": returns[min(train_end - 1, n - 1)].date,
                "test_start": returns[min(train_end, n - 1)].date,
                "test_end": returns[min(test_end - 1, n - 1)].date,
                "train_sharpe": round(train_sharpe, 3),
                "test_sharpe": round(test_sharpe, 3),
            }
        )
    avg_ts = np.mean([s["test_sharpe"] for s in split_data]) if split_data else 0
    return WalkForwardClinicalResult(
        splits=split_data,
        avg_test_sharpe=round(avg_ts, 3),
        is_robust=all(s["test_sharpe"] > 0 for s in split_data),
    )


# ============================================================================
# 4. Advanced Risk Metrics → Ulcer Index = "Patient Suffering Index"
# ============================================================================


@dataclass
class PatientSufferingMetrics:
    patient_id: str
    ulcer_index: float  # depth AND duration of health declines
    cvar_95: float  # expected shortfall
    max_adverse_excursion: float  # worst possible decline threshold
    expectancy_ratio: float | None  # expected value per "trade" (visit)
    profit_factor: float | None  # positive changes / negative changes


def compute_suffering_metrics(
    patient_id: str,
    series: list[SeriesPoint],
) -> PatientSufferingMetrics | None:
    """Ulcer Index + CVaR + MAE + expectancy from health returns."""
    returns = _health_returns(series)
    if len(returns) < 3:
        return None

    vals = np.array([r.value for r in returns])
    # Ulcer Index = RMS of percentage drawdowns from running peak
    scores = np.array([p.value for p in series])
    peak = np.maximum.accumulate(scores)
    dd_pct = (scores - peak) / np.maximum(peak, 0.01) * 100
    ulcer = np.sqrt(np.mean(dd_pct**2))

    sorted_vals = np.sort(vals)
    cvar_idx = max(int(len(sorted_vals) * 0.05), 1)
    cvar = float(np.mean(sorted_vals[:cvar_idx]))

    gains = vals[vals > 0]
    losses = vals[vals < 0]
    pf = (
        float(gains.sum() / abs(losses.sum()))
        if len(losses) > 0 and losses.sum() != 0
        else None
    )
    er = float(np.mean(vals) / max(np.std(vals), 1e-8)) if len(vals) > 2 else None

    return PatientSufferingMetrics(
        patient_id=patient_id,
        ulcer_index=round(float(ulcer), 4),
        cvar_95=round(cvar, 4),
        max_adverse_excursion=round(float(vals.min()), 4),
        expectancy_ratio=round(er, 4) if er else None,
        profit_factor=round(pf, 4) if pf else None,
    )


# ============================================================================
# 5. Risk Contribution → "Organ System Risk Decomposition"
# ============================================================================


def compute_organ_risk_contribution(
    organ_series: dict[str, list[SeriesPoint]],
    weights: dict[str, float] | None = None,
) -> dict:
    """
    Decompose total health risk into per-organ-system contributions.
    Input: {organ_system: health_score_series}
    """
    if not organ_series or len(organ_series) < 2:
        return {}

    if weights is None:
        weights = {k: 1.0 / len(organ_series) for k in organ_series}

    # Variance-based contribution
    ret_dict = {}
    for k, v in organ_series.items():
        rets = _health_returns(v)
        if len(rets) >= 2:
            ret_dict[k] = np.array([r.value for r in rets])

    if len(ret_dict) < 2:
        return {}

    total_var = 0
    contribs = {}
    for k, v in ret_dict.items():
        w = weights.get(k, 1 / len(ret_dict))
        contribs[k] = w * np.var(v)
        total_var += contribs[k]

    if total_var == 0:
        return {}

    return {
        "contribution_pct": {
            k: round(v / total_var * 100, 2) for k, v in contribs.items()
        },
        "marginal_contribution": {k: round(v, 6) for k, v in contribs.items()},
    }


# ============================================================================
# 6. Correlation Matrix → "Lab Cross-Correlation"
# ============================================================================


def compute_lab_correlation_matrix(
    lab_series: dict[str, list[SeriesPoint]],
) -> dict[str, dict[str, float]]:
    """
    Pairwise correlation between different lab test trajectories.
    Input: {lab_name: [SeriesPoint(date, z_score)]}
    """

    keys = list(lab_series.keys())
    result: dict[str, dict[str, float]] = {}
    for i, k1 in enumerate(keys):
        result[k1] = {}
        v1 = np.array([p.value for p in lab_series[k1]])
        for j, k2 in enumerate(keys):
            v2 = np.array([p.value for p in lab_series[k2]])
            minlen = min(len(v1), len(v2))
            if minlen >= 3:
                corr = float(np.corrcoef(v1[:minlen], v2[:minlen])[0, 1])
                result[k1][k2] = round(corr, 3)
            else:
                result[k1][k2] = 0.0
    return result


# ============================================================================
# 7. Mean-Variance Optimization → "Optimal Fusion Weights"
# ============================================================================


@dataclass
class OptimalFusionResult:
    best_weights: dict[str, float]
    best_sharpe: float
    best_return: float
    best_volatility: float


def optimize_fusion_weights(
    component_series: dict[str, list[SeriesPoint]],
) -> OptimalFusionResult | None:
    """
    Find the optimal weights for combining health components
    (health_index, nlp_signal, med_velocity) that maximizes Sharpe.
    """
    if len(component_series) < 2:
        return None

    # Random-search mean-variance optimization
    keys = list(component_series.keys())
    n = len(keys)
    rng = np.random.default_rng(42)
    best_sharpe = -999
    best_w = {k: 1 / n for k in keys}

    # Align to min length
    min_len = min(len(v) for v in component_series.values())
    if min_len < 3:
        return None  # need at least 3 points to compute returns

    # Convert levels → returns before optimization.
    # Sharpe on levels always picks the highest-scoring component (meaningless).
    # Sharpe on returns measures risk-adjusted change over time (clinically useful).
    arrays = {}
    for k, v in component_series.items():
        vals = np.array([p.value for p in v[:min_len]])
        rets = np.diff(vals) / np.maximum(np.abs(vals[:-1]), 0.01)
        arrays[k] = rets

    for _ in range(2000):
        raw = rng.dirichlet(np.ones(n))
        weights = dict(zip(keys, raw))
        combo = sum(weights[k] * arrays[k] for k in keys)
        ret_mean = np.mean(combo)
        ret_std = np.std(combo)
        sharpe = ret_mean / max(ret_std, 1e-8)
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w = {k: round(v, 3) for k, v in weights.items()}
            best_ret = ret_mean
            best_vol = ret_std

    return OptimalFusionResult(
        best_weights=best_w,
        best_sharpe=round(best_sharpe, 3),
        best_return=round(best_ret, 4),
        best_volatility=round(best_vol, 4),
    )


# ============================================================================
# 8. Kelly Criterion → "Optimal Intervention Sizing"
# ============================================================================


@dataclass
class InterventionSizing:
    win_rate_pct: float
    win_loss_ratio: float
    kelly_fraction: float  # 0.0 to 1.0 — how aggressively to intervene
    recommendation: str


def compute_kelly_intervention(
    series: list[SeriesPoint],
    fractional_kelly: float = 0.5,
) -> InterventionSizing | None:
    """
    Given health score changes, what's the optimal 'intervention intensity'?
    Kelly criterion: high win rate + high payoff ratio → intervene aggressively.
    """
    returns = _health_returns(series)
    if len(returns) < 5:
        return None

    vals = np.array([r.value for r in returns])
    wins = vals[vals > 0]
    losses = vals[vals < 0]

    if len(wins) == 0 or len(losses) == 0:
        return InterventionSizing(
            win_rate_pct=100.0 if len(losses) == 0 else 0.0,
            win_loss_ratio=float("inf") if len(losses) == 0 else 0.0,
            kelly_fraction=1.0 if len(losses) == 0 else 0.0,
            recommendation="Patient consistently improving"
            if len(losses) == 0
            else "Patient consistently declining — urgent intervention",
        )

    win_rate = len(wins) / len(vals) * 100
    wl_ratio = abs(np.mean(wins) / np.mean(losses))

    kelly_frac = (
        max(0, (win_rate / 100 - (1 - win_rate / 100) / wl_ratio)) * fractional_kelly
    )

    if kelly_frac > 0.6:
        rec = "Strong positive momentum — maintain current treatment, monitor"
    elif kelly_frac > 0.3:
        rec = "Moderate momentum — standard care, periodic review"
    elif kelly_frac > 0.1:
        rec = "Weak momentum — consider treatment adjustment"
    else:
        rec = "Negative momentum — escalate care, reassess treatment plan"

    return InterventionSizing(
        win_rate_pct=round(win_rate, 1),
        win_loss_ratio=round(wl_ratio, 2),
        kelly_fraction=round(kelly_frac, 3),
        recommendation=rec,
    )


# ============================================================================
# 9. Significance Testing → "Clinical Signal Significance"
# ============================================================================


@dataclass
class ClinicalSignificance:
    t_stat: float
    p_value: float
    bootstrap_p: float
    is_significant: bool  # p < 0.05


def test_clinical_significance(
    strategy_series: list[SeriesPoint],
    baseline_series: list[SeriesPoint] | None = None,
) -> ClinicalSignificance | None:
    """
    Is our health scoring system significantly better than random?
    Bootstrap + t-test significance testing.
    """
    returns = _health_returns(strategy_series)
    if len(returns) < 5:
        return None

    baseline = _health_returns(baseline_series) if baseline_series else None

    # One-sample t-test + bootstrap
    vals = np.array([r.value for r in returns])
    n = len(vals)
    mean = np.mean(vals)
    se = np.std(vals, ddof=1) / np.sqrt(n)
    t_stat = mean / max(se, 1e-10)

    # Approximate p-value from t-distribution
    from math import erfc, sqrt

    p_val = erfc(abs(t_stat) / sqrt(2))

    # Bootstrap
    rng = np.random.default_rng(42)
    n_boot = 1000
    boot_means = [
        float(np.mean(rng.choice(vals, size=n, replace=True))) for _ in range(n_boot)
    ]
    boot_p = np.mean([1 for m in boot_means if m <= 0]) / n_boot

    return ClinicalSignificance(
        t_stat=round(float(t_stat), 3),
        p_value=round(float(p_val), 4),
        bootstrap_p=round(float(boot_p), 4),
        is_significant=p_val < 0.05,
    )


# ============================================================================
# 10. Inverse Vol Weights → "Stability-Weighted Health Score"
# ============================================================================


def compute_inverse_vol_weights(
    lab_series: dict[str, list[SeriesPoint]],
) -> dict[str, float]:
    """
    Weight labs inversely by their volatility.
    Stable labs → high weight (reliable signal). Noisy labs → low weight.
    """
    vols = {}
    for name, series in lab_series.items():
        if len(series) >= 3:
            vals = [p.value for p in series]
            vols[name] = max(np.std(vals), 1e-8)

    if not vols:
        return {}

    inv_vols = {k: 1.0 / v for k, v in vols.items()}
    total = sum(inv_vols.values())
    return {k: round(v / total, 4) for k, v in inv_vols.items()}


# ============================================================================
# 11. Rolling Metrics → "Health Trajectory Dashboard"
# ============================================================================


@dataclass
class HealthRollingPoint:
    date: str
    rolling_return: float | None  # health change over window
    rolling_sharpe: float | None  # improvement efficiency
    rolling_volatility: float | None  # instability over window
    rolling_drawdown: float | None  # worst decline in window


def compute_rolling_health_metrics(
    series: list[SeriesPoint],
    window: int = 5,
) -> list[HealthRollingPoint]:
    """Rolling health analytics: Sharpe, vol, drawdown over a sliding window."""
    if len(series) < window + 1:
        return []

    vals = np.array([p.value for p in series])
    dates = [p.date for p in series]
    results = []
    for i in range(len(vals)):
        if i < window:
            results.append(
                HealthRollingPoint(
                    date=dates[i],
                    rolling_return=None,
                    rolling_sharpe=None,
                    rolling_volatility=None,
                    rolling_drawdown=None,
                )
            )
            continue

        w = vals[i - window : i + 1]
        rets = np.diff(w) / np.maximum(w[:-1], 0.01)
        ret = float((w[-1] / max(w[0], 0.01)) - 1)
        vol = float(np.std(rets)) if len(rets) > 1 else 0
        sharpe = float(np.mean(rets) / max(vol, 1e-8))
        peak = np.maximum.accumulate(w)
        dd = float(np.min((w - peak) / np.maximum(peak, 0.01)))

        results.append(
            HealthRollingPoint(
                date=dates[i],
                rolling_return=round(ret, 4),
                rolling_sharpe=round(sharpe, 4),
                rolling_volatility=round(vol, 4),
                rolling_drawdown=round(dd, 4),
            )
        )
    return results


# ============================================================================
# 12. Maximum Clinical Decline Analysis
# ============================================================================


@dataclass
class ClinicalDrawdown:
    patient_id: str
    max_drawdown_pct: float  # worst peak-to-trough decline
    drawdown_start: str | None  # when the decline started
    drawdown_end: str | None  # when the trough was hit
    recovery_time_days: int | None  # days to recover (None if never recovered)
    current_drawdown_pct: float  # how far below peak right now


def compute_health_drawdown(
    patient_id: str,
    series: list[SeriesPoint],
) -> ClinicalDrawdown | None:
    """Maximum health decline analysis — analogous to max drawdown in portfolios."""
    if len(series) < 2:
        return None

    vals = np.array([p.value for p in series])
    dates = [p.date for p in series]

    peak = np.maximum.accumulate(vals)
    dd = (vals - peak) / np.maximum(peak, 0.01)

    max_dd_idx = np.argmin(dd)
    max_dd = float(dd[max_dd_idx])

    # Find start of this drawdown (last peak before trough)
    start_idx = max_dd_idx
    while start_idx > 0 and vals[start_idx - 1] >= vals[start_idx]:
        start_idx -= 1

    # Check if recovered after trough
    recovery_idx = None
    for i in range(max_dd_idx + 1, len(vals)):
        if vals[i] >= peak[max_dd_idx]:
            recovery_idx = i
            break

    current_dd = float((vals[-1] - peak[-1]) / max(peak[-1], 0.01))

    recovery_days = None
    if recovery_idx is not None:
        try:
            d1 = pd.Timestamp(dates[max_dd_idx])
            d2 = pd.Timestamp(dates[recovery_idx])
            recovery_days = (d2 - d1).days
        except Exception:
            pass

    return ClinicalDrawdown(
        patient_id=patient_id,
        max_drawdown_pct=round(max_dd * 100, 2),
        drawdown_start=dates[start_idx] if start_idx < len(dates) else None,
        drawdown_end=dates[max_dd_idx] if max_dd_idx < len(dates) else None,
        recovery_time_days=recovery_days,
        current_drawdown_pct=round(current_dd * 100, 2),
    )


# ============================================================================
# Batch analysis: run everything for all patients
# ============================================================================


def run_full_advanced_analysis(
    series_by_patient: dict[str, list[SeriesPoint]],
) -> dict[str, dict]:
    """Run all 12 advanced analytics for every patient. Returns nested dict."""
    results = {}
    for pid, series in series_by_patient.items():
        patient_results = {}
        patient_results["garch_vol"] = compute_garch_health_vol(pid, series)
        patient_results["stress_test"] = run_clinical_stress_test(pid, series)
        patient_results["suffering"] = compute_suffering_metrics(pid, series)
        patient_results["kelly"] = compute_kelly_intervention(series)
        patient_results["drawdown"] = compute_health_drawdown(pid, series)
        patient_results["rolling"] = compute_rolling_health_metrics(series, window=3)
        patient_results["significance"] = test_clinical_significance(series)
        results[pid] = patient_results
    return results
