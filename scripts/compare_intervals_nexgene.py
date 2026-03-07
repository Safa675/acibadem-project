#!/usr/bin/env python3
"""
compare_intervals_nexgene.py
============================
Query NexGene AI Medical Reasoning API for reference ranges of our 24 core
clinical parameters (2 vitals + 22 labs) and compare them against our
hardcoded Ozarda 2014 / WHO ISH ranges.

Output: tasks/nexgene_comparison.md

Usage:
    python scripts/compare_intervals_nexgene.py
"""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────

API_URL = "https://api.backend.nexpath.nexgene.ai/api/search"
API_KEY = "nexgene-XakFmgsz40LO81y"
MODEL = "asa-mini"
OUTPUT_STYLE = "concise"
DELAY_BETWEEN_REQUESTS = 0.5  # seconds

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "tasks" / "nexgene_comparison.md"

# ── Our current reference intervals ──────────────────────────────────────

# From src/health_index.py: VITAL_REFERENCE_RANGES (lines 46-50)
# From src/health_index.py: OZARDA_2014_REFERENCE_RANGES (lines 73-116)

OUR_INTERVALS: list[dict] = [
    # Vitals (WHO ISH 2020 / ESH 2018)
    {
        "name": "Systolic Blood Pressure",
        "key": "systolic_bp",
        "unit": "mmHg",
        "low": 90.0,
        "high": 130.0,
        "source": "WHO ISH 2020 / ESH 2018",
        "category": "Vital",
    },
    {
        "name": "Diastolic Blood Pressure",
        "key": "diastolic_bp",
        "unit": "mmHg",
        "low": 60.0,
        "high": 85.0,
        "source": "WHO ISH 2020 / ESH 2018",
        "category": "Vital",
    },
    # Labs (Ozarda 2014, Turkish population)
    {
        "name": "Albumin",
        "key": "Albumin",
        "unit": "g/L",
        "low": 41.0,
        "high": 49.0,
        "source": "Ozarda 2014",
        "category": "Protein",
    },
    {
        "name": "Total Protein",
        "key": "Protein",
        "unit": "g/L",
        "low": 66.0,
        "high": 82.0,
        "source": "Ozarda 2014",
        "category": "Protein",
    },
    {
        "name": "BUN (Urea)",
        "key": "Üre",
        "unit": "mmol/L",
        "low": 2.9,
        "high": 7.2,
        "source": "Ozarda 2014",
        "category": "Renal",
    },
    {
        "name": "Creatinine",
        "key": "Kreatinin",
        "unit": "µmol/L",
        "low": 50.0,
        "high": 92.0,
        "source": "Ozarda 2014",
        "category": "Renal",
    },
    {
        "name": "Uric Acid",
        "key": "Ürik Asit",
        "unit": "µmol/L",
        "low": 166.0,
        "high": 458.0,
        "source": "Ozarda 2014",
        "category": "Renal",
    },
    {
        "name": "Total Bilirubin",
        "key": "Bilirubin",
        "unit": "µmol/L",
        "low": 2.7,
        "high": 24.1,
        "source": "Ozarda 2014",
        "category": "Bilirubin",
    },
    {
        "name": "Glucose (Fasting)",
        "key": "Glukoz",
        "unit": "mmol/L",
        "low": 3.96,
        "high": 5.88,
        "source": "Ozarda 2014",
        "category": "Metabolic",
    },
    {
        "name": "Total Cholesterol",
        "key": "Kolesterol",
        "unit": "mmol/L",
        "low": 3.2,
        "high": 6.45,
        "source": "Ozarda 2014",
        "category": "Metabolic",
    },
    {
        "name": "Triglycerides",
        "key": "Trigliserid",
        "unit": "mmol/L",
        "low": 0.46,
        "high": 3.55,
        "source": "Ozarda 2014",
        "category": "Metabolic",
    },
    {
        "name": "LDL Cholesterol",
        "key": "LDL",
        "unit": "mmol/L",
        "low": 1.32,
        "high": 3.92,
        "source": "Ozarda 2014",
        "category": "Metabolic",
    },
    {
        "name": "HDL Cholesterol",
        "key": "HDL",
        "unit": "mmol/L",
        "low": 0.85,
        "high": 1.56,
        "source": "Ozarda 2014",
        "category": "Metabolic",
    },
    {
        "name": "Sodium",
        "key": "Sodyum",
        "unit": "mmol/L",
        "low": 137.0,
        "high": 144.0,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "Potassium",
        "key": "Potasyum",
        "unit": "mmol/L",
        "low": 3.7,
        "high": 4.9,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "Chloride",
        "key": "Klor",
        "unit": "mmol/L",
        "low": 99.0,
        "high": 107.0,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "Calcium",
        "key": "Kalsiyum",
        "unit": "mmol/L",
        "low": 2.15,
        "high": 2.47,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "Phosphorus (Inorganic)",
        "key": "Fosfor",
        "unit": "mmol/L",
        "low": 0.80,
        "high": 1.40,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "Magnesium",
        "key": "Magnezyum",
        "unit": "mmol/L",
        "low": 0.77,
        "high": 1.06,
        "source": "Ozarda 2014",
        "category": "Electrolyte",
    },
    {
        "name": "ALT (SGPT)",
        "key": "ALT",
        "unit": "U/L",
        "low": 7.0,
        "high": 44.0,
        "source": "Ozarda 2014",
        "category": "Liver Enzyme",
    },
    {
        "name": "AST (SGOT)",
        "key": "AST",
        "unit": "U/L",
        "low": 11.0,
        "high": 30.0,
        "source": "Ozarda 2014",
        "category": "Liver Enzyme",
    },
    {
        "name": "ALP (Alkaline Phosphatase)",
        "key": "ALP",
        "unit": "U/L",
        "low": 34.0,
        "high": 116.0,
        "source": "Ozarda 2014",
        "category": "Liver Enzyme",
    },
    {
        "name": "GGT",
        "key": "GGT",
        "unit": "U/L",
        "low": 7.0,
        "high": 69.0,
        "source": "Ozarda 2014",
        "category": "Liver Enzyme",
    },
    {
        "name": "LDH (Lactate Dehydrogenase)",
        "key": "LDH",
        "unit": "U/L",
        "low": 126.0,
        "high": 220.0,
        "source": "Ozarda 2014",
        "category": "Enzyme",
    },
    {
        "name": "Amylase",
        "key": "Amilaz",
        "unit": "U/L",
        "low": 34.0,
        "high": 119.0,
        "source": "Ozarda 2014",
        "category": "Enzyme",
    },
]


