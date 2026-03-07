# Missing Data Evaluation Report

**Date**: 2025-03 (ACUHIT 2 `_from2025` parquet subset)  
**Dataset**: ACUHIT 2 — Check-Up, Cancer, and Ex cohorts  
**Pipeline**: ILAY Composite Health Index (fusion.py)

---

## 1. Executive Summary

The ILAY pipeline scores **77,204 patients** ("Monitored Patients") based on lab data as the primary source. However, critical data gaps across the three input sources create systematic biases:

- **89.5% of scored patients have no vital signs** → vitals default to 100 (healthy)
- **99.87% of scored patients have no NLP scores** → NLP weight is redistributed away
- **79.7% of visit rows are missing blood pressure**; **99.7% are missing SpO2**
- **20.5% of lab results** (1.4M rows) have no hospital reference ranges; 58.3% of those also have no NexGene AI fallback → scored as 0 (invisible to the model)

These defaults inflate health scores for underrepresented patients and reduce the model's discriminative power.

---

## 2. Patient Coverage Across Data Sources

The three input datasets have dramatically different patient populations:

| Source | Patients | Rows | Description |
|---|---:|---:|---|
| Lab (labdata) | 77,204 | 7,032,687 | Lab results time-series |
| Anadata (visits) | 13,743 | 196,781 | Visit records with vitals, text, ICD codes |
| Recete (prescriptions) | 93,454 | 775,995 | Prescription records |

### Overlap Analysis

| Combination | Patients | % of Monitored (77K) |
|---|---:|---:|
| All 3 sources | 6,343 | 8.2% |
| Lab ∩ Anadata | 8,087 | 10.5% |
| Lab ∩ Recete | 58,608 | 75.9% |
| Lab ONLY (no visits, no Rx) | 16,852 | 21.8% |
| Anadata ONLY | 2,457 | — |
| Recete ONLY | 31,647 | — |

**Key finding**: Only **8.2% of monitored patients** have data in all three sources. The composite score for the remaining 91.8% relies on one or more default values.

### Scoring Impact

| Missing Component | Affected Patients | % of Monitored | Default Applied |
|---|---:|---:|---|
| No vital signs (no anadata) | 69,117 | 89.5% | `vital_score = 100` |
| No prescriptions | 18,596 | 24.1% | `med_change_score = 80` |
| No NLP scores | ~77,104 | 99.87% | Weights redistributed (78.6/0/21.4) |

---

## 3. Column-Level Missingness

### 3.1 Vital Signs (anadata — 196,781 rows)

| Vital | Missing | % Missing |
|---|---:|---:|
| systolic_bp | 156,759 | 79.7% |
| diastolic_bp | 156,765 | 79.7% |
| pulse | 190,190 | 96.7% |
| spo2 | 196,241 | **99.7%** |

SpO2 is effectively absent from the dataset. Only **366 rows** (0.2%) have SBP + Pulse + SpO2 simultaneously (minimum for NEWS2 validation).

**Impact**: Vital scoring operates on <20% of visit rows. When vitals are absent, the model assumes `vital_score = 100` (perfectly healthy), inflating composite scores.

### 3.2 Clinical Text Columns (for NLP — 196,781 rows)

| Column | Weight | Missing | % Missing |
|---|---:|---:|---:|
| YAKINMA (complaint) | 10% | 19,687 | 10.0% |
| Muayene Notu (exam) | 30% | 21,044 | 10.7% |
| ÖYKÜ (history) | 35% | 59,838 | 30.4% |
| Tedavi Notu (treatment) | 5% | 74,254 | 37.7% |
| Kontrol Notu (follow-up) | 20% | 113,945 | 57.9% |

Text availability is moderate (YAKINMA and Muayene Notu present ~90% of the time), but the highest-weighted column (ÖYKÜ, 35%) is missing in 30% of rows. Current NLP scoring has only processed **100 patients** out of 13,743 with visit data (0.73%).

### 3.3 Lab Reference Ranges (7,032,687 rows)

