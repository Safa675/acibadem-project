"use client";

import type { ChangeEvent } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  LabelList,
} from "recharts";
import type { OutcomeData, PatientFilters, PatientMeta } from "@/lib/types";
import { ACCENT, CHART_COLORS, ECI_RATING_COLORS } from "@/lib/constants";
import InfoTooltip from "@/components/ui/InfoTooltip";
import MetricCue from "@/components/ui/MetricCue";
import { getECICue } from "@/lib/interpretation";
import useStaggeredReveal from "@/hooks/useStaggeredReveal";
import PatientSearch from "@/components/ui/PatientSearch";
import PatientFilterBar from "@/components/ui/PatientFilterBar";

interface Props {
  data: OutcomeData | null;
  loading: boolean;
  switching: boolean;
  selectedPatientId: string | null;
  patients: string[];
  filteredPatients: string[];
  patientMeta: PatientMeta[];
  onPatientChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onPatientSelect: (patientId: string | null) => void;
  loadingPatients: boolean;
  filters: PatientFilters;
  onFiltersChange: (filters: PatientFilters) => void;
}

const FEATURE_DESCRIPTIONS: Record<string, string> = {
  mean_health_score: "Average longitudinal health index score for the patient.",
  n_prescriptions: "Total number of prescription events captured in the timeline.",
  n_lab_draws: "Count of recorded laboratory observations.",
  n_comorbidities: "Number of documented comorbidity conditions.",
  total_visits: "Total clinical visit count in available records.",
  age: "Patient age at observed period.",
};

function humanizeFeature(raw: string): string {
  return raw
    .split("_")
    .map((part) => {
      const token = part.toLowerCase();
      if (token === "eci") return "ECI";
      if (token === "nlp") return "NLP";
      if (token === "var") return "VaR";
      if (token === "los") return "LOS";
      return token.charAt(0).toUpperCase() + token.slice(1);
    })
    .join(" ");
}

function FeatureAxisTick(props: {
  x?: number | string;
  y?: number | string;
  payload?: { value?: string | number };
  lookup: Record<string, string>;
}) {
  const value = String(props.payload?.value ?? "");
  const description = props.lookup[value] ?? value;
  return (
    <g transform={`translate(${Number(props.x ?? 0)},${Number(props.y ?? 0)})`}>
      <title>{description}</title>
      <text x={-6} y={0} dy={4} textAnchor="end" fill={CHART_COLORS.text} fontSize={11}>
        {value}
      </text>
    </g>
  );
}

/* ---------- ECI Gauge (SVG semicircle) ---------- */

function ECIGauge({ score, rating, ratingLabel }: { score: number; rating: string; ratingLabel: string }) {
  const cx = 120;
  const cy = 110;
  const r = 90;
  const startAngle = Math.PI;

  // Color stops for the arc: green 0-25, amber 25-50, orange 50-75, red 75-100
  const segments = [
    { from: 0, to: 25, color: "#2ECC71" },
    { from: 25, to: 50, color: "#F39C12" },
    { from: 50, to: 75, color: "#E67E22" },
    { from: 75, to: 100, color: "#E74C3C" },
  ];

  function arcPath(fromPct: number, toPct: number): string {
    const a1 = startAngle - (fromPct / 100) * Math.PI;
    const a2 = startAngle - (toPct / 100) * Math.PI;
    const x1 = cx + r * Math.cos(a1);
    const y1 = cy - r * Math.sin(a1);
    const x2 = cx + r * Math.cos(a2);
    const y2 = cy - r * Math.sin(a2);
    const largeArc = toPct - fromPct > 50 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  }

  // Needle
  const clampedScore = Math.max(0, Math.min(100, score));
  const needleAngle = startAngle - (clampedScore / 100) * Math.PI;
  const needleLen = r - 12;
  const nx = cx + needleLen * Math.cos(needleAngle);
  const ny = cy - needleLen * Math.sin(needleAngle);

  // Determine gauge highlight color
  const gaugeColor =
    clampedScore >= 75
      ? "#E74C3C"
      : clampedScore >= 50
        ? "#E67E22"
        : clampedScore >= 25
          ? "#F39C12"
          : "#2ECC71";

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width={240} height={140} viewBox="0 0 240 140">
        {/* Background track */}
        <path
          d={arcPath(0, 100)}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={18}
          strokeLinecap="round"
        />
        {/* Colored segments */}
        {segments.map((seg) => (
          <path
            key={seg.from}
            d={arcPath(seg.from, seg.to)}
            fill="none"
            stroke={seg.color}
            strokeWidth={18}
            strokeLinecap="butt"
            opacity={0.7}
          />
        ))}
        {/* Needle */}
        <line
          x1={cx}
          y1={cy}
          x2={nx}
          y2={ny}
          stroke="#fff"
          strokeWidth={3}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={6} fill={gaugeColor} stroke="#fff" strokeWidth={2} />
        {/* Min / Max labels */}
        <text x={cx - r - 8} y={cy + 18} fill="#B8C5D9" fontSize={11} textAnchor="middle">
          0
        </text>
        <text x={cx + r + 8} y={cy + 18} fill="#B8C5D9" fontSize={11} textAnchor="middle">
          100
        </text>
      </svg>

      <span
        className="text-3xl font-bold tracking-tight"
        style={{ color: gaugeColor }}
      >
        {score.toFixed(1)}
        <span className="text-base font-normal text-slate-400"> / 100</span>
      </span>
      <span
        className="rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wider"
        style={{
          background: `${gaugeColor}22`,
          color: gaugeColor,
          border: `1px solid ${gaugeColor}44`,
        }}
      >
        {rating} — {ratingLabel}
      </span>
    </div>
  );
}

