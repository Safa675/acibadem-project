"""
nlp_signal.py
Turkish clinical NLP scoring via zero-shot transformer classification.

Scores each patient visit's free-text notes on a spectrum from
-1.0 (strong deterioration language) to +1.0 (strong recovery language).

Scoring method:
  Zero-shot NLI classification using
  MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli (multilingual NLI model).
  Classifies clinical text into deterioration/recovery/neutral without
  task-specific fine-tuning. Works on clinical language because it reasons
  about textual entailment, not emotional sentiment.

Install transformer support:
    pip install transformers torch sentencepiece
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transformer model — lazy-loaded on first use
# ---------------------------------------------------------------------------

# Zero-shot NLI model — reasons about textual meaning, not emotional sentiment.
# Works on clinical Turkish because NLI evaluates entailment, not review polarity.
_TRANSFORMER_MODEL_ID = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"

# Clinical hypothesis templates for zero-shot classification
_CANDIDATE_LABELS = ["kötüleşme", "iyileşme", "nötr"]
_HYPOTHESIS_TEMPLATE = "Bu klinik metin {} ile ilgilidir."

_transformer_pipeline = None  # cached after first load
_transformer_available: Optional[bool] = None  # None = not yet checked


def _load_transformer() -> bool:
    """
    Attempt to load the zero-shot NLI pipeline. Returns True on success.
    Safe to call multiple times — loads only once and caches.
    """
    global _transformer_pipeline, _transformer_available  # noqa: PLW0603

    if _transformer_available is not None:
        return _transformer_available

    try:
        from transformers import pipeline as hf_pipeline  # noqa: PLC0415

        _transformer_pipeline = hf_pipeline(
            "zero-shot-classification",
            model=_TRANSFORMER_MODEL_ID,
        )
        _transformer_available = True
        logger.info("Zero-shot NLI NLP loaded: %s", _TRANSFORMER_MODEL_ID)
    except Exception as exc:  # noqa: BLE001
        _transformer_available = False
        logger.warning("Transformer NLP not available (%s). NLP scoring disabled.", exc)

    return _transformer_available


def reset_transformer_cache() -> None:
    """Reset the cached transformer state, allowing a fresh load attempt.
    Useful when the previous attempt failed due to a transient network error.
    """
    global _transformer_pipeline, _transformer_available  # noqa: PLW0603
    _transformer_pipeline = None
    _transformer_available = None


# Label mapping from zero-shot output → [-1, 0, +1]
_LABEL_TO_SCORE: dict[str, float] = {
    "kötüleşme": -1.0,  # deterioration
    "iyileşme": 1.0,  # recovery
    "nötr": 0.0,  # neutral
}


def transformer_nlp_score(text: str) -> Optional[float]:
    """
    Score text using zero-shot NLI classification.
    Returns float ∈ [-1.0, +1.0] or None if transformer is unavailable / text empty.

    The model evaluates: "Does this clinical text entail deterioration / recovery / neutral?"
    Unlike sentiment models trained on product reviews, NLI models reason about
    textual meaning — so "ateş, burun tıkanıklığı" correctly maps to deterioration.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if not _load_transformer():
        return None
    try:
        result = _transformer_pipeline(
            text[:512],
            candidate_labels=_CANDIDATE_LABELS,
            hypothesis_template=_HYPOTHESIS_TEMPLATE,
        )
        # result: {"labels": [...], "scores": [...]}
        top_label = result["labels"][0]
        top_score = result["scores"][0]
        base_score = _LABEL_TO_SCORE.get(top_label, 0.0)
        # Scale by confidence so uncertain predictions are dampened toward 0
        return float(base_score * top_score)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Transformer inference failed: %s", exc)
        return None


def clinical_nlp_score(text: str) -> float:
    """
    Public API — score a single text string using the transformer.
    Returns 0.0 if the transformer is unavailable.
    """
    score = transformer_nlp_score(text)
    return score if score is not None else 0.0


def dual_nlp_score(text: str) -> dict:
    """
    Score text using the transformer NLP.

    Returns a dict with:
      {
        "rule_based":   None (deprecated — rule-based NLP has been removed),
        "transformer":  float ∈ [-1, +1] or None if unavailable,
        "agreement":    True (always — single-method, no disagreement possible),
        "combined":     float — transformer score, or 0.0 if unavailable,
      }

    NOTE: The "rule_based" key is retained as None for backward compatibility
    with downstream consumers that reference this key. The "agreement" key is
    always True since there is only one scoring method.
    """
    tr = transformer_nlp_score(text)

    return {
        "rule_based": None,
        "transformer": tr,
        "agreement": True,
        "combined": float(tr) if tr is not None else 0.0,
    }


# Columns to score in anadata
TEXT_COLUMNS: list[str] = [
    "ÖYKÜ",
    "YAKINMA",
    "Muayene Notu",
    "Kontrol Notu",
    "Tedavi Notu",
]

# Column weights for composite score
COLUMN_WEIGHTS: dict[str, float] = {
    "ÖYKÜ": 0.35,  # Most detailed — patient history
    "Muayene Notu": 0.30,  # Physical exam
    "Kontrol Notu": 0.20,  # Follow-up notes
    "YAKINMA": 0.10,  # Chief complaint (short)
    "Tedavi Notu": 0.05,  # Treatment note
}


# ---------------------------------------------------------------------------
# Patient-level scoring
# ---------------------------------------------------------------------------


def score_patient_visits(
    ana_df: pd.DataFrame,
    patient_id: int,
) -> pd.DataFrame:
    """
    Score all text fields for a patient across all visits using the transformer.

    Returns a DataFrame with columns:
      visit_date, nlp_<col>, nlp_composite
    """
    mask = ana_df["patient_id"] == patient_id
    rows = ana_df[mask].copy()

    if rows.empty:
        return pd.DataFrame(columns=["visit_date", "patient_id", "nlp_composite"])

    available_cols = [c for c in TEXT_COLUMNS if c in rows.columns]

    # Score each column using transformer (falls back to 0.0 if unavailable)
    for col in available_cols:
        rows[f"nlp_{col}"] = rows[col].apply(clinical_nlp_score)

    # Weighted composite score
    total_weight = sum(COLUMN_WEIGHTS.get(c, 0.1) for c in available_cols)
    composite = pd.Series(0.0, index=rows.index)
    for col in available_cols:
        w = COLUMN_WEIGHTS.get(col, 0.1) / total_weight
        composite += rows[f"nlp_{col}"] * w

    rows["nlp_composite"] = composite.clip(-1.0, 1.0)

    result_cols = (
        ["visit_date", "patient_id"]
        + [f"nlp_{c}" for c in available_cols]
        + ["nlp_composite"]
    )
    return (
        rows[[c for c in result_cols if c in rows.columns]]
        .sort_values("visit_date")
        .reset_index(drop=True)
    )


def score_all_patients(ana_df: pd.DataFrame) -> pd.DataFrame:
    """Score all patients and return a combined DataFrame."""
    results = []
    for pid in ana_df["patient_id"].dropna().unique():
        scored = score_patient_visits(ana_df, int(pid))
        results.append(scored)
    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)