| Condition | Rows | % |
|---|---:|---:|
| Hospital REFMIN/REFMAX present | 5,588,875 | 79.5% |
| Missing — covered by NexGene AI fallback | 601,348 | 8.5% |
| Missing — **no fallback (invisible)** | 842,464 | **12.0%** |

#### Top Tests With Missing Reference Ranges

| Test Name | Missing | Total | % Missing |
|---|---:|---:|---:|
| Nötrofil/Lenfosit Oranı (NLR) | 143,231 | 143,231 | 100% |
| eGFR | 103,032 | 103,032 | 100% |
| AST | 80,781 | 87,886 | 92% |
| CRP | 62,075 | 64,394 | 96% |
| HDL Kolesterol | 50,796 | 50,796 | 100% |
| Vitamin D | 40,238 | 40,238 | 100% |
| Vitamin B12 | 37,834 | 40,191 | 94% |
| HbA1c | 35,312 | 35,470 | 100% |
| ESR | 33,760 | 33,760 | 100% |

**Critical issue**: CRP and AST are clinically important markers (CRP belongs to the `inflammatory` organ system at 25% weight; AST to `hepatic` at 12% weight). When reference ranges are missing, these tests contribute `z = 0` — effectively invisible. This biases certain patients toward appearing healthier than they are.

### 3.4 Demographics (anadata — 196,781 rows)

| Field | Missing | % Missing |
|---|---:|---:|
| age | 0 | 0.0% |
| sex | 0 | 0.0% |
| Boy (height) | 158,481 | 80.5% |
| Kilo (weight) | 155,797 | 79.2% |
| BMI | 195,839 | **99.5%** |

Age and sex are fully populated. Anthropometric data is almost entirely absent.

### 3.5 Comorbidity Flags (anadata — 196,781 rows)

| Flag | Missing | % Missing |
|---|---:|---:|
| Ameliyat Gecmisi (surgery history) | 30,496 | 15.5% |
| Kronik Hastaliklar Diger | 175,764 | 89.3% |
| Hipertansiyon | 181,657 | 92.3% |
| Diyabet | 184,112 | 93.6% |
| Kalp Damar (cardiovascular) | 193,136 | 98.1% |
| Kan Hastaliklari (blood diseases) | 196,550 | **99.9%** |

Most comorbidity flags are almost exclusively NaN. Only surgical history is meaningfully populated. These fields cannot be reliably used as features without imputation.

### 3.6 ICD-10 Diagnosis Codes

| Condition | Count | % |
|---|---:|---:|
| TANIKODU present (≥3 chars) | 196,781 | **100.0%** |
| Missing | 0 | 0.0% |

ICD-10 codes are fully available — a strong structured signal that is currently unused in the main scoring pipeline (only used for NLP training label generation).

---

## 4. Time-Series Depth

### Lab Dates per Patient (77,204 patients)

| Metric | Value |
|---|---:|
| Mean unique dates | 20.9 |
| Median | 16 |
| Single-date only (snapshot) | 3,210 (4.2%) |
| <3 dates (weak time-series) | 6,321 (8.2%) |

### Visits per Patient (13,743 patients)

| Metric | Value |
|---|---:|
| Mean visits | 14.3 |
| Median | 6 |
| Single-visit only | 1,747 (12.7%) |

**Impact on VaR**: Health VaR requires ≥2 time points. **572 patients** (0.7%) have only 1 lab observation and cannot have VaR computed — they return `None`. The 6,321 patients with <3 dates produce unstable Monte Carlo estimates.

---

## 5. Validation Benchmark Availability

### SOFA (4 of 6 organ systems possible)

| Component | Patients With Data | % of Monitored |
|---|---:|---:|
| Trombosit (coagulation) | 70,672 | 91.5% |
| Kreatinin (renal) | 56,888 | 73.7% |
| Bilirubin (liver) | 7,973 | **10.3%** |
| MAP (cardiovascular) — from vitals | ~8,087 | 10.5% |

