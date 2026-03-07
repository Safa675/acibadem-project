# Evidence-Based Justification for Organ System Weighting in the Composite Health Index

**Date:** 2026-02-27  
**Context:** Evaluation of the `ORGAN_WEIGHTS` used in `health_index.py` for the Acıbadem clinical health score  
**Scope:** Systematic literature review of composite clinical scoring systems and biomarker-outcome associations

---

## 1. Current Weights Under Review

| Organ System | Biomarkers | Current Weight |
|---|---|---|
| Inflammatory | CRP, WBC, Neutrophils, Lymphocytes, Monocytes, Procalcitonin | **30%** |
| Renal/Hepatic | Creatinine, BUN, GFR, ALT, AST, ALP, GGT, Bilirubin | **25%** |
| Hematological | Hemoglobin, Hematocrit, RBC, Platelets, MCV, MCH, RDW | **25%** |
| Metabolic | Glucose, HbA1c, Cholesterol, TG, LDL, HDL, Na⁺, K⁺, Ca²⁺, Albumin, Protein | **15%** |
| Endocrine | TSH, T3, T4 | **3%** |
| Coagulation | INR, PT, aPTT | **2%** |
| Other | Unclassified | **5%** |

---

## 2. Reference Composite Scoring Systems

### 2.1 SOFA Score (Sequential Organ Failure Assessment)

**Original paper:** Vincent JL, Moreno R, Takala J, et al. *The SOFA score to describe organ dysfunction/failure.* Intensive Care Med. 1996;22:707–710. **PMID: 8844239**

The SOFA score evaluates **6 organ systems**, each scored 0–4 (total 0–24):

| SOFA Component | Biomarker/Parameter | Max Points | Implied Weight |
|---|---|---|---|
| Respiratory | PaO₂/FiO₂ ratio | 4 | 16.7% |
| Cardiovascular | MAP / vasopressor use | 4 | 16.7% |
| Neurological | Glasgow Coma Scale | 4 | 16.7% |
| Hepatic | Bilirubin | 4 | 16.7% |
| Coagulation | Platelets | 4 | 16.7% |
| Renal | Creatinine / urine output | 4 | 16.7% |

**Key Design Feature:** SOFA uses **equal weighting** (each organ system contributes 1/6 ≈ 16.7%). However, extensive research shows the components do **not** contribute equally to mortality prediction.

**Critical finding (Parviainen et al., 2022):** A Finnish ICU registry study (PMC9322581) of all adult ICU patients (2012–2015) found that **"All SOFA components are associated with mortality, but their weights are not comparable. High scores of other organ systems mean a higher risk of death than high cardiovascular scores."** The authors specifically noted the cardiovascular SOFA score was paradoxically associated with *lower* relative risk of mortality compared to other components.

**Liver SOFA dominance (Crit Care Sci, 2024):** Analysis using eICU-CRD and MIMIC-IV cohorts found the **hepatic component was the most predictive of mortality on Day 1** in both cohorts:
- eICU-CRD: OR 2.2 (95% CI 1.6–2.9) for liver failure
- MIMIC-IV: OR 2.3 (95% CI 1.7–3.1) for liver failure

**SOFA-2 Update (Moreno et al., 2025):** Published in JAMA Network Open, the SOFA-2 update retains 6 organ systems (respiratory, cardiovascular, CNS, renal, coagulation, hepatic) but revises scoring criteria within each component. **PMID: see JAMA Netw Open 2025.**

### 2.2 APACHE II (Acute Physiology and Chronic Health Evaluation II)

**Original paper:** Knaus WA, Draper EA, Wagner DP, Zimmerman JE. *APACHE II: a severity of disease classification system.* Crit Care Med. 1985;13(10):818–829. **PMID: 3928249**

APACHE II uses **12 physiological variables**, all **equally weighted** (0–4 points each), for a max Acute Physiology Score (APS) of 60:

