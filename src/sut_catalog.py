"""
sut_catalog.py
Parse real SUT gazette Excel data (EK-2B, EK-2C) into structured catalogs.

Reads the official Turkish Health Implementation Communiqué (SUT) price
schedules from Excel files and provides:
  - Parsed JSON catalogs (data/sut_ek2b.json, data/sut_ek2c.json)
  - In-memory catalog loader for downstream pricing engine
  - ILAY test name → SUT code mapping for lab price lookups
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger("ilay.sut_catalog")

# ── Paths ─────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SUT_DATA_DIR = _PROJECT_ROOT / "sut data"
_DATA_DIR = _PROJECT_ROOT / "data"

EK2B_PATH = _SUT_DATA_DIR / "EK-2B.xlsx"
EK2C_PATH = _SUT_DATA_DIR / "EK-2C.xlsx"
EK2B_JSON_PATH = _DATA_DIR / "sut_ek2b.json"
EK2C_JSON_PATH = _DATA_DIR / "sut_ek2c.json"


# ── ILAY test name → SUT code mapping ────────────────────────────────────
# Maps the exact test names used in src/health_index.py ORGAN_SYSTEMS
# to their corresponding SUT EK-2B procedure codes.
#
# CBC components are bundled under "Tam Kan (Hemogram)" code 901620.
# GFR is calculated from Creatinine, so maps to Kreatinin code.
# INR is calculated from PT, so maps to Protrombin zamanı code.

ILAY_TO_SUT_CODE: dict[str, int] = {
    # Inflammatory panel
    "CRP": 900890,  # CRP, lateks
    "Prokalsitonin": 903170,  # Procalcitonin
    # Renal panel
    "Kreatinin": 902210,  # Kreatinin
    "Üre": 904100,  # Üre klerensi
    "GFR": 902210,  # GFR calculated from Creatinine
    # Hepatic panel
    "ALT": 900200,  # Alanin aminotransferaz (ALT)
    "AST": 900580,  # Aspartat transaminaz (AST)
    "ALP": 900340,  # Alkalen fosfataz
    "GGT": 901390,  # Gamma glutamil transferaz (GGT)
    "Albumin": 900210,  # Albümin
    "Bilirubin": 900690,  # Bilirubin (Total,direkt)
    # Hematological panel — all bundled under Hemogram
    "Hemoglobin": 901620,  # Tam Kan (Hemogram)
    "Hematokrit": 901620,
    "Eritrosit": 901620,
    "Lökosit": 901620,
    "Trombosit": 901620,
    "MCV": 901620,
    "MCH": 901620,
    "RDW": 901620,
    "Nötrofil": 901620,
    "Lenfosit": 901620,
    "Monosit": 901620,
    "Bazofil": 901620,
    "Eozinofil": 901620,
    # Metabolic panel
    "Glukoz": 901500,  # Glukoz
    "HbA1c": 901450,  # Glikolize hemoglobin (Hb A1C)
    "Kolesterol": 902110,  # Kolesterol
    "Trigliserid": 903990,  # Trigliserid
    "LDL": 902290,  # LDL kolesterol
    "HDL": 901580,  # HDL kolesterol
    "Sodyum": 903670,  # Sodyum (Na)
    "Potasyum": 903130,  # Potasyum
    "Kalsiyum": 901910,  # Kalsiyum (Ca)
    "Protein": 903170,  # Total protein — approximate (Procalcitonin code)
    # Endocrine panel
    "TSH": 904030,  # TSH
    "T3": 903470,  # Serbest T3
    "T4": 903480,  # Serbest T4
    # Coagulation panel
    "PT": 905320,  # Protrombin zamanı (Koagülometre)
    "aPTT": 904290,  # APTT
    "INR": 905320,  # Same as PT (INR calculated from PT)
}

# Reverse mapping: SUT code → ILAY test names (for debugging/reporting)
_SUT_CODE_TO_ILAY: dict[int, list[str]] = {}
for _name, _code in ILAY_TO_SUT_CODE.items():
    _SUT_CODE_TO_ILAY.setdefault(_code, []).append(_name)


# ── EK-2B Parser (Fee-for-service procedures) ────────────────────────────


def _safe_float(val: Any) -> float | None:
    """Convert a value to float, returning None for NaN/None/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _safe_str(val: Any) -> str | None:
    """Convert a value to string, returning None for NaN/None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).strip()
    return s if s else None


def parse_ek2b(path: Path | None = None) -> dict[str, Any]:
    """
    Parse EK-2B.xlsx (fee-for-service procedure prices).

    Structure:
      - Header at row 3 (0-indexed row 2)
      - Columns: SIRA NO | KODU | İŞLEM ADI | AÇIKLAMA | İŞLEM PUANI
      - Rows with KODU=None are section headers → skip
      - Duplicate KODU values = historical revisions → keep LAST per code
      - İŞLEM PUANI values are already in TRY (pre-multiplied)

    Returns:
        Dict with:
          "procedures": list of {code, name, description, price_try}
          "by_code": dict mapping code_str → {name, description, price_try}
          "stats": summary statistics
    """
    path = path or EK2B_PATH
    if not path.exists():
        raise FileNotFoundError(f"EK-2B file not found: {path}")

    logger.info("Parsing EK-2B from %s", path)

    df = pd.read_excel(path, header=2)
    expected_cols = {"KODU", "İŞLEM ADI", "İŞLEM PUANI"}
    if not expected_cols.issubset(set(df.columns)):
        raise ValueError(f"EK-2B missing expected columns. Found: {list(df.columns)}")

    # Filter: skip rows where KODU is None (section headers)
    df_valid = df[df["KODU"].notna()].copy()
    logger.info("EK-2B: %d total rows, %d with valid KODU", len(df), len(df_valid))

    # Deduplicate: keep LAST occurrence per KODU (latest gazette revision)
    # Convert KODU to string for consistent keying
    df_valid["_code_str"] = df_valid["KODU"].astype(str).str.strip()
    df_dedup = df_valid.drop_duplicates(subset="_code_str", keep="last")
    n_dupes = len(df_valid) - len(df_dedup)
    if n_dupes > 0:
        logger.info("EK-2B: dropped %d duplicate codes (kept latest)", n_dupes)

    procedures: list[dict[str, Any]] = []
    by_code: dict[str, dict[str, Any]] = {}

    for _, row in df_dedup.iterrows():
        code_str = str(row["_code_str"])
        name = _safe_str(row["İŞLEM ADI"])
        description = _safe_str(row.get("AÇIKLAMA"))
        price = _safe_float(row["İŞLEM PUANI"])

        if not name or price is None:
            continue

        # Try to parse code as integer for numeric codes
        try:
            code_int = int(float(code_str))
            code_str = str(code_int)
        except (ValueError, TypeError):
            pass

        entry = {
            "code": code_str,
            "name": name,
            "description": description,
            "price_try": round(price, 2),
        }
        procedures.append(entry)
        by_code[code_str] = entry

    # Categorize by code range
    categories: dict[str, int] = {}
    for proc in procedures:
        code = proc["code"]
        try:
            code_int = int(code)
            if 510000 <= code_int < 520000:
                cat = "beds"
            elif 520000 <= code_int < 530000:
                cat = "visits"
            elif 530000 <= code_int < 550000:
                cat = "procedures"
            elif 550000 <= code_int < 560000:
                cat = "anesthesia"
            elif 600000 <= code_int < 619000:
                cat = "surgery"
            elif 700000 <= code_int < 800000:
                cat = "imaging"
            elif 800000 <= code_int < 900000:
                cat = "radiology"
            elif 900000 <= code_int < 913000:
                cat = "lab_tests"
            else:
                cat = "other"
        except (ValueError, TypeError):
            cat = "other"
        categories[cat] = categories.get(cat, 0) + 1

    prices = [p["price_try"] for p in procedures]
    stats = {
        "total_procedures": len(procedures),
        "categories": categories,
        "price_min": round(min(prices), 2) if prices else 0,
        "price_max": round(max(prices), 2) if prices else 0,
        "price_mean": round(sum(prices) / len(prices), 2) if prices else 0,
    }

    logger.info(
        "EK-2B parsed: %d procedures, price range %.2f–%.2f TRY",
        stats["total_procedures"],
        stats["price_min"],
        stats["price_max"],
    )

    return {"procedures": procedures, "by_code": by_code, "stats": stats}


# ── EK-2C Parser (Diagnosis-based procedure packages) ────────────────────


def parse_ek2c(path: Path | None = None) -> dict[str, Any]:
    """
    Parse EK-2C.xlsx (diagnosis-based procedure packages).

    Structure:
      - Header at row 4 (0-indexed row 3)
      - Columns: SIRA NO | PAKET KODU | İŞLEM ADI | AÇIKLAMA | İŞLEM GRUBU | * | İŞLEM PUANI
      - Rows with PAKET KODU=None are section headers → skip
      - Duplicate PAKET KODU = historical revisions → keep LAST
      - Package codes start with 'P' prefix
      - Groups: A1, A2, A3, B, C, D, E

    Returns:
        Dict with:
          "packages": list of {package_code, name, description, group, price_try}
          "by_code": dict mapping package_code → entry
          "group_stats": price statistics per group
          "stats": summary statistics
    """
    path = path or EK2C_PATH
    if not path.exists():
        raise FileNotFoundError(f"EK-2C file not found: {path}")

    logger.info("Parsing EK-2C from %s", path)

    df = pd.read_excel(path, header=3)
    expected_cols = {"PAKET KODU", "İŞLEM ADI", "İŞLEM PUANI"}
    if not expected_cols.issubset(set(df.columns)):
        raise ValueError(f"EK-2C missing expected columns. Found: {list(df.columns)}")

    # Filter: skip rows where PAKET KODU is None
    df_valid = df[df["PAKET KODU"].notna()].copy()
    logger.info(
        "EK-2C: %d total rows, %d with valid PAKET KODU", len(df), len(df_valid)
    )

    # Normalize PAKET KODU to string, strip whitespace
    df_valid["_pkg_code"] = df_valid["PAKET KODU"].astype(str).str.strip()

    # Deduplicate: keep LAST occurrence per PAKET KODU
    df_dedup = df_valid.drop_duplicates(subset="_pkg_code", keep="last")
    n_dupes = len(df_valid) - len(df_dedup)
    if n_dupes > 0:
        logger.info("EK-2C: dropped %d duplicate codes (kept latest)", n_dupes)

    packages: list[dict[str, Any]] = []
    by_code: dict[str, dict[str, Any]] = {}

    for _, row in df_dedup.iterrows():
        pkg_code = str(row["_pkg_code"])
        name = _safe_str(row["İŞLEM ADI"])
        description = _safe_str(row.get("AÇIKLAMA"))
        group = _safe_str(row.get("İŞLEM GRUBU"))
        price = _safe_float(row["İŞLEM PUANI"])

        if not name or price is None:
            continue

        # Normalize group: strip whitespace
        if group:
            group = group.strip()

        entry = {
            "package_code": pkg_code,
            "name": name,
            "description": description,
            "group": group,
            "price_try": round(price, 2),
        }
        packages.append(entry)
        by_code[pkg_code] = entry

    # Group statistics
    group_stats: dict[str, dict[str, Any]] = {}
    for pkg in packages:
        grp = pkg["group"] or "unknown"
        if grp not in group_stats:
            group_stats[grp] = {"count": 0, "prices": []}
        group_stats[grp]["count"] += 1
        group_stats[grp]["prices"].append(pkg["price_try"])

    for grp, gs in group_stats.items():
        prices_list = gs["prices"]
        gs["price_min"] = round(min(prices_list), 2)
        gs["price_max"] = round(max(prices_list), 2)
        gs["price_mean"] = round(sum(prices_list) / len(prices_list), 2)
        del gs["prices"]  # Don't store raw list in stats

    all_prices = [p["price_try"] for p in packages]
    stats = {
        "total_packages": len(packages),
        "unique_groups": sorted(group_stats.keys()),
        "price_min": round(min(all_prices), 2) if all_prices else 0,
        "price_max": round(max(all_prices), 2) if all_prices else 0,
        "price_mean": round(sum(all_prices) / len(all_prices), 2) if all_prices else 0,
    }

    logger.info(
        "EK-2C parsed: %d packages across %d groups, price range %.2f–%.2f TRY",
        stats["total_packages"],
        len(group_stats),
        stats["price_min"],
        stats["price_max"],
    )

    return {
        "packages": packages,
        "by_code": by_code,
        "group_stats": group_stats,
        "stats": stats,
    }


# ── JSON export ───────────────────────────────────────────────────────────


def export_catalogs(
    ek2b_data: dict[str, Any] | None = None,
    ek2c_data: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """
    Export parsed catalogs to JSON files in data/ directory.

    Returns paths to the two JSON files.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    if ek2b_data is None:
        ek2b_data = parse_ek2b()
    if ek2c_data is None:
        ek2c_data = parse_ek2c()

    # For JSON export, include procedures/packages list and stats (not by_code)
    ek2b_export = {
        "procedures": ek2b_data["procedures"],
        "stats": ek2b_data["stats"],
    }
    ek2c_export = {
        "packages": ek2c_data["packages"],
        "group_stats": ek2c_data["group_stats"],
        "stats": ek2c_data["stats"],
    }

    with open(EK2B_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(ek2b_export, f, ensure_ascii=False, indent=2)
    logger.info("Exported EK-2B to %s", EK2B_JSON_PATH)

    with open(EK2C_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(ek2c_export, f, ensure_ascii=False, indent=2)
    logger.info("Exported EK-2C to %s", EK2C_JSON_PATH)

    return EK2B_JSON_PATH, EK2C_JSON_PATH


# ── Catalog loader ────────────────────────────────────────────────────────

# Module-level cache
_catalog_cache: dict[str, Any] | None = None


def load_sut_catalog(force_reload: bool = False) -> dict[str, Any]:
    """
    Load the parsed SUT catalog. Tries JSON cache first, falls back to Excel.

    Returns:
        Dict with keys "ek2b" and "ek2c", each containing parsed data
        with "procedures"/"packages", "by_code", and "stats".
    """
    global _catalog_cache

    if _catalog_cache is not None and not force_reload:
        return _catalog_cache

    # Try loading from JSON first (fast path)
    if EK2B_JSON_PATH.exists() and EK2C_JSON_PATH.exists():
        logger.info("Loading SUT catalog from JSON cache")
        try:
            with open(EK2B_JSON_PATH, encoding="utf-8") as f:
                ek2b_raw = json.load(f)
            with open(EK2C_JSON_PATH, encoding="utf-8") as f:
                ek2c_raw = json.load(f)

            # Rebuild by_code index from procedures/packages list
            ek2b_by_code = {p["code"]: p for p in ek2b_raw["procedures"]}
            ek2c_by_code = {p["package_code"]: p for p in ek2c_raw["packages"]}

            _catalog_cache = {
                "ek2b": {
                    "procedures": ek2b_raw["procedures"],
                    "by_code": ek2b_by_code,
                    "stats": ek2b_raw["stats"],
                },
                "ek2c": {
                    "packages": ek2c_raw["packages"],
                    "by_code": ek2c_by_code,
                    "group_stats": ek2c_raw.get("group_stats", {}),
                    "stats": ek2c_raw["stats"],
                },
            }
            logger.info(
                "SUT catalog loaded: %d EK-2B procedures, %d EK-2C packages",
                len(ek2b_by_code),
                len(ek2c_by_code),
            )
            return _catalog_cache
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("JSON cache corrupted, falling back to Excel: %s", e)

    # Fall back to parsing Excel files
    logger.info("Parsing SUT catalog from Excel files")
    ek2b_data = parse_ek2b()
    ek2c_data = parse_ek2c()

    # Export to JSON for next time
    try:
        export_catalogs(ek2b_data, ek2c_data)
    except OSError as e:
        logger.warning("Could not export JSON cache: %s", e)

    _catalog_cache = {"ek2b": ek2b_data, "ek2c": ek2c_data}
    return _catalog_cache


# ── Lab price lookup ──────────────────────────────────────────────────────


def get_lab_price(test_name: str) -> float | None:
    """
    Get the SUT gazette price (TRY) for an ILAY lab test name.

    Args:
        test_name: ILAY test name (e.g., "ALT", "CRP", "Hemoglobin")

    Returns:
        Price in TRY, or None if the test is not in the mapping or catalog.
    """
    sut_code = ILAY_TO_SUT_CODE.get(test_name)
    if sut_code is None:
        return None

    catalog = load_sut_catalog()
    entry = catalog["ek2b"]["by_code"].get(str(sut_code))
    if entry is None:
        return None

    return entry["price_try"]


def get_all_lab_prices() -> dict[str, float]:
    """
    Get SUT gazette prices for all mapped ILAY lab test names.

    Returns:
        Dict mapping test_name → price_try for all tests in ILAY_TO_SUT_CODE
        that have a valid price in the catalog.
    """
    catalog = load_sut_catalog()
    by_code = catalog["ek2b"]["by_code"]

    result: dict[str, float] = {}
    for test_name, sut_code in ILAY_TO_SUT_CODE.items():
        entry = by_code.get(str(sut_code))
        if entry is not None:
            result[test_name] = entry["price_try"]

    return result


def get_visit_prices() -> dict[str, float]:
    """
    Get SUT gazette prices for bed and visit codes (510xxx, 520xxx).

    Returns:
        Dict mapping descriptive key → price_try.
    """
    catalog = load_sut_catalog()
    by_code = catalog["ek2b"]["by_code"]

    # Key bed/visit codes
    visit_code_map = {
        "standard_bed": "510010",  # Standart yatak tarifesi
        "incubator": "510070",  # Kuvöz
        "icu": "510090",  # Yoğun bakım
        "sterile_room": "510100",  # Steril oda
        "day_bed": "510120",  # Gündüz yatak tarifesi
        "consultation": "520010",  # Konsültasyon
        "emergency_visit": "520020",  # Acil poliklinik muayenesi
        "outpatient_visit": "520030",  # Normal poliklinik muayenesi
        "primary_care_visit": "520080",  # Birinci basamak poliklinik muayenesi
    }

    result: dict[str, float] = {}
    for key, code in visit_code_map.items():
        entry = by_code.get(code)
        if entry is not None:
            result[key] = entry["price_try"]

    return result


def get_ek2c_group_price_ranges() -> dict[str, tuple[float, float]]:
    """
    Get (min, max) price ranges per EK-2C procedure group.

    Returns:
        Dict mapping group name → (min_price, max_price).
    """
    catalog = load_sut_catalog()
    group_stats = catalog["ek2c"].get("group_stats", {})

    result: dict[str, tuple[float, float]] = {}
    for grp, stats in group_stats.items():
        result[grp] = (stats["price_min"], stats["price_max"])

    return result


# ── CLI entry point ───────────────────────────────────────────────────────


def main() -> None:
    """Parse Excel files and export JSON catalogs."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    logger.info("=== SUT Catalog Parser ===")

    ek2b = parse_ek2b()
    ek2c = parse_ek2c()

    p1, p2 = export_catalogs(ek2b, ek2c)
    logger.info("Exported: %s, %s", p1, p2)

    # Print summary
    print(f"\nEK-2B: {ek2b['stats']['total_procedures']} procedures")
    print(
        f"  Price range: {ek2b['stats']['price_min']}–{ek2b['stats']['price_max']} TRY"
    )
    print(f"  Categories: {ek2b['stats']['categories']}")

    print(f"\nEK-2C: {ek2c['stats']['total_packages']} packages")
    print(
        f"  Price range: {ek2c['stats']['price_min']}–{ek2c['stats']['price_max']} TRY"
    )
    print(f"  Groups: {ek2c['stats']['unique_groups']}")
    for grp, gs in sorted(ek2c["group_stats"].items()):
        print(f"    {grp}: {gs['count']} pkgs, {gs['price_min']}–{gs['price_max']} TRY")

    # Verify ILAY lab mappings
    print("\nILAY Lab Price Mapping:")
    lab_prices = get_all_lab_prices()
    for name, price in sorted(lab_prices.items(), key=lambda x: x[1], reverse=True):
        print(f"  {name:20s} → {price:>10.2f} TRY (SUT code {ILAY_TO_SUT_CODE[name]})")

    print(f"\n{len(lab_prices)}/{len(ILAY_TO_SUT_CODE)} tests mapped successfully")


if __name__ == "__main__":
    main()