Bilirubin and MAP are severely underrepresented. SOFA validation scores are heavily compressed toward 0 for most patients.

### NEWS2 (3 of 7 parameters possible)

Only **366 rows** (0.2%) have all three available parameters (SBP, Pulse, SpO2) simultaneously. NEWS2 validation is effectively non-functional at the cohort level.

### APACHE II (7 of 12 APS parameters possible)

Lab-based parameters (Na, K, Creatinine, Hematocrit, WBC) have reasonable coverage (50-90%), but vital parameters (MAP, HR) are limited to the 10.5% with anadata records.

---

## 6. Impact on Model Outputs

### 6.1 Score Inflation from Defaults

The composite score formula: `0.55 × health_index + 0.30 × nlp + 0.15 × med_changes`

For the **69,117 patients** with lab data but no visits (89.5% of monitored):

| Component | Actual Computation | Default Value |
|---|---|---:|
| Vital score (part of health_index) | No data → assume healthy | 100 |
| NLP composite | No data → 0.0, weights redistributed | 50 (neutral on 0-100) |
| Med change velocity | No Rx data for 24.1% | 80 |

This produces systematically higher composite scores for patients with less data, which is the opposite of the desired conservative bias.

### 6.2 Invisible Lab Tests

842,464 lab rows (12%) have no reference range from any source. These tests score `z = 0` (healthy). Clinically significant results in CRP, eGFR, AST, HbA1c, ESR, NLR, and specialty markers (Vitamin D, B12) are invisible to the health index unless the hospital supplies REFMIN/REFMAX in those rows.

### 6.3 NLP Near-Zero Coverage

Only 100 of 77,204 patients (0.13%) have LLM-computed NLP scores. For the remaining 99.87%, the NLP weight (30%) is redistributed to health_index (78.6%) and med_changes (21.4%). This effectively makes the model a two-signal system for almost all patients.

---

## 7. Recommendations

### High Priority (Data Recovery)

1. **Add reference ranges for CRP, AST, eGFR, HbA1c, ESR, NLR**  
   These are clinically critical and have 92-100% ref-range missingness. Adding NexGene AI or international reference ranges for these tests would recover ~842K invisible measurements.

2. **Use ICD-10 codes as a direct signal**  
   TANIKODU has 100% availability. A direct ICD→severity mapping (already built in `prepare_nlp_data.py`) could replace or supplement the NLP signal without requiring transformer inference.

3. **Scale NLP scoring to full cohort**  
   Current 100-patient coverage is negligible. Either run the LLM scorer on all 13.7K anadata patients or adopt a faster approach.

### Medium Priority (Default Strategy)

4. **Reconsider vital defaults**  
   `vital_score = 100` for missing vitals creates positive bias. Consider using the **cohort median** vital score instead of 100, or applying a data-completeness penalty.

5. **Reconsider med-change defaults**  
   `med_change_score = 80` for missing prescriptions is generous. A cohort-median or a neutral value (50) may be more appropriate.

6. **Add data-completeness flag**  
   Attach a `data_completeness` score (0-1) to each patient indicating what fraction of the full signal set was available. This lets downstream consumers weight results by confidence.

### Lower Priority (Structural)

7. **Harmonize the "Monitored Patients" definition**  
   Currently counts lab patients (77K). Consider restricting to patients with ≥2 data sources for more meaningful scoring.

8. **Add missingness-aware weighting**  
   Instead of fixed 55/30/15 weights with binary redistribution, use per-patient weights proportional to data availability across all signals.

---

## Appendix A: Complete Inventory of Rule-Based Calculations

All hardcoded thresholds, scoring formulas, default values, and deterministic mappings in the ILAY pipeline.

---

### A.1 Health Index (`src/health_index.py`)

#### A.1.1 Vital Reference Ranges (Lines 46–52)

| Vital | Normal Min | Normal Max | Unit | Source |
|---|---|---|---|---|
| systolic_bp | 90.0 | 119.0 | mmHg | NexGene AI |
| diastolic_bp | 75.0 | 84.0 | mmHg | NexGene AI |
| pulse | 60.0 | 100.0 | bpm | Standard clinical |
| spo2 | 95.0 | 100.0 | % | WHO / pulse oximetry |

