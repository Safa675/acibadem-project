"""
data_loader.py
Parquet-based data loading for the ACUHIT 2 dataset.

Source files (in .cache/):
  acuhit2_lab_from2025.parquet      — lab results (2025+ subset)
  acuhit2_anadata_from2025.parquet  — visit records (2025+ subset)
  acuhit2_recete_from2025.parquet   — prescriptions (2025+ subset)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeAlias

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).parent.parent  # Acıbadem/
_CACHE_DIR = _BASE_DIR / ".cache"

# Type alias — patient IDs are strings in ACUHIT 2 (ANON_XXXXXX format)
PatientId: TypeAlias = str

# ---------------------------------------------------------------------------
# Column lists for selective Parquet loading (column pruning)
# ---------------------------------------------------------------------------

_LAB_COLUMNS = [
    "patient_id",
    "test_name",
    "value",
    "unit",
    "ref_min",
    "ref_max",
    "date",
    "cohort",
]

# Pipeline-relevant anadata columns (~25 of 62)
_ANA_COLUMNS = [
    "patient_id",
    "visit_date",
    "age",
    "sex",
    # Vitals
    "systolic_bp",
    "diastolic_bp",
    "pulse",
    "spo2",
    # Outcomes
    "los_days",
    "total_visits",
    "visit_num",
    # Text columns (for NLP)
    "ÖYKÜ",
    "YAKINMA",
    "Muayene Notu",
    "Kontrol Notu",
    "Tedavi Notu",
    # Comorbidity flags (Parquet names → will be renamed to pipeline names)
    "Hipertansiyon",
    "Kalp Damar",
    "Diyabet",
    "Kan Hastaliklari",
    "Kronik Hastaliklar Diger",
    "Ameliyat Gecmisi",
    # Demographics / metadata
    "Boy",
    "Kilo",
    "BMI",
    "TANIKODU",
    "SERVISADI",
    "TUM_EPS_TANILAR",
    "Ritmik/ Aritmik",
    "Sigara",
    "Alkol",
    "Ozgecmis Notu",
    "SQ_EPISODE",
    # Cohort tag
    "cohort",
]

_REC_COLUMNS = [
    "patient_id",
    "date",
    "drug_name",
    "dose",
    "route",
    "duration_days",
    "episode",
    "cohort",
]

# Rename Parquet comorbidity column names → names the pipeline expects
_ANA_COMORBIDITY_RENAME = {
    "Hipertansiyon": "Hipertansiyon Hastada",
    "Kalp Damar": "Kalp Damar Hastada",
    "Diyabet": "Diyabet Hastada",
    "Kan Hastaliklari": "Kan Hastalıkları Hastada",
    "Kronik Hastaliklar Diger": "Kronik Hastalıklar Diğer",
    "Ameliyat Gecmisi": "Ameliyat Geçmişi",
    "Ozgecmis Notu": "Özgeçmiş Notu",
}

# Text columns used by NLP pipeline
_ANA_TEXT_COLS = [
    "ÖYKÜ",
    "YAKINMA",
    "Muayene Notu",
    "Kontrol Notu",
    "Tedavi Notu",
]

_ANA_VITAL_COLS = {
    "systolic_bp": "systolic_bp",
    "diastolic_bp": "diastolic_bp",
    # pulse and spo2 dropped — 96.7% and 99.7% missing respectively (see health_index.py)
}

_ANA_OUTCOME_COLS = {
    "los_days": "los_days",
    "total_visits": "total_visits",
    "visit_num": "visit_num",
}

# ---------------------------------------------------------------------------
# Module-level cache for grouped indices
# ---------------------------------------------------------------------------
_data_cache: dict | None = None
_lab_group_idx: dict[str, np.ndarray] | None = None
_ana_group_idx: dict[str, np.ndarray] | None = None
_rec_group_idx: dict[str, np.ndarray] | None = None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def _apply_categorical_dtypes(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Convert specified string columns to categorical dtype for memory savings."""
    for col in columns:
        if col in df.columns and df[col].dtype == "object":
            df[col] = df[col].astype("category")
    return df


