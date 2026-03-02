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
  "cohort.n_high_risk": {
    id: "cohort.n_high_risk",
    title: "High-Risk Patients",
    definition: "Count of patients meeting the configured high-risk composite criterion.",
    formula: "count(high_risk_condition == true)",
    interpretation: "Represents review-queue pressure for proactive intervention.",
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
    formula: "x = health_index_score, y = nlp_score, radius ~ csi_score",
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
      "Critical implies negative trend with elevated volatility relative to patient baseline.",
  },
  "patient.summary.downside_var_pct": {
    id: "patient.summary.downside_var_pct",
    title: "Downside VaR %",
    definition: "Patient-specific relative downside risk from Health VaR simulation.",
    formula: "VaR% = ((p05 - current_score) / max(current_score,1)) * 100",
    interpretation: "Lower values represent greater near-term deterioration exposure.",
  },
  "patient.summary.csi_score": {
    id: "patient.summary.csi_score",
    title: "CSI Score",
    definition: "Clinical Severity Index combining six normalized burden components.",
    formula:
      "0.25*trend + 0.20*volatility + 0.20*critical_fraction + 0.15*nlp + 0.10*rx + 0.10*comorbidity",
    interpretation: "Higher CSI indicates higher expected utilization and severity burden.",
    range: "[0, 100]",
    source: "Outcome model (src/outcomes.py)",
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
  "outcome.csi.gauge": {
    id: "outcome.csi.gauge",
    title: "CSI Gauge",
    definition: "Semicircular visual encoding of CSI magnitude and severity tier.",
    formula: "needle_angle = linear_map(score in [0,100], pi to 0)",
    interpretation: "Higher angular displacement toward red indicates greater severity burden.",
  },
  "outcome.feature_decomposition": {
    id: "outcome.feature_decomposition",
    title: "CSI Feature Decomposition",
    definition: "Component-wise weighted contribution to total CSI score.",
    formula: "contribution_i = normalized_component_i * component_weight_i",
    interpretation:
      "Largest bars identify dominant burden drivers for clinical prioritization.",
  },
  "outcome.cohort_ranking": {
    id: "outcome.cohort_ranking",
    title: "CSI Cohort Ranking",
    definition: "Ordering of cohort patients by CSI score magnitude.",
    formula: "sort_desc(csi_score)",
    interpretation: "Selected patient position contextualizes relative burden percentile.",
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