#### A.1.2 NexGene AI Lab Reference Ranges — Fallback (Lines 67–116)

Used when hospital-supplied REFMIN/REFMAX are missing. Source: NexGene AI Medical Reasoning API (asa-mini model).

| Test (keyword) | Lower | Upper | Unit |
|---|---|---|---|
| Albumin | 35.0 | 50.0 | g/L |
| Protein | 60.0 | 80.0 | g/L |
| Üre | 1.8 | 7.1 | mmol/L |
| Kreatinin | 41.0 | 111.0 | μmol/L |
| Ürik Asit | 137.0 | 488.0 | μmol/L |
| Bilirubin | 0.0 | 21.0 | μmol/L |
| Glukoz | 3.9 | 6.1 | mmol/L |
| Kolesterol | 3.5 | 5.2 | mmol/L |
| Trigliserid | 0.6 | 1.69 | mmol/L |
| LDL | 0.97 | 4.91 | mmol/L |
| HDL | 1.0 | 1.2 | mmol/L |
| Sodyum | 135.0 | 145.0 | mmol/L |
| Potasyum | 3.3 | 5.1 | mmol/L |
| Klor | 96.0 | 106.0 | mmol/L |
| Kalsiyum | 2.2 | 2.6 | mmol/L |
| Fosfor | 0.8 | 1.45 | mmol/L |
| Magnezyum | 0.7 | 1.0 | mmol/L |
| ALT | 19.0 | 25.0 | U/L |
| AST | 10.0 | 44.0 | U/L |
| ALP | 55.0 | 150.0 | U/L |
| GGT | 5.0 | 40.0 | U/L |
| LDH | 105.0 | 280.0 | U/L |
| Amilaz | 30.0 | 110.0 | U/L |

#### A.1.3 Organ System Keyword Mapping (Lines 119–164)

35 substring → organ system rules:

| Keywords | System |
|---|---|
| CRP, Lökosit, Nötrofil, Lenfosit, Bazofil, Eozinofil, Monosit, Prokalsitonin | `inflammatory` |
| Kreatinin, Üre, GFR | `renal_organ` |
| Bilirubin, ALT, AST, ALP, GGT | `hepatic` |
| Hemoglobin, Hematokrit, Eritrosit, Trombosit, MCV, MCH, RDW | `hematological` |
| Glukoz, HbA1c, Kolesterol, Trigliserid, LDL, HDL, Sodyum, Potasyum, Kalsiyum, Albumin, Protein | `metabolic` |
| TSH, T3, T4 | `endocrine` |
| INR, PT, aPTT | `coagulation` |

#### A.1.4 Organ System Weights (Lines 166–177)

| System | Weight |
|---|---|
| inflammatory | 0.125 |
| renal_organ | 0.125 |
| hepatic | 0.125 |
| hematological | 0.125 |
| metabolic | 0.125 |
| endocrine | 0.125 |
| coagulation | 0.125 |
| other | 0.125 |
| **Total** | **1.00** |

Equal weighting — consistent with SOFA / NEWS2 / APACHE II, which treat organ systems with uniform importance.

#### A.1.5 Lab Z-Score Formula (Lines 222–247)

```
ref_std = (ref_max - ref_min) / 4.0       # assumes ±2σ spans the reference range
if value < ref_min:  z = (ref_min - value) / ref_std
if value > ref_max:  z = (value - ref_max) / ref_std
else:                z = 0.0               # within range = healthy
```

No reference range and no NexGene AI fallback → `z = 0.0` (invisible).

#### A.1.6 Health Score from Z-Score — Exponential Decay (Lines 298–300)

```
health_score = 100 × exp(-0.25 × mean_weighted_z)
```

| mean_z | health_score |
|---|---|
| 0 | 100 |
| 2 | ~61 |
| 4 | ~37 |
| 6 | ~22 |