| Variable | Points (0–4) | Organ System |
|---|---|---|
| Temperature | 0–4 | Systemic |
| Mean Arterial Pressure | 0–4 | Cardiovascular |
| Heart Rate | 0–4 | Cardiovascular |
| Respiratory Rate | 0–4 | Respiratory |
| Oxygenation (PaO₂/A-a gradient) | 0–4 | Respiratory |
| Arterial pH | 0–4 | Metabolic/Respiratory |
| Serum Sodium | 0–4 | Metabolic/Electrolyte |
| Serum Potassium | 0–4 | Metabolic/Electrolyte |
| **Serum Creatinine** | 0–4 (**×2 if acute renal failure**) | **Renal** |
| Hematocrit | 0–4 | Hematological |
| White Blood Cell Count | 0–4 | Inflammatory |
| Glasgow Coma Scale (15‑score) | 0–4 | Neurological |

**Notable:** APACHE II applies **double weighting for creatinine in acute renal failure**, the only variable with a non-equal weight — an implicit acknowledgment that acute renal dysfunction carries outsize prognostic significance.

**Implied organ system distribution in APACHE II:**
- Cardiovascular: 2 variables (~16.7%)
- Respiratory: 2 variables (~16.7%)
- Metabolic/Electrolyte: 3 variables (~25%, including pH, Na⁺, K⁺)
- Renal: 1 variable but doubled in ARF (~8.3–16.7%)
- Hematological: 1 variable (~8.3%)
- Inflammatory: 1 variable (~8.3%)
- Neurological: 1 variable (~8.3%)

### 2.3 NEWS / NEWS2 (National Early Warning Score)

**Reference:** Royal College of Physicians. *National Early Warning Score (NEWS) 2.* 2017.

NEWS uses 6 physiological parameters plus supplemental O₂ status. It focuses on **vitals** rather than labs:

| Parameter | Points (0–3) |
|---|---|
| Respiratory rate | 0–3 |
| SpO₂ | 0–3 |
| Supplemental O₂ | 0–2 |
| Systolic BP | 0–3 |
| Heart rate | 0–3 |
| Consciousness (AVPU) | 0–3 |
| Temperature | 0–3 |

NEWS/NEWS2 does **not include any laboratory values**, making it complementary to but not directly comparable with a lab-based composite score. A systematic review in the European Journal of Internal Medicine found NEWS demonstrated "moderate-to-good discrimination" for in-hospital mortality (AUROC generally 0.70–0.87). **PMID: 41618411**

### 2.4 MEWS (Modified Early Warning Score)

Like NEWS, MEWS is purely vitals-based. Not directly applicable to lab-based weighting but consistently shown to have moderate discrimination for deterioration.

---

## 3. Biomarker-Specific Evidence for Mortality Prediction

### 3.1 Inflammatory Markers (CRP, WBC) — Current Weight: 30%

**CRP:**
- **Meta-analysis (ScienceDirect, Curr Med Res Opin):** Pooled HR of all-cause mortality for highest vs. lowest CRP category = **2.07** in acute coronary syndrome patients.
- **Nature Scientific Reports (2023):** In critically ill patients, persistently high CRP trajectories had the highest in-hospital mortality (**32.6%** vs 18.1% for intermediate CRP).
- **CRP/albumin ratio meta-analysis (MDPI, 2018):** CRP/albumin ratio emerged as a predictor of poor prognosis across multiple patient groups.
- **Dynamic biomarkers in sepsis (MDPI Diagnostics, 2024):** PCT, CRP, and lactate dynamic changes are superior to baseline values for predicting 30-day mortality.

**WBC:**
- Included in APACHE II as one of 12 equally weighted variables.
- WBC abnormalities (both leukocytosis and leukopenia) are part of SIRS criteria, which underpin sepsis definitions.

**Assessment:** A 30% weight for inflammation is **higher than any single organ system in SOFA or APACHE II**. However, the inflammatory system includes 6+ markers (CRP, WBC, differential counts, procalcitonin), and inflammation is the most common pathological process in hospitalized patients. **This weight is on the high end but defensible**, especially in a general hospitalized population where infection/sepsis is a leading cause of deterioration.

### 3.2 Renal/Hepatic (Creatinine, BUN, ALT, AST, ALP, GGT, Bilirubin) — Current Weight: 25%

