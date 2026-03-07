#!/usr/bin/env python3
"""
convert_acuhit2_to_parquet.py
Convert 92 sharded ACUHIT 2 CSV files → 3 unified Parquet files.

Output:
  .cache/acuhit2_lab.parquet
  .cache/acuhit2_anadata.parquet
  .cache/acuhit2_recete.parquet

Usage:
  python scripts/convert_acuhit2_to_parquet.py
"""

from __future__ import annotations

import gc
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
ACUHIT2_DIR = BASE_DIR / "ACUHIT 2"
CACHE_DIR = BASE_DIR / ".cache"

# Cohort folder → tag mapping
COHORT_FOLDERS = {
    "Cancer - Data": "cancer",
    "Check-Up - Data": "checkup",
    "Ex - Data": "ex",
}

# Sub-folder names per data type per cohort
DATA_TYPE_FOLDERS = {
    "lab": {
        "cancer": "Cancer_Lab",
        "checkup": "Check_Up_Lab",
        "ex": "Ex_Lab",
    },
    "anadata": {
        "cancer": "Cancer_Anadata",
        "checkup": "Check_Up_Anadata",
        "ex": "Ex_Anadata",
    },
    "recete": {
        "cancer": "Cancer_Recete",
        "checkup": "Check_Up_Recete",
        "ex": "Ex_Recete",
    },
}

# ---------------------------------------------------------------------------
# Column mappings: CSV column name → pipeline column name
# Only map columns we want to KEEP (pipeline-relevant columns).
# Unmapped columns are preserved as-is in the Parquet for future use.
# ---------------------------------------------------------------------------

LAB_RENAME = {
    "HASTA_ID": "patient_id",
    "SUB_CODE": "test_name",
    "RESULT": "value",
    "UNIT": "unit",
    "REFMIN": "ref_min",
    "REFMAX": "ref_max",
    "REP_DATE": "date",
}

ANADATA_RENAME = {
    "HASTA_ID": "patient_id",
    "EPISODE_TARIH": "visit_date",
    "TANI_YASI": "age",
    "CINSIYET": "sex",
    "KB-S": "systolic_bp",
    "KB-D": "diastolic_bp",
    "Nabız": "pulse",
    "SPO2": "spo2",
    "ILK_TANI_SON_TANI_GUN_FARKI": "los_days",
    "TOPLAM_GELIS_SAYISI": "total_visits",
    "GELIS_SAYISI": "visit_num",
    # Text columns — keep Turkish names for NLP consistency with n=9 pipeline
    "ÖYKÜ": "ÖYKÜ",
    "YAKINMA": "YAKINMA",
    "Muayene Notu": "Muayene Notu",
    "Kontrol Notu": "Kontrol Notu",
    "Tedavi Notu": "Tedavi Notu",
    # Comorbidity flags
    "Hipertansiyon Hastada": "Hipertansiyon",
    "Kalp Damar Hastada": "Kalp Damar",
    "Diyabet Hastada": "Diyabet",
    "Kan Hastalıkları Hastada": "Kan Hastaliklari",
    "Kronik Hastalıklar Diğer": "Kronik Hastaliklar Diger",
    "Ameliyat Geçmişi": "Ameliyat Gecmisi",
    # Demographics / metadata
    "Boy": "Boy",
    "Kilo": "Kilo",
    "BMI": "BMI",
    "SQ_EPISODE": "SQ_EPISODE",
    "TANIKODU": "TANIKODU",
    "TANI_TIPI": "TANI_TIPI",
    "GELIS_TIPI": "GELIS_TIPI",
    "SERVISADI": "SERVISADI",
    "TUM_EPS_TANILAR": "TUM_EPS_TANILAR",
    "TANITARIH": "TANITARIH",
    "MIN_TANI_TARIH": "MIN_TANI_TARIH",
    "MAX_TANI_TARIH": "MAX_TANI_TARIH",
    "Ritmik/ Aritmik": "Ritmik/ Aritmik",
    # Additional metadata
    "Sigara": "Sigara",
    "Alkol": "Alkol",
    "Madde": "Madde",
    "Alerji": "Alerji",
    "ilaç Alerjisi": "ilac_alerjisi",
    "Özgeçmiş Notu": "Ozgecmis Notu",
    "Kan Grubu": "Kan Grubu",
    "Engellilik": "Engellilik",
    "Meslek": "Meslek",
    "Sosyal Durum": "Sosyal Durum",
    "Anne KH": "Anne KH",
    "Baba KH": "Baba KH",
    "Erkek Kardeş KH": "Erkek Kardes KH",
    "Kız Kardeş KH": "Kiz Kardes KH",
    "Soygeçmiş Notu": "Soygecmis Notu",
    # New columns (not in n=9 ODS)
    "YAKINMA_BASLANGIC_ZAMANI": "YAKINMA_BASLANGIC_ZAMANI",
    "Düşme Riski": "Dusme Riski",
    "Ağrısı var mı": "Agrisi_var_mi",
    "Ağrı skoru": "Agri_skoru",
    "Sıklık": "Siklik",
    "Yer": "Yer",
    "Nitelik": "Nitelik",
    "Yaralanma Geçmişi": "Yaralanma Gecmisi",
    "Sürekli Kullandığı İlaçlar": "Surekli_Ilaclar",
    # Check-Up only columns
    "RF_EPISODE2": "RF_EPISODE2",
    "BASLANGIC_ZAMANI": "BASLANGIC_ZAMANI",
}