# ── NexGene API ──────────────────────────────────────────────────────────


def query_nexgene(param_name: str, unit: str, request_id: str) -> dict:
    """
    Query NexGene for the normal adult reference range of a parameter.
    Returns dict with keys: raw_text, trust_score, evidence_grade, references.
    """
    prompt = (
        f"What is the standard normal adult reference range for {param_name} "
        f"in {unit}? Provide the lower limit and upper limit as numbers. "
        f"If sex-specific, give the widest sex-neutral range (female lower, male upper)."
    )

    payload = {
        "id": request_id,
        "messages": [{"role": "user", "content": prompt}],
        "outputStyle": OUTPUT_STYLE,
        "model": MODEL,
        "email": "",
    }

    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json",
    }

    resp = requests.post(
        API_URL, headers=headers, json=payload, stream=True, timeout=60
    )
    resp.raise_for_status()

    text_chunks: list[str] = []
    trust_data: dict = {}

    for raw_line in resp.iter_lines(decode_unicode=True):
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line:
            continue

        # Text tokens: lines starting with "0:"
        if line.startswith("0:"):
            raw_token = line[2:]
            try:
                token = json.loads(raw_token)
            except (json.JSONDecodeError, ValueError):
                token = raw_token
            text_chunks.append(str(token))

        # Structured data with nextrustData
        elif line.startswith("a:"):
            try:
                data = json.loads(line[2:])
                nex = (
                    data.get("callResults", {})
                    .get("research", {})
                    .get("nextrustData", {})
                )
                if nex:
                    trust_data = nex
            except (json.JSONDecodeError, AttributeError):
                pass

    full_text = "".join(text_chunks).strip()

    return {
        "raw_text": full_text,
        "trust_score": trust_data.get("trustScore"),
        "evidence_grade": trust_data.get("evidenceGrade"),
        "evidence_strength": trust_data.get("evidenceStrength"),
        "n_studies": trust_data.get("numberOfStudies", 0),
        "references": [
            {
                "title": r.get("title", ""),
                "source": r.get("source", ""),
                "year": r.get("year"),
            }
            for r in trust_data.get("references", [])
        ],
    }


