"""
score_news2.py
Compute National Early Warning Score 2 (NEWS2) for all patients.

Vectorized implementation using np.select for threshold scoring.
Handles 1M+ visits efficiently without iterrows.

Reference:
  Royal College of Physicians. National Early Warning Score (NEWS) 2:
  Standardising the assessment of acute-illness severity in the NHS.
  London: RCP, 2017.  ISBN: 978-1-86016-724-1
  https://www.rcplondon.ac.uk/projects/outputs/national-early-warning-score-news-2

NEWS2 assesses 7 physiological parameters (each scored 0–3):
  1.  Respiratory Rate     — NOT AVAILABLE in this dataset → assumed 0 pts
  2.  SpO2 (Scale 1)       — from anadata SPO2 column           [AVAILABLE]
  3.  Supplemental O2      — NOT AVAILABLE → assumed 0 pts (breathing air)
  4.  Systolic BP          — from anadata KB-S column            [AVAILABLE]
  5.  Pulse (HR)           — from anadata Nabız column           [AVAILABLE]
  6.  Level of consciousness (ACVPU) — NOT AVAILABLE → assumed Alert (0 pts)
  7.  Temperature          — NOT AVAILABLE → assumed 0 pts

Scoring is therefore partial (3 of 7 parameters). The computed score represents a
CONSERVATIVE LOWER BOUND — true NEWS2 is >= the values shown here.

Risk stratification (full NEWS2 scale):
  0–4   Low risk
  5–6   Medium risk  (or any single score = 3)
  >=7   High risk

Output files (saved in scripts/results/):
  news2_per_visit.csv   — per-visit scores (one row per patient x visit)
  news2_per_patient.csv — per-patient aggregate + comparison with HealthIndex

Usage:
  $ cd /path/to/Acibadem
  $ python scripts/score_news2.py
"""

from __future__ import annotations

import sys
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ── project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_labdata, load_anadata

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
_log = logging.getLogger(__name__)

# ── Vectorized NEWS2 scoring ──────────────────────────────────────────────────
# Reference: RCP NEWS2 chart, 2017


def _vec_score_spo2(vals: pd.Series) -> pd.Series:
    """SpO2 Scale 1 (no supplemental O2, no hypercapnic drive target)."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 96, v >= 94, v >= 92],
            [0, 0, 1, 2],
            default=3,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_sbp(vals: pd.Series) -> pd.Series:
    """Systolic blood pressure scoring."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v >= 220, v >= 111, v >= 101, v >= 91],
            [0, 3, 0, 1, 2],
            default=3,
        ),
        index=vals.index,
        dtype="int8",
    )


def _vec_score_pulse(vals: pd.Series) -> pd.Series:
    """Heart rate / pulse scoring."""
    v = vals.values.astype(float)
    return pd.Series(
        np.select(
            [np.isnan(v), v <= 40, v <= 50, v <= 90, v <= 110, v <= 130],
            [0, 3, 1, 0, 1, 2],
            default=3,
        ),
        index=vals.index,
        dtype="int8",
    )


# ── Batch computation (vectorized) ────────────────────────────────────────────


