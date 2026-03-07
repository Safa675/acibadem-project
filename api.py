"""
api.py
FastAPI backend wrapping the ILAY Python pipeline.
Serves pre-computed data to the Next.js frontend.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import warnings
import math
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

_THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS_DIR))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np

from src import (
    load_all_data,
    HealthIndexBuilder,
    classify_all_patients,
    compute_all_composites,
    get_patient_labs,
    get_patient_visits,
    get_patient_prescriptions,
    build_all_outcome_profiles,
    profiles_to_dataframe,
    compute_feature_correlations,
    predict_eci_narrative,
    run_all_validations,
    validation_summary_df,
)
from src.chatbot import (
    stream_chat_response,
    build_patient_context,
    build_cohort_context,
)
from src.fusion import COMPOSITE_TIERS
from src.eci import compute_all_eci, ECI_TIERS
from src.sut_pricing import (
    compute_all_sut_costs,
    estimate_cohort_sut_summary,
    estimate_patient_sut_costs,
    compute_drg_summary,
    compute_cost_var,
    compute_reimbursement_gaps,
    compute_cost_trajectory,
    DRGSummary,
    DRGEpisode,
    CostVaRResult,
    ReimbursementGapAnalysis,
    CostTrajectory,
)
from src.health_var import compute_all_vars_parallel
from src.score_sofa import (
    compute_all_sofa,
    aggregate_per_patient as aggregate_sofa_per_patient,
)
from src.score_news2 import (
    compute_all_news2,
    aggregate_per_patient as aggregate_news2_per_patient,
)
from src.score_apache2 import (
    compute_all_apache2,
    aggregate_per_patient as aggregate_apache2_per_patient,
)

# ── App ──────────────────────────────────────────────────────────────────────

# ── Logging ───────────────────────────────────────────────────────────────────

LOG_DIR = _THIS_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_DIR / "ilay.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ilay")

app = FastAPI(title="ILAY API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://134.209.228.120",
        "http://134.209.228.120:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

_correlation_cache = None


def _safe(v):
    """Convert numpy types and NaN/Inf to JSON-safe Python natives."""
    if v is None:
        return None
    # numpy scalar types → native Python
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, np.ndarray):
        return v.tolist()
    return v


def _safe_dict(d: dict) -> dict:
    return {k: _safe(v) for k, v in d.items()}


def _normalize_sex_code(value: object) -> str | None:
    """Normalize heterogeneous sex values to compact codes used in filters."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None

    raw = str(value).strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper in {"NAN", "NONE", "NULL"}:
        return None
    if upper in {"KADIN", "FEMALE", "F", "BAYAN", "KIZ"}:
        return "K"
    if upper in {"ERKEK", "MALE", "M", "BAY", "ER"}:
        return "E"
    if upper.startswith("K"):
        return "K"
    if upper.startswith("E"):
        return "E"
    return upper


_COMORBIDITY_CONDITION_COLUMNS = [
    ("Hipertansiyon Hastada", "hypertension"),
    ("Kalp Damar Hastada", "cardiovascular"),
    ("Diyabet Hastada", "diabetes"),
    ("Kan Hastalıkları Hastada", "hematologic"),
    ("Kronik Hastalıklar Diğer", "other_chronic"),
    ("Ameliyat Geçmişi", "surgery_history"),
]


def _clean_text_token(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)) and math.isnan(float(value)):
        return None

    token = str(value).strip()
    if not token:
        return None
    if token.upper() in {"NAN", "NONE", "NULL"}:
        return None
    return token


def _has_positive_condition(values: pd.Series) -> bool:
    for value in values:
        if isinstance(value, str):
            if value.strip():
                return True
            continue

        if value is None or pd.isna(value):
            continue

        if isinstance(value, (int, float, np.integer, np.floating, bool, np.bool_)):
            if float(value) > 0:
                return True

    return False


def _latest_non_empty_text_by_patient(
    df: pd.DataFrame, value_col: str, date_col: str = "visit_date"
) -> dict[str, str]:
    required_cols = {"patient_id", value_col}
    if not required_cols.issubset(set(df.columns)):
        return {}

    cols = ["patient_id", value_col]
    if date_col in df.columns:
        cols.append(date_col)

    work = df[cols].copy()
    work[value_col] = work[value_col].map(_clean_text_token)
    work = work[work[value_col].notna()]
    if work.empty:
        return {}

    if date_col in work.columns:
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work = work.sort_values(["patient_id", date_col], na_position="first")
    else:
        work = work.sort_values(["patient_id"])

    return {
        str(pid): str(val)
        for pid, val in work.groupby("patient_id")[value_col].last().items()
    }


def _comorbidity_conditions_by_patient(ana_df: pd.DataFrame) -> dict[str, list[str]]:
    if "patient_id" not in ana_df.columns:
        return {}

    result: dict[str, list[str]] = {}
    for pid, rows in ana_df.groupby("patient_id"):
        conditions: list[str] = []
        for source_col, condition_key in _COMORBIDITY_CONDITION_COLUMNS:
            if source_col not in rows.columns:
                continue
            vals = rows[source_col].dropna()
            if vals.empty:
                continue
            if _has_positive_condition(vals):
                conditions.append(condition_key)
        result[str(pid)] = conditions

    return result


def _build_rating_intervals() -> list[dict]:
    """Build rating interval labels from fusion.py tier source-of-truth."""
    intervals = []
    for idx, (min_score, rating, _) in enumerate(COMPOSITE_TIERS):
        if idx == 0:
            max_score = 100
        else:
            max_score = int(COMPOSITE_TIERS[idx - 1][0]) - 1
        intervals.append(
            {
                "rating": rating,
                "min_score": int(min_score),
                "max_score": int(max_score),
                "label": f"{int(min_score)}-{int(max_score)}",
            }
        )
    return intervals


# ── Pipeline Cache ───────────────────────────────────────────────────────────

_pipeline_cache: dict | None = None