def load_labdata(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load lab data from Parquet with column pruning.

    Returns DataFrame with columns:
      patient_id (str), test_name, value, unit, ref_min, ref_max, date, cohort
    """
    p = Path(path) if path else _CACHE_DIR / "acuhit2_lab_from2025.parquet"
    logger.info("Loading lab data from %s", p.name)

    df = pd.read_parquet(p, columns=_LAB_COLUMNS)

    # Ensure types
    df["patient_id"] = df["patient_id"].astype(str)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["ref_min"] = pd.to_numeric(df["ref_min"], errors="coerce")
    df["ref_max"] = pd.to_numeric(df["ref_max"], errors="coerce")

    # Data quality: drop rows without numeric value or date
    df = df.dropna(subset=["value", "date"]).copy()

    # Data quality: drop impossible dates (Excel serial leaks)
    df = df[df["date"] >= "2000-01-01"]

    # Categorical dtypes for memory savings
    df = _apply_categorical_dtypes(df, ["test_name", "cohort", "patient_id", "unit"])

    df = df.sort_values(["patient_id", "date"]).reset_index(drop=True)
    logger.info(
        "Lab data loaded: %d rows, %d patients", len(df), df["patient_id"].nunique()
    )
    return df


def load_anadata(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load anadata (visit records) from Parquet with column pruning.

    Returns DataFrame with pipeline-expected column names.
    """
    p = Path(path) if path else _CACHE_DIR / "acuhit2_anadata_from2025.parquet"
    logger.info("Loading anadata from %s", p.name)

    df = pd.read_parquet(p, columns=_ANA_COLUMNS)

    # Rename comorbidity columns to match what the pipeline expects
    df = df.rename(columns=_ANA_COMORBIDITY_RENAME)

    # Ensure types
    df["patient_id"] = df["patient_id"].astype(str)
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["sex"] = df["sex"].astype(str)

    # Vitals
    for vital in _ANA_VITAL_COLS:
        if vital in df.columns:
            df[vital] = pd.to_numeric(df[vital], errors="coerce")

    # Outcomes
    for outcome in _ANA_OUTCOME_COLS:
        if outcome in df.columns:
            df[outcome] = pd.to_numeric(df[outcome], errors="coerce")

    # Data quality: clip impossible vitals
    if "systolic_bp" in df.columns:
        df.loc[(df["systolic_bp"] < 40) | (df["systolic_bp"] > 300), "systolic_bp"] = (
            np.nan
        )
    if "diastolic_bp" in df.columns:
        df.loc[
            (df["diastolic_bp"] < 20) | (df["diastolic_bp"] > 200), "diastolic_bp"
        ] = np.nan

    # Data quality: clip impossible ages
    df.loc[(df["age"] < 0) | (df["age"] > 120), "age"] = np.nan

    # Drop rows without a visit date
    df = df.dropna(subset=["visit_date"]).copy()

    # Categorical dtypes
    df = _apply_categorical_dtypes(df, ["cohort", "patient_id", "sex"])

    df = df.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)
    logger.info(
        "Anadata loaded: %d rows, %d patients", len(df), df["patient_id"].nunique()
    )
    return df