**Renal markers:**
- **BUN > 30 mg/dL:** HR 1.90 (95% CI 1.41–2.56) for post-discharge mortality. (ScienceDirect)
- **BUN/Creatinine ratio:** Independently associated with in-hospital mortality (BMJ Open, 2023, PMC data). BUN/Cr identifies high-risk patients even when creatinine is normal.
- **APACHE II double-weights creatinine** in acute renal failure — the only variable receiving this distinction.
- **SOFA renal component** (creatinine/urine output) consistently among the strongest mortality predictors in multivariate analyses.
- **MIMIC-IV / eICU-CRD analysis:** Renal failure (SOFA renal ≥ 3) on Day 1 significantly predicted mortality.

**Hepatic markers:**
- **Shang et al. (Frontiers Cardiovasc Med):** In 2,565 cardiac surgery patients (MIMIC-III), abnormal ALT, AST, albumin, and total bilirubin were **independent risk factors** for hospital mortality and 90-day mortality.
- **SOFA hepatic component:** Was the **most predictive single component** for Day 1 mortality in the 2024 Crit Care Sci analysis (OR 2.2–2.3).
- **CLIF-SOFA:** Superior to other liver-specific scores in predicting mortality in acute-on-chronic liver failure.

**Assessment:** Grouping renal + hepatic as a single 25% category is **well-supported** by the evidence. Both organ systems are individually strong mortality predictors. APACHE II devotes ~8.3–16.7% to renal alone; SOFA gives each 16.7%. Combined at 25%, the weight is reasonable but could arguably be **higher (30%)** given the dual organ coverage and the evidence that hepatic dysfunction is the strongest single SOFA predictor. **Consider splitting into separate Renal (15%) and Hepatic (15%) categories** if granularity is desired.

### 3.3 Hematological (Hemoglobin, Platelets, RBC indices) — Current Weight: 25%

**Platelets:**
- **Meta-analysis of thrombocytopenia in infective endocarditis (2025):** OR for in-hospital mortality: **1.99** (95% CI 1.72–2.31); HR for long-term mortality: **2.08** (95% CI 1.29–3.34). 25 studies, 110,411 patients.
- **PMC4088585:** ICU thrombocytopenia associated with mortality (28.6% vs 13.0%, P < 0.006).
- **Haematologica:** Both thrombocytosis and thrombocytopenia independently predicted mortality in a large outpatient cohort.
- SOFA includes platelets under **coagulation** (not hematological), scored 0–4.

**Hemoglobin/Anemia:**
- **PMC7230611:** Anemia is "extremely common in hospitalized patients" and associated with adverse outcomes.
- Hematocrit is one of the 12 APACHE II variables.
- Anemia is generally a weaker independent mortality predictor than renal or inflammatory markers after adjustment.

**Red cell indices (MCV, MCH, RDW):**
- RDW has emerged as an independent mortality predictor in several studies, but its contribution is modest (HR typically 1.1–1.3 per unit increase).
- MCV/MCH have limited independent prognostic value.

**Assessment:** 25% is **arguably high** for the hematological system as a group. Key observations:
1. In SOFA, platelets are under *coagulation* (not hematological), and the hematological system has no dedicated SOFA component.
2. In APACHE II, hematocrit represents only 1/12 (~8.3%) of the APS.
3. While thrombocytopenia is a strong predictor (OR ~2), anemia/hemoglobin and RBC indices are weaker predictors after multivariate adjustment.
4. **Recommendation: Reduce hematological to 15–20%** and consider moving platelets under coagulation (as in SOFA), or separating platelets for special weighting.

### 3.4 Metabolic (Glucose, Electrolytes, Lipids, Albumin) — Current Weight: 15%

**Electrolyte abnormalities:**
- **French OUTCOMEREA database (12,090 ICU patients):** Both hypokalemia and hyperkalemia independently predicted 28-day mortality. Mild hyperkalemia had HR **1.29** (95% CI 1.13–1.47). Dyskalemia not corrected by day 2 had adjusted HR **1.51** (95% CI 1.30–1.76).
- **Whelan et al.:** Sodium < 125 or > 140 mmol/L: unadjusted OR of death within 30 days = **3.36** and **4.07**, respectively. Association remained after adjustment.
- **ICU electrolyte study (N=355):** Non-survivors had significantly higher rates of hyponatremia (46.9% vs 25.9%), hyperkalemia (21.0% vs 6.6%), and ≥2 simultaneous abnormalities (62.2% vs 32.1%).
- APACHE II includes Na⁺, K⁺, and pH as 3 of 12 variables — **25% of the APS is metabolic/electrolyte**.

