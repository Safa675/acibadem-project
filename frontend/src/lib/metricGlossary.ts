export type MetricGlossaryEntry = {
  id: string;
  title: string;
  definition: string;
  formula: string;
  interpretation: string;
  range?: string;
  source?: string;
};

export const METRIC_GLOSSARY: Record<string, MetricGlossaryEntry> = {
  "cohort.n_patients": {
    id: "cohort.n_patients",
    title: "Monitored Patients",
    definition: "Count of unique patient identifiers in the active cohort snapshot.",
    formula: "n = |unique(patient_id)|",
    interpretation: "Higher n improves cohort-level stability for distributional summaries.",
  },
  "cohort.mean_health_score": {
    id: "cohort.mean_health_score",
    title: "Mean Health Score",
    definition: "Arithmetic mean of patient-level latest health index scores.",
    formula: "mean = (1/n) * sum(health_index_score_i)",
    interpretation:
      "Higher values indicate better aggregate physiologic alignment with reference intervals.",
    range: "[0, 100]",
    source: "HealthIndexBuilder (src/health_index.py)",
  },
  "cohort.mean_eci": {
    id: "cohort.mean_eci",
    title: "Mean ECI Score",
    definition:
      "Arithmetic mean of patient-level Expected Cost Intensity scores across the active cohort.",
    formula: "mean = (1/n) * sum(eci_score_i)",
    interpretation:
      "Higher values indicate greater average expected cost intensity across the cohort.",
    range: "[0, 100]",
    source: "ECI model (src/eci.py)",
  },
  "cohort.n_critical": {
    id: "cohort.n_critical",
    title: "Critical State Now",
    definition: "Count of patients currently assigned to the Critical regime state.",
    formula: "count(regime_state == Critical)",
    interpretation: "Immediate escalation workload proxy.",
    source: "PatientRegime (src/patient_regime.py)",
  },
  "cohort.total_rx": {
    id: "cohort.total_rx",
    title: "Total Prescriptions",
    definition: "Total prescription records accumulated across cohort scope.",
    formula: "sum(n_prescriptions_i)",
    interpretation: "Higher totals often indicate increased care intervention intensity.",
  },
  "cohort.scatter": {
    id: "cohort.scatter",
    title: "Cohort Risk Scatter",
    definition: "Patient-level distribution of health index versus NLP score.",
    formula: "x = health_index_score, y = nlp_score, radius ~ eci_score",
    interpretation:
      "Upper-right indicates stronger multimodal profile; larger points imply greater severity burden.",
    range: "x,y in [0, 100]",
  },
  "cohort.rating_distribution": {
    id: "cohort.rating_distribution",
    title: "Rating Distribution",
    definition: "Frequency histogram over credit-style risk ratings (AAA to B/CCC).",
    formula: "histogram(rating)",
    interpretation:
      "Mass shift toward BB/B-CCC indicates degradation of cohort risk quality.",
    source: "Composite tiers: AAA 85-100, AA 70-84, A 55-69, BBB 40-54, BB 25-39, B/CCC 0-24",
  },
  "cohort.regime_distribution": {
    id: "cohort.regime_distribution",
    title: "Regime State Distribution",
    definition: "Frequency histogram over current regime states across patients.",
    formula: "histogram(regime_state)",
    interpretation:
      "Critical + Deteriorating concentration indicates elevated instability burden.",
  },
  "cohort.var.downside_var_pct": {
    id: "cohort.var.downside_var_pct",
    title: "Downside VaR %",
    definition: "Relative downside risk from Monte Carlo health-score terminal distribution.",
    formula: "VaR% = ((p05 - current_score) / max(current_score,1)) * 100",
    interpretation: "More negative values imply stronger expected downside tail risk.",
    source: "HealthVaR (src/health_var.py)",
  },
  "cohort.var.floor_score": {
    id: "cohort.var.floor_score",
    title: "VaR Floor Score",
    definition: "5th percentile terminal score under bootstrap Monte Carlo projection.",
    formula: "floor = p05(simulated_terminal_scores)",
    interpretation: "Conservative downside floor under current return-regime assumption.",
    range: "[0, 100]",
  },
  "cohort.var.risk_tier": {
    id: "cohort.var.risk_tier",
    title: "Risk Tier",
    definition:
      "Categorical deterioration risk label based on signed Health VaR %, where signed VaR % = ((p05 - current_score) / max(current_score,1)) * 100.",
    formula:
      "Tier thresholds (signed VaR %): RED <= -10 | ORANGE (-10, 0) | YELLOW [0, 5] | GREEN > 5",
    interpretation:
      "Table color guide: Downside VaR % -> 0=#2ECC71, >0-5=#A3E635, >5-15=#FACC15, >15-35=#FB923C, >35=#EF4444. VaR Floor Score -> 0-20=#DC2626, >20-40=#F97316, >40-60=#FACC15, >60-80=#84CC16, >80-100=#22C55E.",
  },
  "patient.summary.composite_score": {
    id: "patient.summary.composite_score",
    title: "Composite Score",
    definition: "Weighted fusion of health index, NLP signal, and medication velocity score.",
    formula: "0.55*health + 0.30*nlp_norm + 0.15*med_score",
    interpretation:
      "Single scalar risk quality measure; thresholded into rating categories.",
    range: "[0, 100]",
    source: "Fusion model (src/fusion.py)",
  },
  "patient.summary.regime_state": {
    id: "patient.summary.regime_state",
    title: "Regime State",
    definition: "Current state in the 2x2 trend-volatility regime model.",
    formula: "state = f(health >= MA3, volatility_percentile >= 60)",
    interpretation:
      "Critical implies negative trend with elevated volatility relative to patient baseline. If shown as Insufficient Data, there are not enough sequential observations to compute moving average and rolling volatility features, so regime classification is unavailable.",
  },
  "patient.summary.downside_var_pct": {
    id: "patient.summary.downside_var_pct",
    title: "Downside VaR %",
    definition: "Patient-specific relative downside risk from Health VaR simulation.",
    formula: "VaR% = ((p05 - current_score) / max(current_score,1)) * 100",
    interpretation: "Lower values represent greater near-term deterioration exposure.",
  },
  "patient.summary.eci_score": {
    id: "patient.summary.eci_score",
    title: "ECI Score",
    definition: "Expected Cost Intensity — percentile-normalized composite of four equal-weight cost drivers.",
    formula:
      "0.25*visit_intensity + 0.25*med_burden + 0.25*diagnostic_intensity + 0.25*trajectory_cost",
    interpretation: "Higher ECI indicates higher expected cost intensity. Rated AAA (lowest) to B/CCC (highest).",
    range: "[0, 100]",
    source: "ECI model (src/eci.py)",
  },
  "patient.regime.timeline": {
    id: "patient.regime.timeline",
    title: "Patient Regime Timeline",
    definition: "Temporal health trajectory with moving-average baseline and regime bands.",
    formula: "trend from MA3, volatility from rolling sigma percentile",
    interpretation:
      "Band transitions expose state persistence versus instability regime shifts.",
  },
  "patient.var.fan": {
    id: "patient.var.fan",
    title: "Health VaR Forecast",
    definition: "Monte Carlo percentile fan chart of projected near-term health score.",
    formula: "bootstrap returns -> p05/p25/p50/p75/p95 terminal paths",
    interpretation:
      "Wider fan implies higher uncertainty; p05 anchors conservative risk floor.",
  },
  "patient.nlp.visit_signal": {
    id: "patient.nlp.visit_signal",
    title: "Visit-Level NLP Signal",
    definition: "Confidence-damped zero-shot NLI composite per clinical visit text bundle.",
    formula: "score = sum(w_i * label_score_i * confidence_i)",
    interpretation:
      "Negative values indicate deterioration language; positive values indicate recovery language.",
    range: "[-1, +1]",
    source: "NLP signal model (src/nlp_signal.py)",
  },
  "patient.nli.score": {
    id: "patient.nli.score",
    title: "NLI Score",
    definition: "Per-row entailment-derived directional signal from zero-shot classifier.",
    formula: "label_score * top_label_confidence",
    interpretation: "Magnitude reflects model confidence-weighted directional strength.",
    range: "[-1, +1]",
  },
  "outcome.eci.gauge": {
    id: "outcome.eci.gauge",
    title: "ECI Gauge",
    definition: "Semicircular visual encoding of Expected Cost Intensity score and rating.",
    formula: "needle_angle = linear_map(score in [0,100], pi to 0)",
    interpretation: "Higher angular displacement toward red indicates greater expected cost intensity.",
  },
  "outcome.feature_decomposition": {
    id: "outcome.feature_decomposition",
    title: "ECI Component Breakdown",
    definition: "Four equal-weight components contributing to the total ECI score.",
    formula: "contribution_i = percentile_rank(component_i) * 0.25",
    interpretation:
      "Largest bars identify dominant cost drivers for resource planning.",
  },
  "outcome.cohort_ranking": {
    id: "outcome.cohort_ranking",
    title: "ECI Cohort Ranking",
    definition: "Ordering of cohort patients by ECI score magnitude.",
    formula: "sort_asc(eci_score)",
    interpretation: "Selected patient position contextualizes relative cost percentile.",
  },
  "outcome.spearman_r": {
    id: "outcome.spearman_r",
    title: "Spearman rho",
    definition: "Rank correlation between candidate feature and total visit count.",
    formula: "rho(feature, total_visits)",
    interpretation:
      "Sign indicates direction; absolute value indicates monotonic association strength.",
    range: "[-1, +1]",
  },
  "explorer.filter.age_range": {
    id: "explorer.filter.age_range",
    title: "Age Range Filter",
    definition: "Patient selector constraint based on age bounds.",
    formula: "include if age >= min_age and age <= max_age",
    interpretation:
      "Set either bound alone for one-sided filtering, or set both for a closed interval.",
  },
  "explorer.filter.weight_range": {
    id: "explorer.filter.weight_range",
    title: "Weight Range Filter",
    definition: "Patient selector constraint based on latest known body weight (kg).",
    formula: "include if weight_kg >= min_weight and weight_kg <= max_weight",
    interpretation:
      "Uses each patient’s latest available weight; if one bound is blank it is ignored.",
  },
  "explorer.filter.gender": {
    id: "explorer.filter.gender",
    title: "Gender Filter",
    definition: "Filters patients by normalized sex code from patient metadata.",
    formula: "Female = K, Male = E, All = no gender constraint",
    interpretation:
      "Use All to include every patient regardless of available sex metadata.",
  },
  "explorer.filter.doctor_code": {
    id: "explorer.filter.doctor_code",
    title: "Doctor Filter",
    definition: "Filters patients by latest visit doctor code (`DOCTOR_CODE`).",
    formula: "include if patient.doctor_code == selected_code",
    interpretation:
      "Select All to disable this filter and include all doctor assignments.",
  },
  "explorer.filter.comorbidities": {
    id: "explorer.filter.comorbidities",
    title: "Comorbidity Conditions Filter",
    definition: "Condition-specific filter using six modeled comorbidity flags.",
    formula: "include if patient contains ALL selected condition keys",
    interpretation:
      "When multiple conditions are checked, only patients matching every selected condition remain.",
  },
  "validation.p_value": {
    id: "validation.p_value",
    title: "p-value",
    definition: "Probability of observing the test statistic under null-hypothesis assumptions.",
    formula: "p = P(|T| >= |t_obs| | H0)",
    interpretation: "p < 0.05 indicates nominal significance under test assumptions.",
    range: "[0, 1]",
  },
  "validation.n_samples": {
    id: "validation.n_samples",
    title: "n samples",
    definition: "Effective count of valid observations used in each experiment.",
    formula: "n = count(valid paired observations)",
    interpretation: "Lower n reduces test power and increases estimate variance.",
  },
};

export function getGlossaryEntry(id: string): MetricGlossaryEntry | null {
  return METRIC_GLOSSARY[id] ?? null;
}
