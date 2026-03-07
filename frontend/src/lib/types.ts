// TypeScript types matching the FastAPI response shapes

export interface KPI {
  n_patients: number;
  mean_score: number;
  mean_eci: number;
  n_critical: number;
  total_rx: number;
  mean_data_completeness?: number;
}

export interface PatientMeta {
  patient_id: string;
  age: number | null;
  sex: string | null;
  sex_raw?: string | null;
  weight_kg: number | null;
  doctor_code: string | null;
  comorbidity_conditions: string[];
}

export interface CompositeRow {
  patient_id: string;
  rating: string;
  composite_score: number;
  health_index_score: number;
  nlp_score: number;
  eci_score?: number;
  eci_rating?: string;
  eci_rating_label?: string;
  eci_visit_intensity?: number;
  eci_med_burden?: number;
  eci_diagnostic_intensity?: number;
  eci_trajectory_cost?: number;
  n_prescriptions?: number;
  n_comorbidities?: number;
  age?: number;
  med_velocity_score?: number;
  data_completeness?: number;
}

export interface VarSummaryRow {
  patient_id: string;
  current_score: number;
  var_pct: number;
  health_var_score: number;
  median_forecast?: number;
  risk_tier: string;
  risk_label?: string;
  downside_var_pct: number;
}

export interface ScatterPoint {
  patient_id: string;
  health_index_score: number;
  nlp_score: number;
  rating: string;
  eci_score: number;
}

export interface RatingInterval {
  rating: string;
  min_score: number;
  max_score: number;
  label: string;
}

export interface CohortData {
  kpi: KPI;
  composites: CompositeRow[];
  composites_pagination?: PaginationMeta;
  var_summary: VarSummaryRow[];
  var_pagination?: PaginationMeta;
  rating_distribution: Record<string, number>;
  rating_intervals: RatingInterval[];
  regime_distribution: Record<string, number>;
  scatter_data: ScatterPoint[];
  scatter_total?: number;
}

export interface PaginationMeta {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export interface PatientSearchResult {
  patient_id: string;
  age: number | null;
  sex: string | null;
  sex_raw?: string | null;
  weight_kg?: number | null;
  doctor_code?: string | null;
  comorbidity_conditions?: string[];
}

export interface PatientSearchResponse {
  results: PatientSearchResult[];
  total_matched: number;
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
  patient_id: string;
  rating: string;
  composite_score: number;
  regime_state: string;
  health_score: number | null;
  downside_var_pct: number | null;
  eci_score: number | null;
  eci_rating: string | null;
  eci_rating_label: string | null;
  eci_visit_intensity: number | null;
  eci_med_burden: number | null;
  eci_diagnostic_intensity: number | null;
  eci_trajectory_cost: number | null;
  age: number | null;
  sex: string | null;
  n_comorbidities: number;
  total_visits: number | null;
  n_lab_draws: number;
  n_prescriptions: number;
  data_completeness: number | null;
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

export interface ECI {
  score: number | null;
  rating: string | null;
  rating_label: string | null;
  visit_intensity: number | null;
  med_burden: number | null;
  diagnostic_intensity: number | null;
  trajectory_cost: number | null;
}

export interface FeatureBar {
  feature: string;
  value: number;
}

export interface CohortRanking {
  patient_id: string;
  label: string;
  eci_score: number;
  is_selected: boolean;
}

export interface FeatureCorrelation {
  feature: string;
  spearman_r: number;
  p_value: number | null;
}

export interface OutcomeData {
  eci: ECI;
  narrative: string;
  feature_bar: FeatureBar[];
  cohort_ranking: CohortRanking[];
  patient_percentile: number | null;
  cohort_total: number;
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
  benchmark: string; // "SOFA" | "NEWS2" | "APACHE II"
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

export interface PatientFilters {
  gender: string;
  doctor: string;
  comorbidityConditions: string[];
  ageMin: string;
  ageMax: string;
  weightMin: string;
  weightMax: string;
}
