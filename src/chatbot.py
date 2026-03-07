"""
chatbot.py
ILAY — OpenRouter-powered chatbot with patient data awareness.

Uses the OpenRouter API (OpenAI-compatible) to answer user questions about
the platform. Supports async streaming via httpx.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import AsyncIterator

import httpx

logger = logging.getLogger("ilay.chatbot")

# Load .env from the project root (two levels up from src/)
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed — fall back to environment variables

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.0-flash-001"

SYSTEM_PROMPT = """\
You are ILAY. And this is your platform — an AI-powered clinical risk \
intelligence platform developed by Acıbadem University for the ACUHIT Hackathon 2026.

Your job is to help doctors, nurses, and clinical staff understand dashboard metrics \
using both cohort-level and selected-patient data (provided below each message). \
Use those numbers to give specific, data-driven answers — never say you don't have access.

═══════════════════════════════════════════
LANGUAGE RULE (CRITICAL)
═══════════════════════════════════════════
- If the user writes in English → reply in English.
- If the user writes in Turkish → reply in Turkish.
- Always match the user's language. Never force one language.

═══════════════════════════════════════════
CONTEXT ROUTING RULE (CRITICAL)
═══════════════════════════════════════════
Each turn includes:
- ACTIVE DASHBOARD TAB
- CURRENT COHORT DATA
- SELECTED PATIENT DATA

How to choose scope:
- Cohort wording (population, cohort, distribution, "patients", "overall") -> answer from CURRENT COHORT DATA.
- Patient wording ("this patient", singular patient detail) -> answer from SELECTED PATIENT DATA.
- Comparison wording ("compare cohort vs this patient") -> use both sections.
- If scope is ambiguous, ask one short clarification question:
  "Do you want cohort-wide or selected-patient interpretation?"

═══════════════════════════════════════════
METRICS — FULL REFERENCE
═══════════════════════════════════════════

1) HEALTH SCORE — 0 to 100
   • Composite score from lab results + vital signs.
   • Each lab test is z-scored against its reference range.
   • Vitals (BP, pulse, SpO2) normalized using clinical standards.
   • Formula: 100 × exp(−0.25 × mean_z) where mean_z is weighted organ-system z-score
   • 100 = perfectly normal, 0 = maximally abnormal
   • Vital weight: 45% (based on NEWS AUROC 0.867)
   • Turkish population reference ranges (Ozarda 2014, PMID: 25153598)
   • Recalculated at each lab draw → forms a time series

2) PatientRegime™ — 4 states
   • Classifies the patient's health trajectory over time.
   • States:
     - Stable: Score steady, low volatility
     - Recovering: Upward trend, score improving
     - Deteriorating: Downward trend, score declining
     - Critical: Steep decline + high volatility
   • Uses 3-draw moving average + rolling standard deviation
   • Finance analogy: market regime detection (bull/bear/stress)
   • Requires minimum 4 lab draws; fewer → "Insufficient Data"

3) Health VaR™ — Monte Carlo Forecast
   • "With 95% confidence, health score won't fall below X in the next 3 lab-draw cycles."
   • 3,000 Monte Carlo bootstrap iterations
   • Risk tiers:
     - GREEN (VaR > +5%): Stable or improving
     - YELLOW (0% to +5%): Slight risk, monitor
     - ORANGE (−10% to 0%): Moderate risk, review within 24h
     - RED (< −10%): High risk, prioritize intervention
   • Fan chart shows 5th–95th percentile confidence band
   • Finance analogy: Value at Risk (VaR)

4) NLP SCORE — −1 to +1
   • AI analysis of doctor's clinical notes (Turkish text)
   • Zero-Shot NLI: Multilingual NLI model (MiniLMv2) reasons about
     clinical meaning without task-specific training
   • Negative (→ −1) = deterioration language detected
   • Positive (→ +1) = recovery language detected
   • Near zero = neutral language
   • Extracts from: ÖYKÜ, Muayene Notu, Kontrol Notu, YAKINMA, Tedavi Notu

