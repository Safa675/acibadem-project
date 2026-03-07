"""
eci.py
Expected Cost Intensity — actuarial-grade patient expenditure risk score.

Analogous to sovereign/corporate credit ratings in finance:
  - S&P/Moody's rates credit risk → likelihood/magnitude of default
  - ECI rates patient cost risk → likelihood/magnitude of resource consumption

ECI ∈ [0, 100] where 100 = highest expected expenditure.

Four equal-weight components (25% each), all percentile-normalized:
  1. Visit Intensity     — visits per month, cohort-ranked
  2. Medication Burden   — drug count + change velocity, cohort-ranked
  3. Diagnostic Intensity — lab tests per month, cohort-ranked
  4. Clinical Trajectory  — health trend + NLP signal, cohort-ranked

Letter rating tiers (same semantic as credit ratings):
  AAA (0-15)    Minimal expenditure risk
  AA  (15-30)   Low expenditure risk
  A   (30-45)   Moderate expenditure risk
  BBB (45-60)   Elevated expenditure risk
  BB  (60-75)   High expenditure risk
  B/CCC (75-100) Very high expenditure risk
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger("ilay.eci")

# ── Component weights (equal — no evidence to differentiate) ──────────────

COMPONENT_WEIGHTS = {
    "visit_intensity": 0.25,
    "med_burden": 0.25,
    "diagnostic_intensity": 0.25,
    "trajectory_cost": 0.25,
}

# ── Rating tier boundaries ────────────────────────────────────────────────

ECI_TIERS = [
    (75, "B/CCC", "Very high expenditure risk"),
    (60, "BB", "High expenditure risk"),
    (45, "BBB", "Elevated expenditure risk"),
    (30, "A", "Moderate expenditure risk"),
    (15, "AA", "Low expenditure risk"),
    (0, "AAA", "Minimal expenditure risk"),
]


@dataclass
class ECIResult:
    patient_id: str
    eci_score: float  # [0, 100]
    eci_rating: str  # AAA / AA / A / BBB / BB / B/CCC
    eci_rating_label: str
    # Component scores (each [0, 100])
    visit_intensity: float
    med_burden: float
    diagnostic_intensity: float
    trajectory_cost: float


def _assign_eci_rating(score: float) -> tuple[str, str]:
    """Assign letter rating based on ECI score (higher score = worse rating)."""
    for threshold, rating, label in ECI_TIERS:
        if score >= threshold:
            return rating, label
    return "AAA", "Minimal expenditure risk"


def _percentile_rank(values: np.ndarray) -> np.ndarray:
    """
    Convert raw values to percentile ranks [0, 100].
    Uses average rank for ties. NaN values get 50 (median imputation).
    """
    n = len(values)
    if n == 0:
        return np.array([])

    # Handle NaN: replace with median, rank, then restore
    mask = np.isnan(values)
    clean = values.copy()
    if mask.any():
        median_val = np.nanmedian(values)
        clean[mask] = median_val

    # Rank using argsort-of-argsort (average rank for ties)
    order = clean.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(n, dtype=float)

    # Handle ties: average rank
    sorted_vals = clean[order]
    i = 0
    while i < n:
        j = i
        while j < n and sorted_vals[j] == sorted_vals[i]:
            j += 1
        avg_rank = (i + j - 1) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg_rank
        i = j

    # Convert ranks to percentiles [0, 100]
    return ranks / max(n - 1, 1) * 100.0


# ── Component computation ────────────────────────────────────────────────


def _compute_visit_intensity(
    ana_df: pd.DataFrame,
    patient_ids: list[str],
    ana_group_idx: dict[str, np.ndarray],
) -> dict[str, float]:
    """
    Compute visits per month for each patient.
    Higher = more resource consumption.
    """
    raw: dict[str, float] = {}
    empty_df = ana_df.iloc[0:0]

    for pid in patient_ids:
        idx = ana_group_idx.get(pid)
        patient_ana = ana_df.iloc[idx] if idx is not None else empty_df

        if patient_ana.empty or "visit_date" not in patient_ana.columns:
            raw[pid] = 0.0
            continue

        dates = patient_ana["visit_date"].dropna()
        n_visits = len(dates)
        if n_visits <= 1:
            # Single visit: assume 1 visit in 1 month
            raw[pid] = 1.0
            continue

        span_days = (dates.max() - dates.min()).days
        if span_days <= 0:
            raw[pid] = float(n_visits)  # all same day
        else:
            span_months = max(span_days / 30.0, 0.1)
            raw[pid] = n_visits / span_months

    return raw


def _compute_med_burden(
    rec_df: pd.DataFrame,
    patient_ids: list[str],
    rec_group_idx: dict[str, np.ndarray],
) -> dict[str, float]:
    """
    Compute medication burden: combination of unique drug count
    and prescription change velocity. Higher = more cost.

    Score = 0.5 * unique_drug_count + 0.5 * change_velocity
    Both sub-components are percentile-ranked internally.
    """
    empty_df = rec_df.iloc[0:0]

    drug_counts: dict[str, float] = {}
    change_velocities: dict[str, float] = {}

    for pid in patient_ids:
        idx = rec_group_idx.get(pid)
        patient_recs = rec_df.iloc[idx] if idx is not None else empty_df

        if patient_recs.empty:
            drug_counts[pid] = 0.0
            change_velocities[pid] = 0.0
            continue

        # Unique drug count
        n_drugs = (
            patient_recs["drug_name"].nunique()
            if "drug_name" in patient_recs.columns
            else 0
        )
        drug_counts[pid] = float(n_drugs)

        # Change velocity: unique drugs per month
        if "date" not in patient_recs.columns or patient_recs["date"].isna().all():
            change_velocities[pid] = float(n_drugs)
            continue

        dates = patient_recs["date"].dropna()
        span_days = (dates.max() - dates.min()).days
        if span_days <= 0:
            change_velocities[pid] = float(n_drugs)
        else:
            change_velocities[pid] = n_drugs / max(span_days / 30.0, 0.1)

    # Percentile-rank both sub-components, then average
    pids = list(patient_ids)
    drug_arr = np.array([drug_counts.get(p, 0.0) for p in pids])
    vel_arr = np.array([change_velocities.get(p, 0.0) for p in pids])

    drug_pct = _percentile_rank(drug_arr)
    vel_pct = _percentile_rank(vel_arr)

    combined = 0.5 * drug_pct + 0.5 * vel_pct

    return {pid: float(combined[i]) for i, pid in enumerate(pids)}


def _compute_diagnostic_intensity(
    lab_df: pd.DataFrame,
    patient_ids: list[str],
    lab_group_idx: dict[str, np.ndarray],
    ana_df: pd.DataFrame,
    ana_group_idx: dict[str, np.ndarray],
) -> dict[str, float]:
    """
    Compute lab tests per month for each patient.
    Uses observation span from ana_df (visit dates) as denominator.
    Higher = more diagnostic resource consumption.
    """
    raw: dict[str, float] = {}
    empty_lab = lab_df.iloc[0:0]
    empty_ana = ana_df.iloc[0:0]

    for pid in patient_ids:
        lab_idx = lab_group_idx.get(pid)
        patient_labs = lab_df.iloc[lab_idx] if lab_idx is not None else empty_lab

        n_labs = len(patient_labs)
        if n_labs == 0:
            raw[pid] = 0.0
            continue

        # Use lab date span, falling back to ana_df date span
        span_days = 0
        if "date" in patient_labs.columns:
            lab_dates = patient_labs["date"].dropna()
            if len(lab_dates) > 1:
                span_days = (lab_dates.max() - lab_dates.min()).days

        if span_days <= 0:
            ana_idx = ana_group_idx.get(pid)
            patient_ana = ana_df.iloc[ana_idx] if ana_idx is not None else empty_ana
            if not patient_ana.empty and "visit_date" in patient_ana.columns:
                ana_dates = patient_ana["visit_date"].dropna()
                if len(ana_dates) > 1:
                    span_days = (ana_dates.max() - ana_dates.min()).days

        if span_days <= 0:
            # Single observation point: count as 1 month
            raw[pid] = float(n_labs)
        else:
            span_months = max(span_days / 30.0, 0.1)
            raw[pid] = n_labs / span_months

    return raw


def _compute_trajectory_cost(
    patient_ids: list[str],
    latest_nlp: dict[str, float],
    all_series: dict[str, dict],
) -> dict[str, float]:
    """
    Compute clinical trajectory cost: combination of health index trend
    (declining = expensive) and NLP signal (deterioration = expensive).

    Both sub-components percentile-ranked, then averaged.

    Health trend: negative slope = declining = high cost
    NLP signal: negative score = deterioration = high cost
    """
    # Health index slope: compute linear trend from time series
    health_slopes: dict[str, float] = {}
    for pid in patient_ids:
        series = all_series.get(pid)
        if series is None:
            health_slopes[pid] = 0.0
            continue

        values = series.get("values", [])
        if len(values) < 2:
            health_slopes[pid] = 0.0
            continue

        # Simple linear regression slope
        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)
        mask = ~np.isnan(y)
        if mask.sum() < 2:
            health_slopes[pid] = 0.0
            continue

        x_clean, y_clean = x[mask], y[mask]
        x_mean = x_clean.mean()
        y_mean = y_clean.mean()
        denom = ((x_clean - x_mean) ** 2).sum()
        if denom < 1e-12:
            health_slopes[pid] = 0.0
        else:
            slope = ((x_clean - x_mean) * (y_clean - y_mean)).sum() / denom
            health_slopes[pid] = float(slope)

    # Invert slope: negative slope (declining health) = high cost
    # Map slope to cost: cost = -slope (so declining = positive cost signal)
    pids = list(patient_ids)
    slope_arr = np.array([-health_slopes.get(p, 0.0) for p in pids])
    nlp_arr = np.array([-latest_nlp.get(p, 0.0) for p in pids])

    # Percentile-rank both (higher = more cost)
    slope_pct = _percentile_rank(slope_arr)
    nlp_pct = _percentile_rank(nlp_arr)

    combined = 0.5 * slope_pct + 0.5 * nlp_pct

    return {pid: float(combined[i]) for i, pid in enumerate(pids)}


# ── Main computation ──────────────────────────────────────────────────────


def compute_all_eci(
    ana_df: pd.DataFrame,
    lab_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    latest_nlp: dict[str, float],
    all_series: dict[str, dict],
    patient_ids: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compute ECI for all patients. Returns DataFrame sorted by eci_score descending.

    Columns: patient_id, eci_score, eci_rating, eci_rating_label,
             visit_intensity, med_burden, diagnostic_intensity, trajectory_cost

    Args:
        ana_df: Patient visits DataFrame
        lab_df: Lab results DataFrame
        rec_df: Prescriptions DataFrame
        latest_nlp: {patient_id: nlp_composite} from NLP cache
        all_series: {patient_id: {dates: [...], values: [...]}} health index series
        patient_ids: Optional subset. If None, uses all patients from all_series.
    """
    import time

    t0 = time.perf_counter()

    if patient_ids is None:
        patient_ids = sorted(all_series.keys())

    n = len(patient_ids)
    if n == 0:
        return pd.DataFrame(
            columns=[
                "patient_id",
                "eci_score",
                "eci_rating",
                "eci_rating_label",
                "visit_intensity",
                "med_burden",
                "diagnostic_intensity",
                "trajectory_cost",
            ]
        )

    logger.info("Computing ECI for %d patients...", n)

    # Build group indices for O(1) per-patient lookups
    ana_group_idx: dict[str, np.ndarray] = {}
    if not ana_df.empty and "patient_id" in ana_df.columns:
        ana_group_idx = {
            str(pid): idx
            for pid, idx in ana_df.groupby(
                "patient_id", sort=False, observed=True
            ).groups.items()
        }

    lab_group_idx: dict[str, np.ndarray] = {}
    if not lab_df.empty and "patient_id" in lab_df.columns:
        lab_group_idx = {
            str(pid): idx
            for pid, idx in lab_df.groupby(
                "patient_id", sort=False, observed=True
            ).groups.items()
        }

    rec_group_idx: dict[str, np.ndarray] = {}
    if not rec_df.empty and "patient_id" in rec_df.columns:
        rec_group_idx = {
            str(pid): idx
            for pid, idx in rec_df.groupby(
                "patient_id", sort=False, observed=True
            ).groups.items()
        }

    # ── Compute raw components ────────────────────────────────────────────
    visit_raw = _compute_visit_intensity(ana_df, patient_ids, ana_group_idx)
    med_raw = _compute_med_burden(rec_df, patient_ids, rec_group_idx)
    diag_raw = _compute_diagnostic_intensity(
        lab_df, patient_ids, lab_group_idx, ana_df, ana_group_idx
    )
    traj_raw = _compute_trajectory_cost(patient_ids, latest_nlp, all_series)

    # ── Percentile-rank visit & diagnostic (med & trajectory already ranked) ──
    pids = list(patient_ids)
    visit_arr = np.array([visit_raw.get(p, 0.0) for p in pids])
    diag_arr = np.array([diag_raw.get(p, 0.0) for p in pids])

    visit_pct = _percentile_rank(visit_arr)
    diag_pct = _percentile_rank(diag_arr)

    # Med and trajectory are already percentile-ranked internally
    med_pct = np.array([med_raw.get(p, 50.0) for p in pids])
    traj_pct = np.array([traj_raw.get(p, 50.0) for p in pids])

    # ── Combine into ECI score ────────────────────────────────────────────
    eci_scores = (
        COMPONENT_WEIGHTS["visit_intensity"] * visit_pct
        + COMPONENT_WEIGHTS["med_burden"] * med_pct
        + COMPONENT_WEIGHTS["diagnostic_intensity"] * diag_pct
        + COMPONENT_WEIGHTS["trajectory_cost"] * traj_pct
    )
    eci_scores = np.clip(eci_scores, 0, 100)

    # ── Build results ─────────────────────────────────────────────────────
    rows = []
    for i, pid in enumerate(pids):
        score = float(eci_scores[i])
        rating, label = _assign_eci_rating(score)
        rows.append(
            {
                "patient_id": pid,
                "eci_score": round(score, 2),
                "eci_rating": rating,
                "eci_rating_label": label,
                "visit_intensity": round(float(visit_pct[i]), 2),
                "med_burden": round(float(med_pct[i]), 2),
                "diagnostic_intensity": round(float(diag_pct[i]), 2),
                "trajectory_cost": round(float(traj_pct[i]), 2),
            }
        )

    df = (
        pd.DataFrame(rows)
        .sort_values("eci_score", ascending=False)
        .reset_index(drop=True)
    )

    elapsed = time.perf_counter() - t0
    logger.info(
        "ECI computed for %d patients in %.1fs — mean=%.1f, median=%.1f",
        n,
        elapsed,
        df["eci_score"].mean(),
        df["eci_score"].median(),
    )

    # Log rating distribution
    rating_counts = df["eci_rating"].value_counts()
    for rating in ["AAA", "AA", "A", "BBB", "BB", "B/CCC"]:
        count = rating_counts.get(rating, 0)
        logger.info("  %s: %d (%.1f%%)", rating, count, count / n * 100 if n else 0)

    return df
