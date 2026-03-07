"use client";

import React, { useState, useMemo } from "react";
import type { ValidationData, ValidationExperiment } from "@/lib/types";
import InfoTooltip from "@/components/ui/InfoTooltip";

interface Props {
  data: ValidationData | null;
  loading: boolean;
}

/* ---------- Benchmark metadata ---------- */

const BENCHMARK_INFO: Record<
  string,
  {
    label: string;
    fullName: string;
    coverage: string;
    available: string[];
    missing: string[];
    reference: string;
  }
> = {
  SOFA: {
    label: "SOFA",
    fullName: "Sequential Organ Failure Assessment",
    coverage: "4/6",
    available: ["Coagulation (Platelets)", "Hepatic (Bilirubin)", "Cardiovascular (MAP)", "Renal (Creatinine)"],
    missing: ["Respiratory (PaO2/FiO2)", "Neurological (GCS)"],
    reference: "Vincent et al. 1996 / Singer et al. 2016",
  },
  "APACHE II": {
    label: "APACHE II",
    fullName: "Acute Physiology and Chronic Health Evaluation II",
    coverage: "7/12",
    available: ["MAP", "Heart Rate", "Sodium", "Potassium", "Creatinine", "Hematocrit", "WBC"],
    missing: ["Temperature", "Respiratory Rate", "Oxygenation", "Arterial pH", "GCS"],
    reference: "Knaus et al. 1985",
  },
};

const BENCHMARK_ORDER = ["SOFA", "APACHE II"] as const;

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

/* ---------- Parameter Availability Tooltip ---------- */