Clipped to [0, 100].

#### A.1.7 Vital Scoring Defaults (Lines 310–356)

- No vitals available → `vital_score = 100` (assume normal)
- Vitals older than **30 days** from scoring date → ignored
- Same `100 × exp(-0.25 × mean_z)` decay

#### A.1.8 Lab/Vital Composite Weighting (Lines 207–209)

| Context | Lab Weight | Vital Weight |
|---|---|---|
| Constructor default | 0.60 | 0.40 |
| api.py override | 0.55 | 0.45 |
| Only labs available | 1.00 | — |
| Only vitals available | — | 1.00 |

---

### A.2 Composite Risk Score (`src/fusion.py`)

#### A.2.1 Fusion Weights (Lines 40–51)

| Component | Normal | NLP Skipped |
|---|---|---|
| health_index | 0.55 | 0.786 |
| nlp | 0.30 | 0.0 |
| med_changes | 0.15 | 0.214 |

NLP weight redistribution is **per-patient**: patients with real NLP scores use full weights, patients without use redistributed weights.

#### A.2.2 Rating Tiers (Lines 54–60)

| Min Score | Rating | Label |
|---|---|---|
| ≥ 85 | AAA | Excellent — stable health, positive prognosis |
| ≥ 70 | AA | Good — minor abnormalities, low risk |
| ≥ 55 | A | Moderate — monitoring recommended |
| ≥ 40 | BBB | Below average — clinical review needed |
| ≥ 25 | BB | Elevated risk — active intervention recommended |
| ≥ 0 | B/CCC | High risk — urgent clinical attention |

#### A.2.3 NLP Score Normalization (Lines 73–79)

```
stretched = nlp_score × 2.0               # [-0.5, +0.5] → [-1, +1]
normalized = clip((stretched + 1) / 2 × 100, 0, 100)
```

#### A.2.4 Medication Change Velocity Score (Lines 81–123)

**Default (no data):** `80.0`

**Single-day:**
```
score = max(10, 100 - n_unique_drugs × 12)     clipped [0, 100]
```

**Multi-day:**
```
changes_per_month = (n_unique_drugs / span_days) × 30
score = max(10, 100 - changes_per_month × 9)   clipped [0, 100]
```

---

### A.3 Health VaR (`src/health_var.py`)

#### A.3.1 Risk Tier Thresholds (Lines 54–61)

| VaR % Change | Tier | Label |
|---|---|---|
| > +5% | GREEN | Health Stable |
| 0% to +5% | YELLOW | Low Risk |
| -10% to 0% | ORANGE | Moderate Risk — review 24–48h |
| < -10% | RED | High Risk — prioritize review |

#### A.3.2 VaR & CVaR Formulas (Lines 152–158)

```
var_pct  = (p05 - current) / max(current, 1) × 100
cvar_pct = var_pct × 1.3    if var_pct < 0 else 0.0
```

#### A.3.3 Monte Carlo Parameters

| Parameter | Default | api.py Startup |
|---|---|---|
| horizon_draws | 3 | 3 |
| iterations | 5,000 | 500 (speed) |
| seed | 42 | 42 |

Minimum data points: **2** (else returns None).

---

### A.4 Regime Detection (`src/patient_regime.py`)

#### A.4.1 Configuration Defaults (Lines 72–82)

| Parameter | Default | Purpose |
|---|---|---|
| ma_window | 3 | Moving average window |
| vol_window | 4 | Rolling volatility window |
| vol_lookback | 20 | Lookback for vol percentile |
| vol_high_percentile | 60.0 | "High volatility" threshold |
| min_observations | 2 | Minimum data points |

#### A.4.2 Four-State Classification (Lines 167–178)

| Trend Positive? | Vol High? | State |
|---|---|---|
| Yes | No | STABLE |
| Yes | Yes | RECOVERING |
| No | No | DETERIORATING |
| No | Yes | CRITICAL |

`Trend positive` = health_score ≥ moving_average.  
`Vol high` = vol_percentile ≥ 60.0.