5) COMPOSITE RISK RATING — AAA to B/CCC
   • Final risk score fusing three data sources:
     - 55% Health Index (lab + vital) — strongest predictor
     - 30% NLP score — clinical notes insight
     - 15% Medication change velocity — polypharmacy risk
   • Rating tiers:
     - AAA (≥85): Excellent — stable, positive prognosis
     - AA (70–84): Good — minor abnormalities, low risk
     - A (55–69): Moderate — monitoring recommended
     - BBB (40–54): Below average — clinical review needed
     - BB (25–39): Elevated risk — active intervention recommended
     - B/CCC (<25): High risk — urgent clinical attention required
   • Finance analogy: credit rating (S&P, Moody's)

6) CSI — Clinical Severity Index — 0 to 100
   • Predicts healthcare utilization intensity.
   • 6 features with exact weights (each sub-score normalized 0–100 before weighting):
     - Health Score Trend (25%): slope mapped so −5/obs → 100, +5/obs → 0
     - Lab Volatility (20%): std dev mapped so 0 → 0, 20+ → 100
     - Critical Regime Fraction (20%): % time in Critical state × 100
     - NLP Signal (15%): NLP score mapped so −1 → 100, +1 → 0
     - Prescription Intensity (10%): Rx velocity mapped so 0 → 0, 10+/mo → 100
     - Comorbidity Burden (10%): comorbidity count mapped so 0 → 0, 4+ → 100
   • The SELECTED PATIENT DATA section includes the exact point contribution of EACH factor
     (feature_contributions dict). USE THESE NUMBERS when explaining the CSI.
   • Tiers: LOW (0–25), MODERATE (25–50), HIGH (50–75), CRITICAL (75–100)
   • 0 = minimal burden, 100 = maximum burden

═══════════════════════════════════════════
COMORBIDITY COLUMNS IN DATA
═══════════════════════════════════════════
The dataset tracks these conditions per patient:
• Hipertansiyon (Hypertension)
• Kalp Damar (Cardiovascular Disease)
• Diyabet (Diabetes)
• Kan Hastalıkları (Blood Disorders)
• Kronik Hastalıklar Diğer (Other Chronic Diseases)
• Ameliyat Geçmişi (Surgical History)

═══════════════════════════════════════════
GENERAL INFORMATION
═══════════════════════════════════════════
• ILAY adapts financial risk analysis methods to healthcare.
• All analyses run on real patient data (labdata.ods, anadata.ods, recete.ods)
• The platform has 5 tabs: Cohort Overview, Patient Explorer, Outcome Predictor, Validation, AI Assistant
• Finance → Healthcare analogies:
  - Market Regime → Patient State (PatientRegime™)
  - Value at Risk → Health VaR™
  - Credit Rating → Composite Risk Rating
  - Monte Carlo Simulation → Health forecasting
  - Earnings Call NLP → Turkish clinical note NLP

