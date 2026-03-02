# ILAY 🏥
### AI-Powered Clinical Risk Intelligence
**ACUHIT Healthcare Innovation & Technology Hackathon 2026 — Acıbadem University**

---

## What is this?

ILAY repurposes **quantitative finance risk tools** (regime detection, Value-at-Risk, credit rating, NLP signal extraction) for real-time clinical decision support on hospital patient data.

The core insight: **lab test time-series behave like financial time-series. Patient clinical states map directly to market regimes. Health risk scoring is structurally identical to credit risk modeling.**

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Optional: transformer NLP (zero-shot NLI — falls back to rule-based automatically)
pip install transformers torch sentencepiece

# Launch the interactive dashboard
cd Acıbadem/
streamlit run streamlit_app.py
```

---

## Directory Structure

```
Acıbadem/
├── requirements.txt          ← pinned dependencies
├── src/
│   ├── __init__.py           ← public API exports
│   ├── data_loader.py        ← ODS parsers (labdata, anadata, recete)
│   ├── health_index.py       ← HealthIndexBuilder: lab + vitals → scalar [0,100]
│   ├── patient_regime.py     ← PatientRegime™: 4-state clinical state machine
│   ├── health_var.py         ← HealthVaR™: Monte Carlo deterioration forecast
│   ├── nlp_signal.py         ← NLP: zero-shot NLI transformer
│   ├── fusion.py             ← Composite Risk Score (AAA–B/CCC credit rating)
│   ├── outcomes.py           ← Clinical Severity Index (CSI) + outcome prediction
│   ├── validation.py         ← 5 retrospective validation experiments
│   ├── advanced_analytics.py ← GARCH vol, drawdown, stress scenarios, rolling metrics
│   └── visualizer.py         ← matplotlib charts
├── docs/
│   ├── CALCULATION_LOGIC.md              ← **PLAIN LANGUAGE guide to all formulas**
│   ├── FUSION_WEIGHTS_EVIDENCE.md        ← evidence for composite score weights
│   ├── HEALTH_INDEX_WEIGHT_JUSTIFICATION.md← evidence for health index weights
│   └── PARAMETER_EVIDENCE_REPORT.md      ← full parameter justification (PMIDs)

