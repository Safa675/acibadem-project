"""
outcomes.py
Clinical Outcome Prediction Engine — ACUHIT Hackathon 2026

Predicts two primary outcomes from patient trajectory features:
  1. Total Care Duration (ILK_TANI_SON_TANI_GUN_FARKI → days from first to last diagnosis)
  2. Healthcare Utilization (TOPLAM_GELIS_SAYISI → total visit count)

Approach: Feature engineering from labs + NLP + regime + vitals → Spearman feature
  correlation + rule-based Clinical Severity Score (CSI).

Why rule-based? n=9 patients is insufficient for ML training + test split.
Instead we demonstrate the FEATURE ENGINEERING pipeline that WILL work on larger
cohorts, and validate signal quality using rank correlation.

Clinical Severity Index (CSI):
  - Health Score Trend (wt=0.25): negative slope → higher severity
  - Lab Volatility (wt=0.20): high std → instability
  - Critical Regime Fraction (wt=0.20): % of time in Critical state
  - NLP Signal (wt=0.15): negative language → deterioration
  - Prescription Intensity (wt=0.10): high Rx velocity → active disease
  - Comorbidity Burden (wt=0.10): ICD comorbidities present

CSI ∈ [0, 100] — 0=minimal burden, 100=maximum burden
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from scipy.stats import spearmanr


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass
class PatientOutcomeProfile:
    patient_id: str

    # ---- Feature vector ----
    initial_health_score: float
    final_health_score: float
    mean_health_score: float
    health_score_trend: float  # slope (score change per observation)
    health_score_volatility: float  # rolling std
    n_lab_draws: int
    n_critical_episodes: int
    critical_fraction: float  # % observations in Critical state
    mean_nlp_composite: float  # mean NLP score [-1, +1]
    n_prescriptions: int
    prescription_velocity: float  # Rx per 30 days
    n_comorbidities: int
    age: Optional[float]
    sex: Optional[str]

    # ---- Outcome targets ----
    total_care_days: Optional[float]  # ILK_TANI_SON_TANI_GUN_FARKI
    total_visits: Optional[int]  # TOPLAM_GELIS_SAYISI

    # ---- Clinical Severity Index ----
    csi_score: float  # [0, 100]
    csi_tier: str  # LOW / MODERATE / HIGH / CRITICAL
    csi_label: str
    feature_contributions: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Comorbidity extraction
# ---------------------------------------------------------------------------

_COMORBIDITY_COLUMNS = [
    "Hipertansiyon Hastada",
    "Kalp Damar Hastada",
    "Diyabet Hastada",
    "Kan Hastalıkları Hastada",
    "Kronik Hastalıklar Diğer",
    "Ameliyat Geçmişi",
]


def _count_comorbidities(
    ana_df: pd.DataFrame, patient_id: str, *, patient_rows: pd.DataFrame | None = None
) -> int:
    """Count how many comorbidity flags are positive for this patient.

    Args:
        ana_df: full anadata DataFrame (used as fallback)
        patient_id: patient identifier
        patient_rows: pre-filtered rows for this patient (O(1) vs O(N) scan)
    """
    rows = (
        patient_rows
        if patient_rows is not None
        else ana_df[ana_df["patient_id"] == patient_id]
    )
    if rows.empty:
        return 0
    count = 0
    for col in _COMORBIDITY_COLUMNS:
        if col in rows.columns:
            # Check if any row has a truthy/non-null value
            vals = rows[col].dropna()
            if not vals.empty:
                for v in vals:
                    if isinstance(v, str) and len(v.strip()) >= 1:
                        count += 1
                        break
                    elif (
                        not isinstance(v, str)
                        and isinstance(v, (int, float, np.integer, np.floating))
                        and v > 0
                    ):
                        count += 1
                        break
    return count


# ---------------------------------------------------------------------------
# Regime feature extraction
# ---------------------------------------------------------------------------


def _extract_regime_features(regime_result) -> tuple[int, float]:
    """Extract n_critical_episodes and critical_fraction from a PatientRegimeResult."""
    if regime_result is None:
        return 0, 0.0
    df = regime_result.to_dataframe()
    if df.empty:
        return 0, 0.0
    n_critical = int((df["state"] == "Critical").sum())
    critical_frac = n_critical / max(len(df), 1)
    return n_critical, critical_frac


# ---------------------------------------------------------------------------
# Health score trend (linear regression slope)
# ---------------------------------------------------------------------------


def _compute_trend(scores: list[float]) -> float:
    """Compute linear regression slope over observation index."""
    if len(scores) < 2:
        return 0.0
    x = np.arange(len(scores), dtype=float)
    y = np.array(scores, dtype=float)
    # Least-squares slope
    x_mean, y_mean = x.mean(), y.mean()
    denom = np.sum((x - x_mean) ** 2)
    if denom < 1e-9:
        return 0.0
    return float(np.sum((x - x_mean) * (y - y_mean)) / denom)


# ---------------------------------------------------------------------------
# CSI scoring
# ---------------------------------------------------------------------------

_CSI_WEIGHTS = {
    "health_trend": 0.25,
    "lab_volatility": 0.20,
    "critical_fraction": 0.20,
    "nlp_signal": 0.15,
    "prescription_intensity": 0.10,
    "comorbidity_burden": 0.10,
}

_CSI_TIERS = [
    (75, "CRITICAL", "Immediate clinical attention required"),
    (50, "HIGH", "Active intervention recommended"),
    (25, "MODERATE", "Enhanced monitoring needed"),
    (0, "LOW", "Routine monitoring"),
]


def _compute_csi(
    health_score_trend: float,
    health_score_volatility: float,
    critical_fraction: float,
    mean_nlp: float,
    prescription_velocity: float,
    n_comorbidities: int,
) -> tuple[float, str, str, dict]:
    """
    Build Clinical Severity Index [0, 100].
    Each component normalized to [0, 100] before weighting.
    """
    # 1. Health trend: negative slope is bad (0 = improving, 100 = fast decline)
    # Slope range: typical ±5 per observation. Map -5→100, +5→0
    trend_component = float(np.clip((-health_score_trend + 5.0) / 10.0 * 100.0, 0, 100))

    # 2. Lab volatility: high std = instability (0 = perfectly stable, 100 = very unstable)
    # Typical range: std 0-20 for health scores
    vol_component = float(np.clip(health_score_volatility / 20.0 * 100.0, 0, 100))

    # 3. Critical fraction: already [0, 1] → scale to [0, 100]
    crit_component = float(np.clip(critical_fraction * 100.0, 0, 100))

    # 4. NLP: -1 (bad) → 100, +1 (good) → 0
    nlp_component = float(np.clip((-mean_nlp + 1.0) / 2.0 * 100.0, 0, 100))

    # 5. Prescription velocity: 0 Rx/month → 0, 10+ → 100
    rx_component = float(np.clip(prescription_velocity / 10.0 * 100.0, 0, 100))

    # 6. Comorbidities: 0 → 0, 4+ → 100
    comorbidity_component = float(np.clip(n_comorbidities / 4.0 * 100.0, 0, 100))

    components = {
        "health_trend": (trend_component, _CSI_WEIGHTS["health_trend"]),
        "lab_volatility": (vol_component, _CSI_WEIGHTS["lab_volatility"]),
        "critical_fraction": (crit_component, _CSI_WEIGHTS["critical_fraction"]),
        "nlp_signal": (nlp_component, _CSI_WEIGHTS["nlp_signal"]),
        "prescription_intensity": (
            rx_component,
            _CSI_WEIGHTS["prescription_intensity"],
        ),
        "comorbidity_burden": (
            comorbidity_component,
            _CSI_WEIGHTS["comorbidity_burden"],
        ),
    }

    csi = sum(score * weight for score, weight in components.values())
    csi = float(np.clip(csi, 0, 100))

    tier, label = "LOW", "Routine monitoring"
    for threshold, t, l in _CSI_TIERS:
        if csi >= threshold:
            tier, label = t, l
            break

    feature_contribs = {
        k: round(score * weight, 2) for k, (score, weight) in components.items()
    }
    return csi, tier, label, feature_contribs


# ---------------------------------------------------------------------------
# Main feature extraction
# ---------------------------------------------------------------------------


def build_patient_outcome_profile(
    patient_id: str,
    snapshots: list,
    regime_result,
    ana_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    nlp_df: pd.DataFrame,
    *,
    patient_ana: pd.DataFrame | None = None,
    patient_recs: pd.DataFrame | None = None,
) -> PatientOutcomeProfile:
    """
    Build a complete PatientOutcomeProfile from all available data sources.

    Args:
        patient_id: patient identifier
        snapshots: list of HealthSnapshot from HealthIndexBuilder
        regime_result: PatientRegimeResult (or None)
        ana_df: full anadata DataFrame (fallback if patient_ana not provided)
        rec_df: full prescriptions DataFrame (fallback if patient_recs not provided)
        nlp_df: NLP-scored visits DataFrame for this patient (from score_patient_visits)
        patient_ana: pre-filtered ana rows for this patient (avoids N+1 scan)
        patient_recs: pre-filtered prescription rows for this patient (avoids N+1 scan)
    """
    # --- Health score series ---
    scores = [s.health_score for s in snapshots] if snapshots else []
    # Drop NaN values to prevent silent propagation into trend/volatility/CSI
    scores = [s for s in scores if not np.isnan(s)]
    initial_score = scores[0] if scores else 50.0
    final_score = scores[-1] if scores else 50.0
    mean_score = float(np.mean(scores)) if scores else 50.0
    trend = _compute_trend(scores)
    volatility = float(np.std(scores, ddof=1)) if len(scores) > 1 else 0.0
    n_labs = len(snapshots) if snapshots else 0

    # --- Regime features ---
    n_critical, crit_frac = _extract_regime_features(regime_result)

    # --- NLP features ---
    mean_nlp = 0.0
    if nlp_df is not None and not nlp_df.empty and "nlp_composite" in nlp_df.columns:
        mean_nlp = float(nlp_df["nlp_composite"].mean())

    # --- Prescription features (use pre-filtered if available) ---
    if patient_recs is None:
        patient_recs = (
            rec_df[rec_df["patient_id"] == patient_id]
            if rec_df is not None
            else pd.DataFrame()
        )
    n_prescriptions = len(patient_recs)
    if not patient_recs.empty and "date" in patient_recs.columns:
        dates = patient_recs["date"].dropna()
        n_dated = len(dates)  # use only dated rows for velocity to avoid inflation
        if n_dated > 1:
            span_days = (dates.max() - dates.min()).days + 1
            rx_velocity = (n_dated / span_days) * 30.0
        elif n_dated == 1:
            rx_velocity = 1.0 * 30.0  # single dated event → 1 Rx/month equivalent
        else:
            rx_velocity = 0.0
    else:
        rx_velocity = 0.0

    # --- Demographics & comorbidities (use pre-filtered if available) ---
    if patient_ana is None:
        patient_ana = (
            ana_df[ana_df["patient_id"] == patient_id]
            if ana_df is not None
            else pd.DataFrame()
        )
    age = None
    sex = None
    total_care_days = None
    total_visits = None

    if not patient_ana.empty:
        if "age" in patient_ana.columns:
            age_vals = patient_ana["age"].dropna()
            if not age_vals.empty:
                age = float(age_vals.iloc[0])
        if "sex" in patient_ana.columns:
            sex_vals = patient_ana["sex"].dropna()
            if not sex_vals.empty:
                sex = str(sex_vals.iloc[0])
        if "los_days" in patient_ana.columns:
            los_vals = patient_ana["los_days"].dropna()
            if not los_vals.empty:
                total_care_days = float(los_vals.iloc[0])
        if "total_visits" in patient_ana.columns:
            vis_vals = patient_ana["total_visits"].dropna()
            if not vis_vals.empty:
                total_visits = int(vis_vals.iloc[0])

    n_comorbidities = (
        _count_comorbidities(ana_df, patient_id, patient_rows=patient_ana)
        if ana_df is not None
        else 0
    )

    # --- CSI ---
    csi, csi_tier, csi_label, feature_contribs = _compute_csi(
        health_score_trend=trend,
        health_score_volatility=volatility,
        critical_fraction=crit_frac,
        mean_nlp=mean_nlp,
        prescription_velocity=rx_velocity,
        n_comorbidities=n_comorbidities,
    )

    return PatientOutcomeProfile(
        patient_id=patient_id,
        initial_health_score=initial_score,
        final_health_score=final_score,
        mean_health_score=mean_score,
        health_score_trend=trend,
        health_score_volatility=volatility,
        n_lab_draws=n_labs,
        n_critical_episodes=n_critical,
        critical_fraction=crit_frac,
        mean_nlp_composite=mean_nlp,
        n_prescriptions=n_prescriptions,
        prescription_velocity=rx_velocity,
        n_comorbidities=n_comorbidities,
        age=age,
        sex=sex,
        total_care_days=total_care_days,
        total_visits=total_visits,
        csi_score=csi,
        csi_tier=csi_tier,
        csi_label=csi_label,
        feature_contributions=feature_contribs,
    )


def build_all_outcome_profiles(
    all_snapshots: dict,
    regimes: dict,
    ana_df: pd.DataFrame,
    rec_df: pd.DataFrame,
    nlp_results: dict | None = None,
) -> list[PatientOutcomeProfile]:
    """
    Build outcome profiles for all patients.

    Args:
        all_snapshots: {patient_id: list[HealthSnapshot]}
        regimes: {patient_id: PatientRegimeResult}
        ana_df, rec_df: DataFrames from data_loader
        nlp_results: {patient_id: nlp_df} (optional, will recompute if None)
    """
    # nlp_signal.py removed — NLP scoring is now LLM-based and cached offline.
    # If nlp_results is None, we simply return an empty DataFrame.
    _empty_nlp_df = pd.DataFrame(columns=["visit_date", "patient_id", "nlp_composite"])

    # Build row-index maps once; avoids materializing per-patient DataFrame copies.
    ana_group_indices: dict[str, object] = {}
    rec_group_indices: dict[str, object] = {}

    if ana_df is not None and not ana_df.empty and "patient_id" in ana_df.columns:
        ana_group_indices = {
            str(pid): idx
            for pid, idx in ana_df.groupby("patient_id", sort=False).groups.items()
        }
    if rec_df is not None and not rec_df.empty and "patient_id" in rec_df.columns:
        rec_group_indices = {
            str(pid): idx
            for pid, idx in rec_df.groupby("patient_id", sort=False).groups.items()
        }

    empty_ana = ana_df.iloc[0:0] if ana_df is not None else pd.DataFrame()
    empty_rec = rec_df.iloc[0:0] if rec_df is not None else pd.DataFrame()
    empty_nlp = pd.DataFrame(columns=["visit_date", "patient_id", "nlp_composite"])

    profiles = []
    all_pids = set(all_snapshots.keys()) | set(regimes.keys())
    for pid in sorted(all_pids):
        pid_key = str(pid)
        snaps = all_snapshots.get(pid, [])
        regime = regimes.get(pid, None)
        if nlp_results is None:
            nlp_df = _empty_nlp_df
        else:
            nlp_df = nlp_results.get(pid)
            if nlp_df is None:
                nlp_df = nlp_results.get(pid_key, empty_nlp)

        ana_idx = ana_group_indices.get(pid_key)
        rec_idx = rec_group_indices.get(pid_key)

        profile = build_patient_outcome_profile(
            patient_id=pid,
            snapshots=snaps,
            regime_result=regime,
            ana_df=ana_df,
            rec_df=rec_df,
            nlp_df=nlp_df,
            patient_ana=ana_df.iloc[ana_idx] if ana_idx is not None else empty_ana,
            patient_recs=rec_df.iloc[rec_idx] if rec_idx is not None else empty_rec,
        )
        profiles.append(profile)

    return profiles


def profiles_to_dataframe(profiles: list[PatientOutcomeProfile]) -> pd.DataFrame:
    """Convert a list of PatientOutcomeProfile to a flat DataFrame."""
    rows = []
    for p in profiles:
        rows.append(
            {
                "patient_id": p.patient_id,
                "initial_health_score": round(p.initial_health_score, 2),
                "final_health_score": round(p.final_health_score, 2),
                "mean_health_score": round(p.mean_health_score, 2),
                "health_score_trend": round(p.health_score_trend, 4),
                "health_score_volatility": round(p.health_score_volatility, 2),
                "n_lab_draws": p.n_lab_draws,
                "n_critical_episodes": p.n_critical_episodes,
                "critical_fraction": round(p.critical_fraction, 3),
                "mean_nlp_composite": round(p.mean_nlp_composite, 3),
                "n_prescriptions": p.n_prescriptions,
                "prescription_velocity": round(p.prescription_velocity, 2),
                "n_comorbidities": p.n_comorbidities,
                "age": p.age,
                "sex": p.sex,
                "total_care_days": p.total_care_days,
                "total_visits": p.total_visits,
                "csi_score": round(p.csi_score, 1),
                "csi_tier": p.csi_tier,
                "csi_label": p.csi_label,
                # Inverted CSI: 100 = healthy, 0 = critical (same direction as Composite Score)
                # Use this when displaying CSI alongside Composite to avoid directional confusion
                "csi_health_score": round(100.0 - p.csi_score, 1),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Correlation analysis (validation utility)
# ---------------------------------------------------------------------------


def compute_feature_correlations(
    df: pd.DataFrame,
    target: str = "total_visits",
) -> pd.DataFrame:
    """
    Compute Spearman rank correlation of all numeric features vs the target.
    Returns a DataFrame sorted by |correlation|.
    """
    numeric_features = [
        "initial_health_score",
        "final_health_score",
        "mean_health_score",
        "health_score_trend",
        "health_score_volatility",
        "n_lab_draws",
        "n_critical_episodes",
        "critical_fraction",
        "mean_nlp_composite",
        "n_prescriptions",
        "prescription_velocity",
        "n_comorbidities",
        "csi_score",
    ]
    valid_df = df.dropna(subset=[target])
    if len(valid_df) < 5:  # was < 3; Spearman on n<5 yields unreliable p-values
        return pd.DataFrame(
            columns=["feature", "spearman_r", "p_value", "interpretation"]
        )

    results = []
    for feat in numeric_features:
        if feat not in valid_df.columns:
            continue
        feat_vals = pd.to_numeric(valid_df[feat], errors="coerce")
        target_vals = pd.to_numeric(valid_df[target], errors="coerce")
        mask = feat_vals.notna() & target_vals.notna()
        if mask.sum() < 5:  # was < 3; need ≥5 for non-degenerate Spearman ranking
            continue
        r, p = spearmanr(feat_vals[mask], target_vals[mask])
        direction = (
            "Higher → more utilization" if r > 0 else "Higher → less utilization"
        )
        strength = (
            "Strong" if abs(r) >= 0.7 else "Moderate" if abs(r) >= 0.4 else "Weak"
        )
        results.append(
            {
                "feature": feat,
                "spearman_r": round(float(r), 3),
                "p_value": round(float(p), 3),
                "interpretation": f"{strength} ({direction})",
            }
        )

    result_df = pd.DataFrame(results)
    if not result_df.empty:
        result_df = result_df.reindex(
            result_df["spearman_r"].abs().sort_values(ascending=False).index
        ).reset_index(drop=True)
    return result_df


# ---------------------------------------------------------------------------
# LOS / care duration prediction narrative
# ---------------------------------------------------------------------------


def predict_care_duration_narrative(profile: PatientOutcomeProfile) -> str:
    """
    Generate a clinical narrative for the predicted care burden of this patient.
    Rule-based interpretation of the CSI score and dominant features.
    """
    lines = [
        f"Patient {profile.patient_id} — Clinical Severity Index: {profile.csi_score:.0f}/100 ({profile.csi_tier})"
    ]

    # Dominant features
    if profile.feature_contributions:
        dominant = max(profile.feature_contributions.items(), key=lambda x: x[1])
        lines.append(
            f"Dominant risk factor: {dominant[0].replace('_', ' ').title()} (contributing {dominant[1]:.1f} points)"
        )

    if profile.health_score_trend < -1.0:
        lines.append(
            f"Health score declining at {abs(profile.health_score_trend):.1f} points/visit — active deterioration."
        )
    elif profile.health_score_trend > 1.0:
        lines.append(
            f"Health score improving at {profile.health_score_trend:.1f} points/visit — positive trajectory."
        )
    else:
        lines.append("Health score trend: stable.")

    if profile.critical_fraction > 0.3:
        lines.append(
            f"{profile.critical_fraction * 100:.0f}% of observations in Critical state — significant instability burden."
        )

    if profile.n_comorbidities >= 3:
        lines.append(
            f"{profile.n_comorbidities} comorbidities detected — complex multimorbidity profile."
        )

    if profile.prescription_velocity > 5:
        lines.append(
            f"High prescription intensity ({profile.prescription_velocity:.1f} Rx/month) — active pharmacological management."
        )

    if profile.total_visits is not None:
        lines.append(f"Actual total visits on record: {profile.total_visits}")

    if profile.total_care_days is not None:
        lines.append(
            f"Total care span: {profile.total_care_days:.0f} days ({profile.total_care_days / 365:.1f} years)"
        )

    return "\n".join(lines)


def predict_eci_narrative(
    eci_data: dict, profile: PatientOutcomeProfile | None = None
) -> str:
    """
    Generate a clinical narrative for the Expected Cost Intensity (ECI) of a patient.
    Rule-based interpretation of the ECI score and its 4 percentile-ranked components.
    """
    pid = eci_data.get("patient_id", "Unknown")
    score = eci_data.get("eci_score")
    rating = eci_data.get("eci_rating", "N/A")
    label = eci_data.get("eci_rating_label", "")

    if score is None:
        return f"Patient {pid} — ECI data not available."

    lines = [f"Patient {pid} — Expected Cost Intensity: {score:.0f}/100 ({rating})"]
    if label:
        lines[0] += f" — {label}"

    # Component breakdown
    components = [
        ("Visit Intensity", eci_data.get("visit_intensity")),
        ("Medication Burden", eci_data.get("med_burden")),
        ("Diagnostic Intensity", eci_data.get("diagnostic_intensity")),
        ("Clinical Trajectory", eci_data.get("trajectory_cost")),
    ]

    # Find dominant component
    scored = [(name, val) for name, val in components if val is not None]
    if scored:
        dominant = max(scored, key=lambda x: x[1])
        lines.append(
            f"Dominant cost driver: {dominant[0]} (percentile score {dominant[1]:.0f}/100)"
        )

    # Interpret each component
    for name, val in components:
        if val is None:
            continue
        if val >= 75:
            level = "very high"
        elif val >= 50:
            level = "elevated"
        elif val >= 25:
            level = "moderate"
        else:
            level = "low"
        lines.append(f"{name}: {val:.0f}/100 ({level} relative to cohort)")

    # Add profile context if available
    if profile is not None:
        if profile.total_visits is not None:
            lines.append(f"Total visits on record: {profile.total_visits}")
        if profile.total_care_days is not None:
            lines.append(
                f"Total care span: {profile.total_care_days:.0f} days ({profile.total_care_days / 365:.1f} years)"
            )

    return "\n".join(lines)
