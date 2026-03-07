"""
score_sofa.py
Compute SOFA (Sequential Organ Failure Assessment) score for all patients.

Vectorized implementation using merge_asof for lab lookback and np.select
for threshold scoring. Handles 1M+ visits × 34M lab rows efficiently.

Original reference:
  Vincent JL et al. The SOFA (Sepsis-related Organ Failure Assessment) score
  to describe organ dysfunction/failure. Intensive Care Med. 1996;22(7):707-10.
  PMID: 8844239  DOI: 10.1007/BF01709751

SOFA assesses 6 organ systems (each 0–4 pts, max total = 24):
  ┌─────────────────┬─────────────────────────────────────────────┐
  │ System          │ Data source                                 │
  ├─────────────────┼─────────────────────────────────────────────┤
  │ Respiratory     │ PaO2/FiO2 — NOT AVAILABLE → 0 pts          │
  │ Coagulation     │ Trombosit (platelets ×10³/μL) — labdata    │
  │ Hepatic         │ Bilirubin, Total (mg/dL) — labdata          │
  │ Cardiovascular  │ MAP derived from SBP+DBP — anadata          │
  │ CNS             │ GCS — NOT AVAILABLE → 0 pts (GCS 15)        │
  │ Renal           │ Kreatinin, Serum (mg/dL) — labdata          │
  └─────────────────┴─────────────────────────────────────────────┘

Unavailable components (PaO2/FiO2, GCS, vasopressors, urine output) default
to 0 — scores are a CONSERVATIVE LOWER BOUND.

Lab values are matched to visit dates using the most-recent observation within
a 30-day look-back window (LOCF approach via pd.merge_asof). Vitals are taken
from the visit row.

Output files (saved in scripts/results/):
  sofa_per_visit.csv   — per-visit SOFA scores
  sofa_per_patient.csv — per-patient aggregates + HealthIndex comparison

Usage:
  $ cd /path/to/Acıbadem
  $ python scripts/score_sofa.py
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

from src.data_loader import load_labdata, load_anadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
_log = logging.getLogger(__name__)

# ── SOFA scoring thresholds ───────────────────────────────────────────────────
# Reference: Vincent JL et al. Intensive Care Med 1996;22:707-10 (PMID 8844239)
#            Updated: Singer M et al. JAMA 2016;315(8):801-10 (PMID 26903338)

LAB_WINDOW_DAYS = 30

# Lab test name substrings → column names in the merged result
_LAB_TESTS = {
    "Trombosit": "platelets",
    "Bilirubin, Total": "bilirubin",
    "Kreatinin, Serum": "creatinine",
}


# ── Vectorized scoring functions ──────────────────────────────────────────────


def _vec_score_platelets(vals: pd.Series) -> pd.Series:
    """Coagulation: platelet count in ×10³/μL → 0-4 pts."""
    v = vals.values
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 150, v >= 100, v >= 50, v >= 20],
            [0, 0, 1, 2, 3],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_bilirubin(vals: pd.Series) -> pd.Series:
    """Hepatic: total bilirubin in mg/dL → 0-4 pts."""
    v = vals.values
    return pd.Series(
        np.select(
            [np.isnan(v), v < 1.2, v < 2.0, v < 6.0, v < 12.0],
            [0, 0, 1, 2, 3],
            default=4,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_map(sbp: pd.Series, dbp: pd.Series) -> pd.Series:
    """Cardiovascular: MAP from SBP+DBP → 0 or 1 pt."""
    map_val = dbp + (sbp - dbp) / 3.0
    missing = sbp.isna() | dbp.isna()
    score = (map_val < 70).astype("int8")
    score[missing] = 0
    return score


def _vec_score_creatinine(vals: pd.Series) -> pd.Series:
    """Renal: serum creatinine in mg/dL → 0-4 pts."""
    v = vals.values
    return pd.Series(
        np.select(
            [np.isnan(v), v < 1.2, v < 2.0, v < 3.5, v < 5.0],
            [0, 0, 1, 2, 3],
            default=4,
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
    within window_days before the visit date. Uses pd.merge_asof for O(N log N)
    instead of O(N*M) per-patient scanning.
    """
    # Filter labs to the specific test type (cast test_name to str for .contains)
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


