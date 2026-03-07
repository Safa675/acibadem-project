"""
nlp_llm.py
LLM-based Turkish clinical NLP scoring via OpenRouter API.

Replaces the broken zero-shot transformer with an LLM (Gemini Flash)
that actually understands Turkish clinical text. Produces the same
[-1.0, +1.0] score contract as the transformer pipeline.

Scores each clinical text on a spectrum from:
  -1.0  = strong clinical deterioration
   0.0  = neutral / stable
  +1.0  = strong clinical recovery

Design:
  - Batches 20 texts per API call (fits ~2K tokens prompt)
  - 10 concurrent requests for throughput
  - JSON-mode response for reliable parsing
  - Retry with exponential backoff on failures
  - Falls back to 0.0 for any text that can't be scored
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx
import pandas as pd

logger = logging.getLogger("ilay.nlp_llm")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "google/gemini-2.0-flash-001"
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Tuning knobs (overridable via env vars)
BATCH_SIZE = int(os.getenv("ILAY_NLP_BATCH_SIZE", "20"))
CONCURRENCY = int(os.getenv("ILAY_NLP_CONCURRENCY", "10"))
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds, doubles each retry

# Text columns to score — equal weights (no evidence to differentiate)
TEXT_COLUMNS = ["ÖYKÜ", "YAKINMA", "Muayene Notu", "Kontrol Notu", "Tedavi Notu"]
COLUMN_WEIGHTS = {
    "ÖYKÜ": 0.20,
    "YAKINMA": 0.20,
    "Muayene Notu": 0.20,
    "Kontrol Notu": 0.20,
    "Tedavi Notu": 0.20,
}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a Turkish clinical NLP scorer for a hospital analytics system.

Your task: For each Turkish clinical text, assign a score from -1.0 to +1.0 indicating the patient's clinical trajectory:

  -1.0 = strong deterioration (critical symptoms, organ failure, emergency, worsening condition)
  -0.5 = moderate deterioration (new symptoms, concerning findings, disease progression)
  -0.2 = mild concern (minor symptoms, suboptimal but not alarming)
   0.0 = neutral/stable (routine follow-up, no change, maintenance visit)
  +0.2 = mild improvement (symptoms reducing, stable after treatment)
  +0.5 = moderate recovery (clear improvement, responding well to treatment)
  +1.0 = strong recovery (resolved, normal findings, discharge-ready, healthy)

Important clinical context:
- "TA yüksek" (high blood pressure), "ateş" (fever), "dispne" (dyspnea) = deterioration
- "ral" (crackles), "ronküs" (rhonchi), "ödem" (edema) = deterioration
- "olağan" (normal), "temiz" (clear), "yok" (absent) when describing symptoms = recovery/stable
- Short medication lists alone without symptoms = neutral (0.0)
- "kontrol" / "izlem" (follow-up/monitoring) without complaints = neutral to mild positive
- ICD codes or procedure mentions alone = neutral unless context suggests severity

Respond with ONLY a JSON array of objects. One object per text, in order.
Format: [{"score": <float>}, {"score": <float>}, ...]
No explanation, no markdown fences, just the raw JSON array."""