function ParamAvailabilityBadge({ benchmarkKey }: { benchmarkKey: string }) {
  const [show, setShow] = useState(false);
  const info = BENCHMARK_INFO[benchmarkKey];
  if (!info) return null;

  return (
    <span
      className="info-tooltip"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      <span
        className="cursor-help rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
        style={{
          background: "rgba(79,195,247,0.12)",
          color: "#4FC3F7",
          border: "1px solid rgba(79,195,247,0.25)",
        }}
      >
        {info.coverage} params
      </span>
      {show && (
        <div className="info-popover" style={{ width: "min(280px, 82vw)", top: "calc(100% + 8px)" }}>
          <div className="info-popover-title">{info.fullName}</div>
          <div className="info-popover-item" style={{ marginTop: 4 }}>
            <strong>Available:</strong>
          </div>
          {info.available.map((p) => (
            <div key={p} className="info-popover-item" style={{ paddingLeft: 8, color: "#7ee8a8" }}>
              &#10003; {p}
            </div>
          ))}
          <div className="info-popover-item" style={{ marginTop: 4 }}>
            <strong>Missing (default 0):</strong>
          </div>
          {info.missing.map((p) => (
            <div key={p} className="info-popover-item" style={{ paddingLeft: 8, color: "#7B8BA5" }}>
              &#10007; {p}
            </div>
          ))}
          <div className="info-popover-item" style={{ marginTop: 6, fontSize: 10, color: "#7B8BA5" }}>
            {info.reference}
          </div>
        </div>
      )}
    </span>
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

        {/* Stat preview */}
        {exp.statistic_value != null && (
          <span className="mr-2 text-xs tabular-nums text-slate-400">
            {"\u03c1"} = {exp.statistic_value.toFixed(3)}
          </span>
        )}

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

/* ---------- Benchmark Group ---------- */

function BenchmarkGroup({
  benchmarkKey,
  experiments,
}: {
  benchmarkKey: string;
  experiments: ValidationExperiment[];
}) {
  const info = BENCHMARK_INFO[benchmarkKey];
  if (!info) return null;

  const passCount = experiments.filter((e) => e.passed).length;
  const totalCount = experiments.length;

  return (
    <div className="space-y-3">
      {/* Group header */}
      <div className="flex items-center gap-3">
        <h4 className="text-sm font-bold uppercase tracking-wider text-white">
          {info.label}
        </h4>
        <ParamAvailabilityBadge benchmarkKey={benchmarkKey} />
        <span
          className="rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
          style={{
            background: passCount === totalCount
              ? "rgba(46,204,113,0.12)"
              : passCount > 0
                ? "rgba(243,156,18,0.12)"
                : "rgba(231,76,60,0.12)",
            color: passCount === totalCount
              ? "#2ECC71"
              : passCount > 0
                ? "#F39C12"
                : "#E74C3C",
            border: `1px solid ${
              passCount === totalCount
                ? "rgba(46,204,113,0.25)"
                : passCount > 0
                  ? "rgba(243,156,18,0.25)"
                  : "rgba(231,76,60,0.25)"
            }`,
          }}
        >
          {passCount}/{totalCount} passed
        </span>
      </div>

      {/* Experiment cards */}
      <div className="space-y-2">
        {experiments.map((exp, i) => (
          <ExperimentCard key={i} exp={exp} />
        ))}
      </div>
    </div>
  );
}

/* ---------- Methodology Table ---------- */

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

/* ---------- Main Component ---------- */

export default function ValidationTab({ data, loading }: Props) {
  // Group experiments by benchmark
  const groupedExperiments = useMemo(() => {
    if (!data?.experiments) return {};
    const groups: Record<string, ValidationExperiment[]> = {};
    for (const exp of data.experiments) {
      const bm = exp.benchmark || "Other";
      if (!groups[bm]) groups[bm] = [];
      groups[bm].push(exp);
    }
    return groups;
  }, [data?.experiments]);

  if (loading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <p className="loading-state-text">Running institutional benchmark validations...</p>
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

  const experimentCount = data.experiments?.length ?? 0;
  const passedCount = data.experiments?.filter((e) => e.passed).length ?? 0;

  return (
    <div className="space-y-6">
      {/* ---- Title ---- */}
      <div className="tab-intro tab-intro-frost frost-panel">
        <h2 className="tab-intro-title">
          Institutional Benchmark Validation
        </h2>
        <p className="tab-intro-subtitle">
          Validating our Composite Health Index against established clinical severity scores.
          A negative Spearman correlation confirms that higher Health Index (healthier) aligns
          with lower institutional severity (sicker), proving directional validity.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <span
            className="rounded-full px-3 py-1 text-xs font-semibold"
            style={{
              background: passedCount > 0 ? "rgba(46,204,113,0.1)" : "rgba(231,76,60,0.1)",
              color: passedCount > 0 ? "#2ECC71" : "#E74C3C",
              border: `1px solid ${passedCount > 0 ? "rgba(46,204,113,0.2)" : "rgba(231,76,60,0.2)"}`,
            }}
          >
            {passedCount}/{experimentCount} passed
          </span>
          <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">
            Expected: negative {"\u03c1"} (Health Index vs severity)
          </span>
          <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-slate-400">
            Pass rule: {"\u03c1"} &lt; 0, p &lt; 0.20, n &gt; 5
          </span>
        </div>
      </div>

      {/* ---- Experiments grouped by benchmark ---- */}
      {BENCHMARK_ORDER.map((bm) => {
        const exps = groupedExperiments[bm];
        if (!exps || exps.length === 0) return null;
        return (
          <BenchmarkGroup key={bm} benchmarkKey={bm} experiments={exps} />
        );
      })}

      {/* ---- Caveats ---- */}
      <div className="frost-panel px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-lg text-amber-400">&#9888;</span>
          <div>
            <h3 className="text-sm font-semibold text-amber-300">Caveats &amp; Limitations</h3>
            <ul className="mt-2 space-y-1.5 text-sm leading-relaxed text-slate-300">
              <li>
                <strong className="text-slate-200">Partial parameters:</strong>{" "}
                SOFA uses 4/6 organ systems, APACHE II uses 7/12 APS variables.
                Missing components default to 0, biasing all institutional scores downward (conservative).
              </li>
              <li>
                <strong className="text-slate-200">Sample context:</strong>{" "}
                Correlations are computed over the full cohort (~8,000+ patients with visit data).
                Institutional benchmark scores (SOFA, APACHE II) rely on partial parameters,
                which may limit interpretability for borderline cases.
              </li>
              <li>
                <strong className="text-slate-200">Outpatient bias:</strong>{" "}
                SOFA and APACHE II are designed for ICU settings. Outpatient scores may cluster
                near zero, making correlation undefined (constant-input guard applied).
              </li>
            </ul>
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
              {METHODOLOGY_TABLE.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-white/[0.03] transition-colors hover:bg-white/[0.02]"
                >
                  <td className="px-5 py-2.5 text-slate-400">{row.finance}</td>
                  <td className="px-5 py-2.5 font-medium text-slate-300">
                    {row.healthcare}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