def extract_range(text: str, unit: str) -> tuple[float | None, float | None]:
    """
    Extract a numeric range (low, high) from NexGene response text.
    Handles formats like "3.5 - 5.0", "3.5–5.0", "3.5 to 5.0",
    "Lower limit: 35 ... Upper limit: 50", etc.
    """
    # Normalize unicode dashes
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2012", "-")

    # Try patterns in order of specificity
    patterns: list[tuple[str, int]] = [
        # "Lower limit: 35 ... Upper limit: 50" (may span multiple lines)
        (
            r"[Ll]ower\s*(?:limit)?[:\s]+(\d+\.?\d*).*?[Uu]pper\s*(?:limit)?[:\s]+(\d+\.?\d*)",
            re.DOTALL,
        ),
        # "35 g/L (lower) to 50 g/L (upper)" or "About 75 mm Hg (lower) to 84 mm Hg (upper)"
        (
            r"(?:about\s+)?(\d+\.?\d*)\s*[^\d]*?\(lower\).*?(\d+\.?\d*)\s*[^\d]*?\(upper\)",
            re.DOTALL | re.IGNORECASE,
        ),
        # "X - Y unit" or "X-Y unit"
        (
            r"(\d+\.?\d*)\s*[-]\s*(\d+\.?\d*)\s*"
            + re.escape(unit).replace("µ", "(?:µ|μ|u)"),
            0,
        ),
        # "X - Y" generic
        (r"(\d+\.?\d*)\s*[-]\s*(\d+\.?\d*)", 0),
        # "X to Y"
        (r"(\d+\.?\d*)\s+to\s+(\d+\.?\d*)", 0),
        # "between X and Y"
        (r"between\s+(\d+\.?\d*)\s+and\s+(\d+\.?\d*)", 0),
    ]

    for pattern, flags in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | flags)
        if matches:
            for m in matches:
                low, high = float(m[0]), float(m[1])
                if low < high:
                    return low, high

    return None, None