RECETE_RENAME = {
    "HASTA_ID": "patient_id",
    "RECETE_TARIH": "date",
    "İlaç Adı": "drug_name",
    "Sıklık X Doz": "dose",
    "VERİLİS_YOLU": "route",
    "Gün": "duration_days",
    "RF_EPISODE": "episode",
    # New columns (not in n=9 ODS)
    "SIKAYETNO": "SIKAYETNO",
    "SUBEKODU": "SUBEKODU",
}

# Chunk size for CSV reading — balances memory vs speed on 16 GB RAM
CHUNK_SIZE = 250_000


def _discover_csvs(cohort_tag: str, data_type: str) -> list[Path]:
    """Find all CSV files for a given cohort + data type, sorted by name."""
    folder_name = DATA_TYPE_FOLDERS[data_type][cohort_tag]
    cohort_folder = [k for k, v in COHORT_FOLDERS.items() if v == cohort_tag][0]
    search_dir = ACUHIT2_DIR / cohort_folder / folder_name

    if not search_dir.exists():
        print(f"  WARNING: {search_dir} does not exist, skipping")
        return []

    csvs = sorted(search_dir.glob("*.csv"))
    return csvs


def _convert_lab(writer_map: dict) -> int:
    """Convert all lab CSVs → single Parquet. Returns total row count."""
    total_rows = 0
    rename = LAB_RENAME

    for cohort_tag in ("cancer", "checkup", "ex"):
        csvs = _discover_csvs(cohort_tag, "lab")
        print(f"  [{cohort_tag}] Found {len(csvs)} lab CSV files")

        for csv_path in csvs:
            for chunk in pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False):
                # Rename columns
                chunk = chunk.rename(columns=rename)

                # Coerce types
                chunk["patient_id"] = chunk["patient_id"].astype(str)
                chunk["value"] = pd.to_numeric(chunk["value"], errors="coerce")
                chunk["ref_min"] = pd.to_numeric(chunk["ref_min"], errors="coerce")
                chunk["ref_max"] = pd.to_numeric(chunk["ref_max"], errors="coerce")
                chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
                chunk["test_name"] = chunk["test_name"].astype(str).str.strip()
                chunk["unit"] = chunk["unit"].astype(str)

                # Add cohort tag
                chunk["cohort"] = cohort_tag

                # Drop rows without a numeric value or date
                chunk = chunk.dropna(subset=["value", "date"])

                # Write to Parquet writer
                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if "lab" not in writer_map:
                    writer_map["lab"] = pq.ParquetWriter(
                        CACHE_DIR / "acuhit2_lab.parquet",
                        table.schema,
                        compression="snappy",
                    )
                writer_map["lab"].write_table(table)
                total_rows += len(chunk)

            gc.collect()

    return total_rows