RESPONSE RULES (YOU MUST FOLLOW THESE STRICTLY):
• Write like a real person — a knowledgeable clinician speaking to a colleague. Casual, precise, no fluff.
• Do NOT use **bold** at all. Zero asterisks. Write plain text only.
• Do NOT use markdown tables, headers (##), horizontal rules (---), or any structured formatting.
• Do NOT start messages with filler like "Great question!", "Sure!", "Here's the breakdown:", "Let me explain".
• Adapt length to complexity:
  - Simple factual question (what is X, what's the score) → 1-3 sentences, direct.
  - Technical or analytical question (why is X, what's driving Y, explain Z) → go as deep as needed.
    Use exact numbers from the patient data. Walk through each factor if relevant. Don't cut the answer short.
  - Conversational chitchat → keep it very short.
• Always use the actual numbers from the relevant context section (cohort and/or selected patient).
  Never speak in vague generalities when exact values are available.
• Sound human. Imagine you're a doctor leaning over to a colleague saying "hey so basically..."
• No bullet points unless listing 3+ genuinely separate items.
• Max 1 emoji per message, only for risk tier color if relevant. Usually zero emoji.
• Do NOT give medical treatment advice — only explain what the data shows.
• If comparing two metrics, explain the difference in one flowing paragraph, not in sections.
"""


_CSI_FACTOR_LABELS = {
    "health_trend": "Health Score Trend (25%)",
    "lab_volatility": "Lab Volatility (20%)",
    "critical_fraction": "Critical Regime Fraction (20%)",
    "nlp_signal": "NLP Signal (15%)",
    "prescription_intensity": "Prescription Intensity (10%)",
    "comorbidity_burden": "Comorbidity Burden (10%)",
}


def build_cohort_context(
    active_tab: str,
    kpi: dict,
    rating_distribution: dict[str, int],
    regime_distribution: dict[str, int],
    var_summary=None,
) -> str:
    """Build a cohort-level context block for scope-aware chat responses."""
    lines = [
        f"\n═══ ACTIVE DASHBOARD TAB: {active_tab or 'Unknown'} ═══",
        "═══ CURRENT COHORT DATA ═══",
    ]

    n_patients = int(kpi.get("n_patients", 0))
    mean_score = float(kpi.get("mean_score", 0.0))
    n_high_risk = int(kpi.get("n_high_risk", 0))
    n_critical = int(kpi.get("n_critical", 0))
    total_rx = int(kpi.get("total_rx", 0))

    lines.append(f"• Monitored Patients: {n_patients}")
    lines.append(f"• Mean Health Score: {mean_score:.1f}")
    lines.append(f"• High-Risk Patients (VaR RED, var_pct < -10%): {n_high_risk}")
    lines.append(f"• Critical State Now: {n_critical}")
    lines.append(f"• Total Prescriptions: {total_rx}")

    rating_order = ["AAA", "AA", "A", "BBB", "BB", "B/CCC"]
    if rating_distribution:
        lines.append("\n⭐ RATING DISTRIBUTION:")
        for rating in rating_order:
            if rating in rating_distribution:
                lines.append(f"  • {rating}: {int(rating_distribution[rating])}")

    if regime_distribution:
        lines.append("\n🏥 REGIME DISTRIBUTION:")
        for state, count in sorted(regime_distribution.items(), key=lambda x: x[0]):
            lines.append(f"  • {state}: {int(count)}")

    if (
        var_summary is not None
        and hasattr(var_summary, "empty")
        and not var_summary.empty
    ):
        if "risk_tier" in var_summary.columns:
            lines.append("\n📉 HEALTH VaR TIER COUNTS:")
            tier_counts = var_summary["risk_tier"].value_counts().to_dict()
            for tier in ["RED", "ORANGE", "YELLOW", "GREEN"]:
                if tier in tier_counts:
                    lines.append(f"  • {tier}: {int(tier_counts[tier])}")

        if {"patient_id", "var_pct", "risk_tier"}.issubset(set(var_summary.columns)):
            lines.append("\n📌 WORST DOWNSIDE VaR PATIENTS (Top 5 by var_pct):")
            worst = var_summary.sort_values("var_pct", ascending=True).head(5)
            for _, row in worst.iterrows():
                lines.append(
                    f"  • Patient {row['patient_id']}: {float(row['var_pct']):.1f}% ({row['risk_tier']})"
                )

    lines.append("═══ END COHORT DATA ═══")
    return "\n".join(lines)


def build_patient_context(
    patient_id: str,
    profile,
    comp_row,
    regime_state: str,
    var_result=None,
    nlp_results=None,
    ana_df=None,
    lab_df=None,
    rec_df=None,
) -> str:
    """Build a text block summarizing the current patient's data for the LLM."""
    lines = [f"\n═══ SELECTED PATIENT DATA: Patient #{patient_id} ═══"]

    # Demographics
    if profile:
        age = f"{profile.age:.0f}" if profile.age else "Unknown"
        sex = profile.sex or "Unknown"
        lines.append(f"• Age: {age}, Sex: {sex}")
        lines.append(f"• Comorbidities: {profile.n_comorbidities}")
        lines.append(
            f"• Total Visits: {int(profile.total_visits) if profile.total_visits else 'N/A'}"
        )
        lines.append(f"• Lab Draws: {profile.n_lab_draws}")
        lines.append(f"• Prescriptions: {profile.n_prescriptions}")
        lines.append(
            f"• Prescription Velocity: {profile.prescription_velocity:.2f} Rx/30 days"
        )

    # Health Score
    if profile:
        lines.append(f"\n📊 HEALTH SCORE:")
        lines.append(f"  Initial: {profile.initial_health_score:.1f}")
        lines.append(f"  Current (Latest): {profile.final_health_score:.1f}")
        lines.append(f"  Mean: {profile.mean_health_score:.1f}")
        lines.append(
            f"  Trend (slope): {profile.health_score_trend:.3f} per observation"
        )
        lines.append(f"  Volatility (std): {profile.health_score_volatility:.2f}")

    # Regime
    lines.append(f"\n🏥 PATIENT REGIME: {regime_state}")

    # Composite Rating
    if comp_row is not None and not comp_row.empty:
        row = comp_row.iloc[0] if hasattr(comp_row, "iloc") else comp_row
        lines.append(f"\n⭐ COMPOSITE RISK RATING:")
        lines.append(f"  Rating: {row.get('rating', 'N/A')}")
        lines.append(f"  Composite Score: {row.get('composite_score', 0):.1f}/100")
        lines.append(
            f"  Health Index Component: {row.get('health_index_score', 0):.1f}"
        )
        lines.append(f"  NLP Component (0-100): {row.get('nlp_score', 0):.1f}")

    # VaR
    if var_result:
        lines.append(f"\n📉 HEALTH VaR™:")
        lines.append(f"  Current Score: {var_result.current_score:.1f}")
        lines.append(f"  VaR (5th percentile): {var_result.p05:.1f}")
        lines.append(f"  Median Forecast: {var_result.p50:.1f}")
        lines.append(f"  VaR %: {var_result.var_pct:.1f}%")
        lines.append(f"  Risk Tier: {var_result.risk_tier} — {var_result.risk_label}")

    # CSI — full breakdown including per-factor contributions
    if profile:
        lines.append(f"\n🎯 CLINICAL SEVERITY INDEX (CSI):")
        lines.append(f"  CSI Score: {profile.csi_score:.1f}/100")
        lines.append(f"  CSI Tier: {profile.csi_tier}")
        lines.append(f"  CSI Label: {getattr(profile, 'csi_label', 'N/A')}")
        lines.append(f"  Critical Episodes: {profile.n_critical_episodes}")
        lines.append(f"  Critical Fraction: {profile.critical_fraction:.1%}")
        lines.append(f"  Mean NLP Composite: {profile.mean_nlp_composite:.3f}")

        # Per-factor weighted point contributions — the key data for precise explanations
        feature_contribs = getattr(profile, "feature_contributions", {})
        if feature_contribs:
            lines.append(
                f"  CSI Factor Contributions (weighted points out of total {profile.csi_score:.1f}):"
            )
            for key, label in _CSI_FACTOR_LABELS.items():
                val = feature_contribs.get(key, 0.0)
                lines.append(f"    - {label}: {val:.2f} pts")

    # Comorbidities detail
    if ana_df is not None:
        patient_ana = ana_df[ana_df["patient_id"] == patient_id]
        if not patient_ana.empty:
            comorbidity_cols = [
                ("Hipertansiyon Hastada", "Hypertension"),
                ("Kalp Damar Hastada", "Cardiovascular Disease"),
                ("Diyabet Hastada", "Diabetes"),
                ("Kan Hastalıkları Hastada", "Blood Disorders"),
                ("Kronik Hastalıklar Diğer", "Other Chronic Diseases"),
                ("Ameliyat Geçmişi", "Surgical History"),
            ]
            active = []
            for col, label in comorbidity_cols:
                if col in patient_ana.columns:
                    vals = patient_ana[col].dropna()
                    for v in vals:
                        if isinstance(v, str) and len(v.strip()) >= 1:
                            active.append(f"{label}: {v.strip()}")
                            break
                        elif not isinstance(v, str) and v and v > 0:
                            active.append(label)
                            break
            if active:
                lines.append(f"\n🏥 COMORBIDITIES / CONDITIONS:")
                for c in active:
                    lines.append(f"  • {c}")

            # Clinical notes excerpts (last 2 visits)
            text_cols = [
                "YAKINMA",
                "ÖYKÜ",
                "Muayene Notu",
                "Kontrol Notu",
                "Tedavi Notu",
            ]
            available_text_cols = [c for c in text_cols if c in patient_ana.columns]
            if available_text_cols:
                lines.append(f"\n📝 RECENT CLINICAL NOTES (last 2 visits):")
                for _, row in patient_ana.tail(2).iterrows():
                    visit_date = row.get("visit_date", "—")
                    lines.append(f"  Visit: {visit_date}")
                    for col in available_text_cols:
                        val = row.get(col, "")
                        if isinstance(val, str) and len(val.strip()) > 2:
                            excerpt = val[:300] + ("…" if len(val) > 300 else "")
                            lines.append(f"    {col}: {excerpt}")

    # Recent lab tests
    if lab_df is not None:
        patient_labs = lab_df[lab_df["patient_id"] == patient_id].sort_values("date")
        if not patient_labs.empty:
            latest = patient_labs.groupby("test_name").last().reset_index()
            lines.append(f"\n🔬 LATEST LAB RESULTS ({len(latest)} tests):")
            for _, row in latest.head(15).iterrows():
                ref_info = ""
                if "ref_min" in row and "ref_max" in row:
                    rmin = row.get("ref_min")
                    rmax = row.get("ref_max")
                    if (
                        rmin is not None
                        and rmax is not None
                        and not (
                            isinstance(rmin, float) and __import__("math").isnan(rmin)
                        )
                    ):
                        ref_info = f" [ref: {rmin}-{rmax}]"
                lines.append(f"  • {row['test_name']}: {row['value']}{ref_info}")

    lines.append("═══ END SELECTED PATIENT DATA ═══")
    return "\n".join(lines)


def _build_messages(messages: list[dict], runtime_context: str) -> list[dict]:
    """Prepend system prompt + context block to the message list."""
    system_content = SYSTEM_PROMPT
    if runtime_context:
        system_content += "\n\n" + runtime_context
    return [{"role": "system", "content": system_content}] + messages


def _get_api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY", "").strip() or None


async def stream_chat_response(
    messages: list[dict], runtime_context: str = ""
) -> AsyncIterator[str]:
    """
    Async generator that streams text tokens from OpenRouter using SSE.

    Yields plain text chunks as they arrive. Yields an error string prefixed
    with "⚠️" on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("OPENROUTER_API_KEY not set — cannot call LLM")
        yield "⚠️ OpenRouter API key not found. Set OPENROUTER_API_KEY in your .env file."
        return

    full_messages = _build_messages(messages, runtime_context)

    msg_count = len(full_messages)
    ctx_len = len(runtime_context)
    logger.info(
        "LLM REQUEST | model=%s | msgs=%d | context_chars=%d",
        MODEL,
        msg_count,
        ctx_len,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://ilay.app",
        "X-Title": "ILAY",
    }
    payload = {
        "model": MODEL,
        "messages": full_messages,
        "max_tokens": 800,
        "temperature": 0.4,
        "stream": True,
    }

    t0 = time.perf_counter()
    token_count = 0

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                OPENROUTER_BASE_URL,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    error_text = body.decode()[:500]
                    logger.error(
                        "LLM API ERROR | status=%d | body=%s",
                        response.status_code,
                        error_text,
                    )
                    yield f"⚠️ API error {response.status_code}: {error_text[:200]}"
                    return

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        token = delta.get("content")
                        if token:
                            token_count += 1
                            yield token
                    except (json.JSONDecodeError, KeyError, IndexError) as exc:
                        logger.warning(
                            "LLM CHUNK PARSE ERROR | data=%r | error=%s",
                            data[:200],
                            exc,
                        )
                        continue

        elapsed = time.perf_counter() - t0
        logger.info(
            "LLM RESPONSE OK | tokens=%d | elapsed=%.2fs",
            token_count,
            elapsed,
        )

    except httpx.TimeoutException:
        logger.error(
            "LLM TIMEOUT after %.1fs | tokens_before_timeout=%d",
            time.perf_counter() - t0,
            token_count,
        )
        yield "\n⚠️ Request timed out. Please try again."
    except httpx.RequestError as exc:
        logger.error("LLM NETWORK ERROR | error=%s", exc, exc_info=True)
        yield f"\n⚠️ Network error: {exc}"
