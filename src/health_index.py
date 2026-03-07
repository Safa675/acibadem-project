"""
health_index.py
HealthIndexBuilder — converts lab results + vitals into a scalar health score.

Strategy:
  - Labs: z-score each test vs embedded reference range.
    Abnormality = |z| (distance from normal, both directions).
  - Vitals: similarly normalized using clinical reference ranges.
  - Composite health score = 100 - (weighted mean abnormality, scaled to 0-100)
    100 = perfectly normal, 0 = maximally abnormal across all measured parameters.

Two execution modes:
  1. build_patient_series(pid)       — single patient (legacy, for on-demand queries)
  2. build_all_patients_bulk()       — ALL patients via vectorised numpy/pandas (Phase 4)
     Processes 196K patients / 34M lab rows in <30s instead of >10h.

The score is a SeriesPoint list used across all analytical modules.
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import NamedTuple

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Reference ranges for vitals
# Source: NexGene AI Medical Reasoning API (asa-mini model, queried 2026-03-07)
#
# DROPPED (2026-03): pulse and SpO2 removed from active scoring.
#   - pulse:  96.7% missing across 196K visit rows — near-zero signal
#   - SpO2:   99.7% missing (only 540 rows) — effectively absent
#   Blood pressure remains at ~20% coverage — the only vital with meaningful data.
# ---------------------------------------------------------------------------

VITAL_REFERENCE_RANGES: dict[str, tuple[float, float]] = {
    # (normal_min, normal_max)
    "systolic_bp": (90.0, 119.0),  # mmHg; NexGene AI
    "diastolic_bp": (75.0, 84.0),  # mmHg; NexGene AI
}

# ---------------------------------------------------------------------------
# Fallback biochemical reference intervals
# Source: NexGene AI Medical Reasoning API (asa-mini model, queried 2026-03-07)
#   Model: Medical Reasoning Foundational Model v0.4.132
#   Previously: Ozarda 2014 (PMID 25153598) — replaced with NexGene AI ranges
#
# These are used ONLY when the hospital data row has NaN REFMIN/REFMAX.
# Priority: hospital-supplied ranges > these fallback values.
#
# Units (SI):
#   Enzymes                  U/L
#   Electrolytes / metabolites  mmol/L
#   Creatinine / uric acid   μmol/L
#   Proteins / albumin       g/L
#   Bilirubin                μmol/L
# ---------------------------------------------------------------------------
NEXGENE_REFERENCE_RANGES: dict[str, tuple[float, float]] = {
    # keyword (case-insensitive substring match) → (lower_limit, upper_limit)
    # --- Proteins ---
    "Albumin": (35.0, 50.0),  # g/L; NexGene AI
    "Protein": (60.0, 80.0),  # g/L; total protein, NexGene AI
    # --- Renal ---
    "Üre": (1.8, 7.1),  # mmol/L; BUN, NexGene AI
    "Kreatinin": (41.0, 111.0),  # μmol/L; NexGene AI
    "Ürik Asit": (137.0, 488.0),  # μmol/L; NexGene AI
    # --- Bilirubin ---
    "Bilirubin": (0.0, 21.0),  # μmol/L; total bilirubin, NexGene AI
    # --- Metabolic ---
    "Glukoz": (3.9, 6.1),  # mmol/L; fasting glucose, NexGene AI
    "Kolesterol": (3.5, 5.2),  # mmol/L; total cholesterol, NexGene AI
    "Trigliserid": (0.6, 1.69),  # mmol/L; NexGene AI
    "LDL": (0.97, 4.91),  # mmol/L; LDL cholesterol, NexGene AI
    "HDL": (1.0, 1.2),  # mmol/L; HDL cholesterol, NexGene AI
    # --- Electrolytes ---
    "Sodyum": (135.0, 145.0),  # mmol/L; NexGene AI
    "Potasyum": (3.3, 5.1),  # mmol/L; NexGene AI
    "Klor": (96.0, 106.0),  # mmol/L; NexGene AI
    "Kalsiyum": (2.2, 2.6),  # mmol/L; NexGene AI
    "Fosfor": (0.8, 1.45),  # mmol/L; inorganic phosphate, NexGene AI
    "Magnezyum": (0.7, 1.0),  # mmol/L; NexGene AI
    # --- Liver enzymes ---
    "ALT": (19.0, 25.0),  # U/L; NexGene AI
    "AST": (10.0, 44.0),  # U/L; NexGene AI
    "ALP": (55.0, 150.0),  # U/L; NexGene AI
    "GGT": (5.0, 40.0),  # U/L; NexGene AI
    # --- Other enzymes ---
    "LDH": (105.0, 280.0),  # U/L; NexGene AI
    "Amilaz": (30.0, 110.0),  # U/L; amylase, NexGene AI
    # NOTE: CRP, WBC, Hemoglobin, Platelets, HbA1c, TSH, INR, PT, aPTT are
    # not covered — those rely on the hospital's own REFMIN/REFMAX.
}

# Organ system groupings for weighted health index
# (test name substring → organ system)
ORGAN_SYSTEM_KEYWORDS: dict[str, str] = {
    "CRP": "inflammatory",
    "Lökosit": "inflammatory",
    "Nötrofil": "inflammatory",
    "Lenfosit": "inflammatory",
    "Bazofil": "inflammatory",
    "Eozinofil": "inflammatory",
    "Monosit": "inflammatory",
    "Prokalsitonin": "inflammatory",
    "Kreatinin": "renal_organ",
    "Üre": "renal_organ",
    "GFR": "renal_organ",
    # Hepatic (bilirubin + liver enzymes) — distinct from renal per SOFA scoring
    "Bilirubin": "hepatic",
    "ALT": "hepatic",
    "AST": "hepatic",
    "ALP": "hepatic",
    "GGT": "hepatic",
    "Hemoglobin": "hematological",
    "Hematokrit": "hematological",
    "Eritrosit": "hematological",
    "Trombosit": "hematological",
    "MCV": "hematological",
    "MCH": "hematological",
    "RDW": "hematological",
    "Glukoz": "metabolic",
    "HbA1c": "metabolic",
    "Kolesterol": "metabolic",
    "Trigliserid": "metabolic",
    "LDL": "metabolic",
    "HDL": "metabolic",
    "Sodyum": "metabolic",
    "Potasyum": "metabolic",
    "Kalsiyum": "metabolic",
    "Albumin": "metabolic",
    "Protein": "metabolic",
    "TSH": "endocrine",
    "T3": "endocrine",
    "T4": "endocrine",
    "INR": "coagulation",
    "PT": "coagulation",
    "aPTT": "coagulation",
}

ORGAN_WEIGHTS: dict[str, float] = {
    # Equal weighting — consistent with SOFA / NEWS2 / APACHE II
    # which treat organ systems with uniform importance.
    "inflammatory": 0.125,
    "renal_organ": 0.125,
    "hepatic": 0.125,
    "hematological": 0.125,
    "metabolic": 0.125,
    "endocrine": 0.125,
    "coagulation": 0.125,
    "other": 0.125,
    # Sum = 1.00
}


@dataclass
class SeriesPoint:
    """Shared SeriesPoint dataclass used across all analytical modules."""

    date: str
    value: float


class HealthSnapshot(NamedTuple):
    date: pd.Timestamp
    health_score: float
    n_labs: int
    has_vitals: bool
    dominant_organ_system: str | None
    data_completeness: float  # [0.0-1.0] fraction of signal sources available


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


class HealthIndexBuilder:
    """
    Build a dynamic health score time-series for a single patient.

    Usage:
        builder = HealthIndexBuilder(lab_df, ana_df)
        snapshots = builder.build_patient_series(patient_id=100643634)
        series = builder.to_series_points(snapshots)
    """

    def __init__(
        self,
        lab_df: pd.DataFrame,
        ana_df: pd.DataFrame,
        vital_weight: float = 0.40,  # weight for vitals vs labs
        *,
        lab_groups: dict[str, pd.DataFrame] | None = None,
        ana_groups: dict[str, pd.DataFrame] | None = None,
    ):
        self.lab_df = lab_df
        self.ana_df = ana_df
        self.vital_weight = vital_weight
        self.lab_weight = 1.0 - vital_weight
        # Pre-grouped DataFrames for O(1) patient lookups (avoids N+1 scans)
        self._lab_groups = lab_groups
        self._ana_groups = ana_groups

    # ------------------------------------------------------------------
    # Lab scoring
    # ------------------------------------------------------------------

    def _lab_z_score(
        self,
        value: float,
        ref_min: float,
        ref_max: float,
        test_name: str = "",
    ) -> float:
        """
        Compute absolute z-score from reference range.
        Higher |z| = more abnormal.
        ref_mean and ref_std derived from min/max (assumes ±2σ spans the range).

        When REFMIN/REFMAX are missing from the hospital data, falls back to
        NEXGENE_REFERENCE_RANGES (NexGene AI Medical Reasoning API).
        """
        # Fallback to NexGene AI reference ranges when hospital data lacks ranges
        if (pd.isna(ref_min) or pd.isna(ref_max) or ref_max <= ref_min) and test_name:
            for keyword, (lo, hi) in NEXGENE_REFERENCE_RANGES.items():
                if keyword.lower() in test_name.lower():
                    ref_min, ref_max = lo, hi
                    break
        if pd.isna(ref_min) or pd.isna(ref_max) or ref_max <= ref_min:
            return 0.0  # no reference data available — exclude from scoring
        ref_std = (ref_max - ref_min) / 4.0  # 95% interval = ±2σ
        # Only penalise values that are OUTSIDE the reference range.
        # abs(z from midpoint) would incorrectly score low-floor tests
        # (e.g. CRP=0 is perfectly healthy but midpoint-z gives |z|=2).
        if value < ref_min:
            return (ref_min - value) / ref_std  # below range
        elif value > ref_max:
            return (value - ref_max) / ref_std  # above range
        else:
            return 0.0  # within range = healthy

    def _classify_test(self, test_name: str) -> str:
        """Map test name to organ system."""
        for keyword, system in ORGAN_SYSTEM_KEYWORDS.items():
            if keyword.lower() in test_name.lower():
                return system
        return "other"

    def _score_labs_on_date(
        self, patient_labs: pd.DataFrame, date: pd.Timestamp
    ) -> tuple[float, str | None]:
        """
        For labs drawn on or before `date`, compute organ-weighted abnormality score.
        Returns (score [0-100], dominant organ system).
        """
        # Use labs on this exact date (one draw = one day in hospital outpatient setting)
        day_labs = patient_labs[patient_labs["date"] == date].copy()
        if day_labs.empty:
            return 0.0, None

        # Classify each test
        day_labs = day_labs.copy()
        day_labs["organ_system"] = day_labs["test_name"].apply(self._classify_test)
        day_labs["z_score"] = day_labs.apply(
            lambda row: self._lab_z_score(
                row["value"], row["ref_min"], row["ref_max"], row["test_name"]
            ),
            axis=1,
        )

        # Warn about tests with no reference range — tracked explicitly, not via z==0
        # (z==0 now means the value is within range, i.e. healthy — not "no reference")
        def _has_ref_range(row: pd.Series) -> bool:
            rim, rax = row["ref_min"], row["ref_max"]
            if not (pd.isna(rim) or pd.isna(rax) or rax <= rim):
                return True  # hospital-supplied range present
            name = row["test_name"]
            return any(kw.lower() in name.lower() for kw in NEXGENE_REFERENCE_RANGES)

        day_labs["has_ref_range"] = day_labs.apply(_has_ref_range, axis=1)
        n_no_ref = int((~day_labs["has_ref_range"]).sum())
        n_total = len(day_labs)
        if n_no_ref > n_total * 0.5 and n_total > 0:
            invisible_tests = day_labs.loc[
                ~day_labs["has_ref_range"], "test_name"
            ].tolist()
            _logger.warning(
                "%d/%d tests on %s have no reference range and score 0 (invisible): %s",
                n_no_ref,
                n_total,
                date,
                invisible_tests[:5],
            )

        # Aggregate by organ system — mean z-score per system
        system_scores: dict[str, float] = {}
        for system, group in day_labs.groupby("organ_system"):
            system_scores[system] = group["z_score"].mean()

        if not system_scores:
            return 0.0, None

        # Weighted aggregate
        total_weight = 0.0
        weighted_sum = 0.0
        for system, score in system_scores.items():
            w = ORGAN_WEIGHTS.get(system, ORGAN_WEIGHTS["other"])
            weighted_sum += score * w
            total_weight += w

        mean_z = weighted_sum / total_weight if total_weight > 0 else 0.0
        dominant = max(system_scores, key=system_scores.get)

        # Convert to health score: z=0 → 100, z=2 → 60, z=4 → 20, z≥6 → 0
        # health = 100 * exp(-0.25 * mean_z)  (soft decay)
        lab_score = 100.0 * np.exp(-0.25 * mean_z)
        return float(np.clip(lab_score, 0, 100)), dominant

    # ------------------------------------------------------------------
    # Vital scoring
    # ------------------------------------------------------------------

    def _score_vitals_on_date(
        self, patient_vitals: pd.DataFrame, date: pd.Timestamp
    ) -> float:
        """
        Score vitals from the visit closest to `date`.
        Returns health score [0-100] from vitals, or NaN if no usable vitals.
        """
        if patient_vitals.empty:
            return float("nan")  # no data → signal absence (not "healthy")

        # ONLY use vitals from on or before the scoring date (no future leakage)
        past_vitals = patient_vitals[patient_vitals["date"] <= date]
        if past_vitals.empty:
            return float("nan")  # no past vitals available

        # Find nearest past visit (within 30 days)
        time_diffs = date - past_vitals["date"]  # all non-negative
        nearest_idx = time_diffs.idxmin()
        nearest_gap = time_diffs[nearest_idx]

        if nearest_gap > pd.Timedelta(days=30):
            return float("nan")  # too far away to use

        vital_row = past_vitals.loc[nearest_idx]
        z_scores = []

        for vital, (ref_min, ref_max) in VITAL_REFERENCE_RANGES.items():
            v = vital_row.get(vital)
            if v is not None and not pd.isna(v):
                ref_std = (ref_max - ref_min) / 4.0
                # Only penalise values OUTSIDE the reference range
                # (same logic as _lab_z_score — avoids penalising healthy values)
                if float(v) < ref_min:
                    z = (ref_min - float(v)) / ref_std
                elif float(v) > ref_max:
                    z = (float(v) - ref_max) / ref_std
                else:
                    z = 0.0  # within range = healthy
                z_scores.append(z)

        if not z_scores:
            return float("nan")  # vital row exists but all values are NaN

        mean_z = np.mean(z_scores)
        return float(np.clip(100.0 * np.exp(-0.25 * mean_z), 0, 100))

    # ------------------------------------------------------------------
    # Patient series builder
    # ------------------------------------------------------------------

    def build_patient_series(self, patient_id: str) -> list[HealthSnapshot]:
        """
        Build health score time-series for one patient.
        Each snapshot corresponds to a unique lab draw date or vital visit date.
        """
        from .data_loader import get_patient_labs, get_patient_vitals

        # Use pre-grouped data if available (O(1) lookup), else fall back to full scan
        if self._lab_groups is not None:
            patient_labs = self._lab_groups.get(patient_id, pd.DataFrame()).copy()
            if not patient_labs.empty:
                patient_labs = patient_labs.sort_values("date")
        else:
            patient_labs = get_patient_labs(self.lab_df, patient_id)

        if self._ana_groups is not None:
            _ana_patient = self._ana_groups.get(patient_id, pd.DataFrame())
            if _ana_patient.empty or "visit_date" not in _ana_patient.columns:
                patient_vitals = pd.DataFrame(columns=["date"])
            else:
                # get_patient_vitals extracts vital columns; replicate that here
                from .data_loader import _ANA_VITAL_COLS

                vital_cols = [
                    c for c in _ANA_VITAL_COLS.keys() if c in _ana_patient.columns
                ]
                cols = ["visit_date"] + vital_cols
                patient_vitals = _ana_patient[
                    [c for c in cols if c in _ana_patient.columns]
                ].copy()
                if vital_cols and not patient_vitals.empty:
                    patient_vitals = patient_vitals.dropna(how="all", subset=vital_cols)
                patient_vitals = patient_vitals.rename(
                    columns={"visit_date": "date"}
                ).reset_index(drop=True)
        else:
            patient_vitals = get_patient_vitals(self.ana_df, patient_id)

        # Collect all unique dates from both sources
        dates: set[pd.Timestamp] = set()
        if "date" in patient_labs.columns:
            for d in patient_labs["date"].dropna():
                dates.add(pd.Timestamp(d).normalize())
        if "date" in patient_vitals.columns:
            for d in patient_vitals["date"].dropna():
                dates.add(pd.Timestamp(d).normalize())

        if not dates:
            return []

        # Align labs to dates
        patient_labs = patient_labs.copy()
        patient_labs["date"] = patient_labs["date"].apply(
            lambda d: pd.Timestamp(d).normalize()
        )
        patient_vitals = patient_vitals.copy()
        patient_vitals["date"] = patient_vitals["date"].apply(
            lambda d: pd.Timestamp(d).normalize()
        )

        snapshots: list[HealthSnapshot] = []
        for date in sorted(dates):
            lab_score, dominant = self._score_labs_on_date(patient_labs, date)
            vital_score = self._score_vitals_on_date(patient_vitals, date)

            has_labs = not patient_labs[patient_labs["date"] == date].empty
            has_vitals = not np.isnan(vital_score)

            if has_labs and has_vitals:
                composite = (
                    self.lab_weight * lab_score + self.vital_weight * vital_score
                )
            elif has_labs:
                composite = lab_score
            else:
                composite = vital_score  # vitals-only date (rare)

            n_labs = int(patient_labs[patient_labs["date"] == date].shape[0])
            completeness = (0.5 if has_labs else 0.0) + (0.5 if has_vitals else 0.0)
            snapshots.append(
                HealthSnapshot(
                    date=date,
                    health_score=round(composite, 2),
                    n_labs=n_labs,
                    has_vitals=has_vitals,
                    dominant_organ_system=dominant,
                    data_completeness=completeness,
                )
            )

        return snapshots

    def to_series_points(self, snapshots: list[HealthSnapshot]) -> list[SeriesPoint]:
        """Convert snapshots to SeriesPoint list for VaR and analytics modules."""
        return [
            SeriesPoint(date=snap.date.strftime("%Y-%m-%d"), value=snap.health_score)
            for snap in snapshots
        ]

    def to_dataframe(self, snapshots: list[HealthSnapshot]) -> pd.DataFrame:
        """Convert snapshots to DataFrame for analysis."""
        return pd.DataFrame(
            [
                {
                    "date": s.date,
                    "health_score": s.health_score,
                    "n_labs": s.n_labs,
                    "has_vitals": s.has_vitals,
                    "dominant_organ_system": s.dominant_organ_system,
                }
                for s in snapshots
            ]
        )

    # ==================================================================
    # Phase 4: Bulk vectorised computation for ALL patients at once
    # ==================================================================

    @staticmethod
    def _build_test_organ_map(unique_tests: np.ndarray) -> dict[str, str]:
        """Map each unique test name → organ system (one-time, ~2600 lookups)."""
        lower_keywords = [
            (kw.lower(), sys) for kw, sys in ORGAN_SYSTEM_KEYWORDS.items()
        ]
        result: dict[str, str] = {}
        for test_name in unique_tests:
            tn_lower = test_name.lower()
            matched = "other"
            for kw_lower, sys in lower_keywords:
                if kw_lower in tn_lower:
                    matched = sys
                    break
            result[test_name] = matched
        return result

    @staticmethod
    def _build_nexgene_fallback_map(
        unique_tests: np.ndarray,
    ) -> dict[str, tuple[float, float]]:
        """Map each unique test name → NexGene AI fallback (ref_min, ref_max)."""
        lower_nexgene = [
            (kw.lower(), lo, hi) for kw, (lo, hi) in NEXGENE_REFERENCE_RANGES.items()
        ]
        result: dict[str, tuple[float, float]] = {}
        for test_name in unique_tests:
            tn_lower = test_name.lower()
            for kw_lower, lo, hi in lower_nexgene:
                if kw_lower in tn_lower:
                    result[test_name] = (lo, hi)
                    break
        return result

    @staticmethod
    def _build_has_ref_map(
        unique_tests: np.ndarray,
        nexgene_map: dict[str, tuple[float, float]],
    ) -> dict[str, bool]:
        """Map each unique test name → whether NexGene has a fallback for it."""
        return {tn: tn in nexgene_map for tn in unique_tests}

    def _vectorised_lab_scores(self, lab_df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute per-(patient, date) lab health scores for ALL patients at once.

        Returns DataFrame with columns:
            patient_id, date_norm, lab_score, n_labs, dominant_organ_system
        """
        import time as _time

        t0 = _time.perf_counter()

        # --- Work on a copy with normalised dates ---
        df = lab_df[
            ["patient_id", "date", "test_name", "value", "ref_min", "ref_max"]
        ].copy()
        df["date_norm"] = df["date"].dt.normalize()

        # --- Step 1: Precompute lookup maps from unique test names (once) ---
        unique_tests = df["test_name"].unique()
        test_organ_map = self._build_test_organ_map(unique_tests)
        nexgene_map = self._build_nexgene_fallback_map(unique_tests)
        has_ref_map = self._build_has_ref_map(unique_tests, nexgene_map)

        _logger.info(
            "Precomputed maps for %d unique tests (organ: %d matched, nexgene: %d fallbacks)",
            len(unique_tests),
            sum(1 for v in test_organ_map.values() if v != "other"),
            len(nexgene_map),
        )

        # --- Step 2: Vectorised organ system classification ---
        df["organ_system"] = df["test_name"].map(test_organ_map)

        # --- Step 3: Fill missing ref ranges from NexGene AI fallback ---
        # Build Series-aligned fallback arrays
        nexgene_min = df["test_name"].map(
            lambda tn: nexgene_map[tn][0] if tn in nexgene_map else np.nan
        )
        nexgene_max = df["test_name"].map(
            lambda tn: nexgene_map[tn][1] if tn in nexgene_map else np.nan
        )
        needs_fallback = (
            df["ref_min"].isna()
            | df["ref_max"].isna()
            | (df["ref_max"] <= df["ref_min"])
        )
        df.loc[needs_fallback, "ref_min"] = nexgene_min[needs_fallback]
        df.loc[needs_fallback, "ref_max"] = nexgene_max[needs_fallback]

        # --- Step 4: Vectorised z-score computation (numpy, no Python loops) ---
        value = df["value"].values.astype(np.float64)
        rmin = df["ref_min"].values.astype(np.float64)
        rmax = df["ref_max"].values.astype(np.float64)
        ref_std = np.maximum((rmax - rmin) / 4.0, 1e-9)

        z = np.where(
            value < rmin,
            (rmin - value) / ref_std,
            np.where(value > rmax, (value - rmax) / ref_std, 0.0),
        )
        # Where ref range is still invalid (NaN or max <= min after fallback), z = 0
        invalid = np.isnan(rmin) | np.isnan(rmax) | (rmax <= rmin)
        z[invalid] = 0.0
        df["z_score"] = z

        t1 = _time.perf_counter()
        _logger.info(
            "Vectorised z-scores computed for %d rows in %.2fs", len(df), t1 - t0
        )

        # --- Step 5: Organ-weighted aggregation per (patient, date) ---
        organ_weight_map = {
            sys: ORGAN_WEIGHTS.get(sys, ORGAN_WEIGHTS["other"])
            for sys in set(test_organ_map.values())
        }
        df["organ_weight"] = df["organ_system"].map(organ_weight_map)

        # Per (patient, date, organ_system): mean z-score and weight
        system_agg = (
            df.groupby(["patient_id", "date_norm", "organ_system"], observed=True)
            .agg(
                mean_z=("z_score", "mean"),
                organ_weight=("organ_weight", "first"),
            )
            .reset_index()
        )

        # Weighted mean z per (patient, date) — avoiding apply() with manual vectorisation
        system_agg["wz"] = system_agg["mean_z"] * system_agg["organ_weight"]
        daily_agg = (
            system_agg.groupby(["patient_id", "date_norm"], observed=True)
            .agg(
                sum_wz=("wz", "sum"),
                sum_w=("organ_weight", "sum"),
            )
            .reset_index()
        )
        daily_agg["mean_z"] = daily_agg["sum_wz"] / daily_agg["sum_w"].clip(lower=1e-9)
        daily_agg["lab_score"] = (100.0 * np.exp(-0.25 * daily_agg["mean_z"])).clip(
            0, 100
        )

        # Dominant organ system per (patient, date) — the system with highest mean_z
        dominant_idx = system_agg.groupby(["patient_id", "date_norm"], observed=True)[
            "mean_z"
        ].idxmax()
        dominant_map = system_agg.loc[
            dominant_idx, ["patient_id", "date_norm", "organ_system"]
        ]
        dominant_map = dominant_map.rename(
            columns={"organ_system": "dominant_organ_system"}
        )

        # Lab count per (patient, date)
        lab_counts = (
            df.groupby(["patient_id", "date_norm"], observed=True)
            .size()
            .reset_index(name="n_labs")
        )

        # Merge all lab results into one DataFrame
        result = (
            daily_agg[["patient_id", "date_norm", "lab_score"]]
            .merge(lab_counts, on=["patient_id", "date_norm"], how="left")
            .merge(dominant_map, on=["patient_id", "date_norm"], how="left")
        )

        # --- Step 6: Reference range coverage warning ---
        df["has_ref"] = df["test_name"].map(has_ref_map)
        # Only flag rows that ALSO have invalid hospital ranges
        no_ref_mask = needs_fallback & ~df["has_ref"]
        n_no_ref = int(no_ref_mask.sum())
        if n_no_ref > 0:
            pct = n_no_ref / len(df) * 100
            _logger.warning(
                "%d rows (%.1f%%) have no reference range (hospital or NexGene) — scored as z=0",
                n_no_ref,
                pct,
            )

        t2 = _time.perf_counter()
        _logger.info(
            "Lab scores aggregated for %d (patient, date) pairs in %.2fs",
            len(result),
            t2 - t1,
        )
        return result

    def _vectorised_vital_scores(
        self, ana_df: pd.DataFrame, lab_dates: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute vital scores for each (patient, date) pair from lab_dates.

        Vitals are 85-99% missing, so this is inherently fast. We still vectorise
        the matching logic to avoid per-patient Python loops.

        Parameters:
            ana_df: Full anadata DataFrame (with visit_date, vitals columns)
            lab_dates: DataFrame with columns [patient_id, date_norm] — the dates
                       we need vital scores for.

        Returns DataFrame with columns:
            patient_id, date_norm, vital_score, has_vitals
        """
        from .data_loader import _ANA_VITAL_COLS

        vital_cols = [c for c in _ANA_VITAL_COLS.keys() if c in ana_df.columns]

        if not vital_cols or "visit_date" not in ana_df.columns:
            # No vitals available at all — return NaN (absence, not "healthy")
            result = lab_dates[["patient_id", "date_norm"]].copy()
            result["vital_score"] = np.nan
            result["has_vitals"] = False
            return result

        # Extract vital rows with at least one non-null vital
        vitals = ana_df[["patient_id", "visit_date"] + vital_cols].copy()
        vitals = vitals.dropna(subset=vital_cols, how="all")

        if vitals.empty:
            result = lab_dates[["patient_id", "date_norm"]].copy()
            result["vital_score"] = np.nan
            result["has_vitals"] = False
            return result

        vitals["date_norm"] = vitals["visit_date"].dt.normalize()

        # Compute z-scores for each vital using vectorised numpy
        z_cols = []
        for vital_name, (ref_min, ref_max) in VITAL_REFERENCE_RANGES.items():
            if vital_name not in vitals.columns:
                continue
            v = vitals[vital_name].values.astype(np.float64)
            ref_std = (ref_max - ref_min) / 4.0
            z = np.where(
                v < ref_min,
                (ref_min - v) / ref_std,
                np.where(v > ref_max, (v - ref_max) / ref_std, 0.0),
            )
            z[np.isnan(v)] = np.nan  # preserve NaN for missing vitals
            col_name = f"z_{vital_name}"
            vitals[col_name] = z
            z_cols.append(col_name)

        if not z_cols:
            result = lab_dates[["patient_id", "date_norm"]].copy()
            result["vital_score"] = np.nan
            result["has_vitals"] = False
            return result

        # Mean z across available vitals per row
        vitals["mean_z"] = vitals[z_cols].mean(axis=1, skipna=True)
        vitals["vital_score"] = (100.0 * np.exp(-0.25 * vitals["mean_z"])).clip(0, 100)

        # For each (patient, date_norm) in lab_dates, find the nearest past vital
        # within 30 days. Use merge_asof for efficient temporal matching.
        vitals_sorted = (
            vitals[["patient_id", "date_norm", "vital_score"]]
            .dropna(subset=["vital_score"])
            .sort_values("date_norm")
        )
        lab_sorted = lab_dates[["patient_id", "date_norm"]].sort_values("date_norm")

        # Cast patient_id to str on both sides — categorical dtypes from
        # different parquets (lab vs ana) have incompatible category sets
        # which causes MergeError in merge_asof.
        vitals_sorted["patient_id"] = vitals_sorted["patient_id"].astype(str)
        lab_sorted["patient_id"] = lab_sorted["patient_id"].astype(str)

        if vitals_sorted.empty:
            result = lab_dates[["patient_id", "date_norm"]].copy()
            result["vital_score"] = np.nan
            result["has_vitals"] = False
            return result

        merged = pd.merge_asof(
            lab_sorted,
            vitals_sorted,
            on="date_norm",
            by="patient_id",
            direction="backward",
            tolerance=pd.Timedelta(days=30),
        )

        merged["has_vitals"] = merged["vital_score"].notna()
        # vital_score stays NaN when no match — composite logic will use labs-only

        # Also flag exact-date vitals matches (has_vitals means vitals ON that date)
        # Build set of (patient_id, date_norm) where vitals actually exist
        exact_vital_dates = set(zip(vitals["patient_id"], vitals["date_norm"]))
        merged["has_vitals_exact"] = [
            (pid, d) in exact_vital_dates
            for pid, d in zip(merged["patient_id"], merged["date_norm"])
        ]

        return merged[
            ["patient_id", "date_norm", "vital_score", "has_vitals", "has_vitals_exact"]
        ]

    def build_all_patients_bulk(
        self,
        patient_ids: list[str] | None = None,
    ) -> tuple[dict[str, list[HealthSnapshot]], dict[str, list[SeriesPoint]]]:
        """
        Vectorised bulk computation of health scores for ALL patients.

        Replaces the per-patient loop:
            for pid in patients:
                snaps = builder.build_patient_series(pid)

        Returns:
            (all_snapshots, all_series) — same structure as the loop above.
        """
        import time as _time

        t0 = _time.perf_counter()

        # --- 1. Compute vectorised lab scores ---
        lab_df = self.lab_df
        if patient_ids is not None:
            lab_df = lab_df[lab_df["patient_id"].isin(set(patient_ids))]

        lab_result = self._vectorised_lab_scores(lab_df)

        # --- 2. Compute vectorised vital scores ---
        # Unique (patient, date) pairs from lab results
        lab_dates = lab_result[["patient_id", "date_norm"]].copy()
        # Normalise patient_id to str — parquets store categorical with
        # different category sets (lab 196K vs ana 49K), causing merge errors.
        lab_dates["patient_id"] = lab_dates["patient_id"].astype(str)

        # Also collect vital-only dates from anadata
        ana_df = self.ana_df
        if patient_ids is not None:
            ana_df = ana_df[ana_df["patient_id"].isin(set(patient_ids))]

        # Add vital-only dates (visits without labs)
        if "visit_date" in ana_df.columns:
            vital_dates = ana_df[["patient_id", "visit_date"]].copy()
            vital_dates["patient_id"] = vital_dates["patient_id"].astype(str)
            vital_dates["date_norm"] = vital_dates["visit_date"].dt.normalize()
            vital_dates = vital_dates[["patient_id", "date_norm"]].drop_duplicates()
            all_dates = pd.concat([lab_dates, vital_dates]).drop_duplicates(
                subset=["patient_id", "date_norm"]
            )
        else:
            all_dates = lab_dates

        vital_result = self._vectorised_vital_scores(ana_df, all_dates)

        t1 = _time.perf_counter()
        _logger.info("Vital scores computed in %.2fs", t1 - t0)

        # --- 3. Merge lab + vital scores ---
        # Left join: every (patient, date) gets a lab score and/or vital score
        merged = all_dates.merge(
            lab_result, on=["patient_id", "date_norm"], how="left"
        ).merge(
            vital_result[["patient_id", "date_norm", "vital_score", "has_vitals"]],
            on=["patient_id", "date_norm"],
            how="left",
        )

        # Determine data availability per row
        has_lab = merged["lab_score"].notna()
        has_vital = merged["has_vitals"].fillna(False)
        merged["lab_score"] = merged["lab_score"].fillna(0.0)
        # vital_score stays NaN when absent — no inflation default
        merged["n_labs"] = merged["n_labs"].fillna(0).astype(int)
        merged["dominant_organ_system"] = merged["dominant_organ_system"].fillna("")

        # Composite score: adaptive weighting based on data availability
        #   - Both labs + vitals → weighted composite (uses 30-day lookback vitals)
        #   - Labs only         → pure lab score (no vital inflation)
        #   - Vitals only       → pure vital score
        composite = np.where(
            has_lab & has_vital,
            self.lab_weight * merged["lab_score"]
            + self.vital_weight * merged["vital_score"],
            np.where(has_lab, merged["lab_score"], merged["vital_score"]),
        )
        merged["health_score"] = np.round(composite, 2)

        # Data completeness: fraction of signal sources available per row
        merged["data_completeness"] = (
            has_lab.astype(float) * 0.5 + has_vital.astype(float) * 0.5
        )

        # Filter out rows with no data at all (no labs AND no vitals)
        has_any = has_lab | has_vital
        merged = merged[has_any].copy()

        t2 = _time.perf_counter()
        _logger.info("Merged %d (patient, date) rows in %.2fs", len(merged), t2 - t1)

        # --- 4. Convert to per-patient dicts of HealthSnapshot + SeriesPoint ---
        all_snapshots: dict[str, list[HealthSnapshot]] = {}
        all_series: dict[str, list[SeriesPoint]] = {}

        # Sort by (patient, date) for correct time-series ordering
        merged = merged.sort_values(["patient_id", "date_norm"])

        # Iterate over groups — this is O(N_rows) not O(N_patients × N_dates)
        for pid, group in merged.groupby("patient_id", observed=True):
            snaps: list[HealthSnapshot] = []
            pts: list[SeriesPoint] = []
            for _, row in group.iterrows():
                snap = HealthSnapshot(
                    date=row["date_norm"],
                    health_score=float(row["health_score"]),
                    n_labs=int(row["n_labs"]),
                    has_vitals=bool(row.get("has_vitals", False)),
                    dominant_organ_system=(
                        row["dominant_organ_system"]
                        if row["dominant_organ_system"]
                        else None
                    ),
                    data_completeness=float(row.get("data_completeness", 0.5)),
                )
                snaps.append(snap)
                pts.append(
                    SeriesPoint(
                        date=row["date_norm"].strftime("%Y-%m-%d"),
                        value=float(row["health_score"]),
                    )
                )
            if snaps:
                all_snapshots[str(pid)] = snaps
                all_series[str(pid)] = pts

        t3 = _time.perf_counter()
        _logger.info(
            "Built snapshots for %d patients in %.2fs (total bulk: %.2fs)",
            len(all_snapshots),
            t3 - t2,
            t3 - t0,
        )

        return all_snapshots, all_series