_ANADATA_SCHEMA = pa.schema(
    [
        ("patient_id", pa.string()),
        ("visit_date", pa.timestamp("ns")),
        ("age", pa.float64()),
        ("sex", pa.string()),
        ("systolic_bp", pa.float64()),
        ("diastolic_bp", pa.float64()),
        ("pulse", pa.float64()),
        ("spo2", pa.float64()),
        ("los_days", pa.float64()),
        ("total_visits", pa.float64()),
        ("visit_num", pa.float64()),
        ("ÖYKÜ", pa.string()),
        ("YAKINMA", pa.string()),
        ("Muayene Notu", pa.string()),
        ("Kontrol Notu", pa.string()),
        ("Tedavi Notu", pa.string()),
        ("Hipertansiyon", pa.string()),
        ("Kalp Damar", pa.string()),
        ("Diyabet", pa.string()),
        ("Kan Hastaliklari", pa.string()),
        ("Kronik Hastaliklar Diger", pa.string()),
        ("Ameliyat Gecmisi", pa.string()),
        ("Boy", pa.string()),
        ("Kilo", pa.string()),
        ("BMI", pa.string()),
        ("SQ_EPISODE", pa.string()),
        ("TANIKODU", pa.string()),
        ("TANI_TIPI", pa.string()),
        ("GELIS_TIPI", pa.string()),
        ("SERVISADI", pa.string()),
        ("TUM_EPS_TANILAR", pa.string()),
        ("TANITARIH", pa.string()),
        ("MIN_TANI_TARIH", pa.string()),
        ("MAX_TANI_TARIH", pa.string()),
        ("Ritmik/ Aritmik", pa.string()),
        ("Sigara", pa.string()),
        ("Alkol", pa.string()),
        ("Madde", pa.string()),
        ("Alerji", pa.string()),
        ("ilac_alerjisi", pa.string()),
        ("Ozgecmis Notu", pa.string()),
        ("Kan Grubu", pa.string()),
        ("Engellilik", pa.string()),
        ("Meslek", pa.string()),
        ("Sosyal Durum", pa.string()),
        ("Anne KH", pa.string()),
        ("Baba KH", pa.string()),
        ("Erkek Kardes KH", pa.string()),
        ("Kiz Kardes KH", pa.string()),
        ("Soygecmis Notu", pa.string()),
        ("YAKINMA_BASLANGIC_ZAMANI", pa.string()),
        ("Dusme Riski", pa.string()),
        ("Agrisi_var_mi", pa.string()),
        ("Agri_skoru", pa.string()),
        ("Siklik", pa.string()),
        ("Yer", pa.string()),
        ("Nitelik", pa.string()),
        ("Yaralanma Gecmisi", pa.string()),
        ("Surekli_Ilaclar", pa.string()),
        ("RF_EPISODE2", pa.string()),
        ("BASLANGIC_ZAMANI", pa.string()),
        ("cohort", pa.string()),
    ]
)


def _convert_anadata(writer_map: dict) -> int:
    """Convert all anadata CSVs → single Parquet. Returns total row count."""
    total_rows = 0
    rename = ANADATA_RENAME

    # Build the union of all expected output column names (for consistent schema)
    all_output_cols = [field.name for field in _ANADATA_SCHEMA]

    # Create writer upfront with fixed schema
    writer_map["anadata"] = pq.ParquetWriter(
        CACHE_DIR / "acuhit2_anadata.parquet",
        _ANADATA_SCHEMA,
        compression="snappy",
    )

    for cohort_tag in ("cancer", "checkup", "ex"):
        csvs = _discover_csvs(cohort_tag, "anadata")
        print(f"  [{cohort_tag}] Found {len(csvs)} anadata CSV files")

        for csv_path in csvs:
            for chunk in pd.read_csv(
                csv_path, chunksize=CHUNK_SIZE, low_memory=False, dtype=str
            ):
                # Rename only columns that exist in this chunk
                actual_rename = {k: v for k, v in rename.items() if k in chunk.columns}
                chunk = chunk.rename(columns=actual_rename)

                # Keep only columns that are in our expected output set
                keep_cols = [c for c in chunk.columns if c in all_output_cols]
                chunk = chunk[keep_cols]

                # Ensure all expected columns exist (empty string for missing)
                for col in all_output_cols:
                    if col not in chunk.columns:
                        chunk[col] = None

                # Reorder columns consistently
                chunk = chunk[all_output_cols]

                # Coerce numeric/date types
                chunk["visit_date"] = pd.to_datetime(
                    chunk["visit_date"], errors="coerce"
                )
                for num_col in (
                    "age",
                    "systolic_bp",
                    "diastolic_bp",
                    "pulse",
                    "spo2",
                    "los_days",
                    "total_visits",
                    "visit_num",
                ):
                    chunk[num_col] = pd.to_numeric(chunk[num_col], errors="coerce")

                # Add cohort tag
                chunk["cohort"] = cohort_tag

                # Drop rows without a visit date
                chunk = chunk.dropna(subset=["visit_date"])

                table = pa.Table.from_pandas(
                    chunk, schema=_ANADATA_SCHEMA, preserve_index=False
                )
                writer_map["anadata"].write_table(table)
                total_rows += len(chunk)

            gc.collect()

    return total_rows


