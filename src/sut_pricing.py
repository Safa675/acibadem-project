"""
sut_pricing.py
SUT (Sağlık Uygulama Tebliği) pricing engine for ILAY.

Maps patient healthcare utilization data to estimated cost ranges (TRY)
based on Turkish Health Implementation Communiqué price schedules.

SUT establishes min/max reimbursement prices for every medical procedure,
lab test, and clinical service in Turkey's healthcare system. This module
translates ILAY's patient-level data (lab tests, visits, prescriptions,
comorbidities) into concrete cost estimates that actuaries and private
hospitals can use for financial planning.

Finance analogy:
  - SUT prices are like "bid/ask" spreads in bond markets
  - Per-patient cost estimate is like portfolio valuation
  - Cost breakdown by category is like sector exposure analysis
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("ilay.sut_pricing")

# ── SUT Price Catalog ─────────────────────────────────────────────────────
# Prices loaded from real SUT gazette data (EK-2B, EK-2C) via sut_catalog.py.
# Falls back to representative estimates if catalog is unavailable.

# Fallback representative prices (used ONLY when gazette catalog fails)
_FALLBACK_LAB_PRICES: dict[str, tuple[float, float]] = {
    "CRP": (15.0, 25.0),
    "Lökosit": (8.0, 15.0),
    "Nötrofil": (8.0, 15.0),
    "Lenfosit": (8.0, 15.0),
    "Eozinofil": (8.0, 15.0),
    "Monosit": (8.0, 15.0),
    "Bazofil": (8.0, 15.0),
    "Prokalsitonin": (45.0, 80.0),
    "Kreatinin": (10.0, 18.0),
    "Üre": (8.0, 15.0),
    "GFR": (10.0, 20.0),
    "Bilirubin": (10.0, 18.0),
    "ALT": (10.0, 18.0),
    "AST": (10.0, 18.0),
    "ALP": (10.0, 18.0),
    "GGT": (10.0, 18.0),
    "Hemoglobin": (8.0, 15.0),
    "Hematokrit": (8.0, 15.0),
    "Eritrosit": (8.0, 15.0),
    "Trombosit": (8.0, 15.0),
    "MCV": (8.0, 15.0),
    "MCH": (8.0, 15.0),
    "RDW": (8.0, 15.0),
    "Glukoz": (8.0, 15.0),
    "HbA1c": (25.0, 45.0),
    "Kolesterol": (10.0, 18.0),
    "Trigliserid": (10.0, 18.0),
    "LDL": (10.0, 18.0),
    "HDL": (10.0, 18.0),
    "Sodyum": (8.0, 15.0),
    "Potasyum": (8.0, 15.0),
    "Kalsiyum": (8.0, 15.0),
    "Albumin": (10.0, 18.0),
    "Protein": (10.0, 18.0),
    "TSH": (20.0, 35.0),
    "T3": (20.0, 35.0),
    "T4": (20.0, 35.0),
    "INR": (12.0, 22.0),
    "PT": (12.0, 22.0),
    "aPTT": (12.0, 22.0),
}


def _load_gazette_lab_prices() -> dict[str, tuple[float, float]]:
    """
    Load real SUT gazette lab prices via sut_catalog.py.

    Returns dict mapping test_name → (price, price) as a point estimate
    from the official gazette (EK-2B). Falls back to representative ranges.
    """
    try:
        from src.sut_catalog import get_all_lab_prices, get_visit_prices

        gazette_prices = get_all_lab_prices()
        if gazette_prices:
            result: dict[str, tuple[float, float]] = {}
            for name, price in gazette_prices.items():
                # Gazette gives a single point price; use as both min and max
                result[name] = (price, price)
            logger.info(
                "Loaded %d real gazette lab prices (e.g. CRP=%.2f TRY)",
                len(result),
                gazette_prices.get("CRP", 0),
            )
            return result
    except Exception as e:
        logger.warning("Failed to load gazette lab prices, using fallback: %s", e)
    return _FALLBACK_LAB_PRICES.copy()


def _load_gazette_visit_prices() -> dict[str, tuple[float, float]]:
    """
    Load real SUT gazette visit/bed prices via sut_catalog.py.
    Falls back to representative ranges.
    """
    try:
        from src.sut_catalog import get_visit_prices

        gazette = get_visit_prices()
        if gazette:
            # Map gazette keys to our internal keys
            result: dict[str, tuple[float, float]] = {}
            # outpatient = normal poliklinik muayenesi
            op = gazette.get("outpatient_visit")
            if op:
                result["outpatient"] = (op, op)
            # inpatient = standard bed per day
            bed = gazette.get("standard_bed")
            if bed:
                result["inpatient_day"] = (bed, bed)
            # ICU = yoğun bakım
            icu = gazette.get("icu")
            if icu:
                result["icu_day"] = (icu, icu)
            # Emergency
            er = gazette.get("emergency_visit")
            if er:
                result["emergency"] = (er, er)
            # Follow-up = primary care
            fu = gazette.get("primary_care_visit")
            if fu:
                result["follow_up"] = (fu, fu)
            if result:
                logger.info("Loaded %d gazette visit prices", len(result))
                # Fill missing with fallback
                for k, v in _FALLBACK_VISIT_PRICES.items():
                    if k not in result:
                        result[k] = v
                return result
    except Exception as e:
        logger.warning("Failed to load gazette visit prices, using fallback: %s", e)
    return _FALLBACK_VISIT_PRICES.copy()


# Initialize from gazette (runs once at import time)
_FALLBACK_VISIT_PRICES: dict[str, tuple[float, float]] = {
    "outpatient": (80.0, 200.0),
    "inpatient_day": (250.0, 600.0),
    "icu_day": (800.0, 2500.0),
    "emergency": (150.0, 400.0),
    "follow_up": (50.0, 120.0),
}

SUT_LAB_PRICES: dict[str, tuple[float, float]] = _load_gazette_lab_prices()

# Pre-build lowercase index for O(1) partial matching
_SUT_LAB_PRICES_LOWER: dict[str, tuple[float, float]] = {
    k.lower(): v for k, v in SUT_LAB_PRICES.items()
}

# Default price for unlisted lab tests (gazette median for lab category)
SUT_LAB_DEFAULT: tuple[float, float] = (8.0, 15.0)

# Visit type prices — loaded from gazette when available
SUT_VISIT_PRICES: dict[str, tuple[float, float]] = _load_gazette_visit_prices()

# Prescription cost tiers: drug complexity → per-prescription (min_try, max_try)
SUT_RX_PRICES: dict[str, tuple[float, float]] = {
    "basic": (10.0, 40.0),  # common generics (antihypertensives, NSAIDs)
    "moderate": (40.0, 150.0),  # branded drugs, injectables
    "specialty": (150.0, 800.0),  # biologics, oncology, immunosuppressants
}
SUT_RX_DEFAULT: tuple[float, float] = (20.0, 80.0)

# Comorbidity-linked procedure cost ranges per episode
# These represent additional procedure costs triggered by specific conditions
SUT_COMORBIDITY_PROCEDURE_COSTS: dict[str, tuple[float, float]] = {
    "Hipertansiyon": (100.0, 500.0),  # BP monitoring, echo, ECG
    "Kalp Damar": (500.0, 5000.0),  # Cardiac cath, angiography, stent
    "Diyabet": (200.0, 1000.0),  # HbA1c monitoring, retinal screening
    "Kan Hastalıkları": (300.0, 2000.0),  # Hematology workup, transfusion
    "Kronik Hastalıklar Diğer": (200.0, 1500.0),  # Chronic disease management
    "Ameliyat Geçmişi": (1000.0, 15000.0),  # Post-surgical follow-up, revision
}

# ICD-10 chapter → estimated procedure cost range
# Maps first character of TANIKODU to typical intervention costs
SUT_ICD10_PROCEDURE_COSTS: dict[str, tuple[float, float]] = {
    "I": (500.0, 8000.0),  # Circulatory — cardiac procedures, vascular surgery
    "C": (1000.0, 25000.0),  # Cancer — oncology, radiation, chemo
    "J": (200.0, 3000.0),  # Respiratory — bronchoscopy, pulmonary function
    "K": (300.0, 5000.0),  # Digestive — endoscopy, colonoscopy
    "G": (400.0, 6000.0),  # Neurological — EEG, MRI, nerve conduction
    "E": (150.0, 1500.0),  # Endocrine — thyroid workup, insulin pump
    "M": (200.0, 4000.0),  # Musculoskeletal — joint replacement, physio
    "N": (300.0, 4000.0),  # Genitourinary — dialysis, cystoscopy
    "L": (100.0, 1000.0),  # Dermatological — biopsy, phototherapy
    "F": (100.0, 800.0),  # Mental health — psych evaluation
    "H": (150.0, 2000.0),  # Eye/ear — cataract, audiometry
    "R": (50.0, 300.0),  # Symptoms — diagnostic workup
    "Z": (50.0, 200.0),  # Check-ups — preventive screening
}


# ── Data structures ──────────────────────────────────────────────────────


@dataclass
class SUTCostBreakdown:
    """Cost breakdown by category for a single patient."""

    lab_cost_min: float = 0.0
    lab_cost_max: float = 0.0
    visit_cost_min: float = 0.0
    visit_cost_max: float = 0.0
    rx_cost_min: float = 0.0
    rx_cost_max: float = 0.0
    procedure_cost_min: float = 0.0
    procedure_cost_max: float = 0.0

    @property
    def total_min(self) -> float:
        return (
            self.lab_cost_min
            + self.visit_cost_min
            + self.rx_cost_min
            + self.procedure_cost_min
        )

    @property
    def total_max(self) -> float:
        return (
            self.lab_cost_max
            + self.visit_cost_max
            + self.rx_cost_max
            + self.procedure_cost_max
        )

    @property
    def total_mid(self) -> float:
        return (self.total_min + self.total_max) / 2.0


@dataclass
class PatientSUTEstimate:
    """Full SUT cost estimate for a single patient."""

    patient_id: str
    cost_min: float
    cost_max: float
    cost_mid: float
    breakdown: SUTCostBreakdown
    n_lab_tests: int = 0
    n_visits: int = 0
    n_prescriptions: int = 0
    n_procedures: int = 0
    cost_tier: str = ""
    cost_tier_label: str = ""


# ── Cost tier classification ──────────────────────────────────────────────

COST_TIERS: list[tuple[float, str, str]] = [
    (10000, "Very High", "Yüksek maliyet — aktif müdahale beklenir"),
    (5000, "High", "Yüksek — yakın takip ve bütçe planlaması gerekir"),
    (2000, "Moderate", "Orta düzey — rutin bakım maliyeti"),
    (500, "Low", "Düşük — minimal kaynak tüketimi"),
    (0, "Minimal", "Minimal maliyet — koruyucu sağlık hizmeti"),
]


def _assign_cost_tier(cost_mid: float) -> tuple[str, str]:
    """Assign cost tier based on midpoint estimate."""
    for threshold, tier, label in COST_TIERS:
        if cost_mid >= threshold:
            return tier, label
    return "Minimal", COST_TIERS[-1][2]


# ── Lab cost estimation ──────────────────────────────────────────────────


def _estimate_lab_costs(
    lab_df: pd.DataFrame,
    patient_id: str,
    lab_group_idx: dict[str, np.ndarray] | None = None,
) -> tuple[float, float, int]:
    """
    Estimate lab test costs for a patient based on SUT pricing.

    Returns (min_cost, max_cost, n_tests).
    """
    if lab_df.empty:
        return 0.0, 0.0, 0

    if lab_group_idx is not None and patient_id in lab_group_idx:
        patient_labs = lab_df.iloc[lab_group_idx[patient_id]]
    else:
        patient_labs = lab_df[lab_df["patient_id"] == patient_id]

    if patient_labs.empty:
        return 0.0, 0.0, 0

    total_min = 0.0
    total_max = 0.0
    n_tests = 0

    if "test_name" in patient_labs.columns:
        test_counts = patient_labs["test_name"].value_counts()
        for test_name, count in test_counts.items():
            test_str = str(test_name).strip()
            # Try exact match first, then lowercase match
            price = SUT_LAB_PRICES.get(test_str)
            if price is None:
                price = _SUT_LAB_PRICES_LOWER.get(test_str.lower())
            if price is None:
                price = SUT_LAB_DEFAULT
            total_min += price[0] * count
            total_max += price[1] * count
            n_tests += count
    else:
        # No test_name column; count rows as generic tests
        n_tests = len(patient_labs)
        total_min = SUT_LAB_DEFAULT[0] * n_tests
        total_max = SUT_LAB_DEFAULT[1] * n_tests

    return total_min, total_max, n_tests


# ── Visit cost estimation ────────────────────────────────────────────────


def _estimate_visit_costs(
    ana_df: pd.DataFrame,
    patient_id: str,
    ana_group_idx: dict[str, np.ndarray] | None = None,
) -> tuple[float, float, int]:
    """
    Estimate visit costs based on SUT pricing.

    Uses LOS (length of stay) to differentiate visit types:
    - LOS = 0 or NaN → outpatient visit
    - LOS >= 1 → inpatient (per day)

    Returns (min_cost, max_cost, n_visits).
    """
    if ana_df.empty:
        return 0.0, 0.0, 0

    if ana_group_idx is not None and patient_id in ana_group_idx:
        patient_visits = ana_df.iloc[ana_group_idx[patient_id]]
    else:
        patient_visits = ana_df[ana_df["patient_id"] == patient_id]

    if patient_visits.empty:
        return 0.0, 0.0, 0

    total_min = 0.0
    total_max = 0.0
    n_visits = len(patient_visits)

    for _, row in patient_visits.iterrows():
        los = row.get("los_days")
        if pd.notna(los) and float(los) >= 1:
            # Inpatient: charge per day
            days = float(los)
            price = SUT_VISIT_PRICES["inpatient_day"]
            total_min += price[0] * days
            total_max += price[1] * days
        else:
            # Outpatient visit
            price = SUT_VISIT_PRICES["outpatient"]
            total_min += price[0]
            total_max += price[1]

    return total_min, total_max, n_visits


# ── Prescription cost estimation ─────────────────────────────────────────


def _estimate_rx_costs(
    rec_df: pd.DataFrame,
    patient_id: str,
    rec_group_idx: dict[str, np.ndarray] | None = None,
) -> tuple[float, float, int]:
    """
    Estimate prescription costs based on SUT pricing.

    Uses a default per-prescription cost range since drug-level SUT mapping
    requires a pharmaceutical database not yet integrated.

    Returns (min_cost, max_cost, n_prescriptions).
    """
    if rec_df.empty:
        return 0.0, 0.0, 0

    if rec_group_idx is not None and patient_id in rec_group_idx:
        patient_rx = rec_df.iloc[rec_group_idx[patient_id]]
    else:
        patient_rx = rec_df[rec_df["patient_id"] == patient_id]

    if patient_rx.empty:
        return 0.0, 0.0, 0

    n_rx = len(patient_rx)
    price = SUT_RX_DEFAULT
    return price[0] * n_rx, price[1] * n_rx, n_rx


# ── Comorbidity-linked procedure cost estimation ────────────────────────


def _estimate_procedure_costs(
    ana_df: pd.DataFrame,
    patient_id: str,
    ana_group_idx: dict[str, np.ndarray] | None = None,
) -> tuple[float, float, int]:
    """
    Estimate procedure costs linked to comorbidities and diagnoses.

    Maps:
    1. Comorbidity flags → SUT procedure cost ranges
    2. TANIKODU (ICD-10 code) → procedure cost ranges

    Returns (min_cost, max_cost, n_procedures).
    """
    if ana_df.empty:
        return 0.0, 0.0, 0

    if ana_group_idx is not None and patient_id in ana_group_idx:
        patient_data = ana_df.iloc[ana_group_idx[patient_id]]
    else:
        patient_data = ana_df[ana_df["patient_id"] == patient_id]

    if patient_data.empty:
        return 0.0, 0.0, 0

    total_min = 0.0
    total_max = 0.0
    n_procedures = 0

    # Comorbidity-linked procedures (use latest visit data)
    latest = patient_data.iloc[-1]
    comorbidity_map = {
        "Hipertansiyon Hastada": "Hipertansiyon",
        "Kalp Damar Hastada": "Kalp Damar",
        "Diyabet Hastada": "Diyabet",
        "Kan Hastalıkları Hastada": "Kan Hastalıkları",
        "Kronik Hastalıklar Diğer": "Kronik Hastalıklar Diğer",
        "Ameliyat Geçmişi": "Ameliyat Geçmişi",
    }

    for col_name, sut_key in comorbidity_map.items():
        if col_name in patient_data.columns:
            val = latest.get(col_name)
            if pd.notna(val) and val:
                has_condition = (isinstance(val, str) and len(val.strip()) >= 1) or (
                    not isinstance(val, str) and val > 0
                )
                if has_condition and sut_key in SUT_COMORBIDITY_PROCEDURE_COSTS:
                    price = SUT_COMORBIDITY_PROCEDURE_COSTS[sut_key]
                    total_min += price[0]
                    total_max += price[1]
                    n_procedures += 1

    # ICD-10 diagnosis-linked procedures
    if "TANIKODU" in patient_data.columns:
        seen_chapters: set[str] = set()
        for _, row in patient_data.iterrows():
            code = row.get("TANIKODU")
            if pd.notna(code):
                code_str = str(code).strip()
                if code_str:
                    chapter = code_str[0].upper()
                    if (
                        chapter not in seen_chapters
                        and chapter in SUT_ICD10_PROCEDURE_COSTS
                    ):
                        seen_chapters.add(chapter)
                        price = SUT_ICD10_PROCEDURE_COSTS[chapter]
                        total_min += price[0]
                        total_max += price[1]
                        n_procedures += 1

    return total_min, total_max, n_procedures


# ── Main per-patient estimation ──────────────────────────────────────────


def estimate_patient_sut_costs(
    patient_id: str,
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    lab_group_idx: dict[str, np.ndarray] | None = None,
    ana_group_idx: dict[str, np.ndarray] | None = None,
    rec_group_idx: dict[str, np.ndarray] | None = None,
) -> PatientSUTEstimate:
    """
    Compute full SUT cost estimate for a single patient.

    Aggregates costs from four categories:
    1. Lab tests — mapped to SUT test prices
    2. Visits — outpatient/inpatient based on LOS
    3. Prescriptions — default per-Rx cost range
    4. Procedures — comorbidity + ICD-10 linked

    Args:
        patient_id: Patient identifier
        lab_df: Lab results DataFrame
        ana_df: Visit records DataFrame
        rec_df: Prescriptions DataFrame
        lab_group_idx: Pre-built lab groupby index (optional, for O(1) lookup)
        ana_group_idx: Pre-built anadata groupby index (optional)
        rec_group_idx: Pre-built recete groupby index (optional)

    Returns:
        PatientSUTEstimate with cost breakdown
    """
    breakdown = SUTCostBreakdown()

    # Lab costs
    lab_min, lab_max, n_labs = _estimate_lab_costs(lab_df, patient_id, lab_group_idx)
    breakdown.lab_cost_min = lab_min
    breakdown.lab_cost_max = lab_max

    # Visit costs
    visit_min, visit_max, n_visits = _estimate_visit_costs(
        ana_df, patient_id, ana_group_idx
    )
    breakdown.visit_cost_min = visit_min
    breakdown.visit_cost_max = visit_max

    # Prescription costs
    rx_min, rx_max, n_rx = _estimate_rx_costs(rec_df, patient_id, rec_group_idx)
    breakdown.rx_cost_min = rx_min
    breakdown.rx_cost_max = rx_max

    # Procedure costs
    proc_min, proc_max, n_procs = _estimate_procedure_costs(
        ana_df, patient_id, ana_group_idx
    )
    breakdown.procedure_cost_min = proc_min
    breakdown.procedure_cost_max = proc_max

    cost_mid = breakdown.total_mid
    tier, tier_label = _assign_cost_tier(cost_mid)

    return PatientSUTEstimate(
        patient_id=patient_id,
        cost_min=round(breakdown.total_min, 2),
        cost_max=round(breakdown.total_max, 2),
        cost_mid=round(cost_mid, 2),
        breakdown=breakdown,
        n_lab_tests=n_labs,
        n_visits=n_visits,
        n_prescriptions=n_rx,
        n_procedures=n_procs,
        cost_tier=tier,
        cost_tier_label=tier_label,
    )


# ── Batch computation ────────────────────────────────────────────────────


def compute_all_sut_costs(
    lab_df: pd.DataFrame,
    ana_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    patient_ids: list[str] | None = None,
) -> dict[str, PatientSUTEstimate]:
    """
    Compute SUT cost estimates for all patients.

    Args:
        lab_df: Lab results DataFrame
        ana_df: Visit records DataFrame
        rec_df: Prescriptions DataFrame
        patient_ids: Optional subset. If None, uses all patients from ana_df.

    Returns:
        Dict mapping patient_id → PatientSUTEstimate
    """
    import time

    t0 = time.perf_counter()

    if patient_ids is None:
        all_ids: set[str] = set()
        if not ana_df.empty and "patient_id" in ana_df.columns:
            all_ids.update(ana_df["patient_id"].unique().astype(str))
        if not lab_df.empty and "patient_id" in lab_df.columns:
            all_ids.update(lab_df["patient_id"].unique().astype(str))
        patient_ids = sorted(all_ids)

    n = len(patient_ids)
    if n == 0:
        return {}

    logger.info("Computing SUT costs for %d patients...", n)

    # Build group indices for O(1) lookups
    lab_group_idx: dict[str, np.ndarray] = {}
    if not lab_df.empty and "patient_id" in lab_df.columns:
        lab_group_idx = {
            str(pid): idx
            for pid, idx in lab_df.groupby(
                "patient_id", sort=False, observed=True
            ).groups.items()
        }

    ana_group_idx: dict[str, np.ndarray] = {}
    if not ana_df.empty and "patient_id" in ana_df.columns:
        ana_group_idx = {
            str(pid): idx
            for pid, idx in ana_df.groupby(
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

    results: dict[str, PatientSUTEstimate] = {}
    for pid in patient_ids:
        results[pid] = estimate_patient_sut_costs(
            pid,
            lab_df,
            ana_df,
            rec_df,
            lab_group_idx,
            ana_group_idx,
            rec_group_idx,
        )

    elapsed = time.perf_counter() - t0

    # Log summary statistics
    costs = [r.cost_mid for r in results.values()]
    if costs:
        logger.info(
            "SUT costs computed for %d patients in %.1fs — "
            "mean=%.0f TRY, median=%.0f TRY, total=%.0f TRY",
            n,
            elapsed,
            np.mean(costs),
            np.median(costs),
            np.sum(costs),
        )

        # Log tier distribution
        tier_counts: dict[str, int] = {}
        for r in results.values():
            tier_counts[r.cost_tier] = tier_counts.get(r.cost_tier, 0) + 1
        for tier_name in ["Very High", "High", "Moderate", "Low", "Minimal"]:
            count = tier_counts.get(tier_name, 0)
            logger.info(
                "  %s: %d (%.1f%%)", tier_name, count, count / n * 100 if n else 0
            )

    return results


# ── Cohort summary ───────────────────────────────────────────────────────


def estimate_cohort_sut_summary(
    sut_results: dict[str, PatientSUTEstimate],
) -> dict:
    """
    Compute cohort-level SUT cost summary statistics.

    Returns a dict suitable for API response.
    """
    if not sut_results:
        return {
            "n_patients": 0,
            "total_cost_min": 0.0,
            "total_cost_max": 0.0,
            "total_cost_mid": 0.0,
            "mean_cost_mid": 0.0,
            "median_cost_mid": 0.0,
            "tier_distribution": {},
            "category_totals": {
                "lab": {"min": 0.0, "max": 0.0},
                "visit": {"min": 0.0, "max": 0.0},
                "rx": {"min": 0.0, "max": 0.0},
                "procedure": {"min": 0.0, "max": 0.0},
            },
        }

    n = len(sut_results)
    mids = [r.cost_mid for r in sut_results.values()]

    tier_dist: dict[str, int] = {}
    cat_lab_min = cat_lab_max = 0.0
    cat_visit_min = cat_visit_max = 0.0
    cat_rx_min = cat_rx_max = 0.0
    cat_proc_min = cat_proc_max = 0.0

    for r in sut_results.values():
        tier_dist[r.cost_tier] = tier_dist.get(r.cost_tier, 0) + 1
        cat_lab_min += r.breakdown.lab_cost_min
        cat_lab_max += r.breakdown.lab_cost_max
        cat_visit_min += r.breakdown.visit_cost_min
        cat_visit_max += r.breakdown.visit_cost_max
        cat_rx_min += r.breakdown.rx_cost_min
        cat_rx_max += r.breakdown.rx_cost_max
        cat_proc_min += r.breakdown.procedure_cost_min
        cat_proc_max += r.breakdown.procedure_cost_max

    return {
        "n_patients": n,
        "total_cost_min": round(sum(r.cost_min for r in sut_results.values()), 2),
        "total_cost_max": round(sum(r.cost_max for r in sut_results.values()), 2),
        "total_cost_mid": round(sum(mids), 2),
        "mean_cost_mid": round(float(np.mean(mids)), 2),
        "median_cost_mid": round(float(np.median(mids)), 2),
        "tier_distribution": tier_dist,
        "category_totals": {
            "lab": {"min": round(cat_lab_min, 2), "max": round(cat_lab_max, 2)},
            "visit": {"min": round(cat_visit_min, 2), "max": round(cat_visit_max, 2)},
            "rx": {"min": round(cat_rx_min, 2), "max": round(cat_rx_max, 2)},
            "procedure": {"min": round(cat_proc_min, 2), "max": round(cat_proc_max, 2)},
        },
    }


# ══════════════════════════════════════════════════════════════════════════
# Phase 4b: DRG Episode Cost Modeling
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class DRGEpisode:
    """A single DRG (Diagnosis-Related Group) care episode."""

    episode_id: int
    primary_icd10: str
    primary_icd10_chapter: str
    description: str
    los_days: float
    lab_cost: float
    visit_cost: float
    rx_cost: float
    procedure_cost: float
    total_cost: float
    admission_date: str | None = None
    discharge_date: str | None = None


@dataclass
class DRGSummary:
    """DRG summary for a patient."""

    patient_id: str
    n_episodes: int
    episodes: list[DRGEpisode]
    total_drg_cost: float
    mean_episode_cost: float
    most_expensive_drg: str
    dominant_icd10_chapter: str


# ICD-10 chapter descriptions
_ICD10_CHAPTER_DESC: dict[str, str] = {
    "A": "Infectious diseases",
    "B": "Infectious diseases",
    "C": "Neoplasms",
    "D": "Blood/immune disorders",
    "E": "Endocrine/metabolic",
    "F": "Mental/behavioral",
    "G": "Nervous system",
    "H": "Eye/ear",
    "I": "Circulatory system",
    "J": "Respiratory system",
    "K": "Digestive system",
    "L": "Skin/subcutaneous",
    "M": "Musculoskeletal",
    "N": "Genitourinary",
    "O": "Pregnancy/childbirth",
    "P": "Perinatal",
    "Q": "Congenital malformations",
    "R": "Symptoms/signs",
    "S": "Injury",
    "T": "Injury/poisoning",
    "U": "Special purpose",
    "V": "External causes",
    "W": "External causes",
    "X": "External causes",
    "Y": "External causes",
    "Z": "Health encounters",
}


def compute_drg_summary(
    patient_id: str,
    ana_df: pd.DataFrame,
    sut_estimate: PatientSUTEstimate,
    ana_group_idx: dict[str, np.ndarray] | None = None,
) -> DRGSummary:
    """
    Build DRG episode cost model for a patient.

    Groups visits by TANIKODU (ICD-10 code) and allocates SUT costs
    proportionally across episodes. Each episode represents a distinct
    clinical encounter grouped by primary diagnosis.

    Args:
        patient_id: Patient identifier
        ana_df: Visit records DataFrame
        sut_estimate: Pre-computed SUT cost estimate for this patient
        ana_group_idx: Pre-built groupby index (optional)

    Returns:
        DRGSummary with per-episode cost breakdown
    """
    if ana_df.empty:
        return DRGSummary(
            patient_id=patient_id,
            n_episodes=0,
            episodes=[],
            total_drg_cost=0.0,
            mean_episode_cost=0.0,
            most_expensive_drg="N/A",
            dominant_icd10_chapter="N/A",
        )

    if ana_group_idx is not None and patient_id in ana_group_idx:
        patient_data = ana_df.iloc[ana_group_idx[patient_id]]
    else:
        patient_data = ana_df[ana_df["patient_id"] == patient_id]

    if patient_data.empty:
        return DRGSummary(
            patient_id=patient_id,
            n_episodes=0,
            episodes=[],
            total_drg_cost=0.0,
            mean_episode_cost=0.0,
            most_expensive_drg="N/A",
            dominant_icd10_chapter="N/A",
        )

    # Group visits by ICD-10 code to form episodes
    episodes: list[DRGEpisode] = []
    chapter_costs: dict[str, float] = {}

    if "TANIKODU" in patient_data.columns:
        grouped = patient_data.groupby("TANIKODU", observed=True)
    else:
        # No diagnosis code → treat everything as a single episode
        grouped = [("R69", patient_data)]

    episode_id = 0
    total_visits = max(len(patient_data), 1)

    for diag_code, group_df in grouped:
        diag_str = str(diag_code).strip()
        if not diag_str or diag_str == "nan":
            diag_str = "R69"  # Unspecified diagnosis

        chapter = diag_str[0].upper() if diag_str else "R"
        desc = _ICD10_CHAPTER_DESC.get(chapter, "Other")

        # LOS for this episode
        los = 0.0
        if "los_days" in group_df.columns:
            los = float(group_df["los_days"].sum())

        # Proportional cost allocation based on number of visits in this episode
        n_visits_episode = len(group_df)
        proportion = n_visits_episode / total_visits

        lab_cost = round(sut_estimate.breakdown.lab_cost_max * proportion, 2)
        visit_cost = round(sut_estimate.breakdown.visit_cost_max * proportion, 2)
        rx_cost = round(sut_estimate.breakdown.rx_cost_max * proportion, 2)

        # Procedure cost: use ICD-10 mapping if available
        proc_price = SUT_ICD10_PROCEDURE_COSTS.get(chapter, (0, 0))
        proc_cost = round((proc_price[0] + proc_price[1]) / 2.0, 2)

        total_ep_cost = round(lab_cost + visit_cost + rx_cost + proc_cost, 2)

        # Extract dates if available
        adm_date = None
        dis_date = None
        if "GELISTARIHI" in group_df.columns:
            dates = group_df["GELISTARIHI"].dropna()
            if not dates.empty:
                adm_date = str(dates.iloc[0])[:10]
                dis_date = str(dates.iloc[-1])[:10]

        episodes.append(
            DRGEpisode(
                episode_id=episode_id,
                primary_icd10=diag_str,
                primary_icd10_chapter=chapter,
                description=f"{desc} ({diag_str})",
                los_days=round(los, 1),
                lab_cost=lab_cost,
                visit_cost=visit_cost,
                rx_cost=rx_cost,
                procedure_cost=proc_cost,
                total_cost=total_ep_cost,
                admission_date=adm_date,
                discharge_date=dis_date,
            )
        )

        chapter_costs[chapter] = chapter_costs.get(chapter, 0) + total_ep_cost
        episode_id += 1

    # Sort episodes by cost descending
    episodes.sort(key=lambda e: e.total_cost, reverse=True)
    total_drg_cost = round(sum(e.total_cost for e in episodes), 2)
    mean_ep_cost = round(total_drg_cost / len(episodes), 2) if episodes else 0.0
    most_expensive = episodes[0].description if episodes else "N/A"
    dominant_chapter = (
        max(chapter_costs, key=chapter_costs.get) if chapter_costs else "N/A"
    )  # type: ignore[arg-type]

    return DRGSummary(
        patient_id=patient_id,
        n_episodes=len(episodes),
        episodes=episodes,
        total_drg_cost=total_drg_cost,
        mean_episode_cost=mean_ep_cost,
        most_expensive_drg=most_expensive,
        dominant_icd10_chapter=dominant_chapter,
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 4c: Cost Value-at-Risk (VaR) via Monte Carlo Simulation
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class CostVaRResult:
    """Monte Carlo Cost VaR result for a patient."""

    patient_id: str
    confidence_level: float  # e.g. 0.95
    var_amount: float  # Cost at specified confidence
    expected_cost: float  # Mean of simulated costs
    cvar_amount: float  # Conditional VaR (Expected Shortfall)
    cost_p5: float  # 5th percentile
    cost_p25: float  # 25th percentile
    cost_p50: float  # Median
    cost_p75: float  # 75th percentile
    cost_p95: float  # 95th percentile
    simulation_count: int
    cost_distribution: list[float]  # Sampled distribution (for histogram)


def compute_cost_var(
    patient_id: str,
    sut_estimate: PatientSUTEstimate,
    confidence: float = 0.95,
    n_simulations: int = 10_000,
    seed: int | None = None,
) -> CostVaRResult:
    """
    Monte Carlo Cost Value-at-Risk (VaR) for a patient.

    Simulates cost outcomes by sampling from triangular distributions
    parameterized by SUT min/max ranges for each cost category.
    The triangular distribution models the min/mode/max nature of SUT pricing.

    Finance analogy:
      - VaR = "What's the maximum cost at 95% confidence?"
      - CVaR = "If costs exceed VaR, what's the average?"

    Args:
        patient_id: Patient identifier
        sut_estimate: Pre-computed SUT cost estimate
        confidence: VaR confidence level (default 0.95)
        n_simulations: Number of Monte Carlo draws (default 10,000)
        seed: Random seed for reproducibility

    Returns:
        CostVaRResult with VaR, CVaR, and distribution percentiles
    """
    rng = np.random.default_rng(seed)
    bd = sut_estimate.breakdown

    # Sample each cost category from triangular(min, mode=mid, max)
    # If min == max (gazette point price), add ±10% perturbation
    def _triangular(lo: float, hi: float, n: int) -> np.ndarray:
        if lo <= 0 and hi <= 0:
            return np.zeros(n)
        lo = max(lo, 0.01)
        hi = max(hi, lo + 0.01)
        mode = (lo + hi) / 2.0
        return rng.triangular(lo, mode, hi, size=n)

    lab_sims = _triangular(bd.lab_cost_min, bd.lab_cost_max, n_simulations)
    visit_sims = _triangular(bd.visit_cost_min, bd.visit_cost_max, n_simulations)
    rx_sims = _triangular(bd.rx_cost_min, bd.rx_cost_max, n_simulations)
    proc_sims = _triangular(bd.procedure_cost_min, bd.procedure_cost_max, n_simulations)

    total_sims = lab_sims + visit_sims + rx_sims + proc_sims
    total_sims.sort()

    # VaR at confidence level
    var_idx = int(np.ceil(confidence * n_simulations)) - 1
    var_amount = float(total_sims[min(var_idx, n_simulations - 1)])

    # CVaR (Expected Shortfall): mean of costs exceeding VaR
    tail = total_sims[total_sims >= var_amount]
    cvar_amount = float(np.mean(tail)) if len(tail) > 0 else var_amount

    # Distribution percentiles
    p5, p25, p50, p75, p95 = np.percentile(total_sims, [5, 25, 50, 75, 95])

    # Subsample distribution for frontend histogram (100 bins)
    hist_sample = np.percentile(total_sims, np.linspace(0, 100, 101)).tolist()

    return CostVaRResult(
        patient_id=patient_id,
        confidence_level=confidence,
        var_amount=round(var_amount, 2),
        expected_cost=round(float(np.mean(total_sims)), 2),
        cvar_amount=round(cvar_amount, 2),
        cost_p5=round(float(p5), 2),
        cost_p25=round(float(p25), 2),
        cost_p50=round(float(p50), 2),
        cost_p75=round(float(p75), 2),
        cost_p95=round(float(p95), 2),
        simulation_count=n_simulations,
        cost_distribution=[round(x, 2) for x in hist_sample],
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 4d: Reimbursement Gap Analysis
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class ReimbursementGap:
    """Gap between estimated actual cost and SUT reimbursement ceiling."""

    category: str  # lab, visit, rx, procedure
    estimated_actual_cost: float  # Hospital's real cost (mid estimate)
    sut_reimbursement: float  # SUT ceiling (max price)
    gap_amount: float  # actual - reimbursement (positive = loss)
    gap_percent: float  # gap as % of actual cost
    status: str  # "covered", "partial", "deficit"


@dataclass
class ReimbursementGapAnalysis:
    """Full reimbursement gap analysis for a patient."""

    patient_id: str
    gaps: list[ReimbursementGap]
    total_estimated_cost: float
    total_reimbursement: float
    total_gap: float
    overall_coverage_pct: float
    risk_rating: str  # "low", "medium", "high"


# Hospital actual cost multipliers relative to SUT max prices.
# These represent the typical markup hospitals charge above SUT ceilings.
# Based on Turkish hospital industry reports: actual costs often 1.2-2.5x SUT.
_HOSPITAL_MARKUP: dict[str, float] = {
    "lab": 1.3,  # Labs typically 30% above SUT
    "visit": 1.5,  # Visits/beds 50% above SUT
    "rx": 1.8,  # Drugs highly marked up
    "procedure": 2.0,  # Procedures highest markup
}


def compute_reimbursement_gaps(
    patient_id: str,
    sut_estimate: PatientSUTEstimate,
) -> ReimbursementGapAnalysis:
    """
    Analyze gap between estimated hospital costs and SUT reimbursement.

    Models the financial risk hospitals face when actual service delivery
    costs exceed what SGK (Social Security) reimburses under SUT.

    Finance analogy: This is like analyzing basis risk in insurance —
    the gap between what the policy covers and actual losses.

    Args:
        patient_id: Patient identifier
        sut_estimate: Pre-computed SUT cost estimate

    Returns:
        ReimbursementGapAnalysis with per-category gap breakdown
    """
    bd = sut_estimate.breakdown
    gaps: list[ReimbursementGap] = []

    categories = [
        ("lab", bd.lab_cost_min, bd.lab_cost_max),
        ("visit", bd.visit_cost_min, bd.visit_cost_max),
        ("rx", bd.rx_cost_min, bd.rx_cost_max),
        ("procedure", bd.procedure_cost_min, bd.procedure_cost_max),
    ]

    total_actual = 0.0
    total_reimbursement = 0.0

    for cat, cost_min, cost_max in categories:
        sut_ceiling = cost_max  # SUT pays up to max
        markup = _HOSPITAL_MARKUP.get(cat, 1.5)
        estimated_actual = round(cost_max * markup, 2)

        gap_amount = round(estimated_actual - sut_ceiling, 2)
        gap_pct = (
            round((gap_amount / estimated_actual) * 100, 1)
            if estimated_actual > 0
            else 0.0
        )

        if gap_pct <= 5:
            status = "covered"
        elif gap_pct <= 25:
            status = "partial"
        else:
            status = "deficit"

        gaps.append(
            ReimbursementGap(
                category=cat,
                estimated_actual_cost=estimated_actual,
                sut_reimbursement=round(sut_ceiling, 2),
                gap_amount=gap_amount,
                gap_percent=gap_pct,
                status=status,
            )
        )

        total_actual += estimated_actual
        total_reimbursement += sut_ceiling

    total_gap = round(total_actual - total_reimbursement, 2)
    coverage_pct = (
        round((total_reimbursement / total_actual) * 100, 1)
        if total_actual > 0
        else 100.0
    )

    # Risk rating
    if coverage_pct >= 85:
        risk_rating = "low"
    elif coverage_pct >= 65:
        risk_rating = "medium"
    else:
        risk_rating = "high"

    return ReimbursementGapAnalysis(
        patient_id=patient_id,
        gaps=gaps,
        total_estimated_cost=round(total_actual, 2),
        total_reimbursement=round(total_reimbursement, 2),
        total_gap=total_gap,
        overall_coverage_pct=coverage_pct,
        risk_rating=risk_rating,
    )


# ══════════════════════════════════════════════════════════════════════════
# Phase 4e: Cost Trajectory Forecasting
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class CostTrajectoryPoint:
    """A single point on the cost trajectory timeline."""

    period: str  # e.g. "2024-Q1", "Month 3"
    cumulative_cost: float
    period_cost: float
    n_visits: int
    n_tests: int


@dataclass
class CostTrajectory:
    """Forward cost trajectory forecast for a patient."""

    patient_id: str
    trajectory: list[CostTrajectoryPoint]
    total_forecast_cost: float
    forecast_horizon_months: int
    trend: str  # "increasing", "stable", "decreasing"
    monthly_burn_rate: float  # Average cost per month
    projected_annual_cost: float


def compute_cost_trajectory(
    patient_id: str,
    ana_df: pd.DataFrame,
    lab_df: pd.DataFrame,
    sut_estimate: PatientSUTEstimate,
    ana_group_idx: dict[str, np.ndarray] | None = None,
    lab_group_idx: dict[str, np.ndarray] | None = None,
    forecast_months: int = 12,
) -> CostTrajectory:
    """
    Build historical cost trajectory and project forward.

    Uses the patient's visit and lab history to establish a monthly
    cost run-rate, then extrapolates forward with trend detection.

    Finance analogy: Like projecting cash burn rate for a startup —
    historical spending pattern → future cost projection.

    Args:
        patient_id: Patient identifier
        ana_df: Visit records DataFrame
        lab_df: Lab results DataFrame
        sut_estimate: Pre-computed SUT cost estimate
        ana_group_idx: Pre-built groupby index (optional)
        lab_group_idx: Pre-built groupby index (optional)
        forecast_months: Forward projection horizon (default 12)

    Returns:
        CostTrajectory with monthly breakdown and projection
    """
    # Get patient's visit data
    if ana_group_idx is not None and patient_id in ana_group_idx:
        patient_visits = ana_df.iloc[ana_group_idx[patient_id]]
    elif not ana_df.empty:
        patient_visits = ana_df[ana_df["patient_id"] == patient_id]
    else:
        patient_visits = pd.DataFrame()

    # Get patient's lab data
    if lab_group_idx is not None and patient_id in lab_group_idx:
        patient_labs = lab_df.iloc[lab_group_idx[patient_id]]
    elif not lab_df.empty:
        patient_labs = lab_df[lab_df["patient_id"] == patient_id]
    else:
        patient_labs = pd.DataFrame()

    # Build monthly timeline from visit dates
    trajectory: list[CostTrajectoryPoint] = []
    monthly_costs: list[float] = []

    # Try to extract date-based timeline
    date_col = None
    for col in ["GELISTARIHI", "visit_date", "date"]:
        if col in patient_visits.columns:
            date_col = col
            break

    if date_col and not patient_visits.empty:
        visits_with_dates = patient_visits.copy()
        visits_with_dates["_date"] = pd.to_datetime(
            visits_with_dates[date_col], errors="coerce"
        )
        visits_with_dates = visits_with_dates.dropna(subset=["_date"])

        if not visits_with_dates.empty:
            visits_with_dates["_month"] = visits_with_dates["_date"].dt.to_period("M")
            months = sorted(visits_with_dates["_month"].unique())

            # Per-visit cost allocation
            total_visit_cost = sut_estimate.cost_mid
            n_total_visits = max(len(patient_visits), 1)
            cost_per_visit = total_visit_cost / n_total_visits

            cumulative = 0.0
            for month in months:
                month_data = visits_with_dates[visits_with_dates["_month"] == month]
                n_vis = len(month_data)
                period_cost = round(cost_per_visit * n_vis, 2)
                cumulative += period_cost

                # Count lab tests in this month
                n_tests = 0
                if not patient_labs.empty:
                    lab_date_col = None
                    for lc in ["ISLEMTARIHI", "test_date", "date"]:
                        if lc in patient_labs.columns:
                            lab_date_col = lc
                            break
                    if lab_date_col:
                        labs_copy = patient_labs.copy()
                        labs_copy["_date"] = pd.to_datetime(
                            labs_copy[lab_date_col], errors="coerce"
                        )
                        labs_copy = labs_copy.dropna(subset=["_date"])
                        labs_copy["_month"] = labs_copy["_date"].dt.to_period("M")
                        n_tests = int((labs_copy["_month"] == month).sum())

                trajectory.append(
                    CostTrajectoryPoint(
                        period=str(month),
                        cumulative_cost=round(cumulative, 2),
                        period_cost=period_cost,
                        n_visits=n_vis,
                        n_tests=n_tests,
                    )
                )
                monthly_costs.append(period_cost)

    # If no date-based timeline, create a synthetic one
    if not trajectory:
        n_visits = sut_estimate.n_visits or 1
        cost_per_visit = sut_estimate.cost_mid / max(n_visits, 1)
        cumulative = 0.0
        for i in range(min(n_visits, 12)):
            period_cost = round(cost_per_visit, 2)
            cumulative += period_cost
            trajectory.append(
                CostTrajectoryPoint(
                    period=f"Visit {i + 1}",
                    cumulative_cost=round(cumulative, 2),
                    period_cost=period_cost,
                    n_visits=1,
                    n_tests=max(sut_estimate.n_lab_tests // max(n_visits, 1), 0),
                )
            )
            monthly_costs.append(period_cost)

    # Trend detection using simple linear regression on monthly costs
    trend = "stable"
    if len(monthly_costs) >= 3:
        x = np.arange(len(monthly_costs), dtype=float)
        y = np.array(monthly_costs, dtype=float)
        if y.std() > 0:
            slope = float(np.polyfit(x, y, 1)[0])
            mean_cost = float(y.mean())
            # Normalize slope relative to mean
            rel_slope = slope / mean_cost if mean_cost > 0 else 0
            if rel_slope > 0.1:
                trend = "increasing"
            elif rel_slope < -0.1:
                trend = "decreasing"

    # Monthly burn rate
    burn_rate = (
        round(float(np.mean(monthly_costs)), 2)
        if monthly_costs
        else round(sut_estimate.cost_mid / 12, 2)
    )

    # Forward projection
    projected_annual = round(burn_rate * 12, 2)

    # Add forecast points
    last_cumulative = trajectory[-1].cumulative_cost if trajectory else 0.0
    for i in range(1, forecast_months + 1):
        # Apply trend multiplier
        if trend == "increasing":
            multiplier = 1.0 + (0.02 * i)  # 2% monthly increase
        elif trend == "decreasing":
            multiplier = max(0.5, 1.0 - (0.02 * i))  # 2% monthly decrease, floor 50%
        else:
            multiplier = 1.0

        period_cost = round(burn_rate * multiplier, 2)
        last_cumulative += period_cost
        trajectory.append(
            CostTrajectoryPoint(
                period=f"Forecast M+{i}",
                cumulative_cost=round(last_cumulative, 2),
                period_cost=period_cost,
                n_visits=0,
                n_tests=0,
            )
        )

    total_forecast = round(last_cumulative, 2)

    return CostTrajectory(
        patient_id=patient_id,
        trajectory=trajectory,
        total_forecast_cost=total_forecast,
        forecast_horizon_months=forecast_months,
        trend=trend,
        monthly_burn_rate=burn_rate,
        projected_annual_cost=projected_annual,
    )
