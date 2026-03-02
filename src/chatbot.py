"""
chatbot.py
ILAY — OpenRouter-powered chatbot with patient data awareness.

Uses the OpenRouter API (OpenAI-compatible) to answer user questions about
the platform.
"""

from __future__ import annotations

import os
import requests
from pathlib import Path

# Load .env from the project root (two levels up from src/)
try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed — fall back to environment variables

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3.5-flash-02-23"

SYSTEM_PROMPT = """\
You are ILAY. And this is your platform its an AI-powered clinical risk \
intelligence platform developed by Acıbadem University for the ACUHIT Hackathon 2026.

Your job is to help doctors, nurses, and clinical staff understand dashboard metrics \
and the current patient's data. You have FULL ACCESS to the patient's computed metrics \
(provided to you in the CURRENT PATIENT DATA section below each message). Use that data \
to give specific, data-driven answers — never say you don't have access.

═══════════════════════════════════════════
LANGUAGE RULE (CRITICAL)
═══════════════════════════════════════════
- If the user writes in English → reply in English.
- If the user writes in Turkish → reply in Turkish.
- Always match the user's language. Never force one language.

═══════════════════════════════════════════
METRICS — FULL REFERENCE
═══════════════════════════════════════════

1) HEALTH SCORE — 0 to 100
   • Composite score from lab results + vital signs.
   • Each lab test is z-scored against its reference range.
   • Vitals (BP, pulse, SpO2) normalized using clinical standards.
   • Formula: 100 − (weighted mean abnormality, scaled 0–100)
   • 100 = perfectly normal, 0 = maximally abnormal
   • Vital weight: 45% (based on NEWS AUROC 0.867)
   • Turkish population reference ranges (Ozarda 2014, PMID: 25153598)
   • Recalculated at each lab draw → forms a time series

2) PatientRegime™ — 4 states
   • Classifies the patient's health trajectory over time.
   • States:
     - 🟢 Stable: Score steady, low volatility
     - 🟡 Recovering: Upward trend, score improving
     - 🟠 Deteriorating: Downward trend, score declining
     - 🔴 Critical: Steep decline + high volatility
   • Uses 3-draw moving average + rolling standard deviation
   • Finance analogy: market regime detection (bull/bear/stress)
   • Requires minimum 4 lab draws; fewer → "Insufficient Data"

3) Health VaR™ — Monte Carlo Forecast
   • "With 95% confidence, health score won't fall below X in the next 3 lab-draw cycles."
   • 3,000 Monte Carlo bootstrap iterations
   • Risk tiers:
     - 🟢 GREEN (VaR > +5%): Stable or improving
     - 🟡 YELLOW (0% to +5%): Slight risk, monitor
     - 🟠 ORANGE (−10% to 0%): Moderate risk, review within 24h
     - 🔴 RED (< −10%): High risk, prioritize intervention
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
   • 6 features:
     - Health Score Trend (25%): Negative slope → higher severity
     - Lab Volatility (20%): High std dev → instability
     - Critical Regime Fraction (20%): % time in Critical state
     - NLP Signal (15%): Negative language → deterioration
     - Prescription Intensity (10%): High Rx velocity → active disease
     - Comorbidity Burden (10%): ICD comorbidities present
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
• Write like a real person texting a colleague — casual, warm, no fluff.
• Do NOT use **bold** at all. Zero asterisks. Write plain text only.
• Do NOT use markdown tables, headers (##), horizontal rules (---), or any structured formatting.
• Do NOT start messages with filler like "Great question!", "Sure!", "Here's the breakdown:", "Let me explain".
• Keep it SHORT: 2-5 sentences max. Only go longer if the user explicitly asks for detail.
• Weave numbers into natural sentences: "their score is 72 right now" not "Health Score: 72".
• No bullet points unless listing 3+ genuinely separate items.
• Max 1 emoji per message, only for risk tier color if relevant. Usually zero emoji.
• Sound human. Imagine you're a doctor leaning over to a colleague saying "hey so basically..."
• Do NOT give medical treatment advice — only explain what the data shows.
• If comparing two metrics, explain the difference in one flowing paragraph, not in sections.
"""


def build_patient_context(
    patient_id: int,
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
    lines = [f"\n═══ CURRENT PATIENT DATA: Patient #{patient_id} ═══"]

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

    # CSI
    if profile:
        lines.append(f"\n🎯 CLINICAL SEVERITY INDEX (CSI):")
        lines.append(f"  CSI Score: {profile.csi_score:.1f}/100")
        lines.append(f"  CSI Tier: {profile.csi_tier}")
        lines.append(f"  Critical Episodes: {profile.n_critical_episodes}")
        lines.append(f"  Critical Fraction: {profile.critical_fraction:.1%}")
        lines.append(f"  Mean NLP Composite: {profile.mean_nlp_composite:.3f}")

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

    lines.append("═══ END PATIENT DATA ═══")
    return "\n".join(lines)


def get_chat_response(messages: list[dict], patient_context: str = "") -> str:
    """
    Send messages to OpenRouter and return the assistant's reply.

    Parameters
    ----------
    messages : list[dict]
        OpenAI-format messages, e.g. [{"role": "user", "content": "..."}].
        The system prompt is prepended automatically.
    patient_context : str
        A text block with the current patient's data, injected into the system prompt.

    Returns
    -------
    str
        The assistant's text reply.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return "⚠️ OpenRouter API key not found. Please set the `OPENROUTER_API_KEY` environment variable in your `.env` file."

    system_content = SYSTEM_PROMPT
    if patient_context:
        system_content += "\n\n" + patient_context

    full_messages = [{"role": "system", "content": system_content}] + messages

    try:
        response = requests.post(
            OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ilay.app",
                "X-Title": "ILAY",
            },
            json={
                "model": MODEL,
                "messages": full_messages,
                "max_tokens": 420,
                "temperature": 0.4,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⚠️ API request timed out. Please try again."
    except requests.exceptions.RequestException as e:
        return f"⚠️ API error: {str(e)}"
    except (KeyError, IndexError):
        return "⚠️ Unexpected response from API."
