"use client";

import React, { useState } from "react";
import type { ValidationData, ValidationExperiment } from "@/lib/types";
import InfoTooltip from "@/components/ui/InfoTooltip";
import useStaggeredReveal from "@/hooks/useStaggeredReveal";

interface Props {
  data: ValidationData | null;
  loading: boolean;
}

/* ---------- Metric Card ---------- */

function MetricCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="frost-panel flex flex-col items-center px-4 py-4">
      <span className="text-[11px] font-medium uppercase tracking-wider text-slate-500">
        {label}
      </span>
      <span
        className="mt-1 text-lg font-bold tabular-nums"
        style={{ color: color ?? "#B8C5D9" }}
      >
        {value}
      </span>
    </div>
  );
}

/* ---------- Experiment Card (collapsible) ---------- */

function ExperimentCard({ exp }: { exp: ValidationExperiment }) {
  const [open, setOpen] = useState(false);
  const passed = exp.passed;

  return (
    <div className="frost-panel overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-white/[0.03]"
      >
        {/* Pass / fail icon */}
        <span
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold"
          style={{
            background: passed ? "rgba(46,204,113,0.15)" : "rgba(231,76,60,0.15)",
            color: passed ? "#2ECC71" : "#E74C3C",
            border: `1px solid ${passed ? "#2ECC7144" : "#E74C3C44"}`,
          }}
        >
          {passed ? "\u2713" : "\u2717"}
        </span>

        <span className="flex-1 text-sm font-semibold text-white">{exp.name}</span>

        {/* Chevron */}
        <svg
          className={`h-4 w-4 text-slate-500 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Expanded content */}
      {open && (
        <div className="space-y-4 border-t border-white/5 px-5 py-4">
          {/* Hypothesis */}
          <p className="text-sm italic leading-relaxed text-slate-400">
            {exp.hypothesis}
          </p>

          {/* Metric cards row */}
          <div className="grid grid-cols-3 gap-3">
            <MetricCard
              label={exp.statistic_name || "Statistic"}
              value={
                exp.statistic_value != null
                  ? exp.statistic_value.toFixed(4)
                  : "N/A"
              }
            />
            <MetricCard
              label="p-value"
              value={
                exp.p_value != null ? exp.p_value.toFixed(4) : "N/A"
              }
              color={
                exp.p_value != null && exp.p_value < 0.05
                  ? "#2ECC71"
                  : "#F39C12"
              }
            />
            <MetricCard
              label="n samples"
              value={String(exp.n_samples)}
            />
          </div>

          <div className="flex flex-wrap gap-4 px-1">
            <span className="section-label-with-info text-xs text-slate-400">
              p-value
              <InfoTooltip metricId="validation.p_value" />
            </span>
            <span className="section-label-with-info text-xs text-slate-400">
              n samples
              <InfoTooltip metricId="validation.n_samples" />
            </span>
          </div>

          {/* Conclusion */}
          <div className="frost-panel px-4 py-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Conclusion
            </span>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">
              {exp.conclusion}
            </p>
          </div>

          {/* Clinical meaning info box */}
          <div className="frost-panel px-4 py-4">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-cyan-400">
              Clinical Meaning
            </span>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">
              {exp.clinical_meaning}
            </p>
          </div>

          {/* Details (if present) */}
          {exp.details && Object.keys(exp.details).length > 0 && (
            <div className="frost-panel p-4">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Details
              </span>
              <pre className="mt-2 overflow-x-auto text-xs leading-relaxed text-slate-400">
                {JSON.stringify(exp.details, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- Main Component ---------- */

const METHODOLOGY_TABLE = [
  { finance: "Portfolio", healthcare: "Patient Cohort" },
  { finance: "Asset Price", healthcare: "Health Index Score" },
  { finance: "Credit Rating (AAA-CCC)", healthcare: "Patient Risk Rating" },
  { finance: "VaR (Value at Risk)", healthcare: "Health VaR (Downside Risk)" },
  { finance: "Market Regime (Bull/Bear)", healthcare: "Clinical Regime (Stable/Critical)" },
  { finance: "Composite Score", healthcare: "Composite Health Score" },
  { finance: "NLP Sentiment", healthcare: "Clinical Note Sentiment" },
  { finance: "Stress Index (CSI)", healthcare: "Clinical Severity Index" },
];

export default function ValidationTab({ data, loading }: Props) {
  const summaryReveal = useStaggeredReveal(data?.summary?.length ?? 0, {
    baseDelayMs: 40,
    stepMs: 50,
    threshold: 0.12,
  });
  const methodologyReveal = useStaggeredReveal(METHODOLOGY_TABLE.length, {
    baseDelayMs: 80,
    stepMs: 50,
    threshold: 0.1,
  });

  if (loading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <p className="loading-state-text">Running retrospective validation summaries…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="empty-state">
        <p className="empty-state-text">No validation data available for current dataset scope.</p>
      </div>
    );
  }

  const summaryKeys =
    data.summary && data.summary.length > 0
      ? Object.keys(data.summary[0])
      : [];

  return (
    <div className="space-y-6">
      {/* ---- Title ---- */}
      <div className="tab-intro tab-intro-frost frost-panel">
        <h2 className="tab-intro-title">
          Retrospective Validation
        </h2>
        <p className="tab-intro-subtitle">
          5 statistical experiments validating the clinical risk model against
          retrospective patient data.
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Nominal interpretation threshold: p &lt; 0.05, with sample-size caveats preserved.
        </p>
      </div>

      {/* ---- Summary Table ---- */}
      {data.summary && data.summary.length > 0 && (
        <div className="frost-panel overflow-hidden">
          <h3 className="border-b border-white/5 px-5 py-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
            Summary
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-white/5">
                  {summaryKeys.map((key) => (
                    <th
                      key={key}
                      className="whitespace-nowrap px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500"
                    >
                      <span className="section-label-with-info">
                        {key.replace(/_/g, " ")}
                        {key === "p_value" && <InfoTooltip metricId="validation.p_value" />}
                        {key === "n_samples" && <InfoTooltip metricId="validation.n_samples" />}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.summary.map((row, i) => {
                  const reveal = summaryReveal.getRevealProps(i, "fade");
                  return (
                  <tr
                    key={i}
                    {...reveal.staggerAttrs}
                    className={`border-b border-white/[0.03] transition-colors hover:bg-white/[0.02] ${reveal.staggerClass}`}
                    style={reveal.staggerStyle}
                  >
                    {summaryKeys.map((key) => {
                      const val = row[key];
                      const display =
                        typeof val === "number"
                          ? val.toFixed(4)
                          : typeof val === "boolean"
                            ? val
                              ? "\u2713"
                              : "\u2717"
                            : String(val ?? "\u2014");
                      return (
                        <td
                          key={key}
                          className="whitespace-nowrap px-5 py-2.5 tabular-nums text-slate-300"
                        >
                          {display}
                        </td>
                      );
                    })}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---- Experiments ---- */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
          Individual Experiments
        </h3>
        {data.experiments.map((exp, i) => (
          <ExperimentCard key={i} exp={exp} />
        ))}
      </div>

      {/* ---- Caveats ---- */}
        <div className="frost-panel px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-lg text-amber-400">&#9888;</span>
          <div>
            <h3 className="text-sm font-semibold text-amber-300">Caveats</h3>
            <p className="mt-1 text-sm leading-relaxed text-slate-300">
              These results are based on a limited synthetic sample size. While
              statistical significance is observed in some tests, results should
              be interpreted with caution and validated on larger, real-world
              clinical datasets before informing clinical decision-making.
              Sample sizes may be insufficient for robust sub-group analyses.
            </p>
          </div>
        </div>
      </div>

      {/* ---- Methodology Table ---- */}
      <div className="frost-panel overflow-hidden">
        <h3 className="border-b border-white/5 px-5 py-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
          Methodology: Finance &rarr; Healthcare Analogies
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-white/5">
                <th className="px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Finance Concept
                </th>
                <th className="px-5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                  Healthcare Analogy
                </th>
              </tr>
            </thead>
            <tbody>
              {METHODOLOGY_TABLE.map((row, i) => {
                const reveal = methodologyReveal.getRevealProps(i, "fade");
                return (
                <tr
                  key={i}
                  {...reveal.staggerAttrs}
                  className={`border-b border-white/[0.03] transition-colors hover:bg-white/[0.02] ${reveal.staggerClass}`}
                  style={reveal.staggerStyle}
                >
                  <td className="px-5 py-2.5 text-slate-400">{row.finance}</td>
                  <td className="px-5 py-2.5 font-medium text-slate-300">
                    {row.healthcare}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
