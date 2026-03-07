"""
score_apache2.py
Compute APACHE II (Acute Physiology and Chronic Health Evaluation II) score
for all patients.

Vectorized implementation using merge_asof for lab lookback and np.select
for threshold scoring. Handles 1M+ visits x 34M lab rows efficiently.

Original reference:
  Knaus WA, Draper EA, Wagner DP, Zimmerman JE.
  APACHE II: a severity of disease classification system.
  Crit Care Med. 1985;13(10):818-29.
  PMID: 3928249  DOI: 10.1097/00003246-198510000-00009

APACHE II = A (Acute Physiology Score) + B (Age points) + C (Chronic Health points)

Acute Physiology Score (APS) -- 12 parameters (each 0-4 pts):
  Available (7): MAP, HR, Na, K, Creatinine, Hematocrit, WBC
  Unavailable (5): Temperature, RR, Oxygenation, pH, GCS -> 0 pts each

Age (B):  <45->0, 45-54->2, 55-64->3, 65-74->5, >=75->6
Chronic health (C): flags empty in dataset -> 0 pts

Available: 7/12 APS parameters.  Scores are CONSERVATIVE LOWER BOUNDS.

Lab values are matched using a 30-day look-back window (LOCF via merge_asof).

Output files (saved in scripts/results/):
  apache2_per_visit.csv   -- per-visit scores
  apache2_per_patient.csv -- per-patient aggregates + HealthIndex comparison

Usage:
  $ cd /path/to/Acibadem
  $ python scripts/score_apache2.py
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from .data_loader import load_labdata, load_anadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
_log = logging.getLogger(__name__)

LAB_WINDOW_DAYS = 30

# Lab test name substrings -> column names in the merged result
_LAB_TESTS = {
    "Sodyum (Na)": "sodium",
    "Potasyum (K)": "potassium",
    "Kreatinin, Serum": "creatinine",
    "Hematokrit": "hematocrit",
    "Lökosit": "wbc",
}


# ── Vectorized APS sub-score functions ────────────────────────────────────────
# Reference: Knaus et al. Crit Care Med 1985;13:818-29 (Table 1)


def _vec_score_map_apache(sbp: pd.Series, dbp: pd.Series) -> pd.Series:
    """MAP (mmHg). >=160->4, 130-159->3, 110-129->2, 70-109->0, 50-69->2, <=49->4"""
    m = dbp + (sbp - dbp) / 3.0
    v = m.values.astype(float)
    missing = np.isnan(v)
    return pd.Series(
        np.select(
            [missing, v >= 160, v >= 130, v >= 110, v >= 70, v >= 50],
            [0, 4, 3, 2, 0, 2],
            default=4,
        ),
        index=sbp.index,
        dtype="int8",
    )


def _vec_score_hr_apache(vals: pd.Series) -> pd.Series:
    """Heart rate (bpm). >=180->4, 140-179->3, 110-139->2, 70-109->0, 55-69->2, 40-54->3, <=39->4"""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 180, v >= 140, v >= 110, v >= 70, v >= 55, v >= 40],
            [0, 4, 3, 2, 0, 2, 3],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_sodium(vals: pd.Series) -> pd.Series:
    """Serum sodium (mmol/L)."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [
                np.isnan(v),
                v >= 180,
                v >= 160,
                v >= 155,
                v >= 150,
                v >= 130,
                v >= 120,
                v >= 111,
            ],
            [0, 4, 3, 2, 1, 0, 2, 3],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_potassium(vals: pd.Series) -> pd.Series:
    """Serum potassium (mmol/L)."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 7.0, v >= 6.0, v >= 5.5, v >= 3.5, v >= 3.0, v >= 2.5],
            [0, 4, 3, 2, 0, 1, 2],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_creatinine(vals: pd.Series) -> pd.Series:
    """Serum creatinine (mg/dL), without ARF multiplier."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 3.5, v >= 2.0, v >= 1.5, v >= 0.6],
            [0, 4, 3, 2, 0],
            default=2,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_hematocrit(vals: pd.Series) -> pd.Series:
    """Hematocrit (%)."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 60, v >= 50, v >= 46, v >= 30, v >= 20],
            [0, 4, 2, 1, 0, 2],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_wbc(vals: pd.Series) -> pd.Series:
    """WBC (x10^3/uL)."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 40, v >= 20, v >= 15, v >= 3, v >= 1],
            [0, 4, 2, 1, 0, 2],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_age(vals: pd.Series) -> pd.Series:
    """Age (years) -> additional points."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 75, v >= 65, v >= 55, v >= 45],
            [0, 6, 5, 3, 2],
            default=0,
        ),
        index=vals.index,
        dtype="int8",
    )


# ── Lab lookback via merge_asof ───────────────────────────────────────────────


def _merge_lab_to_visits(
    visits: pd.DataFrame,
    lab_df: pd.DataFrame,
    test_substr: str,
    value_col_name: str,
    window_days: int = LAB_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    For each visit, find the most recent lab result (matching test_substr)
    within window_days before the visit date. Uses pd.merge_asof.
    """
    test_name_str = lab_df["test_name"].astype(str)
    mask = test_name_str.str.contains(test_substr, case=False, na=False, regex=False)
    test_labs = lab_df.loc[mask, ["patient_id", "date", "value"]].copy()
    test_labs["patient_id"] = test_labs["patient_id"].astype(str)
    test_labs["date"] = pd.to_datetime(test_labs["date"])
    test_labs = test_labs.rename(columns={"value": value_col_name, "date": "_lab_date"})
    test_labs = test_labs.sort_values("_lab_date").reset_index(drop=True)

    # merge_asof requires the 'on' column to be globally monotonically sorted
    visits_sorted = visits.copy()
    visits_sorted["patient_id"] = visits_sorted["patient_id"].astype(str)
    visits_sorted = visits_sorted.sort_values("visit_date").reset_index(drop=True)

    merged = pd.merge_asof(
        visits_sorted,
        test_labs,
        left_on="visit_date",
        right_on="_lab_date",
        by="patient_id",
        direction="backward",
        tolerance=pd.Timedelta(days=window_days),
    )
    merged = merged.drop(columns=["_lab_date"], errors="ignore")
    return merged