├── papers/                   ← reference clinical literature
└── *.ods                     ← labdata.ods · anadata.ods · recete.ods
```

---

## Dashboard — 4 Tabs

### 🏥 Tab 1: Cohort Overview
Real-time risk intelligence across all monitored patients:
- KPI cards: active patients, mean health score, high-risk count, critical-state count
- Cohort risk scatter (composite score vs health index, sized by visits)
- Rating distribution bar chart (AAA → B/CCC)
- Full cohort table with sortable composite scores, ratings, regime states, VaR tiers

### 🔬 Tab 2: Patient Explorer
Deep-dive per selected patient:
- 6 summary metrics (age, sex, composite rating, health index, lab draws, prescriptions)
- **PatientRegime™** timeline with prescription event overlay
- **HealthVaR™** Monte Carlo fan chart
- NLP sentiment bar chart (per-visit composite score over time)
- **NLP Validation table** — every clinical note scored by Zero-Shot NLI, with an overall NLP score footer and CSV download
- Lab time-series (all test values over time)
- Raw clinical notes expander (ÖYKÜ, YAKINMA, Muayene Notu, Kontrol Notu)

### 🎯 Tab 3: Outcome Predictor
- Clinical Severity Index (CSI) gauge + narrative assessment
- CSI feature decomposition bar chart
- Cohort CSI ranking (selected patient highlighted)
- Predictive feature correlations vs healthcare utilization

### 📊 Tab 4: Validation
Five retrospective experiments, all run automatically — no doctor labels required.

---

## The 5 Analysis Engines

### 1. PatientRegime™ (inspired by market regime detection)

Maps a patient's health score trajectory to 4 clinical states using two dimensions simultaneously:

| | Low Volatility | High Volatility |
|---|---|---|
| **Improving Trend** | 🟢 **STABLE** | 🟡 **RECOVERING** |
| **Declining Trend** | 🟠 **DETERIORATING** | 🔴 **CRITICAL** |

- **Trend** = health score vs 3-draw moving average
- **Volatility** = rolling standard deviation percentile rank

### 2. HealthVaR™ (inspired by financial Value-at-Risk)

> *"With 95% confidence, this patient's health score will NOT fall below X in the next 3 lab draws."*

Monte Carlo bootstrap over health score return history → probability cone → 5th percentile = Health VaR.

Risk tiers: 🟢 GREEN (VaR > +5%) → 🟡 YELLOW → 🟠 ORANGE → 🔴 RED (VaR < −10%)

### 3. NLP Signal - Zero-Shot NLI

Scores each visit's free-text notes across **all 5 available note types** (ÖYKÜ, Muayene Notu, Kontrol Notu, YAKINMA, Tedavi Notu) on a spectrum from −1.0 (deterioration) to +1.0 (recovery).

Column weights for the composite NLP score:

| Column | Weight |
|---|---|
| ÖYKÜ (patient history) | 35% |
| Muayene Notu (exam note) | 30% |
| Kontrol Notu (follow-up) | 20% |
| YAKINMA (chief complaint) | 10% |
| Tedavi Notu (treatment note) | 5% |

### 4. Composite Risk Score (inspired by credit rating)

Fuses all signals into a single actionable score:
- **55%** Health Index (lab + vital trajectory)
- **30%** Clinical NLP signal
- **15%** Medication change velocity

Output: **AAA / AA / A / BBB / BB / B/CCC**

### 5. Clinical Severity Index (CSI)

Integrates: health trend · lab volatility · Critical regime fraction · NLP signal · prescription intensity · comorbidity burden → predicts healthcare utilization.

---

## Metric Computation Reference

> This section documents **exactly how every composite metric is calculated**, tracing the logic from raw data all the way to the final number. All references are to files under `src/`.

---

### Metric 1 — Health Index (`src/health_index.py`)

**Purpose:** Convert raw lab results and vital signs into a single scalar score in **[0, 100]** where 100 = perfectly normal and 0 = maximally abnormal.

#### Step 1 — Lab z-score per test

For every lab result on a given draw date, a one-sided z-score is computed against the hospital-supplied reference range (or the Ozarda 2014 Turkish population fallback):

```
ref_std = (ref_max − ref_min) / 4          # assumes ±2σ spans 95% interval
if value < ref_min:   z = (ref_min − value) / ref_std   # below range
elif value > ref_max: z = (value − ref_max) / ref_std   # above range
else:                 z = 0.0                            # within range → healthy
```

Key design decision: z is **one-sided** — a value comfortably within the range gets z = 0 regardless of its distance from the midpoint. This prevents false penalisation for tests like CRP (where 0 is perfectly healthy but midpoint-z would give |z| ≈ 2).

Reference ranges are sourced in priority order:
1. Hospital-supplied `REFMIN` / `REFMAX` columns from `labdata.ods`
2. Fallback: Ozarda 2014 Turkish population RI table (PMID 25153598) for ~20 common analytes

#### Step 2 — Organ-system grouping and weighted mean z

Tests are classified into organ systems (inflammatory, renal, hepatic, hematological, metabolic, endocrine, coagulation, other) via keyword matching on the test name. Within each organ system the mean z-score is computed. Then organ systems are aggregated with a weighted sum:

```
mean_z = Σ (system_mean_z × system_weight) / Σ system_weights
```

| System | Weight | Key tests | Evidence |
|---|---|---|---|
| inflammatory | 0.25 | CRP, WBC, Neutrophils, Lymphocytes | Strong early-warning (HR 2.07) |
| renal | 0.18 | Creatinine, Urea, GFR | SOFA/APACHE emphasis |
| hematological | 0.18 | Haemoglobin, Platelets, MCV, RDW | Anemia predictor (OR 1.99) |
| metabolic | 0.17 | Glucose, Na, K, Albumin, Cholesterol | Electrolyte OR 3–4 |
| hepatic | 0.12 | ALT, AST, ALP, GGT, Bilirubin | SOFA hepatic (OR 2.2) |
| coagulation | 0.07 | INR, PT, aPTT | INR AUC 0.94–0.95 |
| endocrine | 0.02 | TSH, T3, T4 | Epiphenomenon only |
| other | 0.01 | all unclassified tests | Catch-all |

**Full keyword mapping:** See `docs/CALCULATION_LOGIC.md` for the complete list of which test names map to which organ system.

#### Step 3 — Exponential decay to health score

```
lab_score = 100 × exp(−0.25 × mean_z)
```

Intuition: z = 0 → score = 100; z = 2 → score ≈ 60; z = 4 → score ≈ 20; z ≥ 8 → score ≈ 0.

#### Step 4 — Vital signs scoring (parallel path)

The same **one-sided z-score formula** is applied to each of the four vitals (systolic BP, diastolic BP, pulse, SpO2) against published clinical norms (WHO ISH 2020 / ESH 2018). The mean vital z is transformed identically:

```
vital_score = 100 × exp(−0.25 × mean_vital_z)
```

**One-sided z-score explained:**
- Values **inside** the reference range → z = 0 (no penalty, healthy)
- Values **below** the reference range → z = positive (penalized, e.g., low SpO2, low BP)
- Values **above** the reference range → z = positive (penalized, e.g., high BP, high pulse)

**Key difference from traditional z-score:** We do NOT penalize values comfortably within the range. A traditional z-score would penalize CRP=0 as "2 standard deviations below the mean" — but CRP=0 is perfectly healthy (no inflammation). Our one-sided approach correctly assigns z=0 to all in-range values.

**30-day lookup rule:**
1. Find the **nearest past vital signs visit** on or before the scoring date
2. If the nearest visit is **within 30 days** → use those vitals
3. If the nearest visit is **older than 30 days** OR no vitals exist → `vital_score = 100`

**Why 30 days?** Outpatient vitals become stale quickly. A BP measurement from 60 days ago may not reflect current status. The 30-day window balances recency with data availability.

**Conservative default:** If vitals are missing or outdated, we assume `vital_score = 100` (normal). This is **conservative** — we do not penalize patients for missing data, which could introduce bias against patients with sparse records.

| Vital Sign | Normal Range | Source |
|---|---|---|
| Systolic BP | 90–130 mmHg | WHO ISH 2020 / ESH 2018 |
| Diastolic BP | 60–85 mmHg | WHO ISH 2020 / ESH 2018 |
| Pulse | 60–100 bpm | Standard clinical range |
| SpO2 | 95–100% | WHO / BTS guidelines |

#### Step 5 — Composite health score per date

```
if both labs AND vitals available:
    health_score = 0.60 × lab_score + 0.40 × vital_score