**Glucose/HbA1c:**
- Dysglycemia (both hypo- and hyperglycemia) is well-established as a mortality predictor in hospitalized patients.
- Stress hyperglycemia in ICU patients is associated with OR ~1.5–3.0 for mortality depending on the population.

**Albumin:**
- Hypoalbuminemia is one of the strongest single predictors of hospital mortality across populations.
- CRP/albumin ratio is an established prognostic marker.
- Albumin is inversely correlated with ICU and hospital length of stay.

**Assessment:** 15% is **too low** for the metabolic category, especially considering:
1. APACHE II devotes 3/12 variables (25%) to metabolic/electrolyte parameters (Na⁺, K⁺, pH).
2. Electrolyte abnormalities carry ORs of 3–4 for mortality.
3. Albumin alone is one of the strongest single prognostic biomarkers.
4. The metabolic category in this score covers glucose, lipids, electrolytes, AND albumin — a wide span.
5. **Recommendation: Increase to 20–25%.** Alternatively, separate albumin into its own nutritional status marker with elevated weight. Lipid markers (cholesterol, TG, LDL, HDL) could also be deprioritized as they reflect chronic risk rather than acute deterioration.

### 3.5 Endocrine (TSH, T3, T4) — Current Weight: 3%

**Low T3 Syndrome / Euthyroid Sick Syndrome:**
- **PMC9354117:** Low T3 syndrome is a prognostic factor in ICU patients. Decreased T3 levels have a consistent relationship with poor prognosis and can indicate severity of systemic diseases.
- **MDPI Diagnostics (2025):** Low T3, particularly low free T4, predicted mortality in critically ill septic patients.
- **World J Gastroenterol Net (2024):** Mortality rates inversely correlate with serum T3/T4 levels, especially with significant T4 decrease.
- T3/T4 changes in critical illness are generally **epiphenomena of severity** (euthyroid sick syndrome) rather than primary drivers of outcomes.

**TSH:**
- TSH in isolation is a poor acute prognostic marker. It is more relevant for chronic thyroid disease screening.
- TSH may be suppressed or elevated in critical illness without reflecting true thyroid dysfunction.

**Assessment:** 3% is **reasonable**. Thyroid markers in hospitalized patients primarily reflect illness severity via euthyroid sick syndrome and have limited independent prognostic value after adjusting for other markers. No established composite scoring system (SOFA, APACHE, NEWS, MEWS) includes thyroid markers. The 3% weight appropriately reflects available-but-not-primary prognostic value.

### 3.6 Coagulation (INR, PT, aPTT) — Current Weight: 2%

**Evidence:**
- SOFA dedicates a full 1/6 (16.7%) of its score to **coagulation** (platelets), making coagulation a first-class organ system in critical care assessment.
- **Platelet-INR ratio in COVID-19 (2021):** AUC for mortality prediction 0.94 (first wave) and 0.95 (second wave), superior to DIC scores and SIC scores alone.
- **SIC score (Sepsis-Induced Coagulopathy):** Combines PT-INR, platelets, and SOFA, with AUC 0.84–0.96 for mortality.
- **Link Springer (2026):** Non-survivors had lower platelet counts and higher INR. PLR (platelet-to-lymphocyte ratio) was an independent predictor.
- Coagulopathy (DIC, SIC) is a major complication and mortality driver in sepsis, trauma, liver failure, and malignancy.

**Assessment:** 2% is **significantly too low**. This is the most underweighted category relative to published evidence:
1. SOFA gives coagulation full equal weight (16.7%).
2. INR/PT abnormalities carry strong mortality prediction (AUC 0.66–0.78 alone; 0.94–0.95 in platelet-INR ratio).
3. Coagulopathy is a hallmark of multi-organ failure and a direct cause of death (hemorrhage, DIC).
4. **Recommendation: Increase to 8–12%.** If platelets remain under "hematological," the coagulation weight could be 5–8%. If platelets are moved to coagulation (as in SOFA), then 10–15%.