/* ---------- Narrative Panel ---------- */

function NarrativePanel({ narrative }: { narrative: string }) {
  const lines = narrative.split("\n").filter((l) => l.trim());
  return (
    <div className="frost-panel p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
        ECI Assessment Narrative
      </h3>
      <div className="space-y-1.5 text-sm leading-relaxed text-slate-300">
        {lines.map((line, i) => {
          const trimmed = line.trim();
          if (trimmed.startsWith("Patient")) {
            return (
              <p key={i} className="font-semibold text-white">
                {trimmed}
              </p>
            );
          }
          return (
            <p key={i} className="pl-3">
              <span className="mr-2 text-slate-500">&bull;</span>
              {trimmed}
            </p>
          );
        })}
      </div>
    </div>
  );
}

/* ---------- Chart tooltip ---------- */

function ChartTooltipContent({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number; fill?: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="frost-tooltip px-3 py-2 text-xs">
      <p className="mb-1 font-medium text-white">{label}</p>
      {payload.map((entry, i) => (
        <p key={i} style={{ color: entry.fill || ACCENT }}>
          {typeof entry.value === "number" ? entry.value.toFixed(2) : entry.value}
        </p>
      ))}
    </div>
  );
}

/* ---------- Main Component ---------- */

export default function OutcomePredictor({
  data,
  loading,
  switching,
  selectedPatientId,
  patients,
  filteredPatients,
  patientMeta,
  onPatientChange,
  onPatientSelect,
  loadingPatients,
  filters,
  onFiltersChange,
}: Props) {
  const reveal = useStaggeredReveal(4, { baseDelayMs: 40, stepMs: 140, threshold: 0.15 });

  if (loading && !data) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <p className="loading-state-text">Computing outcome analytics and severity decomposition…</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="empty-state">
        <p className="empty-state-text">No outcome data available for the selected patient.</p>
      </div>
    );
  }

  const featureBarData = data.feature_bar.map((row) => ({
    ...row,
    feature_label: humanizeFeature(row.feature),
    feature_desc: FEATURE_DESCRIPTIONS[row.feature] ?? `${humanizeFeature(row.feature)} contribution to ECI scoring.`,
  }));

  const featureCorrelationData = data.feature_correlations.map((row) => ({
    ...row,
    feature_label: humanizeFeature(row.feature),
    feature_desc: FEATURE_DESCRIPTIONS[row.feature] ?? `${humanizeFeature(row.feature)} relationship with total visit count.`,
  }));

  const featureBarLookup = Object.fromEntries(featureBarData.map((row) => [row.feature_label, row.feature_desc]));
  const featureCorrelationLookup = Object.fromEntries(featureCorrelationData.map((row) => [row.feature_label, row.feature_desc]));

  return (
    <div className="relative space-y-6">
      <div className="tab-intro tab-intro-frost frost-panel">
        <div className="tab-intro-header-row">
          <div>
            <h2 className="tab-intro-title">Patient Risk Explorer</h2>
            <p className="tab-intro-subtitle">
              Expected Cost Intensity analysis and component breakdown for resource planning.
            </p>
          </div>
          <div className="app-filter tab-inline-filter" style={{ minWidth: 220 }}>
            <label htmlFor="patient-search-outcome" className="app-filter-label">
              Patient
            </label>
            <PatientSearch
              id="patient-search-outcome"
              selectedPatientId={selectedPatientId}
              onSelect={(pid) => onPatientSelect(pid)}
              disabled={loadingPatients}
              placeholder="Search patient ID..."
            />
          </div>
        </div>
        <PatientFilterBar
          filters={filters}
          onFiltersChange={onFiltersChange}
          patientMeta={patientMeta}
          idPrefix="outcome"
        />
      </div>

      {switching && (
        <div className="tab-switch-overlay" aria-live="polite" aria-busy="true">
          <div className="tab-switch-chip">
            <span className="loading-spinner tab-switch-spinner" />
            <span>Refreshing outcome analytics…</span>
          </div>
        </div>
      )}

      {/* ---- Row 1: Gauge + Narrative ---- */}
      <div
        {...reveal.getRevealProps(0, "scale").staggerAttrs}
        className={`grid gap-6 lg:grid-cols-[280px_1fr] ${reveal.getRevealProps(0, "scale").staggerClass}`}
        style={reveal.getRevealProps(0, "scale").staggerStyle}
      >
        {/* ECI Gauge */}
        <div className="frost-panel flex flex-col items-center justify-center p-6">
          <ECIGauge score={data.eci.score ?? 0} rating={data.eci.rating ?? "—"} ratingLabel={data.eci.rating_label ?? ""} />
          {data.eci.score != null && <MetricCue cue={getECICue(data.eci.score)} />}
        </div>
        {/* Narrative */}
        <NarrativePanel narrative={data.narrative} />
      </div>

      {/* ---- ECI Component Breakdown ---- */}
      <div
        {...reveal.getRevealProps(1, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(1, "scale").staggerClass}`}
        style={reveal.getRevealProps(1, "scale").staggerStyle}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
          <span className="section-label-with-info">
            ECI Component Breakdown
            <InfoTooltip metricId="outcome.feature_decomposition" />
          </span>
        </h3>
        <ResponsiveContainer width="100%" height={Math.max(220, data.feature_bar.length * 36)}>
          <BarChart
            data={featureBarData}
            layout="vertical"
            margin={{ top: 4, right: 30, left: 12, bottom: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={CHART_COLORS.grid}
              horizontal={false}
            />
            <XAxis type="number" tick={{ fill: CHART_COLORS.text, fontSize: 11 }} />
            <YAxis
              dataKey="feature_label"
              type="category"
              width={168}
              tick={(props) => <FeatureAxisTick {...props} lookup={featureBarLookup} />}
            />
            <Tooltip content={<ChartTooltipContent />} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive animationDuration={980} animationBegin={140}>
              {data.feature_bar.map((entry, idx) => (
                <Cell key={idx} fill={entry.value >= 66 ? "#E74C3C" : entry.value >= 33 ? "#F39C12" : "#2ECC71"} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                fill={CHART_COLORS.text}
                fontSize={11}
                formatter={(v) => Number(v).toFixed(1)}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* ---- ECI Cohort Ranking ---- */}
      <div
        {...reveal.getRevealProps(2, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(2, "scale").staggerClass}`}
        style={reveal.getRevealProps(2, "scale").staggerStyle}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
          <span className="section-label-with-info">
            ECI Cohort Ranking
            <InfoTooltip metricId="outcome.cohort_ranking" />
          </span>
        </h3>
        {data.patient_percentile != null && (
          <p className="mb-3 text-xs text-slate-400">
            Patient ranks at the{" "}
            <strong style={{ color: "#4FC3F7" }}>
              {data.patient_percentile.toFixed(1)}th
            </strong>{" "}
            percentile out of{" "}
            <strong style={{ color: "#fff" }}>{data.cohort_total.toLocaleString()}</strong>{" "}
            patients. Showing nearest neighbors by ECI score.
          </p>
        )}
        <ResponsiveContainer width="100%" height={320}>
          <BarChart
            data={data.cohort_ranking}
            margin={{ top: 8, right: 16, left: 8, bottom: 24 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={CHART_COLORS.grid}
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fill: CHART_COLORS.text, fontSize: 10 }}
              angle={-45}
              textAnchor="end"
              height={60}
            />
            <YAxis tick={{ fill: CHART_COLORS.text, fontSize: 11 }} />
            <Tooltip content={<ChartTooltipContent />} />
            <Bar dataKey="eci_score" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive animationDuration={1050} animationBegin={180}>
              {data.cohort_ranking.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={entry.patient_id === selectedPatientId ? "#E74C3C" : ACCENT}
                  fillOpacity={entry.patient_id === selectedPatientId ? 1 : 0.7}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* ---- Feature Correlation (Spearman) ---- */}
      <div
        {...reveal.getRevealProps(3, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(3, "scale").staggerClass}`}
        style={reveal.getRevealProps(3, "scale").staggerStyle}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
          <span className="section-label-with-info">
            Feature &rarr; Total Visit Count (Spearman &rho;)
            <InfoTooltip metricId="outcome.spearman_r" />
          </span>
        </h3>
        <p className="mb-3 text-xs text-slate-400">Hover feature labels for quick definitions.</p>
        <ResponsiveContainer
          width="100%"
          height={Math.max(220, data.feature_correlations.length * 36)}
        >
          <BarChart
            data={featureCorrelationData}
            layout="vertical"
            margin={{ top: 4, right: 30, left: 12, bottom: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              stroke={CHART_COLORS.grid}
              horizontal={false}
            />
            <XAxis
              type="number"
              domain={[-1, 1]}
              tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
            />
            <YAxis
              dataKey="feature_label"
              type="category"
              width={168}
              tick={(props) => <FeatureAxisTick {...props} lookup={featureCorrelationLookup} />}
            />
            <Tooltip content={<ChartTooltipContent />} />
            <ReferenceLine x={0} stroke={CHART_COLORS.text} strokeWidth={1} />
            <Bar dataKey="spearman_r" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive animationDuration={980} animationBegin={210}>
              {data.feature_correlations.map((entry, idx) => (
                <Cell
                  key={idx}
                  fill={entry.spearman_r >= 0 ? CHART_COLORS.positive : CHART_COLORS.negative}
                />
              ))}
              <LabelList
                dataKey="spearman_r"
                position="right"
                fill={CHART_COLORS.text}
                fontSize={11}
                formatter={(v) => Number(v).toFixed(3)}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
