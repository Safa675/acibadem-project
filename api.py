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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import pandas as pd
import numpy as np

from src import (
    load_all_data,
    HealthIndexBuilder,
    classify_all_patients,
    score_patient_visits,
    compute_all_composites,
    dual_nlp_score,
    get_patient_labs,
    get_patient_prescriptions,
    build_all_outcome_profiles,
    profiles_to_dataframe,
    compute_feature_correlations,
    predict_care_duration_narrative,
    run_all_validations,
    validation_summary_df,
)
from src.chatbot import stream_chat_response, build_patient_context
from src.health_var import compute_health_var

# Force-load NLP transformer at startup
from src.nlp_signal import _load_transformer
import src.nlp_signal as _nlp_mod

if _nlp_mod._transformer_available is None:
    _load_transformer()

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


# ── Pipeline Cache ───────────────────────────────────────────────────────────

_pipeline_cache: dict | None = None


def _load_pipeline() -> dict:
    global _pipeline_cache
    if _pipeline_cache is not None:
        return _pipeline_cache

    data = load_all_data(str(_THIS_DIR))
    lab_df = data["lab"]
    ana_df = data["ana"]
    rec_df = data["rec"]

    builder = HealthIndexBuilder(lab_df, ana_df, vital_weight=0.45)
    all_lab_patients = lab_df["patient_id"].unique().tolist()

    all_snapshots = {}
    all_series = {}
    for pid in all_lab_patients:
        snaps = builder.build_patient_series(pid)
        if snaps:
            all_snapshots[pid] = snaps
            all_series[pid] = builder.to_series_points(snaps)

    regimes = classify_all_patients(all_snapshots)

    var_results_by_pid = {}
    for _pid, _series in all_series.items():
        _vr = compute_health_var(
            _pid, _series, horizon_draws=3, iterations=3000, seed=42
        )
        if _vr is not None:
            var_results_by_pid[_pid] = _vr

    _var_rows = []
    for _vr in var_results_by_pid.values():
        _var_rows.append(
            {
                "patient_id": _vr.patient_id,
                "current_score": _vr.current_score,
                "var_pct": _vr.var_pct,
                "health_var_score": _vr.p05,
                "median_forecast": _vr.p50,
                "risk_tier": _vr.risk_tier,
                "risk_label": _vr.risk_label,
            }
        )
    var_summary = (
        pd.DataFrame(_var_rows).sort_values("var_pct").reset_index(drop=True)
        if _var_rows
        else pd.DataFrame()
    )

    nlp_results = {}
    for pid in ana_df["patient_id"].unique():
        nlp_results[int(pid)] = score_patient_visits(ana_df, int(pid))

    latest_health = {
        pid: snaps[-1].health_score for pid, snaps in all_snapshots.items()
    }
    latest_nlp = {}
    for pid, snaps in all_snapshots.items():
        last_snap_date = snaps[-1].date
        nlp_df = nlp_results.get(pid, pd.DataFrame())
        if (
            not nlp_df.empty
            and "nlp_composite" in nlp_df.columns
            and "visit_date" in nlp_df.columns
        ):
            nlp_copy = nlp_df.copy()
            nlp_copy["visit_date"] = pd.to_datetime(nlp_copy["visit_date"])
            past_nlp = nlp_copy[nlp_copy["visit_date"] <= last_snap_date]
            if not past_nlp.empty:
                latest_nlp[pid] = float(past_nlp.iloc[-1]["nlp_composite"])
            elif not nlp_copy.empty:
                latest_nlp[pid] = float(nlp_copy["nlp_composite"].iloc[0])
            else:
                latest_nlp[pid] = 0.0
        else:
            latest_nlp[pid] = 0.0

    composites = compute_all_composites(latest_health, latest_nlp, rec_df, ana_df)

    # Precompute NLI transformer scores for all patients at startup (expensive — do once)
    _all_text_cols = ["ÖYKÜ", "Muayene Notu", "Kontrol Notu", "YAKINMA", "Tedavi Notu"]
    nli_scores_cache: dict[int, list] = {}
    for _pid in ana_df["patient_id"].unique():
        _ana_pt = ana_df[ana_df["patient_id"] == _pid]
        _avail_cols = [c for c in _all_text_cols if c in _ana_pt.columns]
        _scores: list = []
        if _avail_cols and not _ana_pt.empty:
            for _, _vrow in _ana_pt.iterrows():
                _vdate = _vrow.get("visit_date", None)
                _vdate_str = (
                    pd.Timestamp(_vdate).strftime("%Y-%m-%d")
                    if _vdate is not None
                    and not (isinstance(_vdate, float) and pd.isna(_vdate))
                    else "—"
                )
                for _tcol in _avail_cols:
                    _txt = _vrow.get(_tcol, None)
                    if isinstance(_txt, str) and _txt.strip():
                        _res = dual_nlp_score(_txt)
                        _scores.append(
                            {
                                "date": _vdate_str,
                                "source": _tcol,
                                "text": _txt[:300],
                                "nli_score": round(_res["combined"], 3),
                            }
                        )
        nli_scores_cache[int(_pid)] = _scores

    profiles = build_all_outcome_profiles(
        all_snapshots, regimes, ana_df, rec_df, nlp_results
    )
    profiles_df = profiles_to_dataframe(profiles)

    var_sum_for_val = var_summary if not var_summary.empty else None
    validation_results = run_all_validations(profiles_df, var_sum_for_val)

    _pipeline_cache = {
        "lab_df": lab_df,
        "ana_df": ana_df,
        "rec_df": rec_df,
        "all_snapshots": all_snapshots,
        "all_series": all_series,
        "regimes": regimes,
        "var_summary": var_summary,
        "nlp_results": nlp_results,
        "composites": composites,
        "profiles_df": profiles_df,
        "profiles": {p.patient_id: p for p in profiles},
        "validation_results": validation_results,
        "var_results": var_results_by_pid,
        "nli_scores_cache": nli_scores_cache,
    }
    return _pipeline_cache