---

## 4. Comparative Analysis: Current Weights vs. Evidence

| Organ System | Current Weight | SOFA Implied | APACHE II Implied | Evidence-Based Recommendation | Direction |
|---|---|---|---|---|---|
| Inflammatory | 30% | N/A (not separate) | ~8.3% (WBC only) | **20–25%** | ↓ slightly |
| Renal/Hepatic | 25% | 33.3% (two systems) | ~8.3–16.7% | **25–30%** | ↔ or ↑ slightly |
| Hematological | 25% | N/A (Hct not in SOFA) | ~8.3% (Hct only) | **15–20%** | ↓ |
| Metabolic | 15% | N/A | ~25% (Na, K, pH) | **20–25%** | ↑ |
| Endocrine | 3% | N/A | N/A | **2–3%** | ↔ |
| Coagulation | 2% | 16.7% (platelets) | N/A | **8–12%** | ↑↑ |
| Other | 5% | — | — | **3–5%** | ↔ |

---

## 5. Recommended Revised Weights

### Option A: Moderate Revision (Minimal Restructuring)

Keeps the same organ system groupings, adjusts magnitudes:

```python
ORGAN_WEIGHTS = {
    "inflammatory": 0.25,   # was 0.30 — still high but aligned with CRP/WBC evidence
    "renal_organ":  0.25,   # unchanged — well supported by SOFA + APACHE II
    "hematological": 0.18,  # was 0.25 — reduced; Hb/RBC indices weaker predictors
    "metabolic":    0.20,   # was 0.15 — electrolytes + albumin evidence strongly supports increase
    "endocrine":    0.02,   # was 0.03 — marginal prognostic value
    "coagulation":  0.07,   # was 0.02 — major increase; INR/PT strongly predictive
    "other":        0.03,   # was 0.05
}
```

### Option B: SOFA-Aligned Revision (Split Renal/Hepatic, Move Platelets)

Aligns with SOFA organ system boundaries:

```python
ORGAN_WEIGHTS = {
    "inflammatory": 0.22,   # CRP, WBC, differentials, PCT
    "renal":        0.18,   # Creatinine, BUN, GFR
    "hepatic":      0.12,   # ALT, AST, ALP, GGT, Bilirubin
    "hematological": 0.12,  # Hemoglobin, Hematocrit, RBC, MCV, MCH, RDW (NO platelets)
    "metabolic":    0.20,   # Glucose, HbA1c, lipids, electrolytes, albumin
    "endocrine":    0.02,   # TSH, T3, T4
    "coagulation":  0.12,   # INR, PT, aPTT, Platelets (as in SOFA)
    "other":        0.02,
}
```

### Option C: Data-Driven (Regression-Weighted)

The ideal approach would be to derive weights empirically from the Acıbadem patient data:
1. Use multivariate logistic regression with mortality/ICU transfer as the outcome
2. Use the normalized organ-system sub-scores as predictors
3. The regression coefficients become the evidence-based weights
4. Validate with cross-validation or a holdout set

This approach is endorsed by the SOFA-2 development team (Moreno et al., JAMA Netw Open 2025) and avoids the known limitation that expert-assigned equal weights (as in SOFA-1) do not reflect true outcome associations.

---

## 6. Key Citations