def _read_current_rss_mb() -> float | None:
    """Read process RSS from /proc/self/status (Linux)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as status_file:
            for line in status_file:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1]) / 1024.0
    except (OSError, ValueError):
        return None
    return None


def _log_rss(stage: str) -> None:
    rss_mb = _read_current_rss_mb()
    if rss_mb is None:
        logger.info("%s | RSS unavailable", stage)
    else:
        logger.info("%s | RSS %.1f MB", stage, rss_mb)


def _load_pipeline() -> dict:
    global _pipeline_cache
    if _pipeline_cache is not None:
        return _pipeline_cache

    import gc
    import time
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.perf_counter()

    data = load_all_data(str(_THIS_DIR))
    lab_df = data["lab"]
    ana_df = data["ana"]
    rec_df = data["rec"]
    logger.info("Data loaded in %.1fs", time.perf_counter() - t0)
    _log_rss("Stage 1/5 data load complete")

    builder = HealthIndexBuilder(
        lab_df,
        ana_df,
        vital_weight=0.45,
    )

    all_snapshots, all_series = builder.build_all_patients_bulk()

    t_hi = time.perf_counter()
    logger.info(
        "Health Index built for %d patients in %.1fs", len(all_snapshots), t_hi - t0
    )
    _log_rss("Stage 2/5 health index complete")

    def _run_regimes():
        t = time.perf_counter()
        result = classify_all_patients(all_snapshots)
        logger.info("Regimes classified in %.1fs", time.perf_counter() - t)
        return result

    def _run_var():
        t = time.perf_counter()
        var_results_by_pid, var_summary = compute_all_vars_parallel(
            all_series, horizon_draws=3, iterations=500, seed=42
        )
        logger.info(
            "VaR computed for %d patients in %.1fs",
            len(var_results_by_pid),
            time.perf_counter() - t,
        )
        return var_results_by_pid, var_summary

    logger.info("Stage 3/5 launching regimes + VaR with bounded concurrency (2)…")
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline") as pool:
        fut_regimes = pool.submit(_run_regimes)
        fut_var = pool.submit(_run_var)

        regimes = fut_regimes.result()
        var_results_by_pid, var_summary = fut_var.result()
    _log_rss("Stage 3/5 regimes + VaR complete")

    logger.info("Stage 4/5 running benchmarks sequentially to reduce peak RAM…")
    t_bench = time.perf_counter()

    sofa_visit_df = compute_all_sofa(lab_df, ana_df)
    sofa_per_patient = (
        aggregate_sofa_per_patient(sofa_visit_df)
        if not sofa_visit_df.empty
        else pd.DataFrame()
    )
    del sofa_visit_df
    gc.collect()
    _log_rss("Stage 4/5 SOFA complete")

    news2_visit_df = compute_all_news2(ana_df)
    news2_per_patient = (
        aggregate_news2_per_patient(news2_visit_df)
        if not news2_visit_df.empty
        else pd.DataFrame()
    )
    del news2_visit_df
    gc.collect()
    _log_rss("Stage 4/5 NEWS2 complete")

    apache2_visit_df = compute_all_apache2(lab_df, ana_df)
    apache2_per_patient = (
        aggregate_apache2_per_patient(apache2_visit_df)
        if not apache2_visit_df.empty
        else pd.DataFrame()
    )
    del apache2_visit_df
    gc.collect()
    _log_rss("Stage 4/5 APACHE II complete")

    logger.info(
        "Benchmarks computed (SOFA: %d, NEWS2: %d, APACHE II: %d) in %.1fs",
        len(sofa_per_patient),
        len(news2_per_patient),
        len(apache2_per_patient),
        time.perf_counter() - t_bench,
    )

    # ── NLP: load pre-scored results from disk cache ──────────────────────
    logger.info("Stage 4.5/5 loading NLP scores from cache…")
    _log_rss("Stage 4.5/5 NLP cache load start")
    t_nlp = time.perf_counter()

    _cache_dir = _THIS_DIR / ".cache"
    _nlp_parquet = _cache_dir / "nlp_results.parquet"
    _nli_json = _cache_dir / "nli_scores_cache.json"

    nlp_results_df = pd.DataFrame(columns=["patient_id", "visit_date", "nlp_composite"])
    nli_scores_cache: dict[str, list[dict]] = {}

    if _nlp_parquet.exists():
        try:
            nlp_results_df = pd.read_parquet(_nlp_parquet)
            # Drop junk rows with null / "None" / empty patient IDs
            nlp_results_df = nlp_results_df[
                nlp_results_df["patient_id"].notna()
                & (nlp_results_df["patient_id"].astype(str) != "None")
                & (nlp_results_df["patient_id"].astype(str) != "")
            ]
            # Deduplicate (some early runs produced dupes)
            nlp_results_df = nlp_results_df.drop_duplicates(
                subset=["patient_id", "visit_date"]
            )
            logger.info(
                "Loaded %d NLP rows (%d unique patients) from cache",
                len(nlp_results_df),
                nlp_results_df["patient_id"].nunique(),
            )
        except Exception as exc:
            logger.warning("Failed to load NLP parquet cache: %s", exc)
            nlp_results_df = pd.DataFrame(
                columns=["patient_id", "visit_date", "nlp_composite"]
            )
    else:
        logger.info("No NLP cache found at %s — NLP scores will be 0.0", _nlp_parquet)

    if _nli_json.exists():
        try:
            with open(_nli_json) as f:
                nli_scores_cache = json.load(f)
            logger.info("Loaded NLI detail cache: %d patients", len(nli_scores_cache))
        except Exception as exc:
            logger.warning("Failed to load NLI JSON cache: %s", exc)
            nli_scores_cache = {}
    else:
        logger.info("No NLI detail cache found at %s", _nli_json)

    logger.info(
        "NLP cache loaded in %.1fs",
        time.perf_counter() - t_nlp,
    )
    _log_rss("Stage 4.5/5 NLP cache loaded")

    logger.info("Stage 5/5 building composites, outcomes, and validation…")

    latest_health = {
        pid: snaps[-1].health_score for pid, snaps in all_snapshots.items() if snaps
    }
    # Extract latest NLP composite per patient from the scored DataFrame
    if not nlp_results_df.empty and "nlp_composite" in nlp_results_df.columns:
        # Sort by visit_date descending, take the last (most recent) per patient
        _nlp_latest = (
            nlp_results_df.sort_values("visit_date")
            .groupby("patient_id")["nlp_composite"]
            .last()
        )
        latest_nlp = {str(pid): float(val) for pid, val in _nlp_latest.items()}
        # Fill missing patients with 0.0 so fusion auto-adjusts weights
        for pid in latest_health:
            latest_nlp.setdefault(pid, 0.0)
    else:
        latest_nlp = {pid: 0.0 for pid in latest_health}

    composites = compute_all_composites(latest_health, latest_nlp, rec_df, ana_df)

    # Convert nlp_results_df (single DF) → dict[pid, DataFrame] for outcome profiles
    nlp_results_by_pid: dict[str, pd.DataFrame] = {}
    if not nlp_results_df.empty:
        for pid, group in nlp_results_df.groupby("patient_id"):
            nlp_results_by_pid[str(pid)] = group.reset_index(drop=True)

    profiles = build_all_outcome_profiles(
        all_snapshots, regimes, ana_df, rec_df, nlp_results_by_pid
    )
    profiles_df = profiles_to_dataframe(profiles)
    profiles_by_pid = {p.patient_id: p for p in profiles}

    # Lightweight selector metadata for frontend-side filtering.
    latest_weight_by_pid: dict[str, float] = {}
    if {"patient_id", "visit_date", "Kilo"}.issubset(set(ana_df.columns)):
        _weights = ana_df[["patient_id", "visit_date", "Kilo"]].copy()
        _weights["weight_kg"] = pd.to_numeric(_weights["Kilo"], errors="coerce")
        _weights = _weights.dropna(subset=["weight_kg"]).sort_values(
            ["patient_id", "visit_date"]
        )
        if not _weights.empty:
            latest_weight_by_pid = {
                str(pid): float(val)
                for pid, val in _weights.groupby("patient_id")["weight_kg"]
                .last()
                .items()
            }

    latest_sex_raw_by_pid = _latest_non_empty_text_by_patient(ana_df, "sex")
    latest_doctor_code_by_pid = _latest_non_empty_text_by_patient(ana_df, "DOCTOR_CODE")
    comorbidity_conditions_by_pid = _comorbidity_conditions_by_patient(ana_df)

    patient_meta = []
    for pid in sorted(regimes.keys()):
        profile = profiles_by_pid.get(pid)
        age = (
            int(round(profile.age))
            if profile is not None
            and profile.age is not None
            and not pd.isna(profile.age)
            else None
        )
        sex_raw = (
            profile.sex
            if profile is not None and profile.sex is not None
            else latest_sex_raw_by_pid.get(str(pid))
        )
        patient_meta.append(
            _safe_dict(
                {
                    "patient_id": pid,
                    "age": age,
                    "sex": _normalize_sex_code(sex_raw),
                    "sex_raw": str(sex_raw).strip()
                    if sex_raw is not None and str(sex_raw).strip()
                    else None,
                    "weight_kg": latest_weight_by_pid.get(str(pid)),
                    "doctor_code": latest_doctor_code_by_pid.get(str(pid)),
                    "comorbidity_conditions": comorbidity_conditions_by_pid.get(
                        str(pid), []
                    ),
                }
            )
        )

    # ── Validation (depends on benchmarks + health index) ──────────────────
    hi_rows = []
    for pid, series in all_series.items():
        scores = [pt.value for pt in series]
        if scores:
            hi_rows.append(
                {
                    "patient_id": pid,
                    "mean_hi_score": float(np.mean(scores)),
                    "last_hi_score": float(scores[-1]),
                }
            )
    hi_df = pd.DataFrame(hi_rows) if hi_rows else pd.DataFrame()

    logger.info(
        "Benchmark scores — SOFA: %d patients, NEWS2: %d patients, APACHE II: %d patients, HI: %d patients",
        len(sofa_per_patient),
        len(news2_per_patient),
        len(apache2_per_patient),
        len(hi_df),
    )

    validation_results = run_all_validations(
        hi_df=hi_df,
        sofa_df=sofa_per_patient,
        news2_df=news2_per_patient,
        apache2_df=apache2_per_patient,
    )
    _log_rss("Stage 5/5 composites/outcomes/validation complete")

    # ── ECI (Expected Cost Intensity) ─────────────────────────────────────
    logger.info("Computing ECI scores...")
    t_eci = time.perf_counter()

    # all_series is still List[SeriesPoint] at this point; convert to compact
    # format needed by compute_all_eci (dict of {dates, values})
    _eci_series: dict[str, dict] = {}
    for pid, pts in all_series.items():
        _eci_series[pid] = {
            "dates": [p.date for p in pts],
            "values": [p.value for p in pts],
        }

    eci_df = compute_all_eci(ana_df, lab_df, rec_df, latest_nlp, _eci_series)
    del _eci_series

    # Build ECI index for O(1) per-patient lookups
    eci_by_pid: dict[str, dict] = {}
    if not eci_df.empty:
        for row in eci_df.to_dict(orient="records"):
            eci_by_pid[str(row["patient_id"])] = row

    logger.info(
        "ECI computed for %d patients in %.1fs",
        len(eci_df),
        time.perf_counter() - t_eci,
    )
    _log_rss("ECI complete")

    # ── SUT Pricing (Sağlık Uygulama Tebliği cost estimation) ────────────
    logger.info("Computing SUT cost estimates...")
    t_sut = time.perf_counter()
    sut_by_pid = compute_all_sut_costs(
        lab_df, ana_df, rec_df, sorted(all_series.keys())
    )
    sut_cohort_summary = estimate_cohort_sut_summary(sut_by_pid)
    logger.info(
        "SUT costs computed for %d patients in %.1fs",
        len(sut_by_pid),
        time.perf_counter() - t_sut,
    )
    _log_rss("SUT pricing complete")

    # Compute per-patient data completeness (mean across all snapshots)
    # Must happen BEFORE all_snapshots is released.
    data_completeness_by_pid: dict[str, float] = {}
    for pid, snaps in all_snapshots.items():
        if snaps:
            data_completeness_by_pid[str(pid)] = round(
                sum(s.data_completeness for s in snaps) / len(snaps), 3
            )

    # Large intermediate object no longer needed by active endpoints.
    del all_snapshots
    gc.collect()
    _log_rss("Post-cleanup (all_snapshots released)")

    # Build composites index for O(1) per-patient lookups (avoids full DF scan)
    composites_idx: dict[str, int] = {}
    if not composites.empty:
        for i, pid in enumerate(composites["patient_id"]):
            composites_idx[str(pid)] = i

    # ── Pre-cache KPI scalars (avoids re-scanning full DFs per request) ───
    n_patients_cached = int(lab_df["patient_id"].nunique())
    total_rx_cached = int(len(rec_df))
    mean_score_cached = (
        round(float(profiles_df["mean_health_score"].mean()), 1)
        if not profiles_df.empty
        else 0.0
    )
    n_high_risk_cached = (
        int(len(var_summary[var_summary["risk_tier"] == "RED"]))
        if not var_summary.empty and "risk_tier" in var_summary.columns
        else 0
    )
    mean_eci_cached = (
        round(float(eci_df["eci_score"].mean()), 1) if not eci_df.empty else 0.0
    )
    mean_composite_cached = (
        round(float(composites["composite_score"].mean()), 1)
        if not composites.empty
        else 0.0
    )
    mean_data_completeness_cached = (
        round(sum(data_completeness_by_pid.values()) / len(data_completeness_by_pid), 3)
        if data_completeness_by_pid
        else 0.0
    )
    n_critical_cached = sum(
        1
        for r in regimes.values()
        if r.last_known_state() is not None and r.last_known_state().value == "Critical"
    )
    rating_dist_cached = {}
    if not composites.empty:
        for rat, count in composites["rating"].value_counts().items():
            rating_dist_cached[rat] = int(count)
    regime_dist_cached = {}
    for regime_result in regimes.values():
        state = regime_result.last_known_state()
        state_str = state.value if state is not None else "Insufficient Data"
        regime_dist_cached[state_str] = regime_dist_cached.get(state_str, 0) + 1

    # ── Trim raw DataFrames: keep only columns needed by endpoints ────────
    # lab_df: patient_id, date, test_name, value, ref_min, ref_max, ISLEMTARIHI
    #   (drops: unit, cohort)
    lab_keep = [
        "patient_id",
        "date",
        "test_name",
        "value",
        "ref_min",
        "ref_max",
        "ISLEMTARIHI",
    ]
    lab_df = lab_df[[c for c in lab_keep if c in lab_df.columns]].copy()

    # ana_df: patient_id, visit_date, TANIKODU, los_days, GELISTARIHI,
    #   6 comorbidity cols, 5 text cols
    #   (drops: age, sex, vitals, BMI, episode, etc.)
    ana_keep = [
        "patient_id",
        "visit_date",
        "TANIKODU",
        "los_days",
        "GELISTARIHI",
        "Hipertansiyon Hastada",
        "Kalp Damar Hastada",
        "Diyabet Hastada",
        "Kan Hastalıkları Hastada",
        "Kronik Hastalıklar Diğer",
        "Ameliyat Geçmişi",
        "ÖYKÜ",
        "YAKINMA",
        "Muayene Notu",
        "Kontrol Notu",
        "Tedavi Notu",
    ]
    ana_df = ana_df[[c for c in ana_keep if c in ana_df.columns]].copy()

    # rec_df: patient_id, date only
    #   (drops: drug_name, dose, route, duration_days, episode, cohort)
    rec_keep = ["patient_id", "date"]
    rec_df = rec_df[[c for c in rec_keep if c in rec_df.columns]].copy()

    gc.collect()
    _log_rss("Post-trim (raw DFs slimmed, KPIs cached)")

    # ── Compact all_series: List[SeriesPoint] → {"dates": [...], "values": [...]} ─
    # Eliminates Python NamedTuple per-point overhead (~100 bytes/point → ~16 bytes/point)
    all_series_compact: dict[str, dict] = {}
    for pid, pts in all_series.items():
        all_series_compact[pid] = {
            "dates": [p.date for p in pts],
            "values": [p.value for p in pts],
        }
    del all_series
    gc.collect()
    _log_rss("Post-compact (all_series converted)")

    total_elapsed = time.perf_counter() - t0
    logger.info("Pipeline fully loaded in %.1fs", total_elapsed)

    _pipeline_cache = {
        "lab_df": lab_df,
        "ana_df": ana_df,
        "rec_df": rec_df,
        "all_series": all_series_compact,
        "regimes": regimes,
        "var_summary": var_summary,
        "nlp_results": nlp_results_by_pid,
        "nlp_results_df": nlp_results_df,
        "composites": composites,
        "composites_idx": composites_idx,
        "profiles_df": profiles_df,
        "profiles": profiles_by_pid,
        "patient_meta": patient_meta,
        "validation_results": validation_results,
        "var_results": var_results_by_pid,
        "nli_scores_cache": nli_scores_cache,
        "eci_df": eci_df,
        "eci_by_pid": eci_by_pid,
        "sut_by_pid": sut_by_pid,
        "sut_cohort_summary": sut_cohort_summary,
        # Pre-cached KPI scalars
        "kpi_n_patients": n_patients_cached,
        "kpi_total_rx": total_rx_cached,
        "kpi_mean_score": mean_score_cached,
        "kpi_n_high_risk": n_high_risk_cached,
        "kpi_mean_eci": mean_eci_cached,
        "kpi_mean_composite": mean_composite_cached,
        "kpi_n_critical": n_critical_cached,
        "kpi_rating_dist": rating_dist_cached,
        "kpi_regime_dist": regime_dist_cached,
        "kpi_mean_data_completeness": mean_data_completeness_cached,
        "data_completeness_by_pid": data_completeness_by_pid,
    }
    return _pipeline_cache


# ── Startup event ────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    _load_pipeline()


# ── Pydantic Models ──────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    messages: list[dict]
    patient_id: str
    active_tab: str


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/api/patients")
def get_patients():
    """Return total patient count + a small initial set of IDs with metadata."""
    ctx = _load_pipeline()
    dc_by_pid = ctx.get("data_completeness_by_pid", {})
    # Sort by data completeness descending so the default (first) patient has richest data
    all_ids = sorted(
        ctx["regimes"].keys(), key=lambda pid: dc_by_pid.get(str(pid), 0), reverse=True
    )
    meta_lookup = {m["patient_id"]: m for m in ctx.get("patient_meta", [])}
    initial_ids = all_ids[:20]
    meta_list = [meta_lookup.get(pid, {"patient_id": pid}) for pid in all_ids]
    return {
        "patients": initial_ids,
        "total": len(all_ids),
        "patient_meta": meta_list,
    }


@app.get("/api/patients/search")
def search_patients(
    q: str = Query("", description="Prefix to match against patient_id"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """Fast prefix search on patient IDs — for search-as-you-type UI."""
    ctx = _load_pipeline()
    dc_by_pid = ctx.get("data_completeness_by_pid", {})
    all_ids = sorted(
        ctx["regimes"].keys(), key=lambda pid: dc_by_pid.get(str(pid), 0), reverse=True
    )

    if not q.strip():
        # No query: return first `limit` patients
        matched = all_ids[:limit]
    else:
        query = q.strip()
        matched = [pid for pid in all_ids if str(pid).startswith(query)][:limit]

    # Attach lightweight meta for matched patients
    meta_lookup = {m["patient_id"]: m for m in ctx.get("patient_meta", [])}
    results = []
    for pid in matched:
        meta = meta_lookup.get(pid, {})
        results.append(
            {
                "patient_id": pid,
                "age": meta.get("age"),
                "sex": meta.get("sex"),
                "sex_raw": meta.get("sex_raw"),
                "weight_kg": meta.get("weight_kg"),
                "doctor_code": meta.get("doctor_code"),
                "comorbidity_conditions": meta.get("comorbidity_conditions", []),
            }
        )

    return {"results": results, "total_matched": len(matched)}


def _paginate_list(items: list, page: int, per_page: int) -> tuple[list, dict]:
    """Slice a list for pagination; return (page_items, pagination_meta)."""
    total = len(items)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], {
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


@app.get("/api/cohort")
def get_cohort(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    per_page: int = Query(50, ge=1, le=500, description="Rows per page"),
    sort_by: str = Query("composite_score", description="Column to sort composites by"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Sort order"),
    rating: str | None = Query(None, description="Filter by rating (e.g. AAA, AA, A)"),
    regime: str | None = Query(None, description="Filter by regime state"),
):
    """Cohort overview: KPI metrics + paginated composites + var summary."""
    ctx = _load_pipeline()
    composites = ctx["composites"]
    profiles_df = ctx["profiles_df"]
    regimes = ctx["regimes"]
    var_summary = ctx["var_summary"]

    # Use pre-cached KPI scalars (computed once at startup)
    n_patients = ctx["kpi_n_patients"]
    mean_score = ctx["kpi_mean_score"]
    n_high_risk = ctx["kpi_n_high_risk"]
    mean_eci = ctx["kpi_mean_eci"]
    mean_composite = ctx["kpi_mean_composite"]
    n_critical = ctx["kpi_n_critical"]
    total_rx = ctx["kpi_total_rx"]
    mean_data_completeness = ctx["kpi_mean_data_completeness"]
    dc_by_pid = ctx["data_completeness_by_pid"]

    # ── Build composites table (full, then filter, sort, paginate) ────────
    composites_list_full: list[dict] = []
    if not composites.empty:
        display_df = composites.copy()

        # Annotate data completeness per patient
        display_df["data_completeness"] = display_df["patient_id"].map(
            lambda pid: dc_by_pid.get(str(pid), 0.5)
        )

        # Merge ECI + profile columns
        if not profiles_df.empty:
            display_df = display_df.merge(
                profiles_df[
                    [
                        "patient_id",
                        "n_prescriptions",
                        "n_comorbidities",
                        "age",
                    ]
                ],
                on="patient_id",
                how="left",
            )

        # Merge ECI scores
        eci_df = ctx["eci_df"]
        if not eci_df.empty:
            display_df = display_df.merge(
                eci_df[["patient_id", "eci_score", "eci_rating", "eci_rating_label"]],
                on="patient_id",
                how="left",
            )

        # Annotate regime state per patient
        display_df["regime_state"] = display_df["patient_id"].map(
            lambda pid: (
                regimes[pid].last_known_state().value
                if pid in regimes and regimes[pid].last_known_state() is not None
                else "Insufficient Data"
            )
        )

        # ── Filters ──────────────────────────────────────────────────────
        if rating:
            display_df = display_df[display_df["rating"] == rating]
        if regime:
            display_df = display_df[display_df["regime_state"] == regime]

        # ── Sort ─────────────────────────────────────────────────────────
        ascending = order == "asc"
        if sort_by in display_df.columns:
            display_df = display_df.sort_values(
                sort_by, ascending=ascending, na_position="last"
            )
        else:
            display_df = display_df.sort_values(
                "composite_score", ascending=False, na_position="last"
            )

        composites_list_full = [
            _safe_dict(r) for r in display_df.to_dict(orient="records")
        ]

    # Paginate composites
    composites_page, composites_pagination = _paginate_list(
        composites_list_full, page, per_page
    )

    # VaR summary — paginated (same page/per_page as composites)
    var_list_full = []
    if not var_summary.empty:
        var_records = var_summary.to_dict(orient="records")
        for r in var_records:
            r["downside_var_pct"] = round(abs(min(float(r.get("var_pct", 0)), 0.0)), 1)
            var_list_full.append(_safe_dict(r))
    var_page, var_pagination = _paginate_list(var_list_full, page, per_page)

    # Rating distribution (pre-cached at startup)
    rating_dist = ctx["kpi_rating_dist"]
    rating_intervals = _build_rating_intervals()

    # Regime state distribution (pre-cached at startup)
    regime_dist = ctx["kpi_regime_dist"]

    # Cohort scatter data — NLP-scored patients only (nlp_score != 50.0 midpoint)
    scatter_data = []
    scatter_total = 0
    if not composites.empty:
        merged = composites[
            ["patient_id", "health_index_score", "nlp_score", "rating"]
        ].copy()
        eci_df_ref = ctx["eci_df"]
        if not eci_df_ref.empty:
            merged = merged.merge(
                eci_df_ref[["patient_id", "eci_score"]], on="patient_id", how="left"
            )
        else:
            merged["eci_score"] = 30.0

        # Filter to patients with real NLP scores (50.0 = normalized zero = no NLP)
        merged = merged[merged["nlp_score"] != 50.0]
        scatter_total = len(merged)

        # Cap at 12,000 points for browser performance
        MAX_SCATTER = 12000
        if len(merged) > MAX_SCATTER:
            # Stratified sample by rating to preserve distribution
            sampled_frames = []
            for _rating, group in merged.groupby("rating", observed=True):
                frac = max(1, int(MAX_SCATTER * len(group) / len(merged)))
                sampled_frames.append(
                    group.sample(n=min(frac, len(group)), random_state=42)
                )
            merged = pd.concat(sampled_frames, ignore_index=True)

        scatter_data = [
            {
                "patient_id": row["patient_id"],
                "health_index_score": float(row.get("health_index_score", 0)),
                "nlp_score": float(row.get("nlp_score", 0)),
                "rating": row.get("rating", "N/A"),
                "eci_score": float(row.get("eci_score", 30)),
            }
            for row in merged.to_dict(orient="records")
        ]

    return {
        "kpi": {
            "n_patients": n_patients,
            "mean_score": round(mean_score, 1),
            "mean_eci": mean_eci,
            "mean_composite": mean_composite,
            "n_high_risk": n_high_risk,
            "n_critical": n_critical,
            "total_rx": total_rx,
            "mean_data_completeness": round(mean_data_completeness * 100, 1),
        },
        "composites": composites_page,
        "composites_pagination": composites_pagination,
        "var_summary": var_page,
        "var_pagination": var_pagination,
        "rating_distribution": rating_dist,
        "rating_intervals": rating_intervals,
        "regime_distribution": regime_dist,
        "scatter_data": scatter_data,
        "scatter_total": scatter_total,
        "sut_summary": ctx["sut_cohort_summary"],
    }


@app.get("/api/patient/{patient_id}")
def get_patient(patient_id: str):
    """Full patient detail for Explorer tab."""
    ctx = _load_pipeline()
    regimes = ctx["regimes"]
    composites = ctx["composites"]
    profiles = ctx["profiles"]
    all_series = ctx["all_series"]
    nlp_results = ctx["nlp_results"]
    lab_df = ctx["lab_df"]
    ana_df = ctx["ana_df"]
    rec_df = ctx["rec_df"]
    var_results = ctx["var_results"]

    if patient_id not in regimes:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Summary metrics
    profile = profiles.get(patient_id)
    composites_idx = ctx["composites_idx"]
    comp_row = None
    if patient_id in composites_idx:
        comp_row = composites.iloc[[composites_idx[patient_id]]]
    regime_r = regimes.get(patient_id)
    _lks = regime_r.last_known_state() if regime_r else None
    last_state = _lks.value if _lks is not None else "Insufficient Data"

    rating = (
        comp_row["rating"].iloc[0]
        if comp_row is not None and not comp_row.empty
        else "—"
    )
    comp_score = (
        float(comp_row["composite_score"].iloc[0])
        if comp_row is not None and not comp_row.empty
        else 0
    )

    var_ex = var_results.get(patient_id)

    # ECI data for this patient
    eci_data = ctx["eci_by_pid"].get(patient_id, {})

    # SUT cost data for this patient
    sut_estimate = ctx["sut_by_pid"].get(patient_id)

    summary = {
        "patient_id": patient_id,
        "rating": rating,
        "composite_score": round(comp_score, 1),
        "regime_state": last_state,
        "health_score": round(profile.final_health_score, 1) if profile else None,
        "downside_var_pct": round(abs(min(var_ex.var_pct, 0.0)), 1) if var_ex else None,
        "eci_score": eci_data.get("eci_score"),
        "eci_rating": eci_data.get("eci_rating"),
        "eci_rating_label": eci_data.get("eci_rating_label"),
        "eci_visit_intensity": eci_data.get("visit_intensity"),
        "eci_med_burden": eci_data.get("med_burden"),
        "eci_diagnostic_intensity": eci_data.get("diagnostic_intensity"),
        "eci_trajectory_cost": eci_data.get("trajectory_cost"),
        "sut_cost_min": sut_estimate.cost_min if sut_estimate else None,
        "sut_cost_max": sut_estimate.cost_max if sut_estimate else None,
        "sut_cost_mid": sut_estimate.cost_mid if sut_estimate else None,
        "sut_cost_tier": sut_estimate.cost_tier if sut_estimate else None,
        "age": round(profile.age) if profile and profile.age else None,
        "sex": profile.sex if profile else None,
        "n_comorbidities": profile.n_comorbidities if profile else 0,
        "total_visits": int(profile.total_visits)
        if profile and profile.total_visits
        else None,
        "n_lab_draws": profile.n_lab_draws if profile else 0,
        "n_prescriptions": profile.n_prescriptions if profile else 0,
        "data_completeness": round(
            ctx["data_completeness_by_pid"].get(patient_id, 0.5) * 100, 1
        ),
    }

    # Comorbidities
    ana_patient = get_patient_visits(ana_df, patient_id)
    comorbidities = []
    if not ana_patient.empty:
        comorbidity_cols = [
            ("Hipertansiyon Hastada", "Hypertension"),
            ("Kalp Damar Hastada", "Cardiovascular"),
            ("Diyabet Hastada", "Diabetes"),
            ("Kan Hastalıkları Hastada", "Blood Disorders"),
            ("Kronik Hastalıklar Diğer", "Other Chronic"),
            ("Ameliyat Geçmişi", "Surgical History"),
        ]
        for col, label in comorbidity_cols:
            if col in ana_patient.columns:
                vals = ana_patient[col].dropna()
                for v in vals:
                    if isinstance(v, str) and len(v.strip()) >= 1:
                        comorbidities.append({"label": label, "detail": v.strip()[:80]})
                        break
                    elif not isinstance(v, str) and v and v > 0:
                        comorbidities.append({"label": label, "detail": None})
                        break

    # Regime timeline data
    regime_timeline = []
    if regime_r:
        rdf = regime_r.to_dataframe()
        if not rdf.empty:
            records = rdf.to_dict(orient="records")
            for row in records:
                state = (
                    str(row.get("state", "")).replace("PatientState.", "")
                    if "state" in rdf.columns
                    else None
                )
                regime_timeline.append(
                    _safe_dict(
                        {
                            "date": str(row["date"]),
                            "health_score": float(row["health_score"]),
                            "ma": float(row["ma"])
                            if "ma" in row and pd.notna(row.get("ma"))
                            else None,
                            "state": state,
                        }
                    )
                )

    # Prescription dates for timeline overlay
    presc = get_patient_prescriptions(rec_df, patient_id)
    presc_dates = (
        [str(d) for d in presc["date"].dropna().tolist()] if not presc.empty else []
    )

    # VaR fan chart data
    var_fan = None
    series_compact = all_series.get(patient_id, None)
    if var_ex and series_compact:
        dates = [str(d) for d in series_compact["dates"]]
        scores = list(series_compact["values"])
        last_date = pd.Timestamp(series_compact["dates"][-1])
        delta = (
            (
                pd.Timestamp(series_compact["dates"][-1])
                - pd.Timestamp(series_compact["dates"][-2])
            ).days
            if len(series_compact["dates"]) >= 2
            else 7
        )
        future_dates = [
            str(last_date + pd.Timedelta(days=delta * (i + 1))) for i in range(3)
        ]

        var_fan = {
            "history_dates": dates,
            "history_scores": scores,
            "future_dates": future_dates,
            "p05": var_ex.p05,
            "p25": var_ex.p25,
            "p50": var_ex.p50,
            "p75": var_ex.p75,
            "p95": var_ex.p95,
            "risk_tier": var_ex.risk_tier,
            "var_pct": round(abs(min(0.0, float(var_ex.var_pct))), 1),
        }

    # NLP bar data
    nlp_df = nlp_results.get(patient_id, pd.DataFrame())
    nlp_bars = []
    if nlp_df is not None and not nlp_df.empty and "nlp_composite" in nlp_df.columns:
        date_col = "visit_date" if "visit_date" in nlp_df.columns else nlp_df.columns[0]
        for row in nlp_df.to_dict(orient="records"):
            nlp_bars.append(
                _safe_dict(
                    {
                        "date": str(row[date_col]),
                        "nlp_composite": float(row["nlp_composite"]),
                    }
                )
            )

    # NLI transformer scores table — served from startup cache (precomputed)
    nli_scores = ctx["nli_scores_cache"].get(patient_id, [])

    # Lab time series
    patient_labs = get_patient_labs(lab_df, patient_id)
    lab_series = {}
    if not patient_labs.empty:
        top_tests = (
            patient_labs.groupby("test_name")["value"]
            .count()
            .nlargest(5)
            .index.tolist()
        )
        for test in top_tests:
            subset = patient_labs[patient_labs["test_name"] == test].sort_values("date")
            ref_min_val = None
            ref_max_val = None
            rm = subset["ref_min"].dropna()
            rx = subset["ref_max"].dropna()
            if not rm.empty:
                ref_min_val = float(rm.iloc[0])
            if not rx.empty:
                ref_max_val = float(rx.iloc[0])
            lab_series[test] = {
                "dates": [str(d) for d in subset["date"].tolist()],
                "values": [float(v) for v in subset["value"].tolist()],
                "ref_min": _safe(ref_min_val),
                "ref_max": _safe(ref_max_val),
            }

    # Clinical notes
    clinical_notes = []
    if not ana_patient.empty:
        text_cols = [
            c
            for c in ["ÖYKÜ", "YAKINMA", "Muayene Notu", "Kontrol Notu"]
            if c in ana_patient.columns
        ]
        for row in ana_patient.head(5).to_dict(orient="records"):
            note = {"date": str(row.get("visit_date", "—")), "entries": []}
            for col in text_cols:
                val = row.get(col, "")
                if isinstance(val, str) and len(val.strip()) > 2:
                    note["entries"].append({"source": col, "text": val[:500]})
            if note["entries"]:
                clinical_notes.append(note)

    return {
        "summary": _safe_dict(summary),
        "comorbidities": comorbidities,
        "regime_timeline": regime_timeline,
        "prescription_dates": presc_dates,
        "var_fan": _safe_dict(var_fan) if var_fan else None,
        "nlp_bars": nlp_bars,
        "nli_scores": nli_scores,
        "lab_series": lab_series,
        "clinical_notes": clinical_notes,
    }


@app.get("/api/patient/{patient_id}/outcome")
def get_patient_outcome(patient_id: str):
    """Outcome predictor data for a patient."""
    ctx = _load_pipeline()
    profiles = ctx["profiles"]
    profiles_df = ctx["profiles_df"]

    profile = profiles.get(patient_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="No outcome profile for this patient"
        )

    # ECI gauge — replaces old CSI gauge
    eci_data = ctx["eci_by_pid"].get(patient_id, {})
    eci = {
        "score": round(float(eci_data["eci_score"]), 1)
        if eci_data.get("eci_score") is not None
        else None,
        "rating": eci_data.get("eci_rating"),
        "rating_label": eci_data.get("eci_rating_label"),
        "visit_intensity": round(float(eci_data["visit_intensity"]), 1)
        if eci_data.get("visit_intensity") is not None
        else None,
        "med_burden": round(float(eci_data["med_burden"]), 1)
        if eci_data.get("med_burden") is not None
        else None,
        "diagnostic_intensity": round(float(eci_data["diagnostic_intensity"]), 1)
        if eci_data.get("diagnostic_intensity") is not None
        else None,
        "trajectory_cost": round(float(eci_data["trajectory_cost"]), 1)
        if eci_data.get("trajectory_cost") is not None
        else None,
    }

    # SUT cost estimate for this patient
    sut_estimate = ctx["sut_by_pid"].get(patient_id)

    # Narrative — ECI-based (replaces old CSI narrative)
    narrative = predict_eci_narrative(eci_data, profile, sut_estimate)

    # ECI component breakdown (replaces old CSI feature contributions)
    feature_bar = []
    _eci_components = [
        ("Visit Intensity", eci.get("visit_intensity")),
        ("Medication Burden", eci.get("med_burden")),
        ("Diagnostic Intensity", eci.get("diagnostic_intensity")),
        ("Clinical Trajectory", eci.get("trajectory_cost")),
    ]
    for label, val in _eci_components:
        if val is not None:
            feature_bar.append({"feature": label, "value": val})

    # Cohort ranking — neighborhood only (±15 around selected patient) + percentile
    # Now uses ECI score instead of CSI
    eci_df = ctx["eci_df"]
    cohort_ranking = []
    patient_percentile = None
    if not eci_df.empty:
        rank_df = (
            eci_df[["patient_id", "eci_score"]]
            .sort_values("eci_score")
            .reset_index(drop=True)
        )
        total_patients = len(rank_df)
        patient_idx = rank_df.index[
            rank_df["patient_id"].astype(str) == str(patient_id)
        ].tolist()
        if patient_idx:
            idx = patient_idx[0]
            patient_percentile = round((idx / max(total_patients - 1, 1)) * 100, 1)
            # Window: ±15 around the patient
            window_start = max(0, idx - 15)
            window_end = min(total_patients, idx + 16)
            window_df = rank_df.iloc[window_start:window_end]
            for row in window_df.to_dict(orient="records"):
                cohort_ranking.append(
                    {
                        "patient_id": str(row["patient_id"]),
                        "label": f"P-{str(row['patient_id'])[-6:]}",
                        "eci_score": round(float(row["eci_score"]), 1),
                        "is_selected": str(row["patient_id"]) == str(patient_id),
                    }
                )

    # Feature correlations
    corr_data = []
    global _correlation_cache
    if _correlation_cache is None:
        _correlation_cache = compute_feature_correlations(
            profiles_df, target="total_visits"
        )
    corr_df = _correlation_cache
    if not corr_df.empty:
        for row in corr_df.to_dict(orient="records"):
            corr_data.append(
                _safe_dict(
                    {
                        "feature": row["feature"],
                        "spearman_r": round(float(row["spearman_r"]), 3),
                        "p_value": round(float(row["p_value"]), 3)
                        if pd.notna(row.get("p_value"))
                        else None,
                    }
                )
            )

    # SUT cost response object
    sut_cost = None
    drg_data = None
    cost_var_data = None
    gap_data = None
    trajectory_data = None

    if sut_estimate:
        sut_cost = {
            "cost_min": sut_estimate.cost_min,
            "cost_max": sut_estimate.cost_max,
            "cost_mid": sut_estimate.cost_mid,
            "cost_tier": sut_estimate.cost_tier,
            "cost_tier_label": sut_estimate.cost_tier_label,
            "breakdown": {
                "lab": {
                    "min": round(sut_estimate.breakdown.lab_cost_min, 2),
                    "max": round(sut_estimate.breakdown.lab_cost_max, 2),
                },
                "visit": {
                    "min": round(sut_estimate.breakdown.visit_cost_min, 2),
                    "max": round(sut_estimate.breakdown.visit_cost_max, 2),
                },
                "rx": {
                    "min": round(sut_estimate.breakdown.rx_cost_min, 2),
                    "max": round(sut_estimate.breakdown.rx_cost_max, 2),
                },
                "procedure": {
                    "min": round(sut_estimate.breakdown.procedure_cost_min, 2),
                    "max": round(sut_estimate.breakdown.procedure_cost_max, 2),
                },
            },
            "n_lab_tests": sut_estimate.n_lab_tests,
            "n_visits": sut_estimate.n_visits,
            "n_prescriptions": sut_estimate.n_prescriptions,
            "n_procedures": sut_estimate.n_procedures,
        }

        # Phase 4b: DRG Episode Cost Modeling
        try:
            ana_df_full = ctx["ana_df"]
            drg = compute_drg_summary(patient_id, ana_df_full, sut_estimate)
            drg_data = {
                "n_episodes": drg.n_episodes,
                "total_drg_cost": drg.total_drg_cost,
                "mean_episode_cost": drg.mean_episode_cost,
                "most_expensive_drg": drg.most_expensive_drg,
                "dominant_icd10_chapter": drg.dominant_icd10_chapter,
                "episodes": [
                    {
                        "episode_id": ep.episode_id,
                        "primary_icd10": ep.primary_icd10,
                        "primary_icd10_chapter": ep.primary_icd10_chapter,
                        "description": ep.description,
                        "los_days": ep.los_days,
                        "lab_cost": ep.lab_cost,
                        "visit_cost": ep.visit_cost,
                        "rx_cost": ep.rx_cost,
                        "procedure_cost": ep.procedure_cost,
                        "total_cost": ep.total_cost,
                        "admission_date": ep.admission_date,
                        "discharge_date": ep.discharge_date,
                    }
                    for ep in drg.episodes[:10]  # Cap at 10 episodes
                ],
            }
        except Exception as e:
            logger.warning("DRG computation failed for %s: %s", patient_id, e)

        # Phase 4c: Cost VaR (Monte Carlo)
        try:
            var_result = compute_cost_var(patient_id, sut_estimate, seed=42)
            cost_var_data = {
                "confidence_level": var_result.confidence_level,
                "var_amount": var_result.var_amount,
                "expected_cost": var_result.expected_cost,
                "cvar_amount": var_result.cvar_amount,
                "cost_p5": var_result.cost_p5,
                "cost_p25": var_result.cost_p25,
                "cost_p50": var_result.cost_p50,
                "cost_p75": var_result.cost_p75,
                "cost_p95": var_result.cost_p95,
                "simulation_count": var_result.simulation_count,
                "cost_distribution": var_result.cost_distribution,
            }
        except Exception as e:
            logger.warning("Cost VaR computation failed for %s: %s", patient_id, e)

        # Phase 4d: Reimbursement Gap Analysis
        try:
            gap_result = compute_reimbursement_gaps(patient_id, sut_estimate)
            gap_data = {
                "total_estimated_cost": gap_result.total_estimated_cost,
                "total_reimbursement": gap_result.total_reimbursement,
                "total_gap": gap_result.total_gap,
                "overall_coverage_pct": gap_result.overall_coverage_pct,
                "risk_rating": gap_result.risk_rating,
                "gaps": [
                    {
                        "category": g.category,
                        "estimated_actual_cost": g.estimated_actual_cost,
                        "sut_reimbursement": g.sut_reimbursement,
                        "gap_amount": g.gap_amount,
                        "gap_percent": g.gap_percent,
                        "status": g.status,
                    }
                    for g in gap_result.gaps
                ],
            }
        except Exception as e:
            logger.warning("Gap analysis failed for %s: %s", patient_id, e)

        # Phase 4e: Cost Trajectory Forecasting
        try:
            lab_df_full = ctx["lab_df"]
            ana_df_full = ctx["ana_df"]
            traj = compute_cost_trajectory(
                patient_id, ana_df_full, lab_df_full, sut_estimate
            )
            trajectory_data = {
                "total_forecast_cost": traj.total_forecast_cost,
                "forecast_horizon_months": traj.forecast_horizon_months,
                "trend": traj.trend,
                "monthly_burn_rate": traj.monthly_burn_rate,
                "projected_annual_cost": traj.projected_annual_cost,
                "trajectory": [
                    {
                        "period": pt.period,
                        "cumulative_cost": pt.cumulative_cost,
                        "period_cost": pt.period_cost,
                        "n_visits": pt.n_visits,
                        "n_tests": pt.n_tests,
                    }
                    for pt in traj.trajectory
                ],
            }
        except Exception as e:
            logger.warning("Cost trajectory failed for %s: %s", patient_id, e)

    return {
        "eci": eci,
        "narrative": narrative,
        "feature_bar": feature_bar,
        "cohort_ranking": cohort_ranking,
        "patient_percentile": patient_percentile,
        "cohort_total": int(len(eci_df)) if not eci_df.empty else 0,
        "feature_correlations": corr_data,
        "sut_cost": sut_cost,
        "drg_summary": drg_data,
        "cost_var": cost_var_data,
        "reimbursement_gaps": gap_data,
        "cost_trajectory": trajectory_data,
    }


@app.get("/api/validation")
def get_validation():
    """Validation experiments results."""
    ctx = _load_pipeline()
    validation_results = ctx["validation_results"]

    summary = []
    val_df = validation_summary_df(validation_results)
    if not val_df.empty:
        for idx, row_dict in enumerate(val_df.to_dict(orient="records")):
            details = (
                validation_results[idx].details
                if idx < len(validation_results)
                and validation_results[idx].details is not None
                else {}
            )
            if details.get("reason") == "constant_input":
                row_dict["Value"] = "N/A (constant input)"
                row_dict["p-value"] = "N/A (constant input)"
            summary.append(_safe_dict(row_dict))

    experiments = []
    for res in validation_results:
        experiments.append(
            _safe_dict(
                {
                    "name": res.experiment_name,
                    "hypothesis": res.hypothesis,
                    "passed": res.passed,
                    "statistic_name": res.statistic_name,
                    "statistic_value": round(res.statistic_value, 3)
                    if not np.isnan(res.statistic_value)
                    else None,
                    "p_value": round(res.p_value, 3)
                    if res.p_value is not None
                    else None,
                    "n_samples": res.n_samples,
                    "conclusion": res.conclusion,
                    "clinical_meaning": res.clinical_meaning,
                    "benchmark": res.benchmark,
                    "details": res.details if res.details else None,
                }
            )
        )

    return {"summary": summary, "experiments": experiments}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """ILAY chatbot SSE streaming endpoint."""
    import time

    user_text = ""
    if req.messages:
        last_user = [m for m in req.messages if m.get("role") == "user"]
        user_text = last_user[-1].get("content", "")[:120] if last_user else ""

    logger.info(
        "CHAT START | patient=%s | tab=%s | msgs=%d | user=%r",
        req.patient_id,
        req.active_tab,
        len(req.messages),
        user_text,
    )
    t0 = time.perf_counter()

    try:
        ctx = _load_pipeline()
        pid = req.patient_id

        profile = ctx["profiles"].get(pid)
        profiles_df = ctx["profiles_df"]
        composites_df = ctx["composites"]
        composites_idx = ctx["composites_idx"]
        comp_row = None
        if pid in composites_idx:
            comp_row = composites_df.iloc[[composites_idx[pid]]]
        regimes = ctx["regimes"]
        regime_r = regimes.get(pid)
        _lks = regime_r.last_known_state() if regime_r else None
        regime_state = _lks.value if _lks is not None else "Insufficient Data"
        var_result = ctx["var_results"].get(pid)
        var_summary = ctx["var_summary"]

        # Use pre-cached KPI scalars
        n_patients = ctx["kpi_n_patients"]
        mean_score = ctx["kpi_mean_score"]
        n_high_risk = ctx["kpi_n_high_risk"]
        n_critical = ctx["kpi_n_critical"]
        total_rx = ctx["kpi_total_rx"]
        rating_dist = ctx["kpi_rating_dist"]
        regime_dist = ctx["kpi_regime_dist"]

        patient_context = build_patient_context(
            patient_id=pid,
            profile=profile,
            comp_row=comp_row,
            regime_state=regime_state,
            var_result=var_result,
            nlp_results=ctx["nlp_results"],
            ana_df=ctx["ana_df"],
            lab_df=ctx["lab_df"],
            rec_df=ctx["rec_df"],
            eci_data=ctx["eci_by_pid"].get(pid),
            sut_estimate=ctx["sut_by_pid"].get(pid),
        )
        cohort_context = build_cohort_context(
            active_tab=req.active_tab,
            kpi={
                "n_patients": n_patients,
                "mean_score": round(mean_score, 1),
                "n_high_risk": n_high_risk,
                "n_critical": n_critical,
                "total_rx": total_rx,
            },
            rating_distribution=rating_dist,
            regime_distribution=regime_dist,
            var_summary=var_summary,
        )
        chat_context = f"{cohort_context}\n\n{patient_context}"
    except Exception as exc:
        logger.error(
            "CHAT CONTEXT BUILD FAILED | patient=%s | error=%s",
            req.patient_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to build patient context: {exc}"
        )

    async def sse_generator():
        token_count = 0
        try:
            async for token in stream_chat_response(req.messages, chat_context):
                token_count += 1
                # JSON-encode tokens so newlines / special chars don't break SSE framing
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as exc:
            logger.error(
                "CHAT STREAM ERROR | patient=%s | tokens_sent=%d | error=%s",
                pid,
                token_count,
                exc,
                exc_info=True,
            )
            error_payload = json.dumps(f"\n⚠️ Stream error: {exc}")
            yield f"data: {error_payload}\n\n"
        finally:
            elapsed = time.perf_counter() - t0
            logger.info(
                "CHAT END | patient=%s | tokens=%d | elapsed=%.2fs",
                pid,
                token_count,
                elapsed,
            )
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