def _convert_recete(writer_map: dict) -> int:
    """Convert all recete CSVs → single Parquet. Returns total row count."""
    total_rows = 0
    rename = RECETE_RENAME

    for cohort_tag in ("cancer", "checkup", "ex"):
        csvs = _discover_csvs(cohort_tag, "recete")
        print(f"  [{cohort_tag}] Found {len(csvs)} recete CSV files")

        for csv_path in csvs:
            for chunk in pd.read_csv(csv_path, chunksize=CHUNK_SIZE, low_memory=False):
                # Rename columns
                actual_rename = {k: v for k, v in rename.items() if k in chunk.columns}
                chunk = chunk.rename(columns=actual_rename)

                # Coerce types
                chunk["patient_id"] = chunk["patient_id"].astype(str)
                chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
                chunk["duration_days"] = pd.to_numeric(
                    chunk.get("duration_days"), errors="coerce"
                )
                if "drug_name" in chunk.columns:
                    chunk["drug_name"] = chunk["drug_name"].astype(str).str.strip()

                # Add cohort tag
                chunk["cohort"] = cohort_tag

                # Drop rows without a date
                chunk = chunk.dropna(subset=["date"])

                table = pa.Table.from_pandas(chunk, preserve_index=False)
                if "recete" not in writer_map:
                    writer_map["recete"] = pq.ParquetWriter(
                        CACHE_DIR / "acuhit2_recete.parquet",
                        table.schema,
                        compression="snappy",
                    )
                writer_map["recete"].write_table(table)
                total_rows += len(chunk)

            gc.collect()

    return total_rows


def main() -> None:
    if not ACUHIT2_DIR.exists():
        print(f"ERROR: ACUHIT 2 directory not found at {ACUHIT2_DIR}")
        sys.exit(1)

    CACHE_DIR.mkdir(exist_ok=True)

    # Remove existing Parquet files to avoid appending to stale data
    for f in (
        "acuhit2_lab.parquet",
        "acuhit2_anadata.parquet",
        "acuhit2_recete.parquet",
    ):
        p = CACHE_DIR / f
        if p.exists():
            p.unlink()
            print(f"  Removed stale {f}")

    writer_map: dict = {}

    print("=" * 60)
    print("ACUHIT 2 → Parquet Conversion")
    print("=" * 60)

    # --- Lab ---
    print("\n[1/3] Converting LAB data...")
    t0 = time.time()
    lab_rows = _convert_lab(writer_map)
    lab_time = time.time() - t0
    print(f"  Lab: {lab_rows:,} rows in {lab_time:.1f}s")

    # --- Anadata ---
    print("\n[2/3] Converting ANADATA...")
    t0 = time.time()
    ana_rows = _convert_anadata(writer_map)
    ana_time = time.time() - t0
    print(f"  Anadata: {ana_rows:,} rows in {ana_time:.1f}s")

    # --- Recete ---
    print("\n[3/3] Converting RECETE data...")
    t0 = time.time()
    rec_rows = _convert_recete(writer_map)
    rec_time = time.time() - t0
    print(f"  Recete: {rec_rows:,} rows in {rec_time:.1f}s")

    # Close all writers
    for writer in writer_map.values():
        writer.close()

    # --- Summary ---
    print("\n" + "=" * 60)
    print("CONVERSION COMPLETE")
    print("=" * 60)
    total_time = lab_time + ana_time + rec_time

    for name in ("acuhit2_lab", "acuhit2_anadata", "acuhit2_recete"):
        p = CACHE_DIR / f"{name}.parquet"
        if p.exists():
            size_mb = p.stat().st_size / (1024 * 1024)
            print(f"  {p.name}: {size_mb:.1f} MB")

    print(f"\n  Total rows: {lab_rows + ana_rows + rec_rows:,}")
    print(f"  Total time: {total_time:.1f}s")
    print(f"  Output dir: {CACHE_DIR}")


if __name__ == "__main__":
    main()
