#!/usr/bin/env python3
"""
run_nlp_scoring.py
Score clinical texts via LLM and cache results to .cache/ for the app to use.

Usage:
  python run_nlp_scoring.py                  # Score all patients
  python run_nlp_scoring.py --limit 100      # Score first 100 patients
  python run_nlp_scoring.py --resume         # Resume from where we left off
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nlp_scorer")

CACHE_DIR = _ROOT / ".cache"
NLP_RESULTS_PATH = CACHE_DIR / "nlp_results.parquet"
NLI_CACHE_PATH = CACHE_DIR / "nli_scores_cache.json"


def main():
    parser = argparse.ArgumentParser(description="LLM-based NLP scoring")
    parser.add_argument(
        "--limit", type=int, default=None, help="Score only first N patients"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Skip already-scored patients"
    )
    args = parser.parse_args()

    # Load data
    logger.info("Loading data...")
    from src.data_loader import load_all_data

    data = load_all_data(str(_ROOT))
    ana_df = data["ana"]
    all_pids = sorted(ana_df["patient_id"].dropna().unique().tolist())
    all_pids = [str(p) for p in all_pids]
    logger.info("Total patients in ana_df: %d", len(all_pids))

    # Resume: skip already-scored patients
    scored_pids: set[str] = set()
    existing_df = pd.DataFrame()
    existing_cache: dict[str, list[dict]] = {}

    if args.resume and NLP_RESULTS_PATH.exists():
        existing_df = pd.read_parquet(NLP_RESULTS_PATH)
        scored_pids = set(existing_df["patient_id"].unique().tolist())
        logger.info("Resuming: %d patients already scored", len(scored_pids))

        if NLI_CACHE_PATH.exists():
            with open(NLI_CACHE_PATH, "r") as f:
                existing_cache = json.load(f)

    # Filter to unscored patients
    target_pids = [p for p in all_pids if p not in scored_pids]

    if args.limit is not None:
        target_pids = target_pids[: args.limit]

    if not target_pids:
        logger.info("No patients to score. Done.")
        return

    logger.info("Scoring %d patients...", len(target_pids))

    # Score
    from src.nlp_llm import score_all_patients_llm

    t0 = time.time()
    nlp_df, nli_cache = score_all_patients_llm(ana_df, patient_ids=target_pids)
    elapsed = time.time() - t0

    logger.info(
        "Scored %d patients (%d texts) in %.1fs",
        len(target_pids),
        len(nlp_df),
        elapsed,
    )

    # Merge with existing results
    if not existing_df.empty:
        nlp_df = pd.concat([existing_df, nlp_df], ignore_index=True)
        nli_cache = {**existing_cache, **nli_cache}

    # Save to cache
    CACHE_DIR.mkdir(exist_ok=True)
    nlp_df.to_parquet(NLP_RESULTS_PATH, index=False)
    with open(NLI_CACHE_PATH, "w") as f:
        json.dump(nli_cache, f)

    logger.info("Saved to %s (%d rows)", NLP_RESULTS_PATH, len(nlp_df))
    logger.info("Saved to %s (%d patients)", NLI_CACHE_PATH, len(nli_cache))

    # Print summary statistics
    if not nlp_df.empty:
        scores = nlp_df["nlp_composite"]
        print("\n" + "=" * 60)
        print(f"NLP SCORING SUMMARY")
        print(f"=" * 60)
        print(f"Patients scored:  {nlp_df['patient_id'].nunique():,}")
        print(f"Visit rows:       {len(nlp_df):,}")
        print(f"Time elapsed:     {elapsed:.1f}s")
        print(f"")
        print(f"Score distribution (nlp_composite):")
        print(f"  Min:    {scores.min():+.3f}")
        print(f"  25th:   {scores.quantile(0.25):+.3f}")
        print(f"  Median: {scores.median():+.3f}")
        print(f"  Mean:   {scores.mean():+.3f}")
        print(f"  75th:   {scores.quantile(0.75):+.3f}")
        print(f"  Max:    {scores.max():+.3f}")
        print(f"")
        n_neg = (scores < -0.1).sum()
        n_neu = ((scores >= -0.1) & (scores <= 0.1)).sum()
        n_pos = (scores > 0.1).sum()
        print(f"  Deterioration (< -0.1): {n_neg:,} ({n_neg / len(scores) * 100:.1f}%)")
        print(f"  Neutral (-0.1 to 0.1):  {n_neu:,} ({n_neu / len(scores) * 100:.1f}%)")
        print(f"  Recovery (> 0.1):       {n_pos:,} ({n_pos / len(scores) * 100:.1f}%)")
        print(f"=" * 60)

        # Show some examples
        print(f"\nSample per-patient NLI scores (with text excerpts):")
        sample_pids = list(nli_cache.keys())[:5]
        for pid in sample_pids:
            entries = nli_cache.get(pid, [])
            if entries:
                print(f"\n  Patient {pid} ({len(entries)} text scores):")
                for e in entries[:8]:
                    text_excerpt = e.get("text", "")[:100]
                    print(
                        f"    {e['nli_score']:+.3f} | {e['source']:15s} | {e['date']} | {text_excerpt}"
                    )
                if len(entries) > 8:
                    print(f"    ... and {len(entries) - 8} more")

        # Show extreme scores for review
        print(f"\n{'=' * 60}")
        print(f"EXTREME SCORES (most deteriorated & most recovered):")
        print(f"{'=' * 60}")
        all_entries = []
        for pid, entries in nli_cache.items():
            for e in entries:
                all_entries.append({**e, "patient_id": pid})
        all_entries.sort(key=lambda x: x["nli_score"])

        print(f"\n  TOP 10 DETERIORATION:")
        for e in all_entries[:10]:
            txt = e.get("text", "")[:120]
            print(
                f"    {e['nli_score']:+.3f} | {e['patient_id']} | {e['source']:15s} | {txt}"
            )

        print(f"\n  TOP 10 RECOVERY:")
        for e in all_entries[-10:]:
            txt = e.get("text", "")[:120]
            print(
                f"    {e['nli_score']:+.3f} | {e['patient_id']} | {e['source']:15s} | {txt}"
            )


if __name__ == "__main__":
    main()