# ── Startup event ────────────────────────────────────────────────────────────


@app.on_event("startup")
async def startup():
    _load_pipeline()


# ── Pydantic Models ──────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    messages: list[dict]
    patient_id: int


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/api/patients")
def get_patients():
    """List all patient IDs."""
    ctx = _load_pipeline()
    return {"patients": sorted(ctx["regimes"].keys())}


@app.get("/api/cohort")
def get_cohort():
    """Cohort overview: KPI metrics + composites + var summary."""
    ctx = _load_pipeline()
    lab_df = ctx["lab_df"]
    rec_df = ctx["rec_df"]
    composites = ctx["composites"]
    profiles_df = ctx["profiles_df"]
    regimes = ctx["regimes"]
    var_summary = ctx["var_summary"]

    n_patients = int(lab_df["patient_id"].nunique())
    mean_score = (
        float(profiles_df["mean_health_score"].mean()) if not profiles_df.empty else 0
    )
    n_high_risk = (
        int(len(composites[composites["rating"].isin(["BB", "B/CCC"])]))
        if not composites.empty
        else 0
    )
    n_critical = sum(
        1
        for r in regimes.values()
        if r.last_known_state() is not None and r.last_known_state().value == "Critical"
    )
    total_rx = int(len(rec_df))

    # Composites table
    composites_list = []
    if not composites.empty:
        display_df = composites.copy().sort_values("composite_score", ascending=False)
        if not profiles_df.empty:
            display_df = display_df.merge(
                profiles_df[
                    [
                        "patient_id",
                        "csi_score",
                        "csi_tier",
                        "n_prescriptions",
                        "n_comorbidities",
                        "age",
                    ]
                ],
                on="patient_id",
                how="left",
            )
        for _, row in display_df.iterrows():
            composites_list.append(_safe_dict(row.to_dict()))

    # VaR summary
    var_list = []
    if not var_summary.empty:
        for _, row in var_summary.iterrows():
            r = row.to_dict()
            r["downside_var_pct"] = round(abs(min(float(r.get("var_pct", 0)), 0.0)), 1)
            var_list.append(_safe_dict(r))

    # Rating distribution
    rating_dist = {}
    if not composites.empty:
        for rating, count in composites["rating"].value_counts().items():
            rating_dist[rating] = int(count)

    # Regime state distribution
    regime_dist = {}
    for regime_result in regimes.values():
        state = regime_result.last_known_state()
        state_str = state.value if state is not None else "Insufficient Data"
        regime_dist[state_str] = regime_dist.get(state_str, 0) + 1

    # Cohort scatter data
    scatter_data = []
    if not composites.empty:
        merged = composites.copy()
        if not profiles_df.empty:
            merged = merged.merge(
                profiles_df[["patient_id", "csi_score"]], on="patient_id", how="left"
            )
        for _, row in merged.iterrows():
            scatter_data.append(
                _safe_dict(
                    {
                        "patient_id": int(row["patient_id"]),
                        "health_index_score": float(row.get("health_index_score", 0)),
                        "nlp_score": float(row.get("nlp_score", 0)),
                        "rating": row.get("rating", "N/A"),
                        "csi_score": float(row.get("csi_score", 30))
                        if "csi_score" in row
                        else 30,
                    }
                )
            )

    return {
        "kpi": {
            "n_patients": n_patients,
            "mean_score": round(mean_score, 1),
            "n_high_risk": n_high_risk,
            "n_critical": n_critical,
            "total_rx": total_rx,
        },
        "composites": composites_list,
        "var_summary": var_list,
        "rating_distribution": rating_dist,
        "regime_distribution": regime_dist,
        "scatter_data": scatter_data,
    }


