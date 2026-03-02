// TypeScript types matching the FastAPI response shapes

export interface KPI {
  n_patients: number;
  mean_score: number;
  n_high_risk: number;
  n_critical: number;
  total_rx: number;
}

export interface CompositeRow {
  patient_id: number;
  rating: string;
  composite_score: number;
  health_index_score: number;
  nlp_score: number;
  csi_score?: number;
  csi_tier?: string;
  n_prescriptions?: number;
  n_comorbidities?: number;
  age?: number;
  med_velocity_score?: number;
}

export interface VarSummaryRow {
  patient_id: number;
  current_score: number;
  var_pct: number;
  health_var_score: number;
  median_forecast?: number;
  risk_tier: string;
  risk_label?: string;
  downside_var_pct: number;
}

export interface ScatterPoint {
  patient_id: number;
  health_index_score: number;
  nlp_score: number;
  rating: string;
  csi_score: number;
}

export interface CohortData {
  kpi: KPI;
  composites: CompositeRow[];
  var_summary: VarSummaryRow[];
  rating_distribution: Record<string, number>;
  regime_distribution: Record<string, number>;
  scatter_data: ScatterPoint[];
}

export interface Comorbidity {
  label: string;
  detail: string | null;
}

export interface RegimeTimelinePoint {
  date: string;
  health_score: number;
  ma: number | null;
  state: string | null;
}

export interface VarFanData {
  history_dates: string[];
  history_scores: number[];
  future_dates: string[];
  p05: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  risk_tier: string;
  var_pct: number;
}

export interface NlpBar {
  date: string;
  nlp_composite: number;
}

export interface NliScore {
  date: string;
  source: string;
  text: string;
  nli_score: number;
}

export interface LabSeries {
  dates: string[];
  values: number[];
  ref_min: number | null;
  ref_max: number | null;
}

export interface ClinicalNote {
  date: string;
  entries: { source: string; text: string }[];
}

export interface PatientSummary {
  patient_id: number;
  rating: string;
  composite_score: number;
  regime_state: string;
  health_score: number | null;
  downside_var_pct: number | null;
  csi_score: number | null;
  csi_tier: string | null;
  age: number | null;
  sex: string | null;
  n_comorbidities: number;
  total_visits: number | null;
  n_lab_draws: number;
  n_prescriptions: number;
}

export interface PatientData {
  summary: PatientSummary;
  comorbidities: Comorbidity[];
  regime_timeline: RegimeTimelinePoint[];
  prescription_dates: string[];
  var_fan: VarFanData | null;
  nlp_bars: NlpBar[];
  nli_scores: NliScore[];
  lab_series: Record<string, LabSeries>;
  clinical_notes: ClinicalNote[];
}

export interface CSI {
  score: number;
  tier: string;
}

export interface FeatureBar {
  feature: string;
  value: number;
}

export interface CohortRanking {
  patient_id: number;
  label: string;
  csi_score: number;
  is_selected: boolean;
}

export interface FeatureCorrelation {
  feature: string;
  spearman_r: number;
  p_value: number | null;
}

export interface OutcomeData {
  csi: CSI;
  narrative: string;
  feature_bar: FeatureBar[];
  cohort_ranking: CohortRanking[];
  feature_correlations: FeatureCorrelation[];
}

export interface ValidationExperiment {
  name: string;
  hypothesis: string;
  passed: boolean;
  statistic_name: string;
  statistic_value: number | null;
  p_value: number | null;
  n_samples: number;
  conclusion: string;
  clinical_meaning: string;
  details: Record<string, unknown> | null;
}

export interface ValidationData {
  summary: Record<string, unknown>[];
  experiments: ValidationExperiment[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}