def load_recete(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load prescription data from Parquet with column pruning.

    Returns DataFrame with columns:
      patient_id, date, drug_name, dose, route, duration_days, episode, cohort
    """
    p = Path(path) if path else _CACHE_DIR / "acuhit2_recete_from2025.parquet"
    logger.info("Loading recete data from %s", p.name)

    df = pd.read_parquet(p, columns=_REC_COLUMNS)

    # Ensure types
    df["patient_id"] = df["patient_id"].astype(str)
    df["duration_days"] = pd.to_numeric(df["duration_days"], errors="coerce")
    if "drug_name" in df.columns:
        df["drug_name"] = df["drug_name"].astype(str).str.strip()

    # Drop rows without a date
    df = df.dropna(subset=["date"]).copy()

    # Categorical dtypes
    df = _apply_categorical_dtypes(df, ["cohort", "patient_id"])

    df = df.sort_values(["patient_id", "date"]).reset_index(drop=True)
    logger.info(
        "Recete loaded: %d rows, %d patients", len(df), df["patient_id"].nunique()
    )
    return df


# ---------------------------------------------------------------------------
# Patient access helpers
# ---------------------------------------------------------------------------


def _build_group_indices(
    df: pd.DataFrame, id_col: str = "patient_id"
) -> dict[str, np.ndarray]:
    """Build a dict mapping patient_id → array of row indices.

    Uses groupby().groups which stores only index arrays (~50 MB for 196K patients),
    NOT copies of the actual data (which would double RAM usage).
    """
    return {
        str(k): v.values if hasattr(v, "values") else np.array(v)
        for k, v in df.groupby(id_col, observed=True).groups.items()
    }


def get_lab_patients(lab_df: pd.DataFrame) -> list[str]:
    """Return sorted list of unique patient IDs in lab data."""
    return sorted(lab_df["patient_id"].unique().tolist())


def get_patient_labs(lab_df: pd.DataFrame, patient_id: PatientId) -> pd.DataFrame:
    """Return all lab rows for one patient, sorted by date."""
    global _lab_group_idx
    pid = str(patient_id)
    if _lab_group_idx is not None and pid in _lab_group_idx:
        return lab_df.iloc[_lab_group_idx[pid]].sort_values("date").copy()
    return lab_df[lab_df["patient_id"] == pid].sort_values("date").copy()


def pivot_labs(patient_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot from long-form to wide-form:
      index = date, columns = test_name, values = value
    Duplicate (date, test_name) pairs are averaged.
    """
    pivoted = (
        patient_df.groupby(["date", "test_name"], observed=True)["value"]
        .mean()
        .reset_index()
    )
    result = pivoted.pivot(
        index="date", columns="test_name", values="value"
    ).sort_index()
    result.columns.name = None
    return result


def get_patient_visits(ana_df: pd.DataFrame, patient_id: PatientId) -> pd.DataFrame:
    """Return all visit rows for one patient, sorted by visit_date."""
    global _ana_group_idx
    pid = str(patient_id)
    if _ana_group_idx is not None and pid in _ana_group_idx:
        return ana_df.iloc[_ana_group_idx[pid]].sort_values("visit_date").copy()
    return ana_df[ana_df["patient_id"] == pid].sort_values("visit_date").copy()


def get_patient_vitals(ana_df: pd.DataFrame, patient_id: PatientId) -> pd.DataFrame:
    """Return vitals time-series (date + active vital columns from _ANA_VITAL_COLS)."""
    vital_cols = [c for c in _ANA_VITAL_COLS.keys() if c in ana_df.columns]
    cols = ["visit_date"] + vital_cols
    visits = get_patient_visits(ana_df, patient_id)[
        [c for c in cols if c in ana_df.columns]
    ]
    # Only drop rows where ALL vital columns are null
    if vital_cols:
        visits = visits.dropna(how="all", subset=vital_cols)
    return visits.rename(columns={"visit_date": "date"}).reset_index(drop=True)


def get_patient_prescriptions(
    rec_df: pd.DataFrame, patient_id: PatientId
) -> pd.DataFrame:
    """Return all prescription rows for one patient, sorted by date."""
    global _rec_group_idx
    pid = str(patient_id)
    if _rec_group_idx is not None and pid in _rec_group_idx:
        return rec_df.iloc[_rec_group_idx[pid]].sort_values("date").copy()
    return rec_df[rec_df["patient_id"] == pid].sort_values("date").copy()


# ---------------------------------------------------------------------------
# Convenience: load all & group
# ---------------------------------------------------------------------------


def load_all_data(base_dir: str | Path | None = None) -> dict:
    """Load all three Parquet files and return a dict of DataFrames.

    Also builds module-level group indices for O(1) per-patient lookups.
    """
    global _data_cache, _lab_group_idx, _ana_group_idx, _rec_group_idx

    if _data_cache is not None:
        return _data_cache

    lab = load_labdata()
    ana = load_anadata()
    rec = load_recete()

    # Build group indices (index-only, no data copies)
    logger.info("Building group indices for O(1) per-patient lookups...")
    _lab_group_idx = _build_group_indices(lab)
    _ana_group_idx = _build_group_indices(ana)
    _rec_group_idx = _build_group_indices(rec)
    logger.info(
        "Group indices built: lab=%d, ana=%d, rec=%d patients",
        len(_lab_group_idx),
        len(_ana_group_idx),
        len(_rec_group_idx),
    )

    _data_cache = {"lab": lab, "ana": ana, "rec": rec}
    return _data_cache


def get_common_patients(lab_df: pd.DataFrame, ana_df: pd.DataFrame) -> list[str]:
    """Patients present in BOTH labdata and anadata."""
    lab_ids = set(lab_df["patient_id"].unique())
    ana_ids = set(ana_df["patient_id"].unique())
    return sorted(lab_ids & ana_ids)


def get_grouped_data() -> tuple[
    dict[str, np.ndarray],
    dict[str, np.ndarray],
    dict[str, np.ndarray],
]:
    """Return pre-built group indices (lab, ana, rec).

    Must be called after load_all_data().
    """
    if _lab_group_idx is None:
        raise RuntimeError("Call load_all_data() before get_grouped_data()")
    return _lab_group_idx, _ana_group_idx, _rec_group_idx
