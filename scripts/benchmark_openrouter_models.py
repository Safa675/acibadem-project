#!/usr/bin/env python3
"""Benchmark OpenRouter chat latency across multiple models using ILAY full payload."""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api import _load_pipeline
from src.chatbot import OPENROUTER_BASE_URL, SYSTEM_PROMPT, build_patient_context


DEFAULT_MODELS = [
    "qwen/qwen3.5-flash-02-23",
    "openai/gpt-4o-mini",
    "google/gemini-2.0-flash-001",
    "anthropic/claude-3.5-haiku",
    "deepseek/deepseek-chat-v3",
]


@dataclass
class RunResult:
    ok: bool
    latency_ms: float
    error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare OpenRouter model response latency with ILAY full payload.",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        help="User prompt text to send to each model.",
    )
    parser.add_argument(
        "--patient-id",
        type=int,
        default=1,
        help="Patient ID used to build full context payload (default: 1).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Measured runs per model (default: 3).",
    )
    parser.add_argument(
        "--warmups",
        type=int,
        default=1,
        help="Warmup runs per model, excluded from stats (default: 1).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30).",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=420,
        help="Max output tokens for each request (default: 420).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.4,
        help="Sampling temperature (default: 0.4).",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="Space-separated OpenRouter model IDs.",
    )
    return parser.parse_args()


def quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    index = (len(sorted_vals) - 1) * q
    lo = int(index)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = index - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def build_system_content(patient_id: int) -> str:
    ctx = _load_pipeline()
    profile = ctx["profiles"].get(patient_id)
    composites_df = ctx["composites"]
    comp_row = (
        composites_df[composites_df["patient_id"] == patient_id]
        if not composites_df.empty
        else None
    )
    regimes = ctx["regimes"]
    regime_r = regimes.get(patient_id)
    last_known = regime_r.last_known_state() if regime_r else None
    regime_state = last_known.value if last_known is not None else "Insufficient Data"
    var_result = ctx["var_results"].get(patient_id)

    patient_context = build_patient_context(
        patient_id=patient_id,
        profile=profile,
        comp_row=comp_row,
        regime_state=regime_state,
        var_result=var_result,
        nlp_results=ctx["nlp_results"],
        ana_df=ctx["ana_df"],
        lab_df=ctx["lab_df"],
        rec_df=ctx["rec_df"],
    )
    return f"{SYSTEM_PROMPT}\n\n{patient_context}"


def single_request(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: float,
    max_tokens: int,
    temperature: float,
) -> RunResult:
    start = time.perf_counter()
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
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=timeout,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        response.raise_for_status()
        payload = response.json()
        _ = payload["choices"][0]["message"]["content"]
        return RunResult(ok=True, latency_ms=latency_ms)
    except requests.exceptions.Timeout:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return RunResult(ok=False, latency_ms=latency_ms, error="timeout")
    except requests.exceptions.RequestException as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return RunResult(ok=False, latency_ms=latency_ms, error=f"http_error: {exc}")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return RunResult(ok=False, latency_ms=latency_ms, error=f"bad_response: {exc}")


def summarize_runs(model: str, runs: list[RunResult]) -> dict[str, Any]:
    successes = [r.latency_ms for r in runs if r.ok]
    failures = [r.error for r in runs if not r.ok]
    success_rate = (len(successes) / len(runs) * 100.0) if runs else 0.0

    return {
        "model": model,
        "runs": len(runs),
        "successes": len(successes),
        "failures": len(failures),
        "success_rate": success_rate,
        "min_ms": min(successes) if successes else float("nan"),
        "mean_ms": statistics.mean(successes) if successes else float("nan"),
        "p50_ms": quantile(successes, 0.50) if successes else float("nan"),
        "p95_ms": quantile(successes, 0.95) if successes else float("nan"),
        "max_ms": max(successes) if successes else float("nan"),
        "errors": failures,
    }


def fmt_ms(value: float) -> str:
    if value != value:
        return "-"
    return f"{value:8.1f}"


def print_results(rows: list[dict[str, Any]]) -> None:
    ranked = sorted(
        rows,
        key=lambda r: (r["successes"] == 0, r["mean_ms"]),
    )

    print("\nOpenRouter model latency benchmark (lower is better)")
    print(
        "{:<32} {:>8} {:>10} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
            "Model",
            "Runs",
            "Success%",
            "Mean",
            "P50",
            "P95",
            "Min",
            "Max",
        )
    )
    print("-" * 94)

    for row in ranked:
        print(
            "{:<32} {:>8} {:>9.1f}% {} {} {} {} {}".format(
                row["model"][:32],
                row["runs"],
                row["success_rate"],
                fmt_ms(row["mean_ms"]),
                fmt_ms(row["p50_ms"]),
                fmt_ms(row["p95_ms"]),
                fmt_ms(row["min_ms"]),
                fmt_ms(row["max_ms"]),
            )
        )
        if row["errors"]:
            print(f"  errors: {', '.join(row['errors'][:2])}")

    winner = next((r for r in ranked if r["successes"] > 0), None)
    if winner:
        print(
            f"\nFastest successful model: {winner['model']} (mean {winner['mean_ms']:.1f} ms)"
        )
    else:
        print("\nNo successful responses were returned by any model.")


def main() -> int:
    args = parse_args()
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("OPENROUTER_API_KEY is missing. Set it in your environment or .env.")
        return 1

    system_content = build_system_content(args.patient_id)
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": args.prompt},
    ]

    all_rows: list[dict[str, Any]] = []

    print(
        f"Running benchmark for {len(args.models)} models | repeats={args.repeats} | warmups={args.warmups} | patient_id={args.patient_id}"
    )
    for model in args.models:
        print(f"- {model}")

    for model in args.models:
        if args.warmups > 0:
            for _ in range(args.warmups):
                _ = single_request(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    timeout=args.timeout,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                )

        runs: list[RunResult] = []
        for _ in range(args.repeats):
            result = single_request(
                api_key=api_key,
                model=model,
                messages=messages,
                timeout=args.timeout,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
            )
            runs.append(result)
            status = "ok" if result.ok else f"fail ({result.error})"
            print(f"  {model}: {result.latency_ms:.1f} ms - {status}")

        all_rows.append(summarize_runs(model, runs))

    print_results(all_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