@app.get("/api/patient/{patient_id}")
def get_patient(patient_id: int):
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
    comp_row = (
        composites[composites["patient_id"] == patient_id]
        if not composites.empty
        else None
    )
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

    summary = {
        "patient_id": patient_id,
        "rating": rating,
        "composite_score": round(comp_score, 1),
        "regime_state": last_state,
        "health_score": round(profile.final_health_score, 1) if profile else None,
        "downside_var_pct": round(abs(min(var_ex.var_pct, 0.0)), 1) if var_ex else None,
        "csi_score": round(profile.csi_score, 1) if profile else None,
        "csi_tier": profile.csi_tier if profile else None,
        "age": round(profile.age) if profile and profile.age else None,
        "sex": profile.sex if profile else None,
        "n_comorbidities": profile.n_comorbidities if profile else 0,
        "total_visits": int(profile.total_visits)
        if profile and profile.total_visits
        else None,
        "n_lab_draws": profile.n_lab_draws if profile else 0,
        "n_prescriptions": profile.n_prescriptions if profile else 0,
    }

    # Comorbidities
    ana_patient = ana_df[ana_df["patient_id"] == patient_id]
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
            for _, row in rdf.iterrows():
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
    series_pts = all_series.get(patient_id, [])
    if var_ex and series_pts:
        dates = [str(p.date) for p in series_pts]
        scores = [p.value for p in series_pts]
        last_date = pd.Timestamp(series_pts[-1].date)
        delta = (
            (pd.Timestamp(series_pts[-1].date) - pd.Timestamp(series_pts[-2].date)).days
            if len(series_pts) >= 2
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
        for _, row in nlp_df.iterrows():
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
    patient_labs = lab_df[lab_df["patient_id"] == patient_id].copy()
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
        for _, row in ana_patient.head(5).iterrows():
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
def get_patient_outcome(patient_id: int):
    """Outcome predictor data for a patient."""
    ctx = _load_pipeline()
    profiles = ctx["profiles"]
    profiles_df = ctx["profiles_df"]

    profile = profiles.get(patient_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="No outcome profile for this patient"
        )

    # CSI gauge
    csi = {"score": round(profile.csi_score, 1), "tier": profile.csi_tier}

    # Narrative
    narrative = predict_care_duration_narrative(profile)

    # Feature contributions
    feature_bar = []
    if profile.feature_contributions:
        for k, v in profile.feature_contributions.items():
            feature_bar.append(
                {"feature": k.replace("_", " ").title(), "value": round(v, 1)}
            )

    # Cohort ranking
    cohort_ranking = []
    if not profiles_df.empty:
        rank_df = profiles_df.sort_values("csi_score").copy()
        for _, row in rank_df.iterrows():
            cohort_ranking.append(
                {
                    "patient_id": int(row["patient_id"]),
                    "label": f"P-{str(int(row['patient_id']))[-4:]}",
                    "csi_score": round(float(row["csi_score"]), 1),
                    "is_selected": int(row["patient_id"]) == patient_id,
                }
            )

    # Feature correlations
    corr_data = []
    corr_df = compute_feature_correlations(profiles_df, target="total_visits")
    if not corr_df.empty:
        for _, row in corr_df.iterrows():
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

    return {
        "csi": csi,
        "narrative": narrative,
        "feature_bar": feature_bar,
        "cohort_ranking": cohort_ranking,
        "feature_correlations": corr_data,
    }


@app.get("/api/validation")
def get_validation():
    """Validation experiments results."""
    ctx = _load_pipeline()
    validation_results = ctx["validation_results"]

    summary = []
    val_df = validation_summary_df(validation_results)
    if not val_df.empty:
        for _, row in val_df.iterrows():
            summary.append(_safe_dict(row.to_dict()))

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
        "CHAT START | patient=%s | msgs=%d | user=%r",
        req.patient_id,
        len(req.messages),
        user_text,
    )
    t0 = time.perf_counter()

    try:
        ctx = _load_pipeline()
        pid = req.patient_id

        profile = ctx["profiles"].get(pid)
        composites_df = ctx["composites"]
        comp_row = (
            composites_df[composites_df["patient_id"] == pid]
            if not composites_df.empty
            else None
        )
        regimes = ctx["regimes"]
        regime_r = regimes.get(pid)
        _lks = regime_r.last_known_state() if regime_r else None
        regime_state = _lks.value if _lks is not None else "Insufficient Data"
        var_result = ctx["var_results"].get(pid)

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
        )
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
            async for token in stream_chat_response(req.messages, patient_context):
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
