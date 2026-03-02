"""
data_loader.py
All ODS parsing and data access for the ACUHIT project.

Files:
  labdata.ods  — columns: HASTANO, TEST_ID, SUB_CODE (test name), SONUC (value),
                           UNIT, REFMIN, REFMAX, REP_DATE
  anadata.ods  — 69 columns per patient visit; vitals, text notes, demographics
  recete.ods   — prescription records per patient
"""

from __future__ import annotations

import pandas as pd
from pathlib import Path

_EXCEL_EPOCH = pd.Timestamp("1899-12-30")
_BASE_DIR = Path(__file__).parent.parent  # Acıbadem/


def _excel_to_date(serial) -> pd.Timestamp | None:
    """Convert Excel date serial number OR already-parsed Timestamp to pd.Timestamp.

    The odf engine may return dates as datetime/Timestamp objects rather than
    float serial numbers, depending on how the cell was stored in the ODS file.
    Handling both formats here prevents silent data loss.
    """
    if serial is None or (not isinstance(serial, (pd.Timestamp,)) and pd.isna(serial)):
        return None
    # Already a date/datetime — just normalise to Timestamp
    if isinstance(serial, (pd.Timestamp,)):
        return serial
    try:
        import datetime
        if isinstance(serial, (datetime.date, datetime.datetime)):
            return pd.Timestamp(serial)
        # Numeric serial (Excel epoch)
        return _EXCEL_EPOCH + pd.Timedelta(days=float(serial))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# labdata
# ---------------------------------------------------------------------------