# ── Batch computation (vectorized) ────────────────────────────────────────────


def compute_all_apache2(
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute APACHE II for every patient visit.
    Labs are matched with a 30-day look-back window using merge_asof.
    Scoring uses vectorized np.select.
    """
    _log.info("Preparing visits for APACHE II scoring...")
    vital_cols = ["systolic_bp", "diastolic_bp", "pulse", "age"]
    present_v = [c for c in vital_cols if c in ana_df.columns]
    visits = ana_df[["patient_id", "visit_date"] + present_v].copy()

    # Ensure datetime and numeric types; cast patient_id to plain string
    # (categorical dtypes from data_loader cause merge_asof to fail with
    # mismatched category sets between subsetted DataFrames)
    visits["visit_date"] = pd.to_datetime(visits["visit_date"])
    visits["patient_id"] = visits["patient_id"].astype(str)
    for col in ["systolic_bp", "diastolic_bp", "pulse", "age"]:
        if col in visits.columns:
            visits[col] = pd.to_numeric(visits[col], errors="coerce")

    visits = visits.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)

    # Prepare lab data; plain string patient_id
    lab = lab_df[["patient_id", "test_name", "value", "date"]].copy()
    lab["date"] = pd.to_datetime(lab["date"])
    lab["patient_id"] = lab["patient_id"].astype(str)

    # Merge each lab test type to visits via merge_asof
    _log.info("Matching lab values to visits (merge_asof)...")
    for test_substr, col_name in _LAB_TESTS.items():
        visits = _merge_lab_to_visits(visits, lab, test_substr, col_name)

    # Resolve per-patient age: take median age across visits for each patient
    if "age" in visits.columns:
        patient_age = (
            visits.groupby("patient_id")["age"]
            .median()
            .rename("_patient_age")
            .reset_index()
        )
        visits = visits.merge(patient_age, on="patient_id", how="left")
        visits["age"] = visits["_patient_age"]
        visits = visits.drop(columns=["_patient_age"])

    _log.info("Scoring %d visits...", len(visits))

    # Vectorized APS sub-scores
    sbp = visits.get("systolic_bp", pd.Series(np.nan, index=visits.index))
    dbp = visits.get("diastolic_bp", pd.Series(np.nan, index=visits.index))
    hr = visits.get("pulse", pd.Series(np.nan, index=visits.index))

    visits["apache2_map"] = _vec_score_map_apache(sbp.astype(float), dbp.astype(float))
    visits["apache2_hr"] = _vec_score_hr_apache(hr.astype(float))
    visits["apache2_sodium"] = _vec_score_sodium(visits["sodium"].astype(float))
    visits["apache2_potassium"] = _vec_score_potassium(
        visits["potassium"].astype(float)
    )
    visits["apache2_creatinine"] = _vec_score_creatinine(
        visits["creatinine"].astype(float)
    )
    visits["apache2_hematocrit"] = _vec_score_hematocrit(
        visits["hematocrit"].astype(float)
    )
    visits["apache2_wbc"] = _vec_score_wbc(visits["wbc"].astype(float))

    # Unavailable APS components
    visits["apache2_temp"] = np.nan
    visits["apache2_rr"] = np.nan
    visits["apache2_oxygenation"] = np.nan
    visits["apache2_ph"] = np.nan
    visits["apache2_gcs"] = np.nan

    # APS total (available components)
    visits["apache2_aps"] = (
        visits["apache2_map"]
        + visits["apache2_hr"]
        + visits["apache2_sodium"]
        + visits["apache2_potassium"]
        + visits["apache2_creatinine"]
        + visits["apache2_hematocrit"]
        + visits["apache2_wbc"]
    )

    # Age score
    age_col = (
        visits["age"]
        if "age" in visits.columns
        else pd.Series(np.nan, index=visits.index)
    )
    visits["apache2_age_score"] = _vec_score_age(age_col.astype(float))

    # Chronic health score -> 0 (flags empty in dataset)
    visits["apache2_chronic"] = 0

    # Total
    visits["apache2_total"] = (
        visits["apache2_aps"] + visits["apache2_age_score"] + visits["apache2_chronic"]
    )

    # Predicted mortality (Knaus 1985 logistic model)
    log_odds = -3.517 + visits["apache2_total"].astype(float) * 0.146
    visits["apache2_pred_mort"] = (100.0 / (1.0 + np.exp(-log_odds))).round(1)

    # Clinical tiers
    total = visits["apache2_total"].values
    visits["apache2_tier"] = np.select(
        [total >= 25, total >= 20, total >= 10],
        ["CRITICAL", "SEVERE", "MODERATE"],
        default="LOW",
    )
    visits["apache2_partial"] = True

    result = visits.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)
    _log.info(
        "APACHE II scoring complete: %d visits, %d patients",
        len(result),
        result["patient_id"].nunique(),
    )
    return result


def aggregate_per_patient(visit_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-visit APACHE II to per-patient summary."""
    agg = (
        visit_df.groupby("patient_id", observed=True)["apache2_total"]
        .agg(mean_apache2="mean", max_apache2="max", n_visits="count")
        .reset_index()
    )
    last = (
        visit_df.sort_values("visit_date")
        .groupby("patient_id", observed=True)["apache2_total"]
        .last()
        .rename("last_apache2")
        .reset_index()
    )
    return agg.merge(last, on="patient_id")


def compare_with_health_index(
    per_patient: pd.DataFrame,
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute mean HealthIndex per patient and merge for correlation."""
    from .health_index import HealthIndexBuilder

    health_rows = []
    for pid in per_patient["patient_id"].tolist():
        p_lab = lab_df[lab_df["patient_id"] == pid]
        p_ana = ana_df[ana_df["patient_id"] == pid]
        if p_lab.empty:
            continue
        builder = HealthIndexBuilder(p_lab, p_ana)
        snapshots = builder.build_patient_series(pid)
        if not snapshots:
            continue
        scores = [s.health_score for s in snapshots]
        total_visits = None
        if "total_visits" in ana_df.columns:
            tv = p_ana["total_visits"].dropna()
            total_visits = int(tv.iloc[-1]) if not tv.empty else None
        health_rows.append(
            {
                "patient_id": pid,
                "mean_hi_score": float(np.mean(scores)),
                "last_hi_score": float(scores[-1]),
                "total_visits": total_visits,
            }
        )
    hi_df = pd.DataFrame(health_rows)
    return per_patient.merge(hi_df, on="patient_id", how="left")


def print_correlation_report(combined: pd.DataFrame) -> None:
    """Print Spearman correlation + availability summary."""
    print("\n" + "=" * 65)
    print("APACHE II vs HealthIndex — Spearman Correlation Report")
    print("=" * 65)
    pairs = [
        ("mean_apache2", "mean_hi_score", "Mean APACHE II  ↔  Mean HealthIndex"),
        ("max_apache2", "mean_hi_score", "Max APACHE II   ↔  Mean HealthIndex"),
        ("last_apache2", "last_hi_score", "Last APACHE II  ↔  Last HealthIndex"),
    ]
    if "total_visits" in combined.columns:
        pairs += [("mean_apache2", "total_visits", "Mean APACHE II  ↔  Total Visits")]

    for col_a, col_b, label in pairs:
        valid = combined[[col_a, col_b]].dropna()
        if len(valid) < 3:
            print(f"  {label}: insufficient data (n={len(valid)})")
            continue
        try:
            r, p = spearmanr(valid[col_a], valid[col_b])
        except Exception:
            r, p = float("nan"), float("nan")
        if np.isnan(r):
            print(f"  {label}")
            print(f"    ρ = undefined (constant input — no score variation in sample)")
            continue
        sig = (
            "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "(n.s.)"
        )
        note = "← negative expected" if "hi_score" in col_b else ""
        print(f"  {label}")
        print(f"    ρ = {r:+.3f}, p = {p:.4f} {sig}  n={len(valid)}  {note}")

    print()
    print("Available APACHE II APS parameters in this dataset:")
    print("  ✔  Mean arterial pressure  — anadata KB-S + KB-D")
    print("  ✔  Heart rate              — anadata Nabız")
    print("  ✔  Serum Na (mmol/L)       — labdata Sodyum (Na)")
    print("  ✔  Serum K  (mmol/L)       — labdata Potasyum (K)")
    print("  ✔  Creatinine (mg/dL)      — labdata Kreatinin, Serum")
    print("  ✔  Hematocrit (%)           — labdata Hematokrit")
    print("  ✔  WBC (x10^3/uL)          — labdata Lökosit")
    print("  ✔  Age (years)             — anadata [age score, not APS]")
    print("  ✗  Temperature             — NOT in dataset → 0 pts")
    print("  ✗  Respiratory rate        — NOT in dataset → 0 pts")
    print("  ✗  Oxygenation (PaO2/AaDO2)— NOT in dataset → 0 pts")
    print("  ✗  Arterial pH             — NOT in dataset → 0 pts")
    print("  ✗  GCS (15-score)          — NOT in dataset → 0 pts (GCS=15)")
    print("  ✗  Chronic health pts      — Flags empty in dataset → 0 pts")
    print()
    print("⚠  7 of 12 APS parameters available; predicted mortality is")
    print("   a conservative lower bound. ARF multiplier (x2 creatinine)")
    print("   not applied — cannot detect acute renal failure from data.")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results_dir = ROOT / "scripts" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    _log.info("Loading data …")
    lab_df = load_labdata()
    ana_df = load_anadata()

    _log.info("Computing APACHE II per visit …")
    visit_scores = compute_all_apache2(lab_df, ana_df)
    _log.info(
        "  %d visits scored across %d patients",
        len(visit_scores),
        visit_scores["patient_id"].nunique(),
    )

    per_patient = aggregate_per_patient(visit_scores)

    _log.info("Computing HealthIndex scores for correlation …")
    combined = compare_with_health_index(per_patient, lab_df, ana_df)

    visit_out = results_dir / "apache2_per_visit.csv"
    patient_out = results_dir / "apache2_per_patient.csv"
    visit_scores.to_csv(visit_out, index=False)
    combined.to_csv(patient_out, index=False)
    _log.info("Saved → %s", visit_out)
    _log.info("Saved → %s", patient_out)

    print("\n── APACHE II Per-Patient Summary ──")
    print(
        combined[
            [
                "patient_id",
                "mean_apache2",
                "max_apache2",
                "last_apache2",
                "mean_hi_score",
                "last_hi_score",
            ]
        ].to_string(index=False)
    )

    print_correlation_report(combined)