---

### A.5 NLP Scoring

#### A.5.1 Zero-Shot Transformer (`src/nlp_signal.py`)

| Parameter | Value |
|---|---|
| Model | MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli |
| Labels | kötüleşme (-1), iyileşme (+1), nötr (0) |
| Hypothesis | "Bu klinik metin {} ile ilgilidir." |
| Truncation | 512 tokens |
| Column weights | ÖYKÜ 35%, Muayene Notu 30%, Kontrol Notu 20%, YAKINMA 10%, Tedavi Notu 5% |

#### A.5.2 LLM Scorer (`src/nlp_llm.py`)

| Parameter | Value |
|---|---|
| Score scale | -1.0 to +1.0 (7 discrete guideposts) |
| Column weights | Equal 20% each |
| Text truncation | 400 chars |
| Batch size | 20 |
| Concurrency | 10 |
| Temperature | 0.1 |
| Retries | 3 (exponential backoff, base 2s) |
| Fallback on failure | 0.0 (neutral) |

---

### A.6 Outcome Prediction (`src/outcomes.py`)

#### A.6.1 Clinical Severity Index (CSI) Weights (Lines 162–169)

| Component | Weight |
|---|---|
| health_trend | 0.25 |
| lab_volatility | 0.20 |
| critical_fraction | 0.20 |
| nlp_signal | 0.15 |
| prescription_intensity | 0.10 |
| comorbidity_burden | 0.10 |

#### A.6.2 CSI Tier Boundaries (Lines 171–176)

| Min Score | Tier |
|---|---|
| ≥ 75 | CRITICAL |
| ≥ 50 | HIGH |
| ≥ 25 | MODERATE |
| ≥ 0 | LOW |

#### A.6.3 CSI Component Normalization (Lines 185–210)

| Component | Formula | Mapping |
|---|---|---|
| Health trend | `clip((-slope + 5) / 10 × 100, 0, 100)` | slope -5→100, +5→0 |
| Lab volatility | `clip(std / 20 × 100, 0, 100)` | std 20+→100 |
| Critical fraction | `clip(frac × 100, 0, 100)` | 1.0→100 |
| NLP signal | `clip((-mean + 1) / 2 × 100, 0, 100)` | -1→100, +1→0 |
| Rx velocity | `clip(vel / 10 × 100, 0, 100)` | 10+/month→100 |
| Comorbidities | `clip(n / 4 × 100, 0, 100)` | 4+→100 |

#### A.6.4 Narrative Thresholds (Lines 564–602)

| Condition | Interpretation |
|---|---|
| health_score_trend < -1.0 | "declining — active deterioration" |
| health_score_trend > +1.0 | "improving — positive trajectory" |
| critical_fraction > 0.3 | "significant instability" |
| n_comorbidities ≥ 3 | "complex multimorbidity" |
| rx_velocity > 5 | "high prescription intensity" |

#### A.6.5 Correlation Thresholds (Lines 541–542)

| \|r\| | Label |
|---|---|
| ≥ 0.7 | Strong |
| ≥ 0.4 | Moderate |
| < 0.4 | Weak |

Minimum n for Spearman: **5**.

---

### A.7 Validation Benchmarks (`src/validation.py`)

#### A.7.1 Pass Criteria (Lines 205–206)

```
passed = (r < 0) AND (p < 0.20) AND (n > 5)
```

#### A.7.2 Significance Levels (Lines 51–59)

| p-value | Display |
|---|---|
| < 0.001 | *** |
| < 0.01 | ** |
| < 0.05 | * |
| < 0.10 | (trend) |
| ≥ 0.10 | (n.s.) |

---

### A.8 SOFA Scoring (`scripts/score_sofa.py`)

Lab lookback window: **30 days**. Missing components default to **0**.

#### Coagulation (Platelets ×10³/μL)

| ≥150 | ≥100 | ≥50 | ≥20 | <20 |
|---|---|---|---|---|
| 0 | 1 | 2 | 3 | 4 |

