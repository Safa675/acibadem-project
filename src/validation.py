"""
validation.py
Retrospective Validation Experiments for HealthQuant Monitor.

Five validation experiments using only available data (no doctor input needed):

  Experiment 1: Regime Severity → Prescription Intensity
    H0: Mean prescription velocity ≤ 5 Rx/month when regime ≠ Critical
    H1: Prescription velocity is higher for Critical-state patients
    Test: Spearman rank correlation (regime_criticality vs rx_velocity)

  Experiment 2: Health VaR Tier → Visit Frequency
    H0: VaR risk score is uncorrelated with total visit count
    H1: Negative VaR (higher risk) correlates with more visits
    Test: Spearman rank correlation (var_pct vs total_visits)

  Experiment 3: Mean NLP Signal → Total Visits
    H0: Mean NLP composite is uncorrelated with total visits
    H1: Deterioration language predicts higher utilization
    Test: Spearman rank correlation

  Experiment 4: Lab Volatility → Critical Episodes
    H0: High lab volatility (health score std) is unrelated to regime severity
    H1: Higher volatility → more Critical state observations
    Test: Spearman rank correlation

  Experiment 5: CSI Score Calibration
    Validate that CSI rankings line up with actual outcomes (total_visits):
    Higher CSI predicts higher mean visits.
    Test: Spearman rank correlation and Mann-Whitney U for tiers
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from scipy.stats import spearmanr, mannwhitneyu
from typing import Optional


@dataclass
class ValidationResult:
    experiment_name: str
    hypothesis: str
    statistic_name: str
    statistic_value: float
    p_value: Optional[float]
    n_samples: int
    conclusion: str
    clinical_meaning: str
    passed: bool  # True = evidence supports hypothesis
    details: dict = field(default_factory=dict)


def _format_significance(p: Optional[float]) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "N/A"
    if p < 0.001:
        return "p < 0.001 ***"
    elif p < 0.01:
        return f"p = {p:.3f} **"
    elif p < 0.05:
        return f"p = {p:.3f} *"
    elif p < 0.10:
        return f"p = {p:.3f} (trend)"
    else:
        return f"p = {p:.3f} (n.s.)"


# ---------------------------------------------------------------------------
# Experiment 1: Regime Criticality → Prescription Intensity
# ---------------------------------------------------------------------------

def experiment1_regime_vs_prescriptions(
    profiles_df: pd.DataFrame,
) -> ValidationResult:
    """
    Test whether patients with higher critical_fraction have higher prescription velocity.
    Spearman rank correlation: critical_fraction vs prescription_velocity.
    """
    valid = profiles_df[["critical_fraction", "prescription_velocity"]].dropna()
    n = len(valid)

    if n < 3:
        return ValidationResult(
            experiment_name="Regime Severity → Prescription Intensity",
            hypothesis="Critical regime patients require more medications",
            statistic_name="Spearman ρ",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=n,
            conclusion="Insufficient data (n < 3)",
            clinical_meaning="N/A",
            passed=False,
            details={"note": "Need ≥3 patients with both regime and prescription data"},
        )

    r, p = spearmanr(valid["critical_fraction"], valid["prescription_velocity"])
    direction = "positive" if r > 0 else "negative"
    
    # Require p < 0.20 for passage. For tiny n, label as exploratory 
    passed = r > 0 and p < 0.20 if not np.isnan(p) else False
    
    if n <= 5:
        passed = False  # strictly don't pass if n<=5, call it exploratory

    conclusion = (
        f"Spearman ρ={r:.3f} ({_format_significance(p)}). "
        f"{'Supports' if passed else ('Exploratory trend' if n<=5 and r>0 else 'Does not support')} hypothesis."
    )

    return ValidationResult(
        experiment_name="Regime Severity → Prescription Intensity",
        hypothesis="Critical regime episodes correlate with higher prescription velocity",
        statistic_name="Spearman ρ",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=(
            "If Critical state correlates with Rx velocity, the regime classifier "
            "captures clinically meaningful deterioration — not just statistical noise."
        ),
        passed=passed,
        details={
            "direction": direction,
            "critical_fraction_range": [
                round(float(valid["critical_fraction"].min()), 3),
                round(float(valid["critical_fraction"].max()), 3),
            ],
            "rx_velocity_range": [
                round(float(valid["prescription_velocity"].min()), 2),
                round(float(valid["prescription_velocity"].max()), 2),
            ],
        },
    )


# ---------------------------------------------------------------------------
# Experiment 2: Health VaR Tier → Visit Frequency
# ---------------------------------------------------------------------------

def experiment2_var_tier_vs_visits(
    profiles_df: pd.DataFrame,
    var_summary: pd.DataFrame,
) -> ValidationResult:
    """
    Test whether RED VaR tier patients have higher total_visits.
    Requires merging profiles with VaR summary on patient_id.
    """
    if var_summary is None or var_summary.empty:
        return ValidationResult(
            experiment_name="Health VaR Tier → Visit Frequency",
            hypothesis="RED VaR patients have higher visit counts",
            statistic_name="Mann-Whitney U",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=0,
            conclusion="VaR summary not available",
            clinical_meaning="N/A",
            passed=False,
        )

    n_total_profiles = len(profiles_df)
    merged_all = profiles_df.merge(
        var_summary[["patient_id", "risk_tier", "var_pct"]],
        on="patient_id", how="inner"
    )
    n_after_merge = len(merged_all)
    merged = merged_all.dropna(subset=["total_visits"])
    
    n_dropped_merge = n_total_profiles - n_after_merge
    n_dropped_na = n_after_merge - len(merged)

    n = len(merged)
    if n < 3:
        return ValidationResult(
            experiment_name="Health VaR Tier → Visit Frequency",
            hypothesis="RED VaR patients have higher visit counts",
            statistic_name="Spearman ρ (var_pct vs total_visits)",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=n,
            conclusion="Insufficient data",
            clinical_meaning="N/A",
            passed=False,
        )

    # Use var_pct (negative = more risk) → expect negative correlation with visits
    r, p = spearmanr(merged["var_pct"], merged["total_visits"])
    
    passed = r < 0 and p < 0.20 if not np.isnan(p) else False
    if n <= 5: passed = False

    conclusion = (
        f"Spearman ρ(VaR%, total_visits)={r:.3f} ({_format_significance(p)}). "
        f"{'Evidence supports hypothesis' if passed else ('Exploratory finding' if n<=5 and r<0 else 'Weak evidence')}."
    )

    return ValidationResult(
        experiment_name="Health VaR Tier → Visit Frequency",
        hypothesis="Patients with negative Health VaR (higher risk) have more visits",
        statistic_name="Spearman ρ",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=(
            "If Health VaR predicts visit frequency, it has validated predictive power "
            "for healthcare utilization — enabling proactive resource planning."
        ),
        passed=passed,
        details={"var_pct_mean": round(float(merged["var_pct"].mean()), 2),
                 "n_dropped_merge": n_dropped_merge,
                 "n_dropped_na": n_dropped_na},
    )


# ---------------------------------------------------------------------------
# Experiment 3: First-Visit NLP Signal → Total Visits
# ---------------------------------------------------------------------------

def experiment3_nlp_vs_outcomes(
    profiles_df: pd.DataFrame,
) -> ValidationResult:
    """
    Test whether mean NLP composite predicts total visits.
    Negative NLP (deterioration language) → more visits expected.
    """
    valid = profiles_df[["mean_nlp_composite", "total_visits"]].dropna()
    n = len(valid)

    if n < 3:
        return ValidationResult(
            experiment_name="Mean Clinical NLP Signal → Healthcare Utilization",
            hypothesis="Negative mean NLP language correlates with higher visit counts",
            statistic_name="Spearman ρ",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=n,
            conclusion="Insufficient data",
            clinical_meaning="N/A",
            passed=False,
        )

    r, p = spearmanr(valid["mean_nlp_composite"], valid["total_visits"])
    
    passed = r < 0 and p < 0.20 if not np.isnan(p) else False
    if n <= 5: passed = False

    conclusion = (
        f"Spearman ρ(NLP, total_visits)={r:.3f} ({_format_significance(p)}). "
        f"{'Supports hypothesis' if passed else ('Exploratory trend' if n<=5 and r<0 else 'Weakly correlated')}."
    )

    return ValidationResult(
        experiment_name="Mean Clinical NLP Signal → Healthcare Utilization",
        hypothesis="Deterioration language in clinical notes predicts higher visit count",
        statistic_name="Spearman ρ",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=(
            "Turkish free-text NLP on ÖYKÜ/Muayene Notu providing predictive signal "
            "validates the clinical text analysis component of the system."
        ),
        passed=passed,
        details={
            "nlp_mean": round(float(valid["mean_nlp_composite"].mean()), 3),
            "nlp_std": round(float(valid["mean_nlp_composite"].std()), 3),
        },
    )


# ---------------------------------------------------------------------------
# Experiment 4: Lab Volatility → Regime Severity
# ---------------------------------------------------------------------------

def experiment4_volatility_vs_critical(
    profiles_df: pd.DataFrame,
) -> ValidationResult:
    """
    Test whether lab volatility (health_score_volatility) predicts critical_fraction.
    This validates the regime classifier's volatility dimension.
    """
    valid = profiles_df[["health_score_volatility", "critical_fraction"]].dropna()
    n = len(valid)

    if n < 3:
        return ValidationResult(
            experiment_name="Lab Volatility → Critical State Fraction",
            hypothesis="Higher lab volatility → more time in Critical state",
            statistic_name="Spearman ρ",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=n,
            conclusion="Insufficient data",
            clinical_meaning="N/A",
            passed=False,
        )

    r, p = spearmanr(valid["health_score_volatility"], valid["critical_fraction"])
    
    passed = r > 0 and p < 0.20 if not np.isnan(p) else False
    if n <= 5: passed = False

    conclusion = (
        f"Spearman ρ(vol, critical_fraction)={r:.3f} ({_format_significance(p)}). "
        f"{'Supports hypothesis' if passed else ('Exploratory link' if n<=5 and r>0 else 'Weak link')}."
    )

    return ValidationResult(
        experiment_name="Lab Volatility → Critical State Fraction",
        hypothesis="Higher health score volatility predicts more time in Critical regime state",
        statistic_name="Spearman ρ",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=(
            "If volatility correlates with Critical state, the 2D regime classifier "
            "(trend × volatility) has internal consistency — the dimensions are not redundant."
        ),
        passed=passed,
        details={
            "vol_range": [
                round(float(valid["health_score_volatility"].min()), 2),
                round(float(valid["health_score_volatility"].max()), 2),
            ],
        },
    )


# ---------------------------------------------------------------------------
# Experiment 5: CSI Calibration (tier vs outcome)
# ---------------------------------------------------------------------------

def experiment5_csi_calibration(
    profiles_df: pd.DataFrame,
) -> ValidationResult:
    """
    Validate CSI score ordering vs total_visits using Spearman correlation.
    Higher CSI should predict more visits.
    """
    valid = profiles_df[["csi_score", "total_visits"]].dropna()
    n = len(valid)

    if n < 3:
        return ValidationResult(
            experiment_name="CSI Score Calibration vs Healthcare Utilization",
            hypothesis="Higher CSI score predicts more total visits",
            statistic_name="Spearman ρ",
            statistic_value=float("nan"),
            p_value=None,
            n_samples=n,
            conclusion="Insufficient data",
            clinical_meaning="N/A",
            passed=False,
        )

    r, p = spearmanr(valid["csi_score"], valid["total_visits"])
    
    passed = r > 0 and p < 0.20 if not np.isnan(p) else False
    if n <= 5: passed = False

    conclusion = (
        f"Spearman ρ(CSI, total_visits)={r:.3f} ({_format_significance(p)}). "
        f"{'CSI ordering validated.' if passed else ('Exploratory validation' if n<=5 and r>0 else 'CSI ordering weak')}."
    )

    # Tier comparison avoiding janky index locs
    tier_stats = {}
    if "csi_tier" in profiles_df.columns:
        valid_tiers = profiles_df[["csi_score", "csi_tier", "total_visits"]].dropna()
        high = valid_tiers["csi_tier"].isin(["HIGH", "CRITICAL"])
        high_visits = valid_tiers.loc[high, "total_visits"]
        low_visits = valid_tiers.loc[~high, "total_visits"]
        
        if not high_visits.empty and not low_visits.empty:
            ratio = round(float(high_visits.mean()) / max(float(low_visits.mean()), 1), 2)
            tier_stats = {
                "high_csi_mean_visits": round(float(high_visits.mean()), 1),
                "low_csi_mean_visits": round(float(low_visits.mean()), 1),
                "ratio": ratio,
            }
            # Mann-Whitney U test
            try:
                u, p_u = mannwhitneyu(high_visits, low_visits, alternative="greater")
                tier_stats["mwu_p_value"] = round(float(p_u), 3)
                tier_stats["mwu_significant"] = bool(p_u < 0.20)
            except Exception:
                tier_stats["mwu_p_value"] = None

    return ValidationResult(
        experiment_name="CSI Score Calibration vs Healthcare Utilization",
        hypothesis="Higher Clinical Severity Index score predicts more total healthcare visits",
        statistic_name="Spearman ρ",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=(
            "CSI calibration against actual utilization validates the composite index "
            "as a clinically meaningful triage and resource-planning tool."
        ),
        passed=passed,
        details=tier_stats,
    )


# ---------------------------------------------------------------------------
# Run all experiments
# ---------------------------------------------------------------------------

def run_all_validations(
    profiles_df: pd.DataFrame,
    var_summary: pd.DataFrame | None = None,
) -> list[ValidationResult]:
    """Run all 5 validation experiments and return results."""
    results = [
        experiment1_regime_vs_prescriptions(profiles_df),
        experiment2_var_tier_vs_visits(profiles_df, var_summary),
        experiment3_nlp_vs_outcomes(profiles_df),
        experiment4_volatility_vs_critical(profiles_df),
        experiment5_csi_calibration(profiles_df),
    ]
    return results


def validation_summary_df(results: list[ValidationResult]) -> pd.DataFrame:
    """Convert list of ValidationResult to a summary DataFrame."""
    rows = []
    for r in results:
        rows.append({
            "Experiment": r.experiment_name,
            "Statistic": r.statistic_name,
            "Value": r.statistic_value,
            "p-value": r.p_value,
            "n": r.n_samples,
            "Passed": "✅" if r.passed else "❌",
            "Conclusion": r.conclusion,
        })
    return pd.DataFrame(rows)