if only labs:
    health_score = lab_score

if only vitals:
    health_score = vital_score
```

**Output:** A `HealthSnapshot` time-series, one point per unique lab-draw or vital-visit date, with `health_score ∈ [0, 100]`.

---

### Metric 2 — PatientRegime™ (`src/patient_regime.py`)

**Purpose:** Classify each observation in the health score time-series into one of four clinical states using a 2×2 grid of (trend direction × volatility level), inspired by market regime detection.

#### Step 1 – Rolling moving average (MA, window = 3 draws)

```
MA[i] = mean(scores[i − 2 : i + 1])
```

The first 2 observations have no MA and are left unclassified.

#### Step 2 — Rolling standard deviation (volatility, window = 4 draws)

```
vol[i] = std(scores[i − 3 : i + 1], ddof=1)
```

Requires at least 3 observations; otherwise returns `None`.

#### Step 3 — Volatility percentile rank (lookback = 20 draws)

Each `vol[i]` is ranked within the patient's own historical volatility up to that point:

```
vol_percentile[i] = count(historical_vols ≤ vol[i]) / len(historical_vols) × 100
```

Requires ≥ 3 non-null historical vol values; defaults to 50.0 (neutral) otherwise. This is **self-normalising per patient** — it compares against each patient's own baseline.

#### Step 4 — Boolean flags

```
trend_positive = (health_score[i] >= MA[i])
vol_high       = (vol_percentile[i] >= 60.0)    # 60th-percentile threshold
```

#### Step 5 — 2×2 state assignment

```
trend_positive=True,  vol_high=False → STABLE        🟢
trend_positive=True,  vol_high=True  → RECOVERING     🟡
trend_positive=False, vol_high=False → DETERIORATING  🟠
trend_positive=False, vol_high=True  → CRITICAL       🔴
```

**Output:** A `PatientRegimeResult` with a `RegimePoint` per date containing MA, rolling_vol, vol_percentile, trend_positive, vol_high, and state.

---

### Metric 3 — HealthVaR™ (`src/health_var.py`)

**Purpose:** Quantify downside risk over the next N lab draws with a Monte Carlo simulation — analogous to financial Value-at-Risk. Answers: *"With 95% confidence, this patient's health score will NOT fall below X in the next 3 draws."*

#### Step 1 — Arithmetic returns

```
returns[i] = (score[i] − score[i−1]) / max(score[i−1], 1.0)
```

Arithmetic (not log) returns are used because log-returns are numerically explosive when health scores approach zero.

#### Step 2 — Monte Carlo bootstrap (5,000 iterations)

For each of 5,000 paths:
1. Start from `current_score = scores[-1]` (most recent)
2. For each of `horizon = 3` steps: sample one return at random (with replacement) from history → `path = clip(path × (1 + sampled_return), 0, 100)`
3. Record the terminal score

#### Step 3 — Percentile fan chart

```
p05, p25, p50, p75, p95 = percentiles(5000 terminal scores, [5, 25, 50, 75, 95])
```

#### Step 4 — Relative VaR %

```
VaR% = (p05 − current_score) / max(current_score, 1) × 100
```

A negative VaR% means the model expects the patient to decline.

#### Step 5 — Conditional VaR (Expected Shortfall)

```
CVaR% = VaR% × 1.3    if VaR% < 0   (conservative bound; 1.3× is a proxy for proper ES)
CVaR% = 0             if VaR% ≥ 0   (no tail risk)
```

#### Step 6 — Risk tier

| VaR% | Tier | Clinical label |
|---|---|---|
| > +5% | 🟢 GREEN | Health Stable |
| 0 to +5% | 🟡 YELLOW | Low Risk |
| −10% to 0% | 🟠 ORANGE | Moderate Risk — review within 24–48h |
| < −10% | 🔴 RED | High Risk — prioritize review |

**Output:** `HealthVaRResult` — `p05–p95` fan points, `var_pct`, `cvar_pct`, `risk_tier`.

---

### Metric 4 — NLP Signal (`src/nlp_signal.py`)

**Purpose:** Extract a clinical signal from free-text Turkish clinical notes using zero-shot NLI classification and collapse it to a composite score per visit in **[−1.0, +1.0]**.

#### Step 1 — Zero-shot NLI classification per text column

Each non-empty text snippet (truncated to 512 tokens) is fed into the `MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli` pipeline with three candidate labels in Turkish:

```
labels     = ["kötüleşme", "iyileşme", "nötr"]
template   = "Bu klinik metin {} ile ilgilidir."
```

The model uses textual entailment (NLI), not sentiment analysis, which means it reasons about the *meaning* of the text rather than emotional polarity. The top-ranked label and its confidence probability are returned.

#### Step 2 — Score with confidence dampening

```
base_score     = {"kötüleşme": −1.0, "iyileşme": +1.0, "nötr": 0.0}[top_label]
column_score   = base_score × top_confidence
```

Confidence dampening pulls uncertain predictions toward 0 (e.g. 34% confidence → only 34% of the full signal).

#### Step 3 — Weighted composite across columns

```
total_weight   = Σ weight[col]  for available columns
nlp_composite  = Σ (column_score[col] × weight[col] / total_weight)
nlp_composite  = clip(nlp_composite, −1.0, +1.0)
```

Column weights:

| Column | Weight | Rationale |
|---|---|---|
| ÖYKÜ | 0.35 | Most detailed narrative — patient history |
| Muayene Notu | 0.30 | Physical exam findings |
| Kontrol Notu | 0.20 | Follow-up / progress notes |
| YAKINMA | 0.10 | Chief complaint (short, high signal density) |
| Tedavi Notu | 0.05 | Treatment note (often formulaic) |

Missing columns are excluded and remaining weights are re-normalised.

**Output:** A DataFrame with `nlp_<col>` score columns and `nlp_composite ∈ [−1, +1]` per visit.

---

### Metric 5 — Composite Risk Score (`src/fusion.py`)

**Purpose:** Fuse the Health Index, NLP signal, and medication change velocity into a single credit-style score in **[0, 100]** with a rating label (AAA → B/CCC).

#### Step 1 — NLP normalisation: [−1, +1] → [0, 100]

The NLP score is stretched 2× so the typical clinical range [−0.5, +0.5] expands to fill most of [0, 100]:

```
stretched = nlp_composite × 2.0
nlp_norm  = clip((stretched + 1.0) / 2.0 × 100, 0, 100)
```

#### Step 2 — Medication change velocity score: [0, 100]

Based on prescription records from `recete.ods`. The score penalises high rates of new/different drugs (a proxy for unstable or escalating disease):

**Single-day prescriptions** (all on one visit):
```
score = max(10, 100 − n_unique_drugs × 12)
```

**Multi-day prescriptions:**
```
changes_per_month = (n_unique_drugs / date_span_days) × 30
score = max(10, 100 − changes_per_month × 9)
```

Higher velocity → lower score. Default when no data: `80.0`.

#### Step 3 — Weighted fusion

```
composite = 0.55 × health_score
          + 0.30 × nlp_norm
          + 0.15 × med_change_score