def classify_delta(
    our_val: float, nexgene_val: float | None
) -> tuple[str, float | None]:
    """Classify the percentage difference between our value and NexGene's."""
    if nexgene_val is None:
        return "N/A", None
    if our_val == 0:
        return "N/A", None
    pct = abs(nexgene_val - our_val) / abs(our_val) * 100
    if pct <= 10:
        return "MATCH", pct
    elif pct <= 25:
        return "REVIEW", pct
    else:
        return "DIVERGENT", pct


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Comparing {len(OUR_INTERVALS)} parameters against NexGene AI...")
    print(f"Model: {MODEL} | Output: {OUTPUT_PATH}\n")

    results: list[dict] = []

    for i, param in enumerate(OUR_INTERVALS):
        request_id = f"interval-{i + 1:03d}"
        print(
            f"[{i + 1:2d}/{len(OUR_INTERVALS)}] Querying: {param['name']} ({param['unit']})...",
            end=" ",
            flush=True,
        )

        try:
            resp = query_nexgene(param["name"], param["unit"], request_id)
            nex_low, nex_high = extract_range(resp["raw_text"], param["unit"])

            low_status, low_pct = classify_delta(param["low"], nex_low)
            high_status, high_pct = classify_delta(param["high"], nex_high)

            # Overall status: worst of the two
            status_order = {"MATCH": 0, "REVIEW": 1, "DIVERGENT": 2, "N/A": 3}
            overall = max(
                [low_status, high_status], key=lambda s: status_order.get(s, 3)
            )

            result = {
                **param,
                "nex_low": nex_low,
                "nex_high": nex_high,
                "nex_raw": resp["raw_text"][:200],
                "trust_score": resp["trust_score"],
                "evidence_grade": resp["evidence_grade"],
                "evidence_strength": resp["evidence_strength"],
                "n_studies": resp["n_studies"],
                "references": resp["references"],
                "low_delta_pct": low_pct,
                "high_delta_pct": high_pct,
                "low_status": low_status,
                "high_status": high_status,
                "overall_status": overall,
            }
            results.append(result)

            nex_range_str = (
                f"{nex_low:.2f} - {nex_high:.2f}"
                if nex_low is not None
                else "PARSE FAIL"
            )
            print(
                f"Our: {param['low']}-{param['high']} | NexGene: {nex_range_str} | {overall}"
            )

        except Exception as e:
            print(f"ERROR: {e}")
            results.append(
                {
                    **param,
                    "nex_low": None,
                    "nex_high": None,
                    "nex_raw": str(e),
                    "trust_score": None,
                    "evidence_grade": None,
                    "evidence_strength": None,
                    "n_studies": 0,
                    "references": [],
                    "low_delta_pct": None,
                    "high_delta_pct": None,
                    "low_status": "ERROR",
                    "high_status": "ERROR",
                    "overall_status": "ERROR",
                }
            )

        if i < len(OUR_INTERVALS) - 1:
            time.sleep(DELAY_BETWEEN_REQUESTS)

    # ── Generate report ──────────────────────────────────────────────────

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    match_count = sum(1 for r in results if r["overall_status"] == "MATCH")
    review_count = sum(1 for r in results if r["overall_status"] == "REVIEW")
    divergent_count = sum(1 for r in results if r["overall_status"] == "DIVERGENT")
    fail_count = sum(1 for r in results if r["overall_status"] in ("N/A", "ERROR"))

    lines: list[str] = []
    lines.append("# NexGene AI Reference Interval Comparison")
    lines.append("")
    lines.append(f"**Generated:** {now}")
    lines.append(f"**Model:** NexGene `{MODEL}` (Medical Reasoning Foundational Model)")
    lines.append(f"**Parameters compared:** {len(results)}")
    lines.append(
        f"**Our source:** Ozarda 2014 (Turkish population) + WHO ISH 2020 (vitals)"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Status | Count | Criteria |")
    lines.append(f"|--------|-------|----------|")
    lines.append(f"| MATCH | {match_count} | Both limits within 10% |")
    lines.append(f"| REVIEW | {review_count} | At least one limit 10-25% different |")
    lines.append(
        f"| DIVERGENT | {divergent_count} | At least one limit >25% different |"
    )
    lines.append(
        f"| PARSE FAIL / ERROR | {fail_count} | Could not extract range from response |"
    )
    lines.append("")

    # ── Main comparison table ──────────────────────────────────────────

    lines.append("## Detailed Comparison")
    lines.append("")
    lines.append(
        "| # | Parameter | Unit | Our Range | NexGene Range | Low Delta | High Delta | Status | Trust | Evidence |"
    )
    lines.append(
        "|---|-----------|------|-----------|---------------|-----------|------------|--------|-------|----------|"
    )

    for i, r in enumerate(results):
        our_range = f"{r['low']:.2f} - {r['high']:.2f}"
        if r["nex_low"] is not None:
            nex_range = f"{r['nex_low']:.2f} - {r['nex_high']:.2f}"
        else:
            nex_range = "---"

        low_d = (
            f"{r['low_delta_pct']:.1f}%" if r["low_delta_pct"] is not None else "---"
        )
        high_d = (
            f"{r['high_delta_pct']:.1f}%" if r["high_delta_pct"] is not None else "---"
        )
        trust = f"{r['trust_score']:.0f}" if r["trust_score"] is not None else "---"
        evidence = r["evidence_grade"] or "---"

        # Status emoji
        status_icon = {
            "MATCH": "MATCH",
            "REVIEW": "REVIEW",
            "DIVERGENT": "DIVERGENT",
            "N/A": "PARSE FAIL",
            "ERROR": "ERROR",
        }.get(r["overall_status"], r["overall_status"])

        lines.append(
            f"| {i + 1} | {r['name']} | {r['unit']} | {our_range} | {nex_range} | {low_d} | {high_d} | {status_icon} | {trust} | {evidence} |"
        )

    lines.append("")

    # ── Per-parameter details (for REVIEW and DIVERGENT) ──────────────

    flagged = [r for r in results if r["overall_status"] in ("REVIEW", "DIVERGENT")]
    if flagged:
        lines.append("## Flagged Parameters (REVIEW / DIVERGENT)")
        lines.append("")
        for r in flagged:
            lines.append(f"### {r['name']} ({r['unit']}) -- {r['overall_status']}")
            lines.append("")
            lines.append(
                f"- **Our range:** {r['low']:.2f} - {r['high']:.2f} (Source: {r['source']})"
            )
            nex_str = (
                f"{r['nex_low']:.2f} - {r['nex_high']:.2f}"
                if r["nex_low"] is not None
                else "N/A"
            )
            lines.append(f"- **NexGene range:** {nex_str}")
            lines.append(f"- **NexGene raw response:** {r['nex_raw']}")
            lines.append(f"- **Trust score:** {r.get('trust_score', 'N/A')}")
            lines.append(
                f"- **Evidence grade:** {r.get('evidence_grade', 'N/A')} (strength: {r.get('evidence_strength', 'N/A')})"
            )
            if r["references"]:
                lines.append(f"- **References:**")
                for ref in r["references"][:3]:
                    lines.append(
                        f"  - {ref['title']} ({ref['source']}, {ref.get('year', 'N/A')})"
                    )
            lines.append("")

    # ── Parse failures ────────────────────────────────────────────────

    failed = [r for r in results if r["overall_status"] in ("N/A", "ERROR")]
    if failed:
        lines.append("## Parse Failures / Errors")
        lines.append("")
        for r in failed:
            lines.append(f"### {r['name']} ({r['unit']})")
            lines.append(f"- **Raw response:** {r['nex_raw']}")
            lines.append("")

    # ── Methodology note ─────────────────────────────────────────────

    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- Each parameter was queried individually via the NexGene AI Medical Reasoning API (`asa-mini` model)"
    )
    lines.append(
        "- Numeric ranges were extracted from the response text using regex pattern matching"
    )
    lines.append(
        "- Delta percentages computed as `|our_value - nexgene_value| / |our_value| * 100`"
    )
    lines.append(
        "- **MATCH**: both limits within 10% | **REVIEW**: 10-25% | **DIVERGENT**: >25%"
    )
    lines.append(
        "- Our ranges: Ozarda 2014 (PMID 25153598, Turkish population) for labs; WHO ISH 2020 for vitals"
    )
    lines.append(
        "- NexGene trust scores and evidence grades are provided by the API's built-in evidence assessment"
    )
    lines.append("")

    report = "\n".join(lines)

    # ── Write output ─────────────────────────────────────────────────

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Report written to: {OUTPUT_PATH}")
    print(
        f"Summary: {match_count} MATCH | {review_count} REVIEW | {divergent_count} DIVERGENT | {fail_count} FAIL"
    )
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