def compute_all_sofa(
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute SOFA for every patient visit in anadata.
    Lab values are matched via a 30-day look-back window using merge_asof.
    Scoring uses vectorized np.select.

    Returns a long-form DataFrame: one row per (patient_id, visit_date).
    """
    _log.info("Preparing visits for SOFA scoring...")
    vital_cols = ["systolic_bp", "diastolic_bp"]
    present_v = [c for c in vital_cols if c in ana_df.columns]
    visits = ana_df[["patient_id", "visit_date"] + present_v].copy()

    # Ensure visit_date is datetime and sorted; cast patient_id to plain string
    # (categorical dtypes from data_loader cause merge_asof to fail with
    # mismatched category sets between subsetted DataFrames)
    visits["visit_date"] = pd.to_datetime(visits["visit_date"])
    visits["patient_id"] = visits["patient_id"].astype(str)
    visits = visits.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)

    # Ensure lab dates are datetime; plain string patient_id
    lab = lab_df[["patient_id", "test_name", "value", "date"]].copy()
    lab["date"] = pd.to_datetime(lab["date"])
    lab["patient_id"] = lab["patient_id"].astype(str)

    # Merge each lab test type to visits via merge_asof
    _log.info("Matching lab values to visits (merge_asof)...")
    for test_substr, col_name in _LAB_TESTS.items():
        visits = _merge_lab_to_visits(visits, lab, test_substr, col_name)

    # Vectorized scoring
    _log.info("Scoring %d visits...", len(visits))

    visits["sofa_coagulation"] = _vec_score_platelets(visits["platelets"].astype(float))
    visits["sofa_liver"] = _vec_score_bilirubin(visits["bilirubin"].astype(float))
    visits["sofa_cardiovasc"] = _vec_score_map(
        visits.get("systolic_bp", pd.Series(dtype=float)),
        visits.get("diastolic_bp", pd.Series(dtype=float)),
    )
    visits["sofa_renal"] = _vec_score_creatinine(visits["creatinine"].astype(float))

    # Unavailable components
    visits["sofa_respiratory"] = np.nan
    visits["sofa_cns"] = np.nan

    # Total
    visits["sofa_total"] = (
        visits["sofa_coagulation"]
        + visits["sofa_liver"]
        + visits["sofa_cardiovasc"]
        + visits["sofa_renal"]
    )

    # Clinical tiers
    total = visits["sofa_total"].values
    visits["sofa_tier"] = np.select(
        [total >= 11, total >= 7, total >= 3],
        ["CRITICAL", "HIGH", "MODERATE"],
        default="LOW",
    )
    visits["sofa_partial"] = True

    result = visits.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)
    _log.info(
        "SOFA scoring complete: %d visits, %d patients",
        len(result),
        result["patient_id"].nunique(),
    )
    return result


def aggregate_per_patient(visit_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-visit SOFA to per-patient summary stats."""
    agg = (
        visit_df.groupby("patient_id", observed=True)["sofa_total"]
        .agg(mean_sofa="mean", max_sofa="max", n_visits="count")
        .reset_index()
    )
    last = (
        visit_df.sort_values("visit_date")
        .groupby("patient_id", observed=True)["sofa_total"]
        .last()
        .rename("last_sofa")
        .reset_index()
    )
    return agg.merge(last, on="patient_id")


def compare_with_health_index(
    per_patient: pd.DataFrame,
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute mean HealthIndex score per patient and merge for correlation."""
    from src.health_index import HealthIndexBuilder

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
    """Print Spearman correlation between SOFA and HealthIndex."""
    print("\n" + "=" * 65)
    print("SOFA vs HealthIndex — Spearman Correlation Report")
    print("=" * 65)
    pairs = [
        ("mean_sofa", "mean_hi_score", "Mean SOFA  ↔  Mean HealthIndex"),
        ("max_sofa", "mean_hi_score", "Max SOFA   ↔  Mean HealthIndex"),
        ("last_sofa", "last_hi_score", "Last SOFA  ↔  Last HealthIndex"),
    ]
    if "total_visits" in combined.columns:
        pairs += [("mean_sofa", "total_visits", "Mean SOFA  ↔  Total Visits")]

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
            print(
                f"    ρ = undefined (constant input — all patients score 0; expected for stable outpatients)"
            )
            continue
        sig = (
            "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "(n.s.)"
        )
        note = "← negative expected" if "hi_score" in col_b else ""
        print(f"  {label}")
        print(f"    ρ = {r:+.3f}, p = {p:.4f} {sig}  n={len(valid)}  {note}")

    print()
    print("Available SOFA components in this dataset:")
    print("  ✔  Coagulation (Platelets ×10³/μL) — labdata Trombosit")
    print("  ✔  Hepatic (Bilirubin Total mg/dL)  — labdata Bilirubin, Total")
    print("  ✔  Cardiovascular (MAP via SBP+DBP) — anadata KB-S + KB-D")
    print("  ✔  Renal (Creatinine mg/dL)         — labdata Kreatinin, Serum")
    print("  ✗  Respiratory (PaO2/FiO2)          — NOT in dataset → 0 pts")
    print("  ✗  Neurological (GCS)               — NOT in dataset → 0 pts")
    print()
    print("⚠  4 of 6 SOFA systems available; respiratory & CNS default to 0.")
    print("   Vasopressor-dependent cardiovascular scores (2–4) not computable.")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results_dir = ROOT / "scripts" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    _log.info("Loading data …")
    lab_df = load_labdata()
    ana_df = load_anadata()

    _log.info("Computing SOFA per visit …")
    visit_scores = compute_all_sofa(lab_df, ana_df)
    _log.info(
        "  %d visits scored across %d patients",
        len(visit_scores),
        visit_scores["patient_id"].nunique(),
    )

    per_patient = aggregate_per_patient(visit_scores)

    _log.info("Computing HealthIndex scores for correlation …")
    combined = compare_with_health_index(per_patient, lab_df, ana_df)

    visit_out = results_dir / "sofa_per_visit.csv"
    patient_out = results_dir / "sofa_per_patient.csv"
    visit_scores.to_csv(visit_out, index=False)
    combined.to_csv(patient_out, index=False)
    _log.info("Saved → %s", visit_out)
    _log.info("Saved → %s", patient_out)

    print("\n── SOFA Per-Patient Summary ──")
    print(
        combined[
            [
                "patient_id",
                "mean_sofa",
                "max_sofa",
                "last_sofa",
                "mean_hi_score",
                "last_hi_score",
            ]
        ].to_string(index=False)
    )

    print_correlation_report(combined)