composite = clip(composite, 0, 100)
```

Weight evidence: 55% labs/vitals (structured data dominates clinical prediction per Rajkomar 2018, PMID 31304302); 30% NLP (multi-modal gains +1–5% AUROC per Garriga 2023, PMID 37913776); 15% medication (polypharmacy risk per PMID 28784299, conservative for confounding).

#### Step 4 — Credit rating

| composite ≥ | Rating | Label |
|---|---|---|
| 85 | **AAA** | Excellent — stable health |
| 70 | **AA** | Good — minor abnormalities |
| 55 | **A** | Moderate — monitoring recommended |
| 40 | **BBB** | Below average — clinical review needed |
| 25 | **BB** | Elevated risk — active intervention recommended |
| 0 | **B/CCC** | High risk — urgent clinical attention |

**Output:** `CompositeRiskScore` — composite_score, rating, and three component scores.

---

### Metric 6 — Clinical Severity Index / CSI (`src/outcomes.py`)

**Purpose:** A severity burden score in **[0, 100]** integrating six clinical dimensions (0 = minimal burden, 100 = maximum burden) oriented to predict healthcare utilisation.

#### Step 1 — Six component normalisation (each → [0, 100])

| Component | Raw feature | Formula |
|---|---|---|
| **Health trend** | OLS slope of health scores (pts/observation) | `clip((−slope + 5) / 10 × 100, 0, 100)` — −5 pts/visit → 100, +5 pts/visit → 0 |
| **Lab volatility** | Std dev of health score series | `clip(std / 20 × 100, 0, 100)` — std of 20 → 100 |
| **Critical fraction** | Fraction of regime observations in Critical state | `clip(fraction × 100, 0, 100)` |
| **NLP signal** | Mean NLP composite across all visits | `clip((−mean_nlp + 1) / 2 × 100, 0, 100)` — −1 (worst) → 100 |
| **Prescription intensity** | Unique prescriptions per 30 days | `clip(rx_velocity / 10 × 100, 0, 100)` — 10 Rx/month → 100 |
| **Comorbidity burden** | Count of active comorbidity flags | `clip(n_comorbidities / 4 × 100, 0, 100)` — 4 or more → 100 |

The health trend slope uses ordinary least-squares:

```
slope = Σ (x_i − x̄)(y_i − ȳ) / Σ (x_i − x̄)²    where x = observation index, y = health_score
```

Prescription velocity:

```
rx_velocity = (n_dated_prescriptions / date_span_days) × 30
```

Comorbidities are counted from 6 binary flag columns in `anadata.ods`: hypertension, cardiovascular disease, diabetes, blood disorders, other chronic diseases, and surgical history.

#### Step 2 — Weighted sum

```
CSI = 0.25 × health_trend_component
    + 0.20 × lab_volatility_component
    + 0.20 × critical_fraction_component
    + 0.15 × nlp_signal_component
    + 0.10 × prescription_intensity_component
    + 0.10 × comorbidity_burden_component

