"""
validation.py
Institutional benchmark validation for the Composite Health Index.

This module validates our Health Index against established clinical severity scores:
  - SOFA (Sequential Organ Failure Assessment)
  - APACHE II (Acute Physiology and Chronic Health Evaluation II)

Note: NEWS2 is excluded due to insufficient parameter coverage (3/7).

For each benchmark, we run 2 Spearman rank-correlation experiments:
  1) Mean Health Index vs Mean benchmark score
  2) Mean Health Index vs Max benchmark score

Expected direction: Negative (higher Health Index = healthier; higher severity score = sicker).

Data availability:
  - SOFA:     4/6 organ systems  (Coagulation, Liver, Cardiovascular, Renal)
  - APACHE II: 7/12 APS params  (MAP, HR, Na, K, Creatinine, Hematocrit, WBC)
  - Missing parameters default to 0 (conservative lower-bound).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


# ── Data structures ──────────────────────────────────────────────────────────


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
    passed: bool
    benchmark: str = ""  # "SOFA", "APACHE II"
    details: dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _format_significance(p: Optional[float]) -> str:
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "N/A"
    if p < 0.001:
        return "p < 0.001 ***"
    if p < 0.01:
        return f"p = {p:.3f} **"
    if p < 0.05:
        return f"p = {p:.3f} *"
    if p < 0.10:
        return f"p = {p:.3f} (trend)"
    return f"p = {p:.3f} (n.s.)"


def _build_unavailable_result(
    experiment_name: str,
    hypothesis: str,
    clinical_meaning: str,
    conclusion: str,
    benchmark: str = "",
    n_samples: int = 0,
    details: Optional[dict] = None,
) -> ValidationResult:
    return ValidationResult(
        experiment_name=experiment_name,
        hypothesis=hypothesis,
        statistic_name="Spearman \u03c1",
        statistic_value=float("nan"),
        p_value=None,
        n_samples=n_samples,
        conclusion=conclusion,
        clinical_meaning=clinical_meaning,
        passed=False,
        benchmark=benchmark,
        details=details or {},
    )


# ── Core experiment runner ───────────────────────────────────────────────────


def _run_negative_correlation_experiment(
    merged_df: pd.DataFrame,
    hi_col: str,
    institutional_col: str,
    experiment_name: str,
    benchmark: str,
) -> ValidationResult:
    """
    Run a Spearman correlation experiment expecting negative correlation
    between Health Index (higher = healthier) and an institutional severity
    score (higher = sicker).
    """
    hypothesis = (
        f"Higher Health Index should correlate with lower {benchmark} severity "
        "(negative Spearman correlation)."
    )
    clinical_meaning = (
        f"Negative association between Health Index and {benchmark} indicates our "
        "composite score is directionally aligned with an established clinical "
        "severity scale."
    )

    if merged_df is None or merged_df.empty:
        return _build_unavailable_result(
            experiment_name=experiment_name,
            hypothesis=hypothesis,
            clinical_meaning=clinical_meaning,
            conclusion="No merged patient data available for this benchmark.",
            benchmark=benchmark,
            details={"hi_col": hi_col, "institutional_col": institutional_col},
        )

    if hi_col not in merged_df.columns or institutional_col not in merged_df.columns:
        missing = []
        if hi_col not in merged_df.columns:
            missing.append(hi_col)
        if institutional_col not in merged_df.columns:
            missing.append(institutional_col)
        return _build_unavailable_result(
            experiment_name=experiment_name,
            hypothesis=hypothesis,
            clinical_meaning=clinical_meaning,
            conclusion=f"Required columns not found: {', '.join(missing)}.",
            benchmark=benchmark,
            details={"hi_col": hi_col, "institutional_col": institutional_col},
        )

    valid = merged_df[[hi_col, institutional_col]].dropna()
    n = len(valid)
    if n < 3:
        return _build_unavailable_result(
            experiment_name=experiment_name,
            hypothesis=hypothesis,
            clinical_meaning=clinical_meaning,
            conclusion=f"Insufficient data for correlation (n={n}, need at least 3).",
            benchmark=benchmark,
            n_samples=n,
            details={
                "hi_col": hi_col,
                "institutional_col": institutional_col,
                "minimum_required_n": 3,
                "reason": "insufficient_samples",
            },
        )

    x = valid[hi_col]
    y = valid[institutional_col]
    if x.nunique() <= 1 or y.nunique() <= 1:
        return _build_unavailable_result(
            experiment_name=experiment_name,
            hypothesis=hypothesis,
            clinical_meaning=clinical_meaning,
            conclusion=(
                "Non-testable: one input is constant across patients "
                "(correlation undefined)."
            ),
            benchmark=benchmark,
            n_samples=n,
            details={
                "hi_col": hi_col,
                "institutional_col": institutional_col,
                "reason": "constant_input",
                "hi_unique": int(x.nunique()),
                "institutional_unique": int(y.nunique()),
            },
        )

    r, p = spearmanr(x, y)
    if np.isnan(r) or np.isnan(p):
        return _build_unavailable_result(
            experiment_name=experiment_name,
            hypothesis=hypothesis,
            clinical_meaning=clinical_meaning,
            conclusion="Correlation undefined due to numerical/statistical edge case.",
            benchmark=benchmark,
            n_samples=n,
            details={
                "hi_col": hi_col,
                "institutional_col": institutional_col,
                "reason": "undefined_statistic",
            },
        )

    passed = bool(r < 0 and p < 0.20 and n > 5)
    if passed:
        verdict = "Evidence supports expected negative alignment."
    elif n <= 5 and r < 0 and p < 0.20:
        verdict = "Exploratory negative trend (n \u2264 5 guard prevents pass)."
    elif r >= 0:
        verdict = "Direction mismatch (correlation is not negative)."
    else:
        verdict = "Weak evidence for negative alignment."

    conclusion = (
        f"Spearman \u03c1={r:.3f} ({_format_significance(p)}), n={n}. {verdict}"
    )

    return ValidationResult(
        experiment_name=experiment_name,
        hypothesis=hypothesis,
        statistic_name="Spearman \u03c1",
        statistic_value=round(float(r), 3),
        p_value=round(float(p), 3),
        n_samples=n,
        conclusion=conclusion,
        clinical_meaning=clinical_meaning,
        passed=passed,
        benchmark=benchmark,
        details={
            "hi_col": hi_col,
            "institutional_col": institutional_col,
            "expected_direction": "negative",
            "hi_range": [
                round(float(x.min()), 2),
                round(float(x.max()), 2),
            ],
            "institutional_range": [
                round(float(y.min()), 2),
                round(float(y.max()), 2),
            ],
        },
    )


# ── Institutional benchmark experiments ──────────────────────────────────────

_BENCHMARK_SPECS = [
    {
        "benchmark": "SOFA",
        "mean_col": "mean_sofa",
        "max_col": "max_sofa",
        "full_name": "SOFA (Sequential Organ Failure Assessment)",
        "coverage": "4/6 organ systems",
    },
    {
        "benchmark": "APACHE II",
        "mean_col": "mean_apache2",
        "max_col": "max_apache2",
        "full_name": "APACHE II (Acute Physiology and Chronic Health Evaluation)",
        "coverage": "7/12 APS parameters",
    },
]


def _run_institutional_benchmarks(
    hi_df: pd.DataFrame | None,
    sofa_df: pd.DataFrame | None,
    news2_df: pd.DataFrame | None,
    apache2_df: pd.DataFrame | None,
) -> list[ValidationResult]:
    """
    Run 4 Spearman correlation experiments (2 per benchmark) comparing
    Health Index against SOFA and APACHE II severity scores.
    NEWS2 is excluded due to insufficient parameter coverage (3/7).
    """
    results: list[ValidationResult] = []

    score_dfs = {
        "SOFA": sofa_df,
        "APACHE II": apache2_df,
    }

    for spec in _BENCHMARK_SPECS:
        bm = spec["benchmark"]
        score_df = score_dfs[bm]

        # Merge Health Index with institutional score
        if hi_df is None or hi_df.empty or score_df is None or score_df.empty:
            # Create 2 unavailable results
            for variant in ["Mean", "Max"]:
                results.append(
                    _build_unavailable_result(
                        experiment_name=f"Health Index vs {variant} {bm}",
                        hypothesis=f"Higher Health Index should correlate with lower {bm} ({spec['coverage']}).",
                        clinical_meaning=f"Validates alignment with {spec['full_name']}.",
                        conclusion=f"No data available — {'Health Index' if hi_df is None or (hi_df is not None and hi_df.empty) else bm} scores not computed.",
                        benchmark=bm,
                    )
                )
            continue

        merged = hi_df.merge(score_df, on="patient_id", how="inner")

        # Experiment 1: Mean HI vs Mean score
        results.append(
            _run_negative_correlation_experiment(
                merged,
                hi_col="mean_hi_score",
                institutional_col=spec["mean_col"],
                experiment_name=f"Health Index vs Mean {bm}",
                benchmark=bm,
            )
        )

        # Experiment 2: Mean HI vs Max score
        results.append(
            _run_negative_correlation_experiment(
                merged,
                hi_col="mean_hi_score",
                institutional_col=spec["max_col"],
                experiment_name=f"Health Index vs Max {bm}",
                benchmark=bm,
            )
        )

    return results


# ── Public API ───────────────────────────────────────────────────────────────


def run_all_validations(
    hi_df: pd.DataFrame | None = None,
    sofa_df: pd.DataFrame | None = None,
    news2_df: pd.DataFrame | None = None,
    apache2_df: pd.DataFrame | None = None,
) -> list[ValidationResult]:
    """
    Run all institutional benchmark validation experiments.

    Args:
      hi_df:      Per-patient Health Index summary with columns:
                    patient_id, mean_hi_score
      sofa_df:    Per-patient SOFA summary with columns:
                    patient_id, mean_sofa, max_sofa, n_visits
      news2_df:   Per-patient NEWS2 summary (accepted for API compatibility,
                    but NEWS2 experiments are excluded due to insufficient
                    parameter coverage 3/7)
      apache2_df: Per-patient APACHE II summary with columns:
                    patient_id, mean_apache2, max_apache2, n_visits

    Returns:
      List of 4 ValidationResult objects (2 per benchmark: SOFA, APACHE II).
    """
    return _run_institutional_benchmarks(hi_df, sofa_df, news2_df, apache2_df)


def validation_summary_df(results: list[ValidationResult]) -> pd.DataFrame:
    """Convert results to a summary DataFrame for the API."""
    rows = []
    for r in results:
        rows.append(
            {
                "Experiment": r.experiment_name,
                "Benchmark": r.benchmark,
                "Statistic": r.statistic_name,
                "Value": r.statistic_value,
                "p-value": r.p_value,
                "n": r.n_samples,
                "Passed": "\u2705" if r.passed else "\u274c",
                "Conclusion": r.conclusion,
            }
        )
    return pd.DataFrame(rows)
