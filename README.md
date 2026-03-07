# ILAY -- AI Clinical Risk Intelligence Platform

**ACUHIT 2026 Hackathon | Acibadem University**

ILAY is a clinical risk intelligence platform that transforms raw healthcare data (lab results, clinical visits, prescriptions, clinical notes) into actionable patient risk scores using quantitative finance methodologies adapted for healthcare. The platform applies Value-at-Risk modeling, credit-rating-style scoring, and NLP-driven sentiment analysis to Turkish clinical data.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Data Pipeline](#data-pipeline)
- [Core Metrics](#core-metrics)
  - [1. Health Index](#1-health-index)
  - [2. Patient Regime Classification](#2-patient-regime-classification)
  - [3. Health Value-at-Risk (VaR)](#3-health-value-at-risk-var)
  - [4. NLP Clinical Sentiment](#4-nlp-clinical-sentiment)
  - [5. Composite Risk Score](#5-composite-risk-score)
  - [6. Expected Cost Intensity (ECI)](#6-expected-cost-intensity-eci)
  - [7. SUT Cost Estimation](#7-sut-cost-estimation)
  - [8. Clinical Severity Index (CSI)](#8-clinical-severity-index-csi)
  - [9. Feature Correlations (Spearman)](#9-feature-correlations-spearman)
- [Validation Framework](#validation-framework)
- [API Reference](#api-reference)
- [Frontend Structure](#frontend-structure)
- [Score Polarity Contracts](#score-polarity-contracts)
- [Tech Stack](#tech-stack)

---

## Architecture Overview

```
                      +-------------------+
                      |     Raw Data      |
                      | Lab | Visits | Rx |
                      +--------+----------+
                               |
                    +----------v-----------+
                    |   src/data_loader.py  |
                    | Load, clean, index    |
                    +----------+-----------+
                               |
            +------------------+------------------+
            |                  |                  |
   +--------v--------+ +------v------+ +---------v---------+
   | health_index.py | | nlp_llm.py  | | patient_regime.py |
   | Z-score scoring | | LLM scoring | | State machine     |
   | 0-100 per organ | | [-1, +1]    | | 4-state regime    |
   +--------+--------+ +------+------+ +---------+---------+
            |                  |                  |
            +------------------+------------------+
                               |
            +------------------+------------------+
            |                  |                  |
   +--------v--------+ +------v------+ +---------v---------+
   |   fusion.py     | |   eci.py    | | sut_pricing.py    |
   | Composite Score  | | Cost Index  | | TRY cost estimate |
   | AAA-B/CCC rating | | AAA-B/CCC  | | SUT gazette data  |
   +--------+--------+ +------+------+ +---------+---------+
            |                  |                  |
   +--------v--------+ +------v------+            |
   |  health_var.py  | | outcomes.py |            |
   | Monte Carlo VaR | | Profiles +  |            |
   | 5th pctile risk | | Narratives  |            |
   +--------+--------+ +------+------+            |
            |                  |                  |
            +------------------+------------------+
                               |
                    +----------v-----------+
                    |       api.py         |
                    |  FastAPI (7 endpoints)|
                    +----------+-----------+
                               |
                    +----------v-----------+
                    |  Next.js Frontend    |
                    |  4 tabs + chatbot    |
                    +----------------------+
```

---

## Data Pipeline

### Stage 1: Data Loading (`src/data_loader.py`)

Three data sources are loaded from `.cache/` Parquet files:

| Source | Contents | Key Columns |
|--------|----------|-------------|
| **Lab Results** | Test values with reference ranges | `patient_id, test_name, value, ref_min, ref_max, date` |
| **Visit Records** (anadata) | Clinical visits, vitals, notes, comorbidities | `patient_id, visit_date, age, sex, systolic_bp, diastolic_bp, los_days, TANIKODU, comorbidity flags, clinical text columns` |
| **Prescriptions** (recete) | Medication records | `patient_id, date, drug_name, dose, duration_days` |

**Data quality rules applied during loading:**

| Column | Validation | Action |
|--------|-----------|--------|
| `systolic_bp` | < 40 or > 300 mmHg | Set to NaN |
| `diastolic_bp` | < 20 or > 200 mmHg | Set to NaN |
| `age` | < 0 or > 120 years | Set to NaN |
| `pulse` | 96.7% missing | Excluded from scoring |
| `SpO2` | 99.7% missing | Excluded from scoring |
| `date` (all sources) | Before 2000-01-01 | Row dropped (Excel serial leak) |

**Comorbidity flag columns** (6 binary indicators):

| Column | Condition |
|--------|-----------|
| `Hipertansiyon Hastada` | Hypertension |
| `Kalp Damar Hastada` | Cardiovascular disease |
| `Diyabet Hastada` | Diabetes |
| `Kan Hastaliklari Hastada` | Blood disorders |
| `Kronik Hastaliklar Diger` | Other chronic diseases |
| `Ameliyat Gecmisi` | Surgical history |

A flag is "positive" if the value is a non-empty string (length >= 1) or a number > 0.

### Stage 2: Health Index Computation

See [Health Index](#1-health-index) below.

### Stage 3: Parallel Analytics

All downstream modules run on the health index output:
- **Patient regime classification** -- state machine for clinical trajectory
- **Health VaR** -- Monte Carlo risk quantification
- **NLP scoring** -- pre-cached LLM sentiment analysis
- **Composite risk scoring** -- fusion of health index + NLP
- **ECI** -- Expected Cost Intensity (percentile-based)
- **SUT pricing** -- Turkish healthcare cost estimation
- **Validation** -- statistical tests against SOFA and APACHE II benchmarks

### Stage 4: API Serving

The pipeline runs **once at startup** and is cached in memory. All API endpoints read from the cache with zero recomputation per request. JSON sanitization handles NaN, Inf, and numpy types transparently.

---

## Core Metrics

### 1. Health Index

**Module:** `src/health_index.py` (937 lines)
**Output:** Score in **[0, 100]** where 100 = perfectly healthy, 0 = maximally abnormal

The Health Index quantifies a patient's physiological state by measuring how far lab test results deviate from their reference ranges, aggregated across 8 organ systems.

#### 1.1 Organ Systems

Each lab test is classified into one of 8 organ systems by keyword matching on the test name:

| Organ System | Weight | Test Keywords |
|-------------|--------|---------------|
| Inflammatory | 0.125 | CRP, Lokosit, Notrofil, Lenfosit, Bazofil, Eozinofil, Monosit, Prokalsitonin |
| Renal | 0.125 | Kreatinin, Ure, GFR |
| Hepatic | 0.125 | Bilirubin, ALT, AST, ALP, GGT |
| Hematological | 0.125 | Hemoglobin, Hematokrit, Eritrosit, Trombosit, MCV, MCH, RDW |
| Metabolic | 0.125 | Glukoz, HbA1c, Kolesterol, Trigliserid, LDL, HDL, Sodyum, Potasyum, Kalsiyum, Albumin, Protein |
| Endocrine | 0.125 | TSH, T3, T4 |
| Coagulation | 0.125 | INR, PT, aPTT |
| Other | 0.125 | Any test not matching the above |

All 8 systems have **equal weight** (0.125), consistent with SOFA/NEWS2/APACHE II multi-organ scoring philosophy.

#### 1.2 Reference Range Resolution

Three-tier fallback for reference ranges:

1. **Hospital-supplied** `REFMIN` / `REFMAX` from the lab row (highest priority)
2. **NexGene AI intervals** -- source: NexGene AI Medical Reasoning API (asa-mini model, v0.4.132, queried 2026-03-07). Used when hospital data is NaN or `ref_max <= ref_min`.
3. **No range available** -- test receives z = 0.0 (invisible to scoring)

**NexGene AI reference ranges used as fallback:**

| Test Keyword | Range | Unit |
|-------------|-------|------|
| Albumin | 35.0 - 50.0 | g/L |
| Protein | 60.0 - 80.0 | g/L |
| Ure | 1.8 - 7.1 | mmol/L |
| Kreatinin | 41.0 - 111.0 | umol/L |
| Bilirubin | 0.0 - 21.0 | umol/L |
| Glukoz | 3.9 - 6.1 | mmol/L |
| Kolesterol | 3.5 - 5.2 | mmol/L |
| ALT | 19.0 - 25.0 | U/L |
| AST | 10.0 - 44.0 | U/L |
| ALP | 55.0 - 150.0 | U/L |
| GGT | 5.0 - 40.0 | U/L |
| Sodyum | 135.0 - 145.0 | mmol/L |
| Potasyum | 3.3 - 5.1 | mmol/L |
| Kalsiyum | 2.2 - 2.6 | mmol/L |

**Vital sign reference ranges** (NexGene AI):

| Vital | Range | Unit |
|-------|-------|------|
| Systolic BP | 90.0 - 119.0 | mmHg |
| Diastolic BP | 75.0 - 84.0 | mmHg |

#### 1.3 Per-Test Z-Score

The z-score measures **distance outside the reference range** (not distance from midpoint):

```
ref_std = (ref_max - ref_min) / 4.0
```

The reference range is assumed to span +/-2 standard deviations (95% CI), so the total width equals 4 sigma.

```
        { (ref_min - value) / ref_std    if value < ref_min   (below range)
z_i =   { (value - ref_max) / ref_std    if value > ref_max   (above range)
        { 0.0                             if ref_min <= value <= ref_max
```

Key properties:
- **One-sided**: z = 0 for all in-range values (a CRP of 0 is healthy, not penalized)
- **Always non-negative**: measures absolute distance from nearest boundary
- **Division-by-zero guard**: `ref_std = max((ref_max - ref_min) / 4.0, 1e-9)`

#### 1.4 Organ System Aggregation

Within each organ system on a given date:

```
system_z[organ] = mean(z_i for all tests i in that organ on that date)
```

#### 1.5 Weighted Aggregate Z-Score

Across organ systems present on that date:

```
                 sum(system_z[organ] * w[organ])
mean_z = ----------------------------------------
                 sum(w[organ])
```

where `w[organ] = 0.125` for all systems. Only organ systems with at least one test present contribute to both numerator and denominator.

#### 1.6 Health Score Conversion (Exponential Decay)

```
lab_score = clip(100 * exp(-0.25 * mean_z), 0, 100)
```

| mean_z | lab_score | Interpretation |
|--------|-----------|----------------|
| 0.0 | 100.0 | All tests within reference range |
| 2.0 | 60.7 | Mild abnormalities |
| 4.0 | 36.8 | Moderate abnormalities |
| 6.0 | 22.3 | Severe abnormalities |
| 8.0+ | < 13.5 | Critical |

The decay constant 0.25 controls the steepness of the mapping.

#### 1.7 Vital Score

Identical formula applied to vitals (only systolic/diastolic BP active):

```
vital_score = clip(100 * exp(-0.25 * vital_mean_z), 0, 100)
```

Temporal matching: vitals must be on or before the scoring date, within a **30-day lookback** window. Uses `merge_asof` with `direction="backward"` in bulk mode.

#### 1.8 Composite Health Score

```
                { 0.60 * lab_score + 0.40 * vital_score    if both available
health_score =  { lab_score                                 if vitals missing
                { vital_score                               if labs missing
```

Default weights: `lab_weight = 0.60`, `vital_weight = 0.40`.

#### 1.9 Data Completeness

```
                { 0.0    if neither labs nor vitals
completeness =  { 0.5    if labs only or vitals only
                { 1.0    if both labs and vitals present
```

#### 1.10 Dominant Organ System

The organ system with the **highest mean z-score** on a given date (i.e., the most abnormal system).

---

### 2. Patient Regime Classification

**Module:** `src/patient_regime.py` (360 lines)
**Output:** One of 4 clinical states per observation date

Inspired by Hidden Markov Models in quantitative finance (regime detection for bull/bear markets), the patient regime classifier assigns a clinical state at each observation point using a **2x2 grid** of trend direction and volatility level.

#### 2.1 State Definitions

| State | Trend | Volatility | Color | Clinical Meaning |
|-------|-------|-----------|-------|-----------------|
| **Stable** | Positive (score >= MA) | Low | Green (#2ECC71) | Patient on track, no intervention needed |
| **Recovering** | Positive (score >= MA) | High | Amber (#F39C12) | Improving but volatile -- continue monitoring |
| **Deteriorating** | Negative (score < MA) | Low | Orange (#E67E22) | Steady decline -- review care plan |
| **Critical** | Negative (score < MA) | High | Red (#E74C3C) | Rapid decline with instability -- urgent review |

#### 2.2 Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `ma_window` | 3 | Moving average window (observations) |
| `vol_window` | 4 | Rolling standard deviation window |
| `vol_lookback` | 20 | History window for volatility percentile ranking |
| `vol_high_percentile` | 60.0 | Percentile threshold for "high" volatility |
| `min_observations` | 2 | Minimum data points before classification |

#### 2.3 Rolling Calculations

**Moving Average:**
```
MA_t = mean(score_{t-w+1}, ..., score_t)     where w = ma_window = 3
```

**Rolling Volatility:**
```
vol_t = std(score_{t-w+1}, ..., score_t), ddof=1     where w = vol_window = 4
```
Requires minimum 3 data points (`min_periods=3`).

**Volatility Percentile Rank:**
```
vol_pct_t = (count of historical vol values <= vol_t) / (count of historical vol values) * 100
```
Computed within the patient's own history (last `vol_lookback = 20` observations). If fewer than 3 historical values exist, defaults to 50.0 (neutral).

#### 2.4 Classification Logic

```
trend_positive = (score_t >= MA_t)
vol_high = (vol_pct_t >= 60.0)

if trend_positive and not vol_high:     -> STABLE
if trend_positive and vol_high:         -> RECOVERING
if not trend_positive and not vol_high: -> DETERIORATING
if not trend_positive and vol_high:     -> CRITICAL
```

#### 2.5 Transition Events

State transitions are detected by sequential comparison of consecutive states. Each transition records `{date, from_state, to_state}`.

---

### 3. Health Value-at-Risk (VaR)

**Module:** `src/health_var.py` (338 lines)
**Output:** "With 95% confidence, this patient's health score will NOT fall below X in the next N lab-draw cycles."

Adapted from financial Value-at-Risk (VaR), the Health VaR uses Monte Carlo bootstrap simulation to forecast the probability distribution of a patient's future health score.

#### 3.1 Algorithm

**Step 1 -- Compute arithmetic returns:**
```
r_i = (S_i - S_{i-1}) / max(S_{i-1}, 1.0)     for i = 1, ..., n
```
Arithmetic returns are used instead of log-returns because log-returns explode when health scores approach zero.

**Step 2 -- Bayesian shrinkage:**
```
w_data = n_obs / (n_obs + 3)
r'_i = r_i * w_data
r'_i = clip(r'_i, -0.5, +0.5)
```
The prior is a zero-return (stable health assumption). With 1 observation, only 25% of the data signal is retained; with 10 observations, ~77%.

**Step 3 -- Monte Carlo simulation:**
```
For each path j = 1, ..., N_iterations:
    Draw r^j_1, ..., r^j_H with replacement from {r'_i}
    Terminal^j = current * product(1 + r^j_k, k=1..H)
    Terminal^j = clip(Terminal^j, 0, 100)
```

**Step 4 -- Percentile extraction:**
```
p05 = percentile(terminals, 5)      <-- This IS the Health VaR
p25 = percentile(terminals, 25)
p50 = percentile(terminals, 50)     <-- Median forecast
p75 = percentile(terminals, 75)
p95 = percentile(terminals, 95)
```

**Step 5 -- Relative VaR:**
```
var_pct = (p05 - current) / max(current, 1) * 100
```

#### 3.2 Default Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `horizon_draws` | 3 | Lab-draw cycles to forecast |
| `iterations` | 5,000 (single) / 3,000 (batch) | Monte Carlo paths |
| `seed` | 42 | Random seed for reproducibility |

#### 3.3 CVaR (Expected Shortfall) Approximation

```
CVaR_pct = var_pct * 1.3    if var_pct < 0
CVaR_pct = 0.0              otherwise
```

The 1.3x multiplier is a conservative proxy. True CVaR would be `E[Terminal | Terminal < p05]`.

#### 3.4 Risk Tier Thresholds

| VaR % Range | Tier | Label |
|------------|------|-------|
| > +5.0% | GREEN | Health Stable -- minimal risk of decline |
| 0.0% to +5.0% | YELLOW | Low Risk -- slight downside possible |
| -10.0% to 0.0% | ORANGE | Moderate Risk -- review within 24-48h |
| <= -10.0% | RED | High Risk -- prioritize clinical review |

#### 3.5 Edge Cases

| Condition | Behavior |
|-----------|----------|
| < 2 data points | Returns `None` (VaR not computed) |
| Single data point | All percentiles = that score (flat forecast) |
| Zero data points | All percentiles = 50.0 (neutral midpoint) |

---

### 4. NLP Clinical Sentiment

**Module:** `src/nlp_llm.py` (459 lines)
**Output:** Score in **[-1.0, +1.0]** per clinical visit

The NLP module uses a large language model to score the clinical sentiment of Turkish medical text from 5 clinical note columns.

#### 4.1 Scoring Scale

| Score | Meaning |
|-------|---------|
| -1.0 | Strong deterioration (critical symptoms, organ failure, emergency) |
| -0.5 | Moderate deterioration (new symptoms, concerning findings) |
| -0.2 | Mild concern (minor symptoms, suboptimal) |
| 0.0 | Neutral/stable (routine follow-up, no change) |
| +0.2 | Mild improvement (symptoms reducing) |
| +0.5 | Moderate recovery (clear improvement) |
| +1.0 | Strong recovery (resolved, discharge-ready) |

#### 4.2 Text Columns and Weights

| Column | Turkish Name | Weight |
|--------|-------------|--------|
| `OYKU` | Medical history | 0.20 |
| `YAKINMA` | Chief complaint | 0.20 |
| `Muayene Notu` | Physical exam notes | 0.20 |
| `Kontrol Notu` | Follow-up notes | 0.20 |
| `Tedavi Notu` | Treatment notes | 0.20 |

All 5 columns carry equal weight. If some columns are missing, weights are renormalized across available columns.

#### 4.3 Composite Calculation

```
nlp_composite = sum(score_col * w_col / total_weight for col in available_columns)
nlp_composite = clip(nlp_composite, -1.0, +1.0)
```

Where `total_weight = sum(w_col for col in available_columns)`.

#### 4.4 Model and API

| Parameter | Value |
|-----------|-------|
| Model | `google/gemini-2.5-flash-lite` via OpenRouter |
| Temperature | 0.1 |
| Batch size | 20 texts per API call |
| Concurrency | 10 simultaneous requests |
| Text truncation | 400 characters per text |
| Max retries | 3 (exponential backoff) |
| Timeout | 60 seconds per request |

#### 4.5 Turkish Clinical Keyword Mapping

The LLM prompt includes explicit mappings for Turkish medical terminology:
- **Deterioration signals:** "TA yuksek" (high BP), "ates" (fever), "dispne" (dyspnea), "ral" (crackles), "ronkus" (rhonchi), "odem" (edema)
- **Stability/recovery signals:** "olagan" (normal), "temiz" (clear), "yok" (absent for symptoms)
- **Neutral signals:** "kontrol" / "izlem" (follow-up), short medication lists alone, ICD codes alone

---

### 5. Composite Health Score

**Module:** `src/fusion.py` (266 lines)
**Output:** Score in **[0, 100]** with credit-style rating (AAA to B/CCC)

The Composite Risk Score fuses the Health Index and NLP signal into a single patient risk metric, analogous to a credit rating in finance.

#### 5.1 Formula

```
CompositeScore = 0.70 * HealthIndex + 0.30 * NLP_normalized
CompositeScore = clip(CompositeScore, 0, 100)
```

When NLP is unavailable (score = 0.0):
```
CompositeScore = 1.0 * HealthIndex
```

#### 5.2 NLP Normalization ([-1, +1] to [0, 100])

```
NLP_normalized = clip(100 * nlp_score + 50, 0, 100)
```

The 2x stretch maps the typical clinical NLP range [-0.5, +0.5] to the full [0, 100] instead of being compressed into [25, 75].

| NLP Input | NLP Normalized |
|-----------|---------------|
| -1.0 | 0 |
| -0.5 | 0 |
| 0.0 | 50 |
| +0.5 | 100 |
| +1.0 | 100 |

#### 5.3 Weight Evidence

| Weight | Source | Justification |
|--------|--------|--------------|
| 70% Health Index | Labs + vitals | NEWS AUROC 0.867; Rajkomar et al. 2018: structured data AUROC 0.93-0.94 for mortality |
| 30% NLP | Clinical notes | Garriga et al. (JMIR 2024): multimodal fusion adds +1-5% AUROC; feature importance 20-35% from notes |

#### 5.4 Medication Change Velocity (Informational, weight = 0)

```
                  { 80.0                                          if no Rx data
med_score =       { clip(100 - n_drugs * 12, 10, 100)            if single day
                  { clip(100 - (n_drugs / span_days * 30) * 9, 10, 100)  otherwise
```

Interpretation: 0 changes/month = 100 (stable), 10+ changes/month = 10 (unstable).


### 6. Expected Cost Intensity (ECI)

**Module:** `src/eci.py` (469 lines)
**Output:** Score in **[0, 100]** where 100 = highest expected healthcare expenditure

The ECI translates clinical risk into expected resource consumption, using percentile-ranking within the patient cohort. It answers: "How much healthcare utilization should we expect for this patient relative to peers?"

#### 6.1 Master Formula

```
ECI = 0.25 * visit_intensity_pct + 0.25 * med_burden_pct + 0.25 * diagnostic_intensity_pct + 0.25 * trajectory_cost_pct
ECI = clip(ECI, 0, 100)
```

All four components carry **equal weight** (0.25). No evidence exists to differentiate.

#### 6.2 Component 1: Visit Intensity

**Raw metric:** visits per month
```
visits_per_month = n_visits / max((date_max - date_min).days / 30.0, 0.1)
```

**Normalization:** Percentile-ranked across the entire cohort. A patient at the 90th percentile of visit frequency scores 90.

#### 6.3 Component 2: Medication Burden

Two sub-components, each percentile-ranked internally:

**Sub-A:** Unique drug count = `patient_prescriptions.drug_name.nunique()`
**Sub-B:** Drug change velocity = `unique_drugs / max(span_days / 30.0, 0.1)`

```
med_burden = 0.50 * percentile_rank(drug_count) + 0.50 * percentile_rank(change_velocity)
```

#### 6.4 Component 3: Diagnostic Intensity

**Raw metric:** lab tests per month
```
labs_per_month = n_lab_rows / max(span_days / 30.0, 0.1)
```

**Normalization:** Percentile-ranked across the cohort.

#### 6.5 Component 4: Clinical Trajectory Cost

Two sub-components, each percentile-ranked:

**Sub-A:** Health index slope (inverted)
```
slope = OLS regression slope of health_score vs. observation index
trajectory_slope_signal = -slope     (declining health = HIGH cost signal)
```

**Sub-B:** NLP signal (inverted)
```
trajectory_nlp_signal = -nlp_composite    (negative NLP = HIGH cost signal)
```

```
trajectory_cost = 0.50 * percentile_rank(-slope) + 0.50 * percentile_rank(-nlp)
```

#### 6.6 Percentile Ranking Function

Converts raw values to [0, 100] percentiles using average rank for ties. NaN values are imputed with the **cohort median** before ranking.

```
percentile = rank / max(n - 1, 1) * 100
```

#### 6.7 ECI Rating Tiers

| ECI Score | Rating | Label |
|-----------|--------|-------|
| >= 75 | B/CCC | Very high expenditure risk |
| >= 60 | BB | High expenditure risk |
| >= 45 | BBB | Elevated expenditure risk |
| >= 30 | A | Moderate expenditure risk |
| >= 15 | AA | Low expenditure risk |
| >= 0 | AAA | Minimal expenditure risk |

---

### 7. SUT Cost Estimation

**Module:** `src/sut_pricing.py` (670 lines) + `src/sut_catalog.py` (602 lines)
**Output:** Cost range in **TRY** (Turkish Lira) per patient

SUT (Saglik Uygulama Tebligi) is Turkey's Health Implementation Communique, establishing standardized reimbursement prices for every medical procedure. This module translates patient utilization data into concrete cost estimates.

**Data source:** Official SUT gazette appendices (EK-2B: 5,074 fee-for-service procedures; EK-2C: 2,423 diagnosis-based packages) parsed from Excel into JSON catalogs.

#### 7.1 Cost Categories

Total cost is the sum of 4 categories:

```
total_min = lab_min + visit_min + rx_min + procedure_min
total_max = lab_max + visit_max + rx_max + procedure_max
total_mid = (total_min + total_max) / 2.0
```

#### 7.2 Lab Test Costs

Each lab test name is matched against the SUT price catalog (40 ILAY test names mapped to SUT codes). Price range per test instance:
- **min** = SUT gazette price (official reimbursement rate)
- **max** = SUT price * 1.20 (private hospital markup allowance)

```
lab_cost = sum(price_range * count for each unique test name)
```

Unmapped tests use a default: `SUT_LAB_DEFAULT = (1.85, 2.22) TRY`

**Sample real SUT gazette prices:**

| Test | SUT Code | Price (TRY) |
|------|----------|-------------|
| CRP | 900890 | 2.53 |
| ALT | 900200 | 1.85 |
| TSH | 904030 | 7.59 |
| HbA1c | 901450 | 7.59 |
| Prokalsitonin | 903170 | 43.00 |
| Hemogram (CBC) | 901620 | 7.59 |

#### 7.3 Visit Costs

Based on length of stay (LOS):

| Visit Type | Condition | Min TRY | Max TRY | Per |
|-----------|-----------|---------|---------|-----|
| Outpatient | LOS = 0 or NaN | Based on SUT code 520010 | x 1.20 | per visit |
| Inpatient | LOS >= 1 day | Based on SUT code 510010 (~50.59) | x 1.20 | per day |

#### 7.4 Prescription Costs

Flat per-prescription default (drug-level SUT mapping not yet integrated):
```
rx_cost = SUT_RX_DEFAULT * n_prescriptions = (20.0, 80.0) * n_rx
```

#### 7.5 Procedure Costs

**Source A -- Comorbidity-linked:**
Each active comorbidity flag adds its cost range once (from real EK-2C group price ranges).

**Source B -- ICD-10 diagnosis-linked:**
Each unique ICD-10 chapter (first character of TANIKODU) adds its cost range once (from EK-2C procedure group price distributions).

#### 7.6 Cost Tier Classification

Based on midpoint cost:

| Cost Midpoint (TRY) | Tier | Turkish Label |
|---------------------|------|---------------|
| >= 10,000 | Very High | Yuksek maliyet -- aktif mudahale beklenir |
| >= 5,000 | High | Yuksek -- yakin takip ve butce planlamasi gerekir |
| >= 2,000 | Moderate | Orta duzey -- rutin bakim maliyeti |
| >= 500 | Low | Dusuk -- minimal kaynak tuketimi |
| >= 0 | Minimal | Minimal maliyet -- koruyucu saglik hizmeti |

#### 7.7 Finance Analogy

| Finance Concept | Healthcare Implementation |
|----------------|--------------------------|
| Bond bid/ask spread | SUT min/max price range per procedure |
| Portfolio valuation | Patient total estimated cost |
| Sector exposure | Cost breakdown by category (lab/visit/Rx/procedure) |
| Net Asset Value | Midpoint cost estimate |
| Benchmark pricing | SUT gazette as market reference |

---

### 8. Clinical Severity Index (CSI)

**Module:** `src/outcomes.py` (621 lines)
**Output:** Score in **[0, 100]** where 100 = most severe (note: inverted polarity from Health Index)

The CSI aggregates 6 weighted clinical dimensions into a single severity score.

#### 8.1 Formula

```
CSI = sum(component_score_i * weight_i for i = 1..6)
CSI = clip(CSI, 0, 100)
```

#### 8.2 Components

| Component | Weight | Raw Input | Normalization to [0, 100] |
|-----------|--------|-----------|--------------------------|
| Health Trend | 0.25 | OLS slope of health scores | `clip((-slope + 5) / 10 * 100, 0, 100)` |
| Lab Volatility | 0.20 | std(health_scores) | `clip(volatility / 20 * 100, 0, 100)` |
| Critical Fraction | 0.20 | % time in Critical regime | `clip(fraction * 100, 0, 100)` |
| NLP Signal | 0.15 | mean NLP composite [-1,+1] | `clip((-nlp + 1) / 2 * 100, 0, 100)` |
| Rx Intensity | 0.10 | Prescriptions per month | `clip(velocity / 10 * 100, 0, 100)` |
| Comorbidity Burden | 0.10 | Count of comorbidities (0-6) | `clip(count / 4 * 100, 0, 100)` |

#### 8.3 Component Normalization Details

**Health Trend:** slope of -5 (rapid decline) maps to 100; slope of +5 (rapid improvement) maps to 0.

**Lab Volatility:** std of 20 (highly variable) maps to 100; std of 0 maps to 0.

**NLP Signal:** nlp of -1 (strongly negative notes) maps to 100; nlp of +1 maps to 0.

**Prescription Velocity:**
```
if n_dated > 1:
    rx_velocity = (n_prescriptions / (date_span_days + 1)) * 30    (Rx per month)
elif n_dated == 1:
    rx_velocity = 30.0    (single event assumed as 1/month)
else:
    rx_velocity = 0.0
```

#### 8.4 CSI Tiers

| CSI Score | Tier | Action |
|-----------|------|--------|
| >= 75 | CRITICAL | Immediate clinical attention required |
| >= 50 | HIGH | Active intervention recommended |
| >= 25 | MODERATE | Enhanced monitoring needed |
| >= 0 | LOW | Routine monitoring |

#### 8.5 Inverted Display Score

For UI consistency (higher = healthier):
```
csi_health_score = 100 - CSI
```

---

### 9. Feature Correlations (Spearman)

**Module:** `src/outcomes.py`, function `compute_feature_correlations()`

Computes Spearman rank correlations between patient profile features and a target variable (default: `total_visits`).

**Features tested:**
`initial_health_score`, `final_health_score`, `mean_health_score`, `health_score_trend`, `health_score_volatility`, `n_lab_draws`, `n_critical_episodes`, `critical_fraction`, `mean_nlp_composite`, `n_prescriptions`, `prescription_velocity`, `n_comorbidities`, `csi_score`

**Minimum sample size:** n >= 5 (raised from 3 because Spearman on n < 5 yields unreliable p-values).

**Interpretation labels:**

| |r| | Strength |
|-----|----------|
| >= 0.7 | Strong |
| >= 0.4 | Moderate |
| < 0.4 | Weak |

---

## Validation Framework

**Module:** `src/validation.py` (368 lines)

Validates the Health Index against established clinical severity benchmarks using Spearman rank correlation.

### Benchmarks

| Benchmark | Coverage | Missing Parameters |
|-----------|----------|-------------------|
| **SOFA** (Sequential Organ Failure Assessment) | 4/6 organ systems (Coagulation, Liver, Cardiovascular, Renal) | Respiratory, Neurological |
| **APACHE II** (Acute Physiology and Chronic Health Eval) | 7/12 APS parameters (MAP, HR, Na, K, Creatinine, Hematocrit, WBC) | Temperature, RR, PaO2, pH, GCS |
| **NEWS2** | Excluded -- only 3/7 parameters available | Insufficient coverage |

Missing parameters default to 0 (conservative lower-bound).

### Experiments

| Experiment | Expected Direction | Test |
|------------|-------------------|------|
| Health Index vs Mean SOFA | Negative (higher HI = healthier = lower SOFA) | Spearman rho |
| Health Index vs Max SOFA | Negative | Spearman rho |
| Health Index vs Mean APACHE II | Negative | Spearman rho |
| Health Index vs Max APACHE II | Negative | Spearman rho |

### Pass Criteria

A test passes when **all three** conditions are met:
1. `r < 0` -- correlation is negative (expected direction)
2. `p < 0.20` -- p-value below 0.20 (lenient due to limited parameter coverage)
3. `n > 5` -- more than 5 samples

### Significance Formatting

| p-value | Display |
|---------|---------|
| < 0.001 | `p < 0.001 ***` |
| < 0.01 | `p = X.XXX **` |
| < 0.05 | `p = X.XXX *` |
| < 0.10 | `p = X.XXX (trend)` |
| >= 0.10 | `p = X.XXX (n.s.)` |

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/patients` | Top 20 patients by data completeness + full patient metadata |
| `GET` | `/api/patients/search?q=&limit=` | Prefix search on patient IDs |
| `GET` | `/api/cohort?page=&per_page=&sort_by=&order=&rating=&regime=` | Cohort KPIs, paginated composites, VaR summary, distributions, NLP scatter, SUT summary |
| `GET` | `/api/patient/{patient_id}` | Full patient data (scores, timeline, VaR fan, NLP, labs, notes) |
| `GET` | `/api/patient/{patient_id}/outcome` | ECI gauge + components, narrative, cohort ranking, correlations, SUT costs |
| `GET` | `/api/validation` | Validation experiment results (SOFA/APACHE II) |
| `POST` | `/api/chat` | SSE-streamed AI chatbot with patient/cohort context |

---

## Frontend Structure

### Landing Page

Full-screen hero with animated gradient, particle effects, 4 feature value cards, and "Launch Dashboard" CTA.

### Dashboard Tabs

| Tab | Name | Key Visualizations |
|-----|------|--------------------|
| 0 | **Cohort Overview** | KPI cards, rating distribution, NLP scatter, risk regime pie, paginated patient table, VaR summary |
| 1 | **Patient Health Explorer** | Health score timeline, regime color-coded bars, VaR fan chart, NLP bar chart, lab sparklines, clinical notes, prescriptions |
| 2 | **Patient Risk Explorer** | ECI gauge (semicircle), narrative panel, SUT cost card + breakdown chart, ECI component bars, cohort ranking, Spearman correlations |
| 3 | **Validation** | Experiment result cards with pass/fail, statistics, p-values, clinical interpretation |

### AI Chatbot

Floating assistant (Gemini 2.5 Flash Lite via OpenRouter) with:
- Patient-specific context (health scores, regime, VaR, ECI, SUT costs, comorbidities)
- Cohort-level context (distributions, percentiles)
- Tab-aware suggested prompts
- SSE token streaming

---

## Score Polarity Contracts

| Score | Range | Direction | Meaning |
|-------|-------|-----------|---------|
| `health_index` | 0 - 100 | Higher is better | 100 = healthy |
| `nlp_raw` | -1 to +1 | Positive is good | +1 = strong recovery |
| `nlp_normalized` | 0 - 100 | Higher is better | 100 = positive sentiment |
| `composite_score` | 0 - 100 | Higher is better | 100 = lowest risk |
| `eci_score` | 0 - 100 | Higher is WORSE | 100 = highest expected cost |
| `csi_score` | 0 - 100 | Higher is WORSE | 100 = most severe |
| `csi_health_score` | 0 - 100 | Higher is better | 100 = least severe |
| `var_pct` | Unbounded | Negative is risk | -10% = high risk of decline |
| `sut_cost_mid` | 0+ TRY | Higher is costlier | Absolute currency amount |

---

## Tech Stack

### Backend
- **Python 3.10+** with FastAPI + Uvicorn
- **NumPy, Pandas, SciPy** for computation
- **Pydantic** for request validation
- **CORS + GZip** middleware

### Frontend
- **Next.js 16** (App Router) with React 19
- **TypeScript 5**
- **Tailwind CSS 4** with glassmorphism design system
- **Recharts 3** for data visualization
- **Radix UI** for accessible primitives

### AI/ML
- **Gemini 2.5 Flash Lite** (Google) via OpenRouter for NLP scoring and chatbot
- **NexGene AI** (asa-mini model) for reference interval validation

### Data
- **SUT Gazette** (EK-2B, EK-2C) -- official Turkish healthcare pricing
- **Parquet** for cached pipeline artifacts

---

## Project Structure

```
.
+-- api.py                          # FastAPI server (7 endpoints)
+-- src/
|   +-- __init__.py                 # Package exports + polarity contracts
|   +-- data_loader.py              # Load lab/visit/Rx data
|   +-- health_index.py             # Health Index scoring engine
|   +-- patient_regime.py           # 4-state regime classification
|   +-- health_var.py               # Monte Carlo Health VaR
|   +-- nlp_llm.py                  # LLM-based NLP scoring
|   +-- fusion.py                   # Composite risk score + rating
|   +-- eci.py                      # Expected Cost Intensity
|   +-- sut_pricing.py              # SUT cost estimation
|   +-- sut_catalog.py              # SUT gazette parser
|   +-- outcomes.py                 # Patient profiles + CSI + narratives
|   +-- validation.py               # SOFA/APACHE II validation
|   +-- chatbot.py                  # AI chatbot context + streaming
|   +-- visualizer.py               # Matplotlib plotting utilities
+-- frontend/
|   +-- src/app/page.tsx            # Main page (landing + dashboard)
|   +-- src/components/             # React components
|   +-- src/lib/types.ts            # TypeScript interfaces
|   +-- src/lib/constants.ts        # Colors, ratings, chart config
+-- data/
|   +-- sut_ek2b.json              # 5,074 SUT procedures (parsed)
|   +-- sut_ek2c.json              # 2,423 SUT packages (parsed)
+-- scripts/                        # Offline scoring scripts
+-- docs/                           # Documentation
+-- sut data/                       # Raw SUT gazette Excel files
```