def load_labdata(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load labdata.ods and return a clean DataFrame with columns:
      patient_id, test_name, value, unit, ref_min, ref_max, date
    """
    path = path or _BASE_DIR / "labdata.ods"
    raw = pd.read_excel(str(path), engine="odf")

    df = pd.DataFrame()
    df["patient_id"] = raw["HASTANO"]
    df["test_id"] = raw["TEST_ID"]
    df["test_name"] = raw["SUB_CODE"].str.strip()
    df["value"] = pd.to_numeric(raw["SONUC"], errors="coerce")
    df["unit"] = raw["UNIT"]
    df["ref_min"] = pd.to_numeric(raw["REFMIN"], errors="coerce")
    df["ref_max"] = pd.to_numeric(raw["REFMAX"], errors="coerce")
    df["date"] = raw["REP_DATE"].apply(_excel_to_date)

    # Drop rows without a numeric value
    df = df.dropna(subset=["value", "date"]).copy()
    df = df.sort_values(["patient_id", "date"]).reset_index(drop=True)
    return df


def get_lab_patients(lab_df: pd.DataFrame) -> list[int]:
    return sorted(lab_df["patient_id"].unique().tolist())


def get_patient_labs(lab_df: pd.DataFrame, patient_id: int) -> pd.DataFrame:
    """Return all lab rows for one patient, sorted by date."""
    return lab_df[lab_df["patient_id"] == patient_id].sort_values("date").copy()


def pivot_labs(patient_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot from long-form to wide-form:
      index = date, columns = test_name, values = value
    Duplicate (date, test_name) pairs are averaged.
    """
    pivoted = patient_df.groupby(["date", "test_name"])["value"].mean().reset_index()
    result = pivoted.pivot(index="date", columns="test_name", values="value").sort_index()
    result.columns.name = None  # drop the axis label so columns behave like a plain Index
    return result


# ---------------------------------------------------------------------------
# anadata
# ---------------------------------------------------------------------------

_ANA_TEXT_COLS = [
    "ÖYKÜ",
    "YAKINMA",
    "Muayene Notu",
    "Kontrol Notu",
    "Tedavi Notu",
]

_ANA_VITAL_COLS = {
    "systolic_bp": "KB-S",
    "diastolic_bp": "KB-D",
    "pulse": "Nabız",
    "spo2": "SPO2",
}

_ANA_OUTCOME_COLS = {
    "los_days": "ILK_TANI_SON_TANI_GUN_FARKI",
    "total_visits": "TOPLAM_GELIS_SAYISI",
    "visit_num": "GELIS_SAYISI",
}


def load_anadata(path: str | Path | None = None) -> pd.DataFrame:
    """
    Load anadata.ods and return a clean DataFrame.
    Dates are converted; numeric vitals are coerced.
    """
    path = path or _BASE_DIR / "anadata.ods"
    raw = pd.read_excel(str(path), engine="odf")

    df = raw.copy()
    df["patient_id"] = df["HASTANO"]
    df["visit_date"] = df["EPISODE_TARIH"].apply(_excel_to_date)

    # Vitals
    for new_col, old_col in _ANA_VITAL_COLS.items():
        if old_col in df.columns:
            df[new_col] = pd.to_numeric(df[old_col], errors="coerce")

    # Outcomes
    for new_col, old_col in _ANA_OUTCOME_COLS.items():
        if old_col in df.columns:
            df[new_col] = pd.to_numeric(df[old_col], errors="coerce")

    # Age / sex
    df["age"] = pd.to_numeric(df.get("YAŞ"), errors="coerce")
    # Use empty-string default so the column has a consistent string dtype
    # when the source column is absent (avoids float-NaN dtype on a text field)
    df["sex"] = df["CINSIYET"].astype(str) if "CINSIYET" in df.columns else ""

    # Keep all original columns plus the clean ones
    # Drop rows without a visit date (consistent with load_labdata's date requirement)
    df = df.dropna(subset=["visit_date"]).copy()
    df = df.sort_values(["patient_id", "visit_date"]).reset_index(drop=True)
    return df


def get_patient_visits(ana_df: pd.DataFrame, patient_id: int) -> pd.DataFrame:
    return ana_df[ana_df["patient_id"] == patient_id].sort_values("visit_date").copy()


def get_patient_vitals(ana_df: pd.DataFrame, patient_id: int) -> pd.DataFrame:
    """Return vitals time-series (date, systolic_bp, diastolic_bp, pulse, spo2)."""
    vital_cols = [c for c in _ANA_VITAL_COLS.keys() if c in ana_df.columns]
    cols = ["visit_date"] + vital_cols
    visits = get_patient_visits(ana_df, patient_id)[cols]
    # Only drop rows where ALL vital columns are null (keep rows with at least 1 vital)
    if vital_cols:
        visits = visits.dropna(how="all", subset=vital_cols)
    return visits.rename(columns={"visit_date": "date"}).reset_index(drop=True)


# ---------------------------------------------------------------------------
# recete
# ---------------------------------------------------------------------------

def load_recete(path: str | Path | None = None) -> pd.DataFrame:
    """Load recete.ods (prescriptions) and return a clean DataFrame."""
    path = path or _BASE_DIR / "recete.ods"
    raw = pd.read_excel(str(path), engine="odf")

    df = pd.DataFrame()
    df["patient_id"] = raw["HASTANO"]
    df["date"] = raw["RECETE_TARIH"].apply(_excel_to_date)
    df["drug_name"] = raw["İlaç Adı"].str.strip() if "İlaç Adı" in raw.columns else None
    df["dose"] = raw.get("Sıklık X Doz")
    df["route"] = raw.get("VERİLİS_YOLU")
    df["duration_days"] = pd.to_numeric(raw.get("Gün"), errors="coerce")
    df["episode"] = raw.get("RF_EPISODE")

    df = df.dropna(subset=["date"]).sort_values(["patient_id", "date"]).reset_index(drop=True)
    return df


def get_patient_prescriptions(rec_df: pd.DataFrame, patient_id: int) -> pd.DataFrame:
    return rec_df[rec_df["patient_id"] == patient_id].sort_values("date").copy()


# ---------------------------------------------------------------------------
# Convenience: load all & join
# ---------------------------------------------------------------------------

def load_all_data(base_dir: str | Path | None = None) -> dict:
    """Load all three ODS files and return a dict of DataFrames."""
    base = Path(base_dir) if base_dir else _BASE_DIR
    return {
        "lab": load_labdata(base / "labdata.ods"),
        "ana": load_anadata(base / "anadata.ods"),
        "rec": load_recete(base / "recete.ods"),
    }


def get_common_patients(lab_df: pd.DataFrame, ana_df: pd.DataFrame) -> list[int]:
    """Patients present in BOTH labdata and anadata."""
    lab_ids = set(lab_df["patient_id"].unique())
    ana_ids = set(ana_df["patient_id"].unique())
    return sorted(lab_ids & ana_ids)
