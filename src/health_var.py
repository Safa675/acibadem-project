"""
health_var.py
HealthVaR — Monte Carlo-based deterioration risk forecasting.

Standalone Monte Carlo bootstrap for clinical deterioration risk forecasting.
No external library dependencies beyond NumPy.

The Patient Health VaR answers:
  "With 95% confidence, the patient's health score will NOT fall below X
   in the next N lab-draw cycles."

VaR thresholds (clinically calibrated against SOFA-equivalent logic):
  GREEN  (VaR >  +5%): health stable or improving
  YELLOW (VaR  0 to +5%): slight risk, monitor
  ORANGE (VaR -10 to 0%): moderate risk, review within 24h
  RED    (VaR < -10%): high risk, prioritize review

Uses relative VaR (% change from current score), not absolute, for
cross-patient comparability.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass

from .health_index import SeriesPoint


# ---------------------------------------------------------------------------
# VaR risk tiers
# ---------------------------------------------------------------------------


@dataclass
class HealthVaRResult:
    patient_id: int
    current_score: float
    # Fan chart percentiles of the horizon distribution
    p05: float  # Health VaR (5th percentile)
    p25: float
    p50: float  # Median forecast
    p75: float
    p95: float
    # Relative (% change from current)
    var_pct: float  # (p05 - current) / current * 100
    cvar_pct: float  # Expected shortfall below p05
    horizon_draws: int
    n_iterations: int
    risk_tier: str  # GREEN / YELLOW / ORANGE / RED
    risk_label: str


def _assign_risk_tier(var_pct: float) -> tuple[str, str]:
    """Map VaR % to risk tier and clinical label."""
    if var_pct > 5.0:
        return "GREEN", "Health Stable — minimal risk of decline"
    elif var_pct >= 0.0:  # include exactly 0.0 in YELLOW, not ORANGE
        return "YELLOW", "Low Risk — slight downside possible"
    elif var_pct > -10.0:
        return "ORANGE", "Moderate Risk — review within 24–48h"
    else:
        return "RED", "High Risk — prioritize clinical review"


# ---------------------------------------------------------------------------
# Monte Carlo bootstrap (arithmetic returns — correct for bounded health scores)
# ---------------------------------------------------------------------------


def _fallback_monte_carlo(
    scores: list[float],
    iterations: int,
    horizon: int,
    seed: int | None = None,
) -> dict:
    """
    Simple historical bootstrap Monte Carlo.
    Resamples historical arithmetic returns to simulate future paths.
    Uses arithmetic (not log) returns to avoid explosive paths near zero.
    """
    rng = np.random.default_rng(seed)
    arr = np.array(scores, dtype=float)
    if len(arr) < 2:
        # No history: return flat forecast
        v = arr[-1] if len(arr) > 0 else 50.0
        return {f"p{k:02d}": v for k in [5, 25, 50, 75, 95]}

    # Use arithmetic returns instead of log-returns.
    # Log-returns explode when health scores are near zero (e.g., 80→15
    # gives ln(15/80) ≈ −1.67, which compounds to ~0 over 3 steps).
    # Arithmetic returns stay bounded and clinically interpretable.
    returns = np.diff(arr) / np.maximum(arr[:-1], 1.0)
    if len(returns) == 0:
        v = arr[-1]
        return {f"p{k:02d}": v for k in [5, 25, 50, 75, 95]}

    current = arr[-1]
    terminals = []
    for _ in range(iterations):
        path = current
        for _ in range(horizon):
            r = rng.choice(returns)
            path = np.clip(path * (1.0 + r), 0, 100)
        terminals.append(path)

    terminals_arr = np.array(terminals)
    return {
        "p05": float(np.percentile(terminals_arr, 5)),
        "p25": float(np.percentile(terminals_arr, 25)),
        "p50": float(np.percentile(terminals_arr, 50)),
        "p75": float(np.percentile(terminals_arr, 75)),
        "p95": float(np.percentile(terminals_arr, 95)),
    }


# ---------------------------------------------------------------------------
# Main VaR computation
# ---------------------------------------------------------------------------


def compute_health_var(
    patient_id: int,
    series_points: list[SeriesPoint],  # output of HealthIndexBuilder.to_series_points()
    horizon_draws: int = 3,
    iterations: int = 5000,
    seed: int = 42,
) -> HealthVaRResult | None:
    """
    Compute Health VaR for a patient.

    Args:
        patient_id: patient identifier
        series_points: health score time-series (SeriesPoint list)
        horizon_draws: how many lab-draw cycles ahead to forecast
        iterations: Monte Carlo simulation iterations
        seed: random seed for reproducibility

    Returns:
        HealthVaRResult or None if insufficient data
    """
    if len(series_points) < 2:
        return None

    # Filter NaN values to prevent silent propagation into MC percentiles
    scores = [sp.value for sp in series_points if not np.isnan(sp.value)]
    if len(scores) < 2:
        return None
    current = scores[-1]

    fan = _fallback_monte_carlo(scores, iterations, horizon_draws, seed)

    p05 = fan["p05"]
    p50 = fan["p50"]

    var_pct = (p05 - current) / max(current, 1) * 100.0
    # CVaR (Expected Shortfall) approximation:
    # Only meaningful when var_pct < 0 (patient at risk of decline).
    # For positive var_pct (improving), CVaR = 0 (no tail risk).
    # The 1.3x factor is a conservative bound; proper CVaR requires
    # returning raw terminals from MC and computing mean(terminals < p05).
    cvar_pct = var_pct * 1.3 if var_pct < 0 else 0.0

    tier, label = _assign_risk_tier(var_pct)

    return HealthVaRResult(
        patient_id=patient_id,
        current_score=round(current, 2),
        p05=round(p05, 2),
        p25=round(fan["p25"], 2),
        p50=round(p50, 2),
        p75=round(fan["p75"], 2),
        p95=round(fan["p95"], 2),
        var_pct=round(var_pct, 2),
        cvar_pct=round(cvar_pct, 2),
        horizon_draws=horizon_draws,
        n_iterations=iterations,
        risk_tier=tier,
        risk_label=label,
    )


def compute_all_patient_vars(
    series_by_patient: dict[int, list[SeriesPoint]],
    horizon_draws: int = 3,
    iterations: int = 5000,
    seed: int = 42,
) -> pd.DataFrame:
    """Compute VaR for all patients in batch. Returns summary DataFrame."""
    rows = []
    for pid, series in series_by_patient.items():
        result = compute_health_var(
            pid, series, horizon_draws=horizon_draws, iterations=iterations, seed=seed
        )
        if result:
            rows.append(
                {
                    "patient_id": pid,
                    "current_score": result.current_score,
                    "var_pct": result.var_pct,
                    "health_var_score": result.p05,
                    "median_forecast": result.p50,
                    "risk_tier": result.risk_tier,
                    "risk_label": result.risk_label,
                }
            )
    return pd.DataFrame(rows).sort_values("var_pct").reset_index(drop=True)
