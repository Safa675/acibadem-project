# SUT Pricing Integration Roadmap

## Overview

**SUT (Sağlık Uygulama Tebliği)** — Turkey's Health Implementation Communiqué — establishes
standardized min/max reimbursement prices for every medical procedure, lab test, drug, and
clinical service. Integrating SUT pricing transforms ILAY's relative-percentile ECI score
into a concrete cost estimation engine that actuaries and private hospitals can use for
financial planning.

---

## Phase 1 — SUT Price Catalog (✅ Implemented)

**Goal**: Create a reference price catalog mapping procedures/tests/visits to SUT TRY ranges.

| Task | Status |
|------|--------|
| Build `src/sut_pricing.py` with typed dataclass catalog | ✅ |
| Map lab tests from `health_index.py` organ systems to SUT codes | ✅ |
| Map visit types (outpatient, inpatient, ICU, ER) to SUT ranges | ✅ |
| Map prescription cost tiers by drug category | ✅ |
| Map comorbidity-linked procedures (HTN, DM, CVD, etc.) | ✅ |
| Per-patient cost estimation: `estimate_patient_sut_costs()` | ✅ |
| Cohort-level summary: `estimate_cohort_sut_summary()` | ✅ |

**Data Sources**:
- SUT 2024 official gazette prices (representative values)
- Mapped to ILAY's existing lab test names, visit types, and prescription data
- ICD-10 chapter → procedure cost associations

---

## Phase 2 — Backend Integration (✅ Implemented)

| Task | Status |
|------|--------|
| Export SUT functions from `src/__init__.py` | ✅ |
| Add SUT cost data to `/api/patient/{id}/outcome` endpoint | ✅ |
| Add cohort-level SUT summary to `/api/cohort` endpoint | ✅ |
| Integrate SUT context into chatbot patient context builder | ✅ |
| Add SUT reference to chatbot system prompt | ✅ |
| Add SUT cost info to ECI narrative generator | ✅ |

---

## Phase 3 — Frontend Integration (✅ Implemented)

| Task | Status |
|------|--------|
| Add TypeScript interfaces for SUT pricing data | ✅ |
| Add SUT pricing glossary entries | ✅ |

---

## Phase 4 — Future Enhancements (🔮 Planned)

These items require external data sources or significant infrastructure changes:

### 4a. Real SUT Data Integration
- [ ] Parse official SUT PDF/XML gazette into structured database
- [ ] Map SUT procedure codes (SUT Kodu) to ILAY's lab test names
- [ ] Implement versioned pricing (SUT updates annually)
- [ ] Add SUT price update mechanism (API or file-based)

### 4b. Diagnosis-Driven Cost Modeling
- [ ] Map TANIKODU (ICD-10) → typical procedure bundles from SUT
- [ ] Build DRG-style (Diagnosis Related Group) cost packages
- [ ] Predict total episode cost based on diagnosis + patient risk profile

### 4c. Actuarial Cost Projections
- [ ] Monte Carlo cost simulation (analogous to HealthVaR but for TRY)
- [ ] Cost VaR: "With 95% confidence, this patient won't cost more than X TRY"
- [ ] Portfolio-level cost distribution for insurer panels
- [ ] Risk-adjusted premium estimation

### 4d. Hospital Revenue Optimization
- [ ] SUT reimbursement gap analysis (hospital charge vs SUT max)
- [ ] Service mix optimization based on SUT price margins
- [ ] Capacity planning linked to procedure cost tiers

### 4e. Advanced Analytics
- [ ] Cost trajectory forecasting (time-series cost prediction)
- [ ] Comorbidity interaction cost multipliers
- [ ] Drug cost optimization (generic substitution savings)
- [ ] Procedure bundling cost efficiency analysis

---

## Architecture Decision: Representative vs. Real SUT Prices

The current implementation uses **representative SUT price ranges** based on publicly
available information about Turkish healthcare pricing tiers. This is intentional:

1. **Real SUT codes require official gazette parsing** — the full SUT is a 2,000+ page
   regulatory document updated annually by SGK (Social Security Institution)
2. **Representative prices are sufficient for the model's purpose** — the relative ranking
   and cost distribution patterns are what matter for ECI enhancement
3. **The architecture supports drop-in replacement** — when real SUT data becomes available,
   only the price catalog in `sut_pricing.py` needs updating; all downstream consumers
   (API, frontend, chatbot) work unchanged

---

## Finance → Healthcare Analogy

| Finance Concept | Healthcare (ILAY) Implementation |
|----------------|----------------------------------|
| Bond pricing (bid/ask spread) | SUT min/max price range per procedure |
| Portfolio valuation | Patient total estimated cost (sum of procedures) |
| Sector exposure | Cost breakdown by category (lab, visit, Rx, procedure) |
| NAV (Net Asset Value) | Midpoint cost estimate per patient |
| Benchmark pricing | SUT gazette as the "market rate" reference |
| Risk premium | Cost above SUT minimum (hospital margin potential) |

---

## Key Metrics Added

| Metric | Type | Description |
|--------|------|-------------|
| `sut_cost_min` | TRY | Lower bound of estimated patient cost (SUT minimums) |
| `sut_cost_max` | TRY | Upper bound of estimated patient cost (SUT maximums) |
| `sut_cost_mid` | TRY | Midpoint estimate: (min + max) / 2 |
| `sut_lab_cost` | TRY range | Cost attributable to lab/diagnostic tests |
| `sut_visit_cost` | TRY range | Cost attributable to clinic visits |
| `sut_rx_cost` | TRY range | Cost attributable to prescriptions |
| `sut_procedure_cost` | TRY range | Cost attributable to comorbidity-linked procedures |