CSI = clip(CSI, 0, 100)
```

#### Step 3 — Tier assignment

| CSI ≥ | Tier | Label |
|---|---|---|
| 75 | **CRITICAL** | Immediate clinical attention required |
| 50 | **HIGH** | Active intervention recommended |
| 25 | **MODERATE** | Enhanced monitoring needed |
| 0 | **LOW** | Routine monitoring |

**Output:** `csi_score`, `csi_tier`, `csi_label`, and `feature_contributions` dict (each component's weighted contribution in CSI points).

---

### Advanced Analytics (`src/advanced_analytics.py`)

All 12 analytics operate on the health score `SeriesPoint` list. Arithmetic returns are computed first:

```
returns[i] = (score[i] − score[i−1]) / max(score[i−1], 1.0)
```

---

#### AA-1 — Lab Instability Forecaster (EWMA/GARCH Volatility)

Predicts whether lab variability will increase or decrease using an Exponentially Weighted Moving Average variance update:

```
σ²[i] = 0.15 × r[i]² + 0.85 × σ²[i−1]    (α = 0.15, λ = 0.85)

forecast_vol[i] = sqrt(σ²[i]) × 100   (%)
realized_vol[i] = std(r[max(0, i−5) : i+1]) × 100
```

Regimes: `low` if `forecast_vol < 5%`, `high` if `> 20%`, else `normal`.

---

#### AA-2 — Clinical Stress Testing

Applies quantile-based shocks from the return distribution:

```
worst_day              = min(returns) × 100
99th_pct_adverse       = percentile(returns, 1) × 100
2x_historical_worst    = min(returns) × 200
expected_shortfall     = mean(returns[returns < percentile(returns, 5)]) × 100
```

---

#### AA-3 — Temporal Clinical Validation (Walk-Forward)

Expanding-window walk-forward split over the health return series. For each split s:

```
train = returns[0 : chunk × (s+1)]
test  = returns[chunk × (s+1) : chunk × (s+2)]
train_sharpe = mean(train) / std(train) × sqrt(252)
test_sharpe  = mean(test)  / std(test)  × sqrt(252)
```

`is_robust = True` if `test_sharpe > 0` across all splits. Uses 3 splits by default.

---

#### AA-4 — Patient Suffering Index (Ulcer Index + CVaR + Profit Factor)

**Ulcer Index** — captures both depth *and* duration of health declines (unlike max drawdown which only captures depth):

```
peak[i]     = max(scores[0 : i+1])              (running peak)
dd_pct[i]   = (scores[i] − peak[i]) / peak[i] × 100
ulcer_index = sqrt(mean(dd_pct²))
```

**CVaR (5%):**
```
CVaR = mean(sorted_returns[ : max(int(n × 0.05), 1)])
```

**Profit Factor:**
```
profit_factor = sum(positive returns) / |sum(negative returns)|
```

**Expectancy Ratio:**
```
expectancy = mean(returns) / std(returns)
```

---

#### AA-5 — Organ System Risk Decomposition

Decomposes total health risk into per-organ-system contributions using weighted variance:

```
contrib[k]       = weight[k] × var(returns_k)
contribution_pct[k] = contrib[k] / Σ contrib × 100
```

Shows which organ system is driving the most volatility in the overall health score.

---

#### AA-6 — Lab Cross-Correlation Matrix

Pairwise Pearson correlation between any two lab test time-series (aligned to minimum shared length, minimum 3 points):

```
corr(lab1, lab2) = corrcoef(lab1_values, lab2_values)[0, 1]
```

---

#### AA-7 — Optimal Fusion Weights (Mean-Variance Optimisation)

Random-search mean-variance optimisation over 2,000 Dirichlet-sampled weight vectors. For each weight vector `w`:

```
combo  = Σ w[k] × returns_k
sharpe = mean(combo) / std(combo)
```

`best_weights = argmax(sharpe)`. Dirichlet sampling guarantees weights sum to 1.

---

#### AA-8 — Optimal Intervention Sizing (Kelly Criterion)

Adapted half-Kelly from trading to clinical intervention intensity:

```
win_rate  = count(returns > 0) / len(returns)
wl_ratio  = mean(positive_returns) / |mean(negative_returns)|
kelly     = max(0, win_rate − (1 − win_rate) / wl_ratio) × 0.5   (half-Kelly)
```

| kelly | Recommendation |
|---|---|
| > 0.6 | Maintain current treatment |
| 0.3 – 0.6 | Standard care, periodic review |
| 0.1 – 0.3 | Consider treatment adjustment |
| < 0.1 | Escalate care — reassess treatment plan |

---

#### AA-9 — Clinical Signal Significance Testing

One-sample t-test combined with bootstrap permutation:

```
t_stat  = mean(returns) / (std(returns, ddof=1) / sqrt(n))
p_val   = erfc(|t_stat| / sqrt(2))       # Gaussian approximation