| # | Citation | PMID | Key Finding |
|---|---|---|---|
| 1 | Vincent JL et al. SOFA score. Intensive Care Med. 1996;22:707-710 | **8844239** | Original SOFA: 6 organ systems, equal weight (0-4 each) |
| 2 | Knaus WA et al. APACHE II. Crit Care Med. 1985;13(10):818-829 | **3928249** | 12 variables equally weighted; creatinine doubled in ARF |
| 3 | Vincent JL et al. Use of SOFA. Crit Care Med. 1998;26:1793-1800 | **9824069** | SOFA validation: mortality increases with score |
| 4 | Moreno R et al. Maximum SOFA. Intensive Care Med. 1999;25:686-696 | **10470572** | Max SOFA strongly predicts mortality |
| 5 | Parviainen A et al. SOFA components. Acta Anaesth Scand. 2022 (PMC9322581) | **35579938** | SOFA components have **unequal** mortality associations; cardiovascular weakest |
| 6 | Crit Care Sci. 2024;36:e20240030en | — | Hepatic SOFA most predictive on Day 1 (OR 2.2–2.3) |
| 7 | Moreno R et al. SOFA-2. JAMA Netw Open. 2025 | — | SOFA-2 update rationale; retains 6 organ systems |
| 8 | CRP mortality meta-analysis. Curr Med Res Opin (ScienceDirect) | — | Pooled HR 2.07 for highest vs lowest CRP |
| 9 | BUN > 30 mg/dL post-discharge. ScienceDirect | — | HR 1.90 (95% CI 1.41-2.56) |
| 10 | BUN/Cr ratio and in-hospital mortality. BMJ Open. 2023;13:e069345 | — | High BUN/Cr significantly associated with mortality |
| 11 | Thrombocytopenia & IE mortality meta-analysis (25 studies, 110,411 pts) | — | OR 1.99 (1.72-2.31) in-hospital; HR 2.08 long-term |
| 12 | PMC4088585 — Thrombocytopenia in ICU | **24393365** | ICU mortality 28.6% vs 13.0% (P<0.006) |
| 13 | Whelan et al. Sodium & mortality | — | Na <125: OR 3.36; Na >140: OR 4.07 for 30-day death |
| 14 | French OUTCOMEREA database — Dyskalemia | — | Hyperkalemia HR 1.29; uncorrected dyskalemia HR 1.51 |
| 15 | Platelet-INR ratio in COVID-19 | — | AUC 0.94-0.95 for mortality prediction |
| 16 | Low T3 syndrome in ICU. PMC9354117 | — | Low T3 correlates with severity but is epiphenomenal |
| 17 | Shang L et al. LFTs in cardiac surgery. Front Cardiovasc Med | — | ALT, AST, bilirubin, albumin: independent risk factors |
| 18 | NexGene AI Medical Reasoning API (asa-mini model). Reference intervals queried 2026-03-07 | — | Reference ranges used in the score |
| 19 | NEWS2 systematic review. PMID 41618411 | **41618411** | NEWS moderate-to-good mortality discrimination |
| 20 | Bosch NA et al. SOFA predictive validity. Ann Am Thorac Soc. 2022 | — | SOFA validated measure of acute illness severity |

---

## 7. Summary and Conclusions

### What the evidence supports:
1. **Inflammation deserves high but not dominant weight.** CRP and WBC are strong predictors (HR ~2.0), but 30% exceeds what any established system assigns. 22–25% is more consistent with evidence.

2. **Renal/Hepatic at 25% is well-supported.** Both systems are first-class SOFA components. Hepatic SOFA was the strongest Day 1 predictor. Creatinine is the only APACHE II variable with double-weighting. If anything, this could go to 28–30%.

3. **Hematological at 25% is over-weighted.** APACHE II gives hematocrit 8.3%. SOFA has no hematological component (platelets are under coagulation). Anemia/RBC indices are weaker predictors after adjustment. 15–18% is more evidence-based.

4. **Metabolic at 15% is under-weighted.** APACHE II devotes 25% to electrolytes/pH. Sodium/potassium abnormalities carry OR 3–4. Albumin is among the strongest single predictors. 20–25% is better supported.

5. **Endocrine at 3% is appropriate.** No established scoring system includes thyroid markers. Low T3 is an epiphenomenon of illness severity.

6. **Coagulation at 2% is the largest gap with evidence.** SOFA gives it 16.7%. INR/PT have AUC 0.66–0.78 alone and 0.94–0.95 in combination with platelets. Coagulopathy is a direct cause of death. 8–12% minimum is warranted.

### Final recommendation:
Adopt **Option A** (moderate revision) as a near-term improvement, and pursue **Option C** (regression-weighted from Acıbadem data) as the ideal medium-term solution. The most urgent change is increasing coagulation from 2% → 7–10% and reducing hematological from 25% → 18%.
