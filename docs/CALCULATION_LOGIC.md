# Clinical Calculation Logic — Plain Language Guide

**Purpose:** Explain **how** every metric is calculated in non-technical language. For clinicians who want to understand the math without reading Python code.

**Audience:** Doctors, nurses, clinical researchers reviewing the ILAY system.

---

## 1. Health Index Calculation

### What Goes In
- **Lab results** (blood tests from `labdata.ods`)
- **Vital signs** (BP, pulse, SpO2 from `anadata.ods`)

### What Comes Out
- **Health Score**: 0–100 (100 = perfectly normal, 0 = maximally abnormal)

---

### Step 1: Compare Each Lab to "Normal Range"

Every lab test has a **reference range** (what's considered normal for healthy adults):

| Test | Normal Range | Patient Result | Status |
|------|--------------|----------------|--------|
| Hemoglobin | 11.9–14.9 g/dL | **8.0** | ❌ Too LOW |
| Hemoglobin | 11.9–14.9 g/dL | **13.0** | ✅ Normal |
| Hemoglobin | 11.9–14.9 g/dL | **18.0** | ❌ Too HIGH |
| CRP | 0–5 mg/L | **0** | ✅ Normal (low is GOOD!) |
| CRP | 0–5 mg/L | **100** | ❌ Too HIGH |

**Key Rule:** We only penalize values **outside** the range. Inside = healthy.

**Special Case — "Low-Floor" Tests:**
Some tests are "good when low":
- **CRP**: 0 = no inflammation (perfectly healthy)
- **Prokalsitonin**: 0 = no bacterial infection
- **D-Dimer**: 0 = no blood clot

For these, "below range" is NOT penalized — only "above range" matters.

---

### Step 2: Convert "How Abnormal" to a Z-Score

**Z-score** = "How many standard deviations away from normal?"

```
If too LOW:   z = (ref_min - value) / standard_deviation
If too HIGH:  z = (value - ref_max) / standard_deviation
If normal:    z = 0
```

**Examples:**

| Test | Range | Patient | Z-Score | Meaning |
|------|-------|---------|---------|---------|
| Hemoglobin | 11.9–14.9 | 8.0 | **2.6** | Severely low |
| Sodium | 137–144 | 120 | **5.7** | Critically low |
| Glucose | 70–100 | 200 | **6.7** | Severely high |
| CRP | 0–5 | 0 | **0** | Perfectly normal |
| CRP | 0–5 | 100 | **19.0** | Extremely high |

---

### Step 3: Group Labs by Organ System

Each test belongs to an **organ system**:

| Organ System | Tests Included | Weight |
|--------------|----------------|--------|
| **Inflammatory** | CRP, WBC, Neutrophils, Lymphocytes, Prokalsitonin | **25%** |
| **Renal** | Creatinine, Urea, GFR | **25%** |
| **Hematological** | Hemoglobin, Hematocrit, RBC, MCV, MCH, RDW | **18%** |
| **Metabolic** | Glucose, Sodium, Potassium, Albumin, Cholesterol | **20%** |
| **Hepatic** | ALT, AST, ALP, GGT, Bilirubin | **12%** |
| **Coagulation** | INR, PT, aPTT | **7%** |
| **Endocrine** | TSH, T3, T4 | **2%** |
| **Other** | Unclassified tests | **3%** |

**Why weights matter:**
- Inflammatory markers get 25% because they're early warning signals (infection, sepsis)
- Coagulation gets 7% because INR/PT abnormalities strongly predict mortality (AUC 0.94–0.95)
- Endocrine gets only 2% because thyroid markers are "epiphenomena" (result of illness, not cause)

---

### Step 4: Calculate Weighted Average Z-Score

**Example Patient:**

| Organ System | Mean Z-Score | Weight | Contribution |
|--------------|--------------|--------|--------------|
| Inflammatory | 3.0 | 25% | 3.0 × 0.25 = **0.75** |
| Renal | 1.5 | 25% | 1.5 × 0.25 = **0.375** |
| Hematological | 0.5 | 18% | 0.5 × 0.18 = **0.09** |
| Metabolic | 2.0 | 20% | 2.0 × 0.20 = **0.40** |
| **Total** | | **100%** | **mean_z = 1.615** |

---

### Step 5: Convert to Health Score Using Exponential Decay

**Formula:**
```
Lab Score = 100 × e^(-0.25 × mean_z)
```

**Why exponential?**
- Gentle penalty for small abnormalities
- Steep penalty for large abnormalities
- Never goes negative (unlike linear formulas)

**Lookup Table:**

| Mean Z-Score | Calculation | Health Score | Clinical Meaning |
|--------------|-------------|--------------|------------------|
| 0 (all normal) | 100 × e^0 | **100** | Perfectly healthy |
| 1 (mild) | 100 × e^(-0.25) | **78** | Minor issues |
| 2 (moderate) | 100 × e^(-0.5) | **61** | Noticeable decline |
| 3 (significant) | 100 × e^(-0.75) | **47** | Concerning |
| 4 (severe) | 100 × e^(-1.0) | **37** | Critical range |
| 6 (very severe) | 100 × e^(-1.5) | **22** | Near failure |

---

### Step 6: Vital Signs Scoring (Same Formula)

**4 Vitals Checked:**

| Vital | Normal Range | Source |
|-------|--------------|--------|
| Systolic BP | 90–130 mmHg | WHO ISH 2020 |
| Diastolic BP | 60–85 mmHg | ESC/ESH 2018 |
| Pulse | 60–100 bpm | Standard clinical |
| SpO2 | 95–100% | WHO / BTS |

**Same z-score formula:**
```
If BP = 160/95: z = (160-130)/std = 2.5 → penalized
If SpO2 = 88%:  z = (95-88)/std = 4.7 → penalized
If Pulse = 72:  z = 0 → no penalty (in range)
```

**30-Day Rule:**
- Use the **closest past visit within 30 days**
- If no vitals within 30 days → assume **vital_score = 100** (conservative)
- **Rationale:** Don't penalize missing data; assume normal if unknown

---

### Step 7: Combine Labs + Vitals

```
If both labs AND vitals available:
    Health Score = 0.60 × Lab Score + 0.40 × Vital Score

If only labs available:
    Health Score = Lab Score

If only vitals available:
    Health Score = Vital Score
```

**Why 60/40?**
- Outpatient data is lab-rich, vital-sparse
- Labs provide more granular organ function data
- Vitals are still important (40% weight)

---

## 2. PatientRegime™ Classification

### What It Does
Classifies patient trajectory into 4 states: 🟢 Stable, 🟡 Recovering, 🟠 Deteriorating, 🔴 Critical

### Two Dimensions

| | **Low Volatility** | **High Volatility** |
|---|---|---|
| **Improving Trend** | 🟢 **Stable** | 🟡 **Recovering** |
| **Declining Trend** | 🟠 **Deteriorating** | 🔴 **Critical** |

### Step 1: Calculate Trend

```
Trend = Current Health Score vs 3-Draw Moving Average

If current ≥ moving_average → Trend is POSITIVE (improving)
If current < moving_average → Trend is NEGATIVE (declining)
```

**Example:**
```
Last 4 health scores: [65, 70, 72, 78]
3-draw MA = (70 + 72 + 78) / 3 = 73.3
Current = 78

78 ≥ 73.3 → POSITIVE trend ✓
```

---

### Step 2: Calculate Volatility

**Volatility** = "How much does the score bounce around?"

```
1. Calculate standard deviation of last 4 draws
2. Compare to patient's own history (percentile rank)
3. If above 60th percentile → HIGH volatility
```

**Why percentile rank?**
- Patients have different baselines
- A "volatile" diabetic may be "stable" for a trauma patient
- Self-normalizing: compares to own history

---

### Step 3: Assign State

```python
if trend_positive and not vol_high:
    state = "Stable"        🟢
elif trend_positive and vol_high:
    state = "Recovering"    🟡
elif not trend_positive and not vol_high:
    state = "Deteriorating" 🟠
else:
    state = "Critical"      🔴
```

---

## 3. Health VaR™ (Value at Risk)

### What It Answers
*"With 95% confidence, this patient's health score will NOT fall below X in the next 3 lab draws."*

### Step 1: Calculate Historical Returns

**Return** = "Percentage change from one draw to next"

```
Return = (Score_today - Score_yesterday) / Score_yesterday

Example: [80, 75, 78, 72]
Returns: [(75-80)/80=-0.0625, (78-75)/75=+0.04, (72-78)/78=-0.077]
```

---

### Step 2: Monte Carlo Simulation (5,000 Iterations)

For each of 5,000 simulated futures:
1. Start from current score (e.g., 72)
2. Randomly pick 3 returns from history (with replacement)
3. Apply them sequentially: `new_score = old_score × (1 + return)`
4. Record final score

**Result:** 5,000 possible future scores

---

### Step 3: Extract Percentiles

```
p05  = 5th percentile  (worst 5% of outcomes)
p25  = 25th percentile
p50  = 50th percentile (median forecast)
p75  = 75th percentile
p95  = 95th percentile (best 5% of outcomes)
```

**Health VaR = p05** (the "worst reasonable case")

---

### Step 4: Assign Risk Tier

| VaR% | Tier | Label |
|------|------|-------|
| > +5% | 🟢 GREEN | Health Stable |
| 0 to +5% | 🟡 YELLOW | Low Risk |
| −10% to 0% | 🟠 ORANGE | Moderate Risk |
| < −10% | 🔴 RED | High Risk |

**VaR% formula:**
```
VaR% = (p05 - current_score) / current_score × 100

Negative VaR% = expected decline
Positive VaR% = expected improvement
```

---

## 4. NLP Signal Scoring

### What It Does
Scores clinical text notes from −1.0 (deterioration) to +1.0 (recovery)

### Step 1: Zero-Shot NLI Classification

**Model:** `multilingual-MiniLMv2-L6-mnli-xnli`

**Task:** "This clinical text is about {deterioration / recovery / neutral}"

**Template (Turkish):**
```
"Bu klinik metin {kötüleşme / iyileşme / nötr} ile ilgilidir."
```

**Output:**
```
Text: "Hastanın genel durumu kötüleşti, ateş yükseldi."
Result:
  Label: "kötüleşme" (deterioration)
  Confidence: 0.87
  Score: -1.0 × 0.87 = -0.87
```

**Confidence Dampening:**
- 87% confident → 87% of full signal (-0.87)
- 34% confident → 34% of full signal (-0.34)
- Uncertain predictions pulled toward 0

---

### Step 2: Weight by Note Type

| Note Type | Weight | Rationale |
|-----------|--------|-----------|
| **ÖYKÜ** (History) | 35% | Most detailed narrative |
| **Muayene Notu** (Exam) | 30% | Physical exam findings |
| **Kontrol Notu** (Follow-up) | 20% | Progress notes |
| **YAKINMA** (Complaint) | 10% | Short, high signal density |
| **Tedavi Notu** (Treatment) | 5% | Often formulaic |

**Formula:**
```
Total Weight = sum of weights for available notes

NLP Composite = Σ (note_score × note_weight) / Total Weight

Result clipped to [-1.0, +1.0]
```

**Example:**
```
Patient has: ÖYKÜ (-0.6), Muayene Notu (+0.2), YAKINMA (-0.4)

Total Weight = 0.35 + 0.30 + 0.10 = 0.75

NLP Composite = [(-0.6×0.35) + (+0.2×0.30) + (-0.4×0.10)] / 0.75
              = [-0.21 + 0.06 - 0.04] / 0.75
              = -0.19 / 0.75
              = -0.25 (mild deterioration signal)
```

---

## 5. Composite Risk Score (Credit Rating Style)

### What It Does
Fuses Health Index, NLP, and Medication changes into AAA→B/CCC rating

### Step 1: Normalize NLP to 0–100 Scale

NLP is [-1, +1] but needs to be [0, 100] for fusion:

```
stretched = nlp_composite × 2.0
nlp_norm  = (stretched + 1.0) / 2.0 × 100

Example: NLP = -0.3
stretched = -0.6
nlp_norm  = (-0.6 + 1.0) / 2.0 × 100 = 0.4 / 2.0 × 100 = 20
```

**Why stretch 2×?**
- Typical clinical range is [-0.5, +0.5]
- Without stretching, this maps to [25, 75] (compressed)
- With stretching, [-0.5, +0.5] → [0, 100] (full range)

---

### Step 2: Medication Change Velocity

**Question:** "How rapidly is this patient's medication regimen changing?"

**Single-Day Prescriptions** (all on one visit):
```
score = max(10, 100 - n_unique_drugs × 12)

Example: 6 drugs on one day
score = 100 - 6 × 12 = 100 - 72 = 28
```

**Multi-Day Prescriptions:**
```
changes_per_month = (n_unique_drugs / date_span_days) × 30
score = max(10, 100 - changes_per_month × 9)

Example: 22 unique drugs over 600 days
changes_per_month = (22 / 600) × 30 = 1.1
score = 100 - 1.1 × 9 = 100 - 9.9 = 90.1
```

**Interpretation:**
- High velocity (many new drugs) → LOW score (bad)
- Low velocity (stable regimen) → HIGH score (good)
- Default when no data: 80.0 (assume moderate stability)

---

### Step 3: Weighted Fusion

```
Composite = 0.55 × Health_Index
          + 0.30 × NLP_Normalized
          + 0.15 × Med_Change_Score

Example:
  Health Index = 72
  NLP Normalized = 20
  Med Change = 90

  Composite = 0.55×72 + 0.30×20 + 0.15×90
            = 39.6 + 6.0 + 13.5
            = 59.1 → clipped to [0,100] = 59.1
```

---

### Step 4: Assign Credit Rating

| Composite ≥ | Rating | Label | Action |
|-------------|--------|-------|--------|
| 85 | **AAA** | Excellent | Routine monitoring |
| 70 | **AA** | Good | Standard care |
| 55 | **A** | Moderate | Enhanced monitoring |
| 40 | **BBB** | Below Average | Clinical review needed |
| 25 | **BB** | Elevated Risk | Active intervention |
| 0 | **B/CCC** | High Risk | Urgent attention |

**Example:** Composite = 59.1 → **Rating = A** (Moderate)

---

## 6. Clinical Severity Index (CSI)

### What It Predicts
Healthcare utilization (total visits, LOS, resource use)

### Six Components (Each 0–100)

| Component | Raw Input | Formula | Weight |
|-----------|-----------|---------|--------|
| **Health Trend** | OLS slope (pts/visit) | `(-slope + 5) / 10 × 100` | 25% |
| **Lab Volatility** | Std dev of scores | `std / 20 × 100` | 20% |
| **Critical Fraction** | % time in Critical state | `fraction × 100` | 20% |
| **NLP Signal** | Mean NLP composite | `(-mean_nlp + 1) / 2 × 100` | 15% |
| **Rx Intensity** | Prescriptions per month | `velocity / 10 × 100` | 10% |
| **Comorbidity Burden** | Count of conditions | `n_comorbidities / 4 × 100` | 10% |

**Example Calculation:**
```
Health trend slope: -2.0 pts/visit (declining)
  → component = (-(-2.0) + 5) / 10 × 100 = 70

Lab volatility (std): 15
  → component = 15 / 20 × 100 = 75

Critical fraction: 30% of visits
  → component = 0.30 × 100 = 30

Mean NLP: -0.2 (mild deterioration)
  → component = (-(-0.2) + 1) / 2 × 100 = 60

Rx velocity: 3 per month
  → component = 3 / 10 × 100 = 30

Comorbidities: 2 conditions
  → component = 2 / 4 × 100 = 50

CSI = 0.25×70 + 0.20×75 + 0.20×30 + 0.15×60 + 0.10×30 + 0.10×50
    = 17.5 + 15.0 + 6.0 + 9.0 + 3.0 + 5.0
    = 55.5 → Tier: HIGH
```

---

### CSI Tiers

| CSI ≥ | Tier | Label |
|-------|------|-------|
| 75 | **CRITICAL** | Immediate attention |
| 50 | **HIGH** | Active intervention |
| 25 | **MODERATE** | Enhanced monitoring |
| 0 | **LOW** | Routine care |

---

## Summary Table

| Metric | Input | Output | Key Formula |
|--------|-------|--------|-------------|
| **Health Index** | Labs + Vitals | 0–100 score | `100 × e^(-0.25 × mean_z)` |
| **PatientRegime™** | Health trajectory | 4 states | Trend × Volatility grid |
| **Health VaR™** | Score returns | p05–p95 fan | Monte Carlo bootstrap |
| **NLP Signal** | Clinical text | -1 to +1 | Zero-shot NLI |
| **Composite Score** | Health + NLP + Meds | AAA–B/CCC | 55/30/15 weighted fusion |
| **CSI** | 6 dimensions | 0–100 + tier | Weighted sum |

---

**For Questions:** See individual evidence reports:
- `HEALTH_INDEX_WEIGHT_JUSTIFICATION.md` — organ weights
- `FUSION_WEIGHTS_EVIDENCE.md` — composite weights
- `PARAMETER_EVIDENCE_REPORT.md` — all parameter citations