#### Hepatic (Bilirubin mg/dL)

| <1.2 | <2.0 | <6.0 | <12.0 | ≥12.0 |
|---|---|---|---|---|
| 0 | 1 | 2 | 3 | 4 |

#### Cardiovascular (MAP mmHg)

MAP < 70 → 1, else → 0 (vasopressor grades not computable).

#### Renal (Creatinine mg/dL)

| <1.2 | <2.0 | <3.5 | <5.0 | ≥5.0 |
|---|---|---|---|---|
| 0 | 1 | 2 | 3 | 4 |

#### SOFA Tiers

| Score | ≥11 | ≥7 | ≥3 | <3 |
|---|---|---|---|---|
| Tier | CRITICAL | HIGH | MODERATE | LOW |

---

### A.9 NEWS2 Scoring (`scripts/score_news2.py`)

Fixed assumptions: Supplemental O₂ = 0 (room air), AVPU = 0 (Alert).

#### SpO₂ (Scale 1)

| ≥96 | ≥94 | ≥92 | <92 |
|---|---|---|---|
| 0 | 1 | 2 | 3 |

#### Systolic BP (mmHg)

| ≥220 | ≥111 | ≥101 | ≥91 | <91 |
|---|---|---|---|---|
| 3 | 0 | 1 | 2 | 3 |

#### Pulse (bpm)

| ≤40 | ≤50 | ≤90 | ≤110 | ≤130 | >130 |
|---|---|---|---|---|---|
| 3 | 1 | 0 | 1 | 2 | 3 |

#### NEWS2 Risk Bands

| Condition | Risk |
|---|---|
| Total ≥ 7 | HIGH |
| Total ≥ 5 OR any single = 3 | MEDIUM |
| Otherwise | LOW |

---

### A.10 APACHE II Scoring (`scripts/score_apache2.py`)

Lab lookback: **30 days**. Chronic health hardcoded to **0**.

Scoring tables for: MAP, Heart Rate, Sodium, Potassium, Creatinine, Hematocrit, WBC (see standard APACHE II tables). Age points: <45→0, ≥45→2, ≥55→3, ≥65→5, ≥75→6.

**Predicted mortality (Knaus 1985):**
```
log_odds = -3.517 + apache2_total × 0.146
mortality_% = 100 / (1 + exp(-log_odds))
```

#### APACHE II Tiers

| Score | ≥25 | ≥20 | ≥10 | <10 |
|---|---|---|---|---|
| Tier | CRITICAL | SEVERE | MODERATE | LOW |

---

### A.11 Advanced Analytics (`src/advanced_analytics.py`)

| Rule | Value |
|---|---|
| EWMA alpha | 0.15 |
| Vol regime: low/normal/high | <5% / 5–20% / >20% |
| Stress test: 2× worst | `min(returns) × 200` |
| CVaR percentile | 5th (0.05) |
| Walk-forward Sharpe annualization | √252 |
| Kelly fractional | 0.5 |
| Bootstrap iterations | 1,000 |
| Clinical significance | p < 0.05 |
| Rolling metrics window | 5 |
| Mean-variance optimization | 2,000 random iterations |

---

### A.12 Data Loader (`src/data_loader.py`)

| Rule | Threshold | Action |
|---|---|---|
| Systolic BP | <40 or >300 | Set to NaN |
| Diastolic BP | <20 or >200 | Set to NaN |
| Age | <0 or >120 | Set to NaN |
| Lab date | < 2000-01-01 | Drop row |

---

### A.13 API (`api.py`)

| Rule | Value |
|---|---|
| Sex normalization | KADIN/FEMALE/F→K, ERKEK/MALE/M→E |
| Vital weight override | 0.45 (vs default 0.40) |
| Startup VaR iterations | 500 (vs default 5,000) |
| Scatter plot max points | 2,000 |
| Cohort ranking neighborhood | ±15 patients |
| ThreadPool workers | 2 |

---

**Total: 100+ distinct rule-based calculations across 13 modules.**