bootstrap (1000 resamples):
  boot_p = count(bootstrap_mean ≤ 0) / 1000
```

`is_significant = True` if `p_val < 0.05`.

---

#### AA-10 — Stability-Weighted Health Score (Inverse Volatility)

Weights each lab test time-series inversely by its own volatility so that noisier labs exert less influence:

```
inv_vol[k] = 1 / std(lab_values_k)
weight[k]  = inv_vol[k] / Σ inv_vol
```

---

#### AA-11 — Rolling Health Trajectory Dashboard

Sliding-window (default 5 observations) metrics computed at each time step `i`:

```
window slice: w = scores[i − window : i + 1]
rets          = diff(w) / max(w[:-1], 0.01)

rolling_return    = (w[−1] / w[0]) − 1
rolling_vol       = std(rets)
rolling_sharpe    = mean(rets) / std(rets)
rolling_drawdown  = min((w − running_peak(w)) / running_peak(w))
```

---

#### AA-12 — Maximum Clinical Decline (Drawdown Analysis)

Full peak-to-trough drawdown analysis identical to financial max drawdown:

```
peak[i]          = max(scores[0 : i+1])            (running peak)
dd[i]            = (scores[i] − peak[i]) / peak[i]   (always ≤ 0)
max_drawdown_pct = min(dd) × 100  (%)
```

Recovery is detected as the first index after the trough where `scores[i] ≥ peak[at_trough]`. Recovery time is measured in calendar days.

```
current_drawdown_pct = (scores[−1] − peak[−1]) / peak[−1] × 100
```

---

## Data Pipeline

| File | Content |
|---|---|
| `labdata.ods` | Lab results time-series per patient |
| `anadata.ods` | Patient visits with Turkish clinical text (69 columns) |
| `recete.ods` | Prescription records |

---

## Validation Experiments

Five retrospective experiments (no ground-truth labels required):

| # | Hypothesis | Test | Clinical Meaning |
|---|---|---|---|
| 1 | Critical regime → higher Rx velocity | Spearman ρ | Regime is clinically meaningful |
| 2 | RED VaR → more visits | Spearman ρ | VaR has predictive power |
| 3 | Negative NLP → more visits | Spearman ρ | Turkish NLP detects clinical signal |
| 4 | High volatility → more Critical episodes | Spearman ρ | Regime dimensions are not redundant |
| 5 | Higher CSI → more visits | Spearman ρ | CSI calibrated to utilization |

> **Caveat:** Small cohort — all statistical results are exploratory and directional. The framework is designed for scale.

---

## Documentation Guide — For Different Audiences

### 👨‍⚕️ **For Clinicians / Medical Reviewers**

Start here — no coding required:

| Document | What It Explains | Why Read It |
|----------|------------------|-------------|
| **`docs/CALCULATION_LOGIC.md`** | **Plain language guide to all formulas** | Understand exactly how scores are calculated without reading code |
| `docs/PARAMETER_EVIDENCE_REPORT.md` | Clinical evidence for all parameters (PMIDs included) | See which guidelines and studies justify each number |
| `docs/FUSION_WEIGHTS_EVIDENCE.md` | Why 55% labs, 30% NLP, 15% meds | Evidence from Rajkomar 2018, Garriga 2023, polypharmacy meta-analyses |

**Key questions answered:**
- Why is CRP=0 not penalized but Hemoglobin=8 is? → **One-sided z-score** (see CALCULATION_LOGIC.md Step 1)
- What happens if vitals are missing? → **30-day rule + conservative default** (see CALCULATION_LOGIC.md Step 6)
- Which organ systems matter most? → **Inflammatory 25%, Renal 25%, Metabolic 20%** (see HEALTH_INDEX_WEIGHT_JUSTIFICATION.md)
- Why these specific weights? → **SOFA/APACHE comparison + outcome studies** (see PARAMETER_EVIDENCE_REPORT.md)

---

## Key Technical Decisions

**Why percentile-rank volatility instead of absolute std?**  
Patient baselines differ. Percentile rank is self-normalizing within each patient's own history.

**Why credit ratings (AAA–B)?**  
Clinicians already use risk-tier language. We quantify existing intuition rather than introducing new vocabulary.

**Why Monte Carlo on health score returns?**
Assumes today's volatility regime is representative of near-term future — same assumption used in finance, same caveat applies post-surgery.

---

### 👨‍💻 **For Developers / Modelers**

| Document | What It Explains |
|----------|------------------|
| `src/health_index.py` | Lab/vital scoring (z-score, organ weights, exponential decay) |
| `src/patient_regime.py` | 4-state classification (trend × volatility grid) |
| `src/health_var.py` | Monte Carlo VaR (5,000 iterations, bootstrap) |
| `src/fusion.py` | Composite fusion (55/30/15, credit rating tiers) |
| `src/outcomes.py` | CSI calculation (6 components, OLS trend) |
| `src/nlp_signal.py` | Zero-shot NLI (Turkish text, confidence dampening) |

---

### 📊 **For Data Scientists / Researchers**

| Document | What It Explains |
|----------|------------------|
| `docs/HEALTH_INDEX_WEIGHT_JUSTIFICATION.md` | Organ weight derivation from SOFA/APACHE II |
| `docs/PARAMETER_EVIDENCE_REPORT.md` | Full parameter table with PMIDs (vital ranges, decay constant λ=0.25) |
| `src/validation.py` | 5 retrospective experiments (Spearman ρ, no labels needed) |
| `src/advanced_analytics.py` | 12 finance→healthcare transfers (GARCH, Kelly, Ulcer Index) |
| `src/advanced_analytics.py` | Mean-variance optimization for weight calibration |

---

## Explicit Limitations

1. **Small cohort** — all statistical results are exploratory
2. **Irregular lab spacing** — regime uses observation-indexed time, not calendar time
3. **No clinical ground truth** — Critical state NOT validated against APACHE/SOFA
4. **Threshold calibration** — regime percentiles tuned heuristically, not from clinical data
5. **NLP coverage** — ~70 keywords; will miss rare medical abbreviations

---

*ILAY — "From Wall Street to the Bedside"*  
*ACUHIT Hackathon 2026 | Acıbadem Mehmet Ali Aydınlar University*