def _build_batch_prompt(texts: list[str]) -> str:
    """Build the user message for a batch of texts."""
    lines = [f"Score these {len(texts)} clinical texts:\n"]
    for i, text in enumerate(texts):
        # Truncate to 400 chars to keep token count reasonable
        truncated = text[:400].strip()
        lines.append(f"{i + 1}. {truncated}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call with retry
# ---------------------------------------------------------------------------


def _get_api_key() -> str | None:
    """Get OpenRouter API key from environment."""
    try:
        from dotenv import load_dotenv
        from pathlib import Path

        load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
    except ImportError:
        pass
    return os.environ.get("OPENROUTER_API_KEY", "").strip() or None


async def _call_llm_batch(
    client: httpx.AsyncClient,
    texts: list[str],
    api_key: str,
    model: str,
    semaphore: asyncio.Semaphore,
) -> list[float]:
    """
    Score a batch of texts via LLM API. Returns list of floats [-1, +1].
    On failure after retries, returns 0.0 for all texts.
    """
    n = len(texts)
    prompt = _build_batch_prompt(texts)

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max(n * 30, 200),  # ~30 tokens per score entry
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ilay.app",
        "X-Title": "ILAY-NLP",
    }

    for attempt in range(MAX_RETRIES):
        try:
            async with semaphore:
                resp = await client.post(
                    _OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )

            if resp.status_code == 429:
                delay = RETRY_BASE_DELAY * (2**attempt)
                logger.warning("Rate limited (429), backing off %.1fs", delay)
                await asyncio.sleep(delay)
                continue

            if resp.status_code != 200:
                logger.warning(
                    "LLM API error %d (attempt %d/%d): %s",
                    resp.status_code,
                    attempt + 1,
                    MAX_RETRIES,
                    resp.text[:200],
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))
                continue

            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Parse JSON — handle markdown fences if present
            clean = content.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            scores_raw = json.loads(clean)
            scores = []
            for item in scores_raw:
                if isinstance(item, dict):
                    s = float(item.get("score", 0.0))
                elif isinstance(item, (int, float)):
                    s = float(item)
                else:
                    s = 0.0
                scores.append(max(-1.0, min(1.0, s)))

            # Verify count matches
            if len(scores) != n:
                logger.warning(
                    "Score count mismatch: expected %d, got %d. Padding/truncating.",
                    n,
                    len(scores),
                )
                if len(scores) < n:
                    scores.extend([0.0] * (n - len(scores)))
                else:
                    scores = scores[:n]

            return scores

        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            logger.warning(
                "JSON parse error (attempt %d/%d): %s. Response: %s",
                attempt + 1,
                MAX_RETRIES,
                exc,
                content[:200] if "content" in dir() else "N/A",
            )
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY)
            continue
        except httpx.TimeoutException:
            logger.warning("Timeout (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_BASE_DELAY * (2**attempt))
            continue
        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
            break

    # All retries exhausted — return neutral scores
    logger.error("All %d retries failed for batch of %d texts", MAX_RETRIES, n)
    return [0.0] * n


# ---------------------------------------------------------------------------
# Batch orchestration
# ---------------------------------------------------------------------------


async def _score_texts_async(
    texts: list[str],
    api_key: str,
    model: str = _DEFAULT_MODEL,
    batch_size: int = BATCH_SIZE,
    concurrency: int = CONCURRENCY,
) -> list[float]:
    """
    Score all texts using concurrent LLM API calls.
    Returns list of floats, same length as input.
    """
    n = len(texts)
    if n == 0:
        return []

    # Split into batches
    batches = [texts[i : i + batch_size] for i in range(0, n, batch_size)]

    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient() as client:
        # Schedule ALL batches as concurrent tasks (semaphore gates to `concurrency`)
        async_tasks = [
            asyncio.create_task(
                _call_llm_batch(client, batch, api_key, model, semaphore)
            )
            for batch in batches
        ]
        # Run all concurrently — semaphore limits active requests
        gathered = await asyncio.gather(*async_tasks)

    # Flatten
    flat = []
    for r in gathered:
        flat.extend(r)

    return flat[:n]  # safety trim


def score_texts_sync(
    texts: list[str],
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> list[float]:
    """
    Synchronous wrapper for async scoring.
    Returns list of floats [-1.0, +1.0], same length as input.
    """
    if api_key is None:
        api_key = _get_api_key()
    if not api_key:
        logger.error("No OPENROUTER_API_KEY available — returning all 0.0")
        return [0.0] * len(texts)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_score_texts_async(texts, api_key, model))
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Patient-level scoring (same contract as nlp_signal.score_all_patients_batched)
# ---------------------------------------------------------------------------


def score_all_patients_llm(
    ana_df: pd.DataFrame,
    patient_ids: list[str] | None = None,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> tuple[pd.DataFrame, dict[str, list[dict]]]:
    """
    Score clinical texts for patients using LLM API.

    Args:
        ana_df: Visit DataFrame with text columns
        patient_ids: Optional subset of patient IDs to score. If None, scores all.
        api_key: OpenRouter API key (auto-detected from env if None)
        model: LLM model ID

    Returns:
        nlp_results_df:   DataFrame with [patient_id, visit_date, nlp_composite]
        nli_scores_cache:  dict[patient_id -> list of {date, source, nli_score}]

    Same output contract as nlp_signal.score_all_patients_batched().
    """
    if api_key is None:
        api_key = _get_api_key()
    if not api_key:
        logger.error("No OPENROUTER_API_KEY — returning empty NLP results")
        return pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"]), {}

    available_cols = [c for c in TEXT_COLUMNS if c in ana_df.columns]
    if not available_cols:
        logger.warning("No text columns found in ana_df")
        return pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"]), {}

    total_weight = sum(COLUMN_WEIGHTS.get(c, 0.1) for c in available_cols)

    # Filter to requested patients
    if patient_ids is not None:
        pid_set = set(str(p) for p in patient_ids)
        work_df = ana_df[ana_df["patient_id"].isin(pid_set)].copy()
    else:
        work_df = ana_df

    if work_df.empty:
        return pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"]), {}

    all_pids = [str(p) for p in work_df["patient_id"].unique()]
    logger.info(
        "LLM NLP: scoring %d patients, %d visits, %d text columns",
        len(all_pids),
        len(work_df),
        len(available_cols),
    )

    # ── Collect all (row_index, col, text) tuples ──
    text_entries: list[
        tuple[int, str, str, str, str]
    ] = []  # (row_idx, pid, date, col, text)
    all_texts: list[str] = []

    t0 = time.time()
    for row in work_df.to_dict(orient="records"):
        pid = str(row["patient_id"])
        vdate = row.get("visit_date", None)
        vdate_str = (
            pd.Timestamp(vdate).strftime("%Y-%m-%d")
            if vdate is not None and not (isinstance(vdate, float) and pd.isna(vdate))
            else "—"
        )
        for col in available_cols:
            txt = row.get(col, None)
            if isinstance(txt, str) and txt.strip() and len(txt.strip()) > 2:
                text_entries.append((0, pid, vdate_str, col, txt[:400]))
                all_texts.append(txt[:400])

    logger.info(
        "Collected %d texts from %d visits in %.1fs",
        len(all_texts),
        len(work_df),
        time.time() - t0,
    )

    if not all_texts:
        logger.warning("No non-empty texts found")
        empty_df = pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"])
        empty_cache: dict[str, list[dict]] = {pid: [] for pid in all_pids}
        return empty_df, empty_cache

    # ── Score all texts via LLM ──
    t1 = time.time()
    all_scores = score_texts_sync(all_texts, api_key, model)
    logger.info(
        "LLM scored %d texts in %.1fs (%.1f texts/sec)",
        len(all_scores),
        time.time() - t1,
        len(all_scores) / max(0.1, time.time() - t1),
    )

    # ── Map scores back to (pid, date, col) ──
    score_map: dict[tuple[str, str, str], float] = {}
    nli_scores_cache: dict[str, list[dict]] = {}

    for (_, pid, vdate_str, col, _txt), score in zip(text_entries, all_scores):
        score_val = float(score)
        score_map[(pid, vdate_str, col)] = score_val

        nli_scores_cache.setdefault(pid, [])
        nli_scores_cache[pid].append(
            {
                "date": vdate_str,
                "source": col,
                "nli_score": round(score_val, 3),
                "text": _txt[:200],  # excerpt for review
            }
        )

    # ── Compute per-visit composite scores ──
    result_rows: list[dict] = []
    for row in work_df.to_dict(orient="records"):
        pid = str(row["patient_id"])
        vdate = row.get("visit_date", None)
        vdate_str = (
            pd.Timestamp(vdate).strftime("%Y-%m-%d")
            if vdate is not None and not (isinstance(vdate, float) and pd.isna(vdate))
            else "—"
        )
        composite = 0.0
        for col in available_cols:
            w = COLUMN_WEIGHTS.get(col, 0.1) / total_weight
            s = score_map.get((pid, vdate_str, col), 0.0)
            composite += s * w
        composite = max(-1.0, min(1.0, composite))
        result_rows.append(
            {
                "patient_id": pid,
                "visit_date": vdate_str,
                "nlp_composite": round(composite, 4),
            }
        )
        nli_scores_cache.setdefault(pid, [])

    # Ensure all patients have cache entries
    for pid in all_pids:
        nli_scores_cache.setdefault(pid, [])

    nlp_results_df = (
        pd.DataFrame(result_rows)
        if result_rows
        else pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"])
    )

    total_time = time.time() - t0
    logger.info(
        "LLM NLP complete: %d patients, %d texts scored, %d result rows in %.1fs",
        len(all_pids),
        len(all_texts),
        len(nlp_results_df),
        total_time,
    )

    return nlp_results_df, nli_scores_cache
