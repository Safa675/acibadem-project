"""
src/__init__.py
HealthQuant Clinical Intelligence — package init.
"""

from .data_loader import (
    load_labdata,
    load_anadata,
    load_recete,
    load_all_data,
    get_patient_labs,
    get_patient_vitals,
    get_patient_visits,
    get_patient_prescriptions,
    get_common_patients,
)
from .health_index import HealthIndexBuilder, SeriesPoint, HealthSnapshot
from .patient_regime import (
    PatientStateClassifier,
    PatientState,
    STATE_COLORS,
    STATE_EMOJI,
    PatientRegimeResult,
    RegimeConfig,
    classify_all_patients,
    compute_cohort_stats,
)
from .health_var import compute_health_var, compute_all_patient_vars, HealthVaRResult
from .nlp_signal import clinical_nlp_score, score_patient_visits, score_all_patients, dual_nlp_score, transformer_nlp_score
from .fusion import compute_composite_score, compute_all_composites, CompositeRiskScore
from .visualizer import (
    plot_regime_timeline,
    plot_health_var_fan,
    plot_nlp_heatmap,
    plot_stock_vs_patient_hook,
    plot_cohort_risk_dashboard,
)
from .outcomes import (
    PatientOutcomeProfile,
    build_patient_outcome_profile,
    build_all_outcome_profiles,
    profiles_to_dataframe,
    compute_feature_correlations,
    predict_care_duration_narrative,
)
from .validation import (
    ValidationResult,
    run_all_validations,
    validation_summary_df,
)

__all__ = [
    "load_labdata", "load_anadata", "load_recete", "load_all_data",
    "get_patient_labs", "get_patient_vitals", "get_patient_visits",
    "get_patient_prescriptions", "get_common_patients",
    "HealthIndexBuilder", "SeriesPoint", "HealthSnapshot",
    "PatientStateClassifier", "PatientState", "PatientRegimeResult",
    "STATE_COLORS", "STATE_EMOJI",
    "RegimeConfig", "classify_all_patients", "compute_cohort_stats",
    "compute_health_var", "compute_all_patient_vars", "HealthVaRResult",
    "clinical_nlp_score", "score_patient_visits", "score_all_patients",
    "dual_nlp_score", "transformer_nlp_score",
    "compute_composite_score", "compute_all_composites", "CompositeRiskScore",
    "plot_regime_timeline", "plot_health_var_fan", "plot_nlp_heatmap",
    "plot_stock_vs_patient_hook", "plot_cohort_risk_dashboard",
    "PatientOutcomeProfile", "build_patient_outcome_profile",
    "build_all_outcome_profiles", "profiles_to_dataframe",
    "compute_feature_correlations", "predict_care_duration_narrative",
    "ValidationResult", "run_all_validations", "validation_summary_df",
]

# ---------------------------------------------------------------------------
# Score Polarity Contracts (BUG 5.2 fix)
# ---------------------------------------------------------------------------
# Documents the directional semantics of every score in the system.
# If you refactor a scoring module, update this contract AND verify
# that all downstream consumers (fusion, validation, dashboard) agree.
#
# Format: (min, max, direction_of_good)
#   "higher_is_better" = 100 is healthy / safe
#   "higher_is_worse"  = 100 is sick / critical
#   "higher_is_better_signed" = positive is good, negative is bad
SCORE_POLARITY_CONTRACTS = {
    "health_index":       (0, 100,  "higher_is_better"),
    "nlp_raw":            (-1, 1,   "higher_is_better_signed"),
    "nlp_normalized":     (0, 100,  "higher_is_better"),
    "composite_score":    (0, 100,  "higher_is_better"),
    "med_change_velocity":(0, 100,  "higher_is_better"),
    "csi_score":          (0, 100,  "higher_is_WORSE"),
    "csi_health_score":   (0, 100,  "higher_is_better"),
    "var_pct":            (None, None, "negative_is_risk"),
}
