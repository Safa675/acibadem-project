"""
fusion.py
Composite Risk Score — fuses lab/vital health index and NLP signal.

Weights (evidence-based — see FUSION_WEIGHTS_EVIDENCE.md for full citations):
  70% HealthIndex (lab + vital regime component)
      - Labs + vitals are consistently the dominant modality in clinical prediction
        models (NEWS AUROC 0.867, eCART superior to MEWS across 5 hospitals).
        Rajkomar et al. 2018 (PMID: 31304302): structured data is the primary
        contributor in deep learning EHR models (AUROC 0.93–0.94 for mortality).
  30% NLP clinical signal
      - Multimodal hybrid fusion models show NLP adds +1–5% AUROC over structured
        data alone (Garriga et al. PMID: 37913776; JMIR 2024 e54363). Feature
        importance analyses consistently attribute 20–35% of predictive information
        to clinical notes when combined with structured data. Captures clinical
        reasoning, subjective assessments, and context absent from structured fields.

Medication change velocity is retained as a computed field for informational
purposes but no longer contributes to the composite score (weight = 0).

Output: CompositeRiskScore ∈ [0, 100]
  100 = lowest risk (healthy, positive notes)
  0   = highest risk

This is the final "credit rating" per patient — the clinically communicable output.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


WEIGHTS = {
    "health_index": 0.70,
    "nlp": 0.30,
    "med_changes": 0.00,
}

# Redistributed weights when NLP is skipped (ILAY_SKIP_NLP=1).
# When NLP is unavailable, 100% weight goes to health index.
WEIGHTS_NO_NLP = {
    "health_index": 1.0,
    "nlp": 0.0,
    "med_changes": 0.0,
}

# Risk tier boundaries for composite score
COMPOSITE_TIERS = [
    (85, "AAA", "Excellent — stable health, positive prognosis"),
    (70, "AA", "Good — minor abnormalities, low risk"),
    (55, "A", "Moderate — monitoring recommended"),
    (40, "BBB", "Below average — clinical review needed"),
    (25, "BB", "Elevated risk — active intervention recommended"),
    (0, "B/CCC", "High risk — urgent clinical attention"),
]


@dataclass
class CompositeRiskScore:
    patient_id: str
    composite_score: float  # [0, 100]
    health_index_score: float  # [0, 100]
    nlp_score_normalized: float  # [0, 100] (from [-1, +1])
    med_change_score: float  # [0, 100]
    rating: str  # AAA / AA / A / BBB / BB / B/CCC
    rating_label: str
    # Component weights used
    weights_used: dict


def _nlp_to_0_100(nlp_score: float) -> float:
    """Convert NLP score from [-1, +1] to [0, 100].

    Applies 2x stretch so the typical clinical range [-0.5, +0.5]
    fills more of [0, 100] instead of being crushed to [25, 75].
    """
    stretched = nlp_score * 2.0  # [-0.5, +0.5] → [-1, +1]
    return float(np.clip((stretched + 1.0) / 2.0 * 100.0, 0, 100))


def _med_change_velocity_score(
    rec_df: pd.DataFrame,
    patient_id: str,
    *,
    patient_recs: pd.DataFrame | None = None,
) -> float:
    """
    Compute medication change velocity score.
    HIGH velocity (many new prescriptions in short window) → LOW score (bad).
    LOW velocity → HIGH score (stable).

    Score [0, 100]: 100 = no changes in the period, 0 = very high change rate.

    Args:
        rec_df: full prescriptions DataFrame (fallback if patient_recs not provided)
        patient_id: patient identifier
        patient_recs: pre-filtered prescription rows (avoids O(N) scan)
    """
    if patient_recs is None:
        patient_recs = rec_df[rec_df["patient_id"] == patient_id].copy()
    if patient_recs.empty:
        return 80.0  # default: no data → assume moderate stability

    # Use unique drug count as complexity proxy (not total rows, which
    # double-counts routine refills of standing prescriptions)
    n_unique_drugs = (
        patient_recs["drug_name"].nunique()
        if "drug_name" in patient_recs.columns
        else len(patient_recs)
    )
    if "date" not in patient_recs.columns:
        return 80.0  # no date column — assume moderate stability
    date_span = (patient_recs["date"].max() - patient_recs["date"].min()).days + 1

    if date_span <= 1:
        # Single-day: all prescriptions on one visit.
        # 1-3 unique drugs = routine refill, 5+ = escalation
        score = max(10.0, 100.0 - n_unique_drugs * 12.0)
        return float(np.clip(score, 0, 100))

    # Multi-day: unique drugs per month of observation
    changes_per_month = (n_unique_drugs / date_span) * 30.0

    # Map: 0 changes/month → 100, 10+ changes/month → 10
    score = max(10.0, 100.0 - changes_per_month * 9.0)
    return float(np.clip(score, 0, 100))


def _assign_rating(composite_score: float) -> tuple[str, str]:
    for threshold, rating, label in COMPOSITE_TIERS:
        if composite_score >= threshold:
            return rating, label
    # Should never be reached since COMPOSITE_TIERS covers score >= 0
    # and scores are clipped to [0, 100] before calling this function.
    return COMPOSITE_TIERS[-1][1], COMPOSITE_TIERS[-1][2]


def compute_composite_score(
    patient_id: str,
    health_score: float,  # [0, 100] from HealthIndexBuilder
    nlp_composite: float,  # [-1, +1] from NLPSignal
    rec_df: pd.DataFrame,
    ana_df: pd.DataFrame,
    weights: dict | None = None,
    *,
    patient_recs: pd.DataFrame | None = None,
) -> CompositeRiskScore:
    """
    Fuse all signals into a composite risk score.

    Args:
        patient_id: patient identifier
        health_score: most recent or mean health score [0, 100]
        nlp_composite: NLP signal for this visit [-1, +1]
        rec_df: prescriptions DataFrame (from load_recete)
        ana_df: patient visits DataFrame (from load_anadata)
        weights: optional weight override dict
        patient_recs: pre-filtered prescription rows (avoids O(N) scan)

    Returns:
        CompositeRiskScore
    """
    w = {**WEIGHTS, **(weights or {})}
    if abs(sum(w.values()) - 1.0) > 1e-6:
        raise ValueError(f"Weights must sum to 1.0, got {sum(w.values()):.4f}")
    if not w.keys() >= WEIGHTS.keys():
        missing = WEIGHTS.keys() - w.keys()
        raise KeyError(f"Missing weight keys: {missing}")

    nlp_norm = _nlp_to_0_100(nlp_composite)
    med_score = _med_change_velocity_score(
        rec_df, patient_id, patient_recs=patient_recs
    )

    composite = (
        w["health_index"] * health_score
        + w["nlp"] * nlp_norm
        + w["med_changes"] * med_score
    )
    composite = float(np.clip(composite, 0, 100))

    rating, label = _assign_rating(composite)

    return CompositeRiskScore(
        patient_id=patient_id,
        composite_score=round(composite, 2),
        health_index_score=round(health_score, 2),
        nlp_score_normalized=round(nlp_norm, 2),
        med_change_score=round(med_score, 2),
        rating=rating,
        rating_label=label,
        weights_used=w,
    )


def compute_all_composites(
    health_scores: dict[str, float],  # {patient_id: health_score}
    nlp_scores: dict[str, float],  # {patient_id: nlp_composite}
    rec_df: pd.DataFrame,
    ana_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute composite scores for all patients. Returns ranked DataFrame.

    Uses **per-patient** NLP weight selection:
    - Patients with a real NLP score (non-zero) use full weights (70/30).
    - Patients without NLP data (score == 0.0) use 100% health index
      so NLP's missing contribution doesn't drag scores toward 50.
    """
    import logging

    _log = logging.getLogger(__name__)

    # Count how many patients have real NLP scores
    n_with_nlp = sum(1 for v in nlp_scores.values() if v != 0.0) if nlp_scores else 0
    n_total = len(health_scores)
    _log.info(
        "Fusion: %d/%d patients have real NLP scores (%.1f%% coverage)",
        n_with_nlp,
        n_total,
        (n_with_nlp / n_total * 100) if n_total else 0,
    )

    # Build index map once to avoid materializing per-patient DataFrame copies.
    rec_group_indices: dict[str, np.ndarray] = {}
    if not rec_df.empty and "patient_id" in rec_df.columns:
        rec_group_indices = {
            str(pid): idx
            for pid, idx in rec_df.groupby("patient_id", sort=False).groups.items()
        }
    empty_rec = rec_df.iloc[0:0]

    rows = []
    for pid in health_scores:
        h = health_scores[pid]
        n = nlp_scores.get(pid, 0.0)
        # Per-patient weight selection: real NLP → full weights, missing → redistributed
        weights = None if n != 0.0 else WEIGHTS_NO_NLP
        rec_idx = rec_group_indices.get(str(pid))
        patient_recs = rec_df.iloc[rec_idx] if rec_idx is not None else empty_rec
        result = compute_composite_score(
            pid,
            h,
            n,
            rec_df,
            ana_df,
            weights=weights,
            patient_recs=patient_recs,
        )
        rows.append(
            {
                "patient_id": pid,
                "composite_score": result.composite_score,
                "health_index_score": result.health_index_score,
                "nlp_score": result.nlp_score_normalized,
                "med_change_score": result.med_change_score,
                "rating": result.rating,
                "rating_label": result.rating_label,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values("composite_score", ascending=False)
        .reset_index(drop=True)
    )