def compute_all_news2(ana_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute NEWS2 for every visit in anadata where at least one vital is present.
    Uses vectorized np.select — no iterrows.

    Returns a DataFrame with columns:
      patient_id, visit_date, systolic_bp, diastolic_bp, pulse, spo2,
      news2_*, news2_total, news2_risk
    """
    vital_cols = ["systolic_bp", "diastolic_bp", "pulse", "spo2"]
    present = [c for c in vital_cols if c in ana_df.columns]
    working = (
        ana_df[["patient_id", "visit_date"] + present]
        .dropna(how="all", subset=present)
        .copy()
    )

    _log.info("Scoring %d visits for NEWS2...", len(working))

    # Ensure float types for scoring
    for col in ["systolic_bp", "pulse", "spo2"]:
        if col in working.columns:
            working[col] = pd.to_numeric(working[col], errors="coerce")

    # Vectorized component scores
    spo2_col = (
        working["spo2"]
        if "spo2" in working.columns
        else pd.Series(np.nan, index=working.index)
    )
    sbp_col = (
        working["systolic_bp"]
        if "systolic_bp" in working.columns
        else pd.Series(np.nan, index=working.index)
    )
    hr_col = (
        working["pulse"]
        if "pulse" in working.columns
        else pd.Series(np.nan, index=working.index)
    )

    working["news2_spo2"] = _vec_score_spo2(spo2_col)
    working["news2_sbp"] = _vec_score_sbp(sbp_col)
    working["news2_hr"] = _vec_score_pulse(hr_col)

    # Unavailable components — fixed values
    working["news2_rr"] = np.nan  # respiratory rate — not in data
    working["news2_temp"] = np.nan  # temperature — not in data
    working["news2_o2"] = 0  # supplemental O2 — assumed air
    working["news2_avpu"] = 0  # consciousness — assumed Alert

    # Total (available components only)
    working["news2_total"] = (
        working["news2_spo2"] + working["news2_sbp"] + working["news2_hr"]
    )

    # Risk stratification (vectorized)
    total = working["news2_total"].values
    max_single = np.maximum(
        np.maximum(working["news2_spo2"].values, working["news2_sbp"].values),
        working["news2_hr"].values,
    )
    working["news2_risk"] = np.select(
        [total >= 7, (total >= 5) | (max_single == 3)],
        ["HIGH", "MEDIUM"],
        default="LOW",
    )
    working["news2_partial"] = True

    result = working.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)
    _log.info(
        "NEWS2 scoring complete: %d visits, %d patients",
        len(result),
        result["patient_id"].nunique(),
    )
    return result


def aggregate_per_patient(visit_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate per-visit NEWS2 scores to per-patient summaries.
      - mean_news2, max_news2, last_news2 (most recent visit)
    """
    agg = (
        visit_df.groupby("patient_id", observed=True)["news2_total"]
        .agg(mean_news2="mean", max_news2="max", n_visits="count")
        .reset_index()
    )
    # Last value: sort by date and take tail
    last = (
        visit_df.sort_values("visit_date")
        .groupby("patient_id", observed=True)["news2_total"]
        .last()
        .rename("last_news2")
        .reset_index()
    )
    return agg.merge(last, on="patient_id")


def compare_with_health_index(
    per_patient: pd.DataFrame,
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute mean HealthIndex score per patient and merge for correlation analysis.
    """
    from src.health_index import HealthIndexBuilder

    all_pids = per_patient["patient_id"].tolist()
    health_rows = []

    for pid in all_pids:
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
    """Print Spearman correlation between NEWS2 and HealthIndex."""
    print("\n" + "=" * 65)
    print("NEWS2 vs HealthIndex — Spearman Correlation Report")
    print("=" * 65)

    pairs = [
        ("mean_news2", "mean_hi_score", "Mean NEWS2  ↔  Mean HealthIndex"),
        ("max_news2", "mean_hi_score", "Max NEWS2   ↔  Mean HealthIndex"),
        ("last_news2", "last_hi_score", "Last NEWS2  ↔  Last HealthIndex"),
    ]
    if "total_visits" in combined.columns:
        pairs += [
            ("mean_news2", "total_visits", "Mean NEWS2  ↔  Total Visits"),
        ]

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
        note = (
            "(negative expected: HIGH NEWS2 = LOW HealthIndex)"
            if "hi_score" in col_b
            else ""
        )
        print(f"  {label}")
        print(f"    ρ = {r:+.3f}, p = {p:.4f} {sig}  n={len(valid)}  {note}")

    print()
    print("Available parameters in NEWS2 computation:")
    print("  ✔  SpO2 (Scale 1)         — anadata SPO2")
    print("  ✔  Systolic BP            — anadata KB-S")
    print("  ✔  Heart rate / Pulse     — anadata Nabız")
    print("  ✗  Respiratory rate       — NOT in dataset → 0 pts assumed")
    print("  ✗  Temperature            — NOT in dataset → 0 pts assumed")
    print("  ✗  Supplemental O2 flag   — NOT in dataset → 'air' assumed")
    print("  ✗  Consciousness (ACVPU)  — NOT in dataset → Alert assumed")
    print()
    print("⚠  Scores are a conservative lower bound (3 of 7 parameters).")
    print("=" * 65 + "\n")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results_dir = ROOT / "scripts" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    _log.info("Loading data …")
    lab_df = load_labdata()
    ana_df = load_anadata()

    _log.info("Computing NEWS2 per visit …")
    visit_scores = compute_all_news2(ana_df)
    _log.info(
        "  %d visits scored across %d patients",
        len(visit_scores),
        visit_scores["patient_id"].nunique(),
    )

    per_patient = aggregate_per_patient(visit_scores)

    _log.info("Computing HealthIndex scores for correlation …")
    combined = compare_with_health_index(per_patient, lab_df, ana_df)

    # ── Save outputs ──────────────────────────────────────────────────────────
    visit_out = results_dir / "news2_per_visit.csv"
    patient_out = results_dir / "news2_per_patient.csv"
    visit_scores.to_csv(visit_out, index=False)
    combined.to_csv(patient_out, index=False)
    _log.info("Saved → %s", visit_out)
    _log.info("Saved → %s", patient_out)

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n── NEWS2 Per-Patient Summary ──")
    print(
        combined[
            [
                "patient_id",
                "mean_news2",
                "max_news2",
                "last_news2",
                "mean_hi_score",
                "last_hi_score",
            ]
        ].to_string(index=False)
    )

    print_correlation_report(combined)
