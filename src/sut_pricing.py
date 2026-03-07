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
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("ilay.sut_pricing")

# ── SUT Price Catalog ─────────────────────────────────────────────────────
# Representative price ranges (TRY) based on SUT 2024 official gazette.
# Format: (min_try, max_try) per unit of service.
#
# When real SUT gazette data is parsed, only this section needs updating.
# All downstream consumers (API, frontend, chatbot) work unchanged.

# Lab test prices: test_name → (min_try, max_try)
# Mapped to the exact test names used in src/health_index.py ORGAN_SYSTEMS
SUT_LAB_PRICES: dict[str, tuple[float, float]] = {
    # Inflammatory panel
    "CRP": (15.0, 25.0),
    "Lökosit": (8.0, 15.0),
    "Nötrofil": (8.0, 15.0),
    "Lenfosit": (8.0, 15.0),
    "Eozinofil": (8.0, 15.0),
    "Monosit": (8.0, 15.0),
    "Bazofil": (8.0, 15.0),
    "Prokalsitonin": (45.0, 80.0),
    # Renal panel
    "Kreatinin": (10.0, 18.0),
    "Üre": (8.0, 15.0),
    "GFR": (10.0, 20.0),
    # Hepatic panel
    "Bilirubin": (10.0, 18.0),
    "ALT": (10.0, 18.0),
    "AST": (10.0, 18.0),
    "ALP": (10.0, 18.0),
    "GGT": (10.0, 18.0),
    # Hematological panel
    "Hemoglobin": (8.0, 15.0),
    "Hematokrit": (8.0, 15.0),
    "Eritrosit": (8.0, 15.0),
    "Trombosit": (8.0, 15.0),
    "MCV": (8.0, 15.0),
    "MCH": (8.0, 15.0),
    "RDW": (8.0, 15.0),
    # Metabolic panel
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
    # Endocrine panel
    "TSH": (20.0, 35.0),
    "T3": (20.0, 35.0),
    "T4": (20.0, 35.0),
    # Coagulation panel
    "INR": (12.0, 22.0),
    "PT": (12.0, 22.0),
    "aPTT": (12.0, 22.0),
}

# Default price for unlisted lab tests
SUT_LAB_DEFAULT: tuple[float, float] = (8.0, 15.0)

# Visit type prices: visit_category → (min_try, max_try)
SUT_VISIT_PRICES: dict[str, tuple[float, float]] = {
    "outpatient": (80.0, 200.0),
    "inpatient_day": (250.0, 600.0),
    "icu_day": (800.0, 2500.0),
    "emergency": (150.0, 400.0),
    "follow_up": (50.0, 120.0),
}

# Prescription cost tiers: drug complexity → per-prescription (min_try, max_try)
SUT_RX_PRICES: dict[str, tuple[float, float]] = {
    "basic": (10.0, 40.0),       # common generics (antihypertensives, NSAIDs)
    "moderate": (40.0, 150.0),   # branded drugs, injectables
    "specialty": (150.0, 800.0), # biologics, oncology, immunosuppressants
}
SUT_RX_DEFAULT: tuple[float, float] = (20.0, 80.0)

# Comorbidity-linked procedure cost ranges per episode
# These represent additional procedure costs triggered by specific conditions
SUT_COMORBIDITY_PROCEDURE_COSTS: dict[str, tuple[float, float]] = {
    "Hipertansiyon": (100.0, 500.0),        # BP monitoring, echo, ECG
    "Kalp Damar": (500.0, 5000.0),          # Cardiac cath, angiography, stent
    "Diyabet": (200.0, 1000.0),             # HbA1c monitoring, retinal screening
    "Kan Hastalıkları": (300.0, 2000.0),    # Hematology workup, transfusion
    "Kronik Hastalıklar Diğer": (200.0, 1500.0),  # Chronic disease management
    "Ameliyat Geçmişi": (1000.0, 15000.0),  # Post-surgical follow-up, revision
}

# ICD-10 chapter → estimated procedure cost range
# Maps first character of TANIKODU to typical intervention costs
SUT_ICD10_PROCEDURE_COSTS: dict[str, tuple[float, float]] = {
    "I": (500.0, 8000.0),    # Circulatory — cardiac procedures, vascular surgery
    "C": (1000.0, 25000.0),  # Cancer — oncology, radiation, chemo
    "J": (200.0, 3000.0),    # Respiratory — bronchoscopy, pulmonary function
    "K": (300.0, 5000.0),    # Digestive — endoscopy, colonoscopy
    "G": (400.0, 6000.0),    # Neurological — EEG, MRI, nerve conduction
    "E": (150.0, 1500.0),    # Endocrine — thyroid workup, insulin pump
    "M": (200.0, 4000.0),    # Musculoskeletal — joint replacement, physio
    "N": (300.0, 4000.0),    # Genitourinary — dialysis, cystoscopy
    "L": (100.0, 1000.0),    # Dermatological — biopsy, phototherapy
    "F": (100.0, 800.0),     # Mental health — psych evaluation
    "H": (150.0, 2000.0),    # Eye/ear — cataract, audiometry
    "R": (50.0, 300.0),      # Symptoms — diagnostic workup
    "Z": (50.0, 200.0),      # Check-ups — preventive screening
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
            # Try exact match first, then partial match
            price = SUT_LAB_PRICES.get(test_str)
            if price is None:
                # Partial match: check if any catalog key is in the test name
                for catalog_name, catalog_price in SUT_LAB_PRICES.items():
                    if catalog_name.lower() in test_str.lower():
                        price = catalog_price
                        break
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
            days = max(float(los), 1.0)
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
                # Check for non-empty string or truthy value
                if isinstance(val, str) and len(val.strip()) >= 1:
                    has_condition = True
                elif not isinstance(val, str) and val > 0:
                    has_condition = True
                else:
                    has_condition = False

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
                    if chapter not in seen_chapters and chapter in SUT_ICD10_PROCEDURE_COSTS:
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
    lab_min, lab_max, n_labs = _estimate_lab_costs(
        lab_df, patient_id, lab_group_idx
    )
    breakdown.lab_cost_min = lab_min
    breakdown.lab_cost_max = lab_max

    # Visit costs
    visit_min, visit_max, n_visits = _estimate_visit_costs(
        ana_df, patient_id, ana_group_idx
    )
    breakdown.visit_cost_min = visit_min
    breakdown.visit_cost_max = visit_max

    # Prescription costs
    rx_min, rx_max, n_rx = _estimate_rx_costs(
        rec_df, patient_id, rec_group_idx
    )
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
            pid, lab_df, ana_df, rec_df,
            lab_group_idx, ana_group_idx, rec_group_idx,
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
