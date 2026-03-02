"""
health_index.py
HealthIndexBuilder — converts lab results + vitals into a scalar health score.

Strategy:
  - Labs (from labdata.ods): z-score each test vs embedded reference range.
    Abnormality = |z| (distance from normal, both directions).
  - Vitals (from anadata.ods): similarly normalized using clinical reference ranges.
  - Composite health score = 100 - (weighted mean abnormality, scaled to 0-100)
    100 = perfectly normal, 0 = maximally abnormal across all measured parameters.

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
# Reference ranges for vitals (clinical standards, sex-neutral)
# Sources:
#   - Blood pressure: WHO ISH 2020 guidelines; ESH/ESC 2018 (normal < 130/85)
#   - Pulse (resting HR): standard clinical range 60-100 bpm
#   - SpO2: normal ≥ 95% (WHO / standard pulse oximetry guidelines)
#
# NOTE: Ozarda 2014 (PMID 25153598) is a pure SERUM BIOCHEMISTRY paper covering 25
# analytes (proteins, electrolytes, metabolites, enzymes). It contains NO vital-sign
# data — blood pressure, pulse, and SpO2 are NOT in that paper.
# ---------------------------------------------------------------------------

VITAL_REFERENCE_RANGES: dict[str, tuple[float, float]] = {
    # (normal_min, normal_max)
    "systolic_bp": (90.0, 130.0),  # mmHg; WHO ISH 2020 / ESH 2018 normal range
    "diastolic_bp": (60.0, 85.0),  # mmHg; WHO ISH 2020 / ESH 2018 normal range
    "pulse": (60.0, 100.0),  # bpm;  standard clinical resting HR
    "spo2": (95.0, 100.0),  # %;    WHO / pulse oximetry normal
}

# ---------------------------------------------------------------------------
# Fallback biochemical reference intervals — Turkish population
# Source: Ozarda Y et al., Table 4 & 6 (parametric method, 2.5th–97.5th percentile)
#   Clin Chem Lab Med. 2014 Dec;52(12):1823-33.
#   PMID: 25153598  |  DOI: https://doi.org/10.1515/cclm-2014-0228
#   PubMed: https://pubmed.ncbi.nlm.nih.gov/25153598/
#
# These are used ONLY when the hospital data row has NaN REFMIN/REFMAX.
# Priority: hospital-supplied ranges > these fallback values.
#
# Sex-neutralisation strategy: when the paper gives sex-specific limits,
# the female lower-limit and male upper-limit are used to create the widest
# plausible sex-neutral interval (conservative — avoids false alarms).
#
# Units match the paper's SI reporting:
#   Enzymes                  U/L
#   Electrolytes / metabolites  mmol/L
#   Creatinine / uric acid   μmol/L
#   Proteins / albumin       g/L
#   Bilirubin                μmol/L
# ---------------------------------------------------------------------------
OZARDA_2014_REFERENCE_RANGES: dict[str, tuple[float, float]] = {
    # keyword (case-insensitive substring match) → (lower_limit, upper_limit)
    # --- Proteins ---
    "Albumin": (41.0, 49.0),  # g/L; Table 6 combined, ages 20–60
    # (covers both 'Albumin' in data; Albümin variant removed — no match in SUB_CODE)
    "Protein": (66.0, 82.0),  # g/L; TP, Table 6 combined
    # --- Renal ---
    "Üre": (2.9, 7.2),  # mmol/L; BUN, males <50 (wider)
    "Kreatinin": (50.0, 92.0),  # μmol/L; female LL (50), male UL (92)
    "Ürik Asit": (
        166.0,
        458.0,
    ),  # μmol/L; female LL, male UL  (data col is 'Ürik Asit'; ASCII variant removed — no match)
    # --- Bilirubin ---
    "Bilirubin": (2.7, 24.1),  # μmol/L; total, female LL, male UL
    # --- Metabolic ---
    "Glukoz": (3.96, 5.88),  # mmol/L; strict BMI criteria, Table 6
    # (data uses 'Glukoz'; Glikoz variant removed — no match in SUB_CODE)
    "Kolesterol": (3.2, 6.45),  # mmol/L; total cholesterol, age <50 combined
    "Trigliserid": (
        0.46,
        3.55,
    ),  # mmol/L; female LL, ≥50 male UL (widest)  # FIX: data SUB_CODE is 'Trigliserid' not 'Trigliserit'
    "LDL": (1.32, 3.92),  # mmol/L; age <50, female LL, male UL
    "HDL": (0.85, 1.56),  # mmol/L; male LL, female UL (sex-neutral)
    # --- Electrolytes ---
    "Sodyum": (137.0, 144.0),  # mmol/L; Table 6 combined
    "Potasyum": (3.7, 4.9),  # mmol/L; Table 6 combined
    "Klor": (99.0, 107.0),  # mmol/L; Table 6 combined
    "Kalsiyum": (2.15, 2.47),  # mmol/L; Table 6 combined
    "Fosfor": (0.80, 1.40),  # mmol/L; inorganic phosphate, combined
    "Magnezyum": (0.77, 1.06),  # mmol/L; Mg, Table 6 combined
    # --- Liver enzymes ---
    "ALT": (7.0, 44.0),  # U/L; strict criteria male UL (44); female ~22
    "AST": (11.0, 30.0),  # U/L; female LL (11), male UL (30)
    "ALP": (34.0, 116.0),  # U/L; age <50, female LL (34), male UL (116)
    "GGT": (7.0, 69.0),  # U/L; female LL (7), male UL (69)
    # --- Other enzymes ---
    "LDH": (126.0, 220.0),  # U/L; Table 6 combined
    "Amilaz": (34.0, 119.0),  # U/L; AMY, Table 6 combined
    # (data uses 'Amilaz'; Amylaz variant removed — no match in SUB_CODE)
    # NOTE: CRP, WBC, Hemoglobin, Platelets, HbA1c, TSH, INR, PT, aPTT are
    # NOT in the Ozarda 2014 paper — those rely on the hospital's own REFMIN/REFMAX.
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
    # Evidence-based revision — see docs/PARAMETER_EVIDENCE_REPORT.md
    # References: SOFA (PMID 8844239), APACHE II (PMID 3928249),
    #             Parviainen et al. Acta Anaesth Scand 2022 (PMID 35579938)
    "inflammatory": 0.25,  # CRP/WBC — strong early-warning signal
    "renal_organ": 0.18,  # creatinine, urea, GFR only (hepatic split out below)
    "hepatic": 0.12,  # ALT, AST, ALP, GGT, bilirubin — SOFA hepatic component
    "hematological": 0.18,  # Hb/RBC indices
    "metabolic": 0.17,  # electrolytes, glucose, albumin
    "endocrine": 0.02,  # thyroid markers
    "coagulation": 0.07,  # INR, PT, aPTT — SOFA coagulation component
    "other": 0.01,
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
    ):
        self.lab_df = lab_df
        self.ana_df = ana_df
        self.vital_weight = vital_weight
        self.lab_weight = 1.0 - vital_weight

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
        OZARDA_2014_REFERENCE_RANGES (Turkish population, PMID 25153598).
        """
        # Fallback to Ozarda 2014 Turkish population RIs when hospital data lacks ranges
        if (pd.isna(ref_min) or pd.isna(ref_max) or ref_max <= ref_min) and test_name:
            for keyword, (lo, hi) in OZARDA_2014_REFERENCE_RANGES.items():
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
            return any(
                kw.lower() in name.lower() for kw in OZARDA_2014_REFERENCE_RANGES
            )

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
        Returns health score [0-100] from vitals.
        """
        if patient_vitals.empty:
            return 100.0  # unknown → assume normal (conservative)

        # ONLY use vitals from on or before the scoring date (no future leakage)
        past_vitals = patient_vitals[patient_vitals["date"] <= date]
        if past_vitals.empty:
            return 100.0  # no past vitals available

        # Find nearest past visit (within 30 days)
        time_diffs = date - past_vitals["date"]  # all non-negative
        nearest_idx = time_diffs.idxmin()
        nearest_gap = time_diffs[nearest_idx]

        if nearest_gap > pd.Timedelta(days=30):
            return 100.0  # too far away to use

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
            return 100.0

        mean_z = np.mean(z_scores)
        return float(np.clip(100.0 * np.exp(-0.25 * mean_z), 0, 100))

    # ------------------------------------------------------------------
    # Patient series builder
    # ------------------------------------------------------------------

    def build_patient_series(self, patient_id: int) -> list[HealthSnapshot]:
        """
        Build health score time-series for one patient.
        Each snapshot corresponds to a unique lab draw date or vital visit date.
        """
        from .data_loader import get_patient_labs, get_patient_vitals

        patient_labs = get_patient_labs(self.lab_df, patient_id)
        patient_vitals = get_patient_vitals(self.ana_df, patient_id)

        # Collect all unique dates from both sources
        dates: set[pd.Timestamp] = set()
        for d in patient_labs["date"].dropna():
            dates.add(pd.Timestamp(d).normalize())
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
            has_vitals = not patient_vitals[patient_vitals["date"] == date].empty

            if has_labs and has_vitals:
                composite = (
                    self.lab_weight * lab_score + self.vital_weight * vital_score
                )
            elif has_labs:
                composite = lab_score
            else:
                composite = vital_score

            n_labs = int(patient_labs[patient_labs["date"] == date].shape[0])
            snapshots.append(
                HealthSnapshot(
                    date=date,
                    health_score=round(composite, 2),
                    n_labs=n_labs,
                    has_vitals=has_vitals,
                    dominant_organ_system=dominant,
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
