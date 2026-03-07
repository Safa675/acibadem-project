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
  AreaChart,
  Area,
  LineChart,
  Line,
  Legend,
} from "recharts";
import type {
  OutcomeData,
  PatientFilters,
  PatientMeta,
  DRGEpisodeData,
  CostVaRData,
  ReimbursementGapData,
  CostTrajectoryData,
  DRGSummaryData,
  SUTCostEstimate,
} from "@/lib/types";
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

function NarrativePanel({ narrative, hasSutCost }: { narrative: string; hasSutCost: boolean }) {
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

      {hasSutCost && (
        <>
          <div className="my-4 border-t border-white/10" />
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300"
            style={{ color: "#4FC3F7" }}
          >
            SUT Financial Analytics
          </h3>
          <div className="space-y-2 text-sm leading-relaxed text-slate-400">
            <p>
              Cost projections below are derived from Turkey&apos;s{" "}
              <strong className="text-slate-200">
                Sa&#287;l&#305;k Uygulama Tebli&#287;i (SUT)
              </strong>{" "}
              &mdash; the official Health Implementation Communiqu&eacute; published in the
              Resm&icirc; Gazete (Official Gazette). SUT defines the maximum reimbursable prices
              that SGK (Sosyal G&uuml;venlik Kurumu / Social Security Institution) will pay for
              every medical procedure, laboratory test, hospital bed-day, and clinical service
              in Turkey&apos;s healthcare system.
            </p>
            <p>
              Prices are sourced directly from the{" "}
              <strong className="text-slate-200">EK-2B</strong> schedule
              (5,074 fee-for-service procedure codes including lab tests, imaging, surgery, and
              bed tariffs) and the{" "}
              <strong className="text-slate-200">EK-2C</strong> schedule
              (2,423 diagnosis-based bundled packages grouped by clinical complexity: A1, A2, A3,
              B, C, D, E). All amounts are in Turkish Lira (TRY) at current gazette rates.
            </p>
            <p>
              The analytics include{" "}
              <strong className="text-slate-200">DRG episode modeling</strong> (cost allocation
              per diagnosis-related group),{" "}
              <strong className="text-slate-200">Monte Carlo Cost VaR</strong> (10,000-simulation
              value-at-risk using triangular distributions),{" "}
              <strong className="text-slate-200">reimbursement gap analysis</strong> (estimated
              hospital cost vs. SGK ceiling with markup factors), and{" "}
              <strong className="text-slate-200">cost trajectory forecasting</strong> (monthly
              burn rate extrapolation with trend detection).
            </p>
          </div>
        </>
      )}
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
  const reveal = useStaggeredReveal(7, { baseDelayMs: 40, stepMs: 140, threshold: 0.15 });

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

      {/* ---- Row 1: Gauge + SUT Cost + Narrative ---- */}
      <div
        {...reveal.getRevealProps(0, "scale").staggerAttrs}
        className={`grid gap-6 lg:grid-cols-[280px_1fr] ${reveal.getRevealProps(0, "scale").staggerClass}`}
        style={reveal.getRevealProps(0, "scale").staggerStyle}
      >
        {/* Left column: ECI Gauge + SUT Cost Card stacked */}
        <div className="flex flex-col gap-6">
          <div className="frost-panel flex flex-col items-center justify-center p-6">
            <ECIGauge score={data.eci.score ?? 0} rating={data.eci.rating ?? "—"} ratingLabel={data.eci.rating_label ?? ""} />
            {data.eci.score != null && <MetricCue cue={getECICue(data.eci.score)} />}
          </div>
          {data.sut_cost && <SUTCostCard sut={data.sut_cost} />}
        </div>
        {/* Narrative + SUT explanation */}
        <NarrativePanel narrative={data.narrative} hasSutCost={!!data.sut_cost} />
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

      {/* ---- Feature Correlation (Spearman) ---- */}
      <div
        {...reveal.getRevealProps(2, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(2, "scale").staggerClass}`}
        style={reveal.getRevealProps(2, "scale").staggerStyle}
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

      {/* ═══════════════════════════════════════════════════════════════════
          SUT FINANCIAL ANALYTICS SECTION
          ═══════════════════════════════════════════════════════════════════ */}

      {data.sut_cost && (
        <>
          {/* ---- Cost Breakdown Chart ---- */}
          <div
            {...reveal.getRevealProps(3, "scale").staggerAttrs}
            className={reveal.getRevealProps(3, "scale").staggerClass}
            style={reveal.getRevealProps(3, "scale").staggerStyle}
          >
            <SUTBreakdownChart sut={data.sut_cost} />
          </div>

          {/* ---- Cost VaR + Reimbursement Gap ---- */}
          <div
            {...reveal.getRevealProps(4, "scale").staggerAttrs}
            className={`grid gap-6 lg:grid-cols-2 ${reveal.getRevealProps(4, "scale").staggerClass}`}
            style={reveal.getRevealProps(4, "scale").staggerStyle}
          >
            {data.cost_var && <CostVaRPanel data={data.cost_var} />}
            {data.reimbursement_gaps && <ReimbursementGapPanel data={data.reimbursement_gaps} />}
          </div>

          {/* ---- DRG Episodes ---- */}
          {data.drg_summary && data.drg_summary.n_episodes > 0 && (
            <div
              {...reveal.getRevealProps(5, "scale").staggerAttrs}
              className={`frost-panel p-5 ${reveal.getRevealProps(5, "scale").staggerClass}`}
              style={reveal.getRevealProps(5, "scale").staggerStyle}
            >
              <DRGPanel data={data.drg_summary} />
            </div>
          )}

          {/* ---- Cost Trajectory ---- */}
          {data.cost_trajectory && (
            <div
              {...reveal.getRevealProps(6, "scale").staggerAttrs}
              className={`frost-panel p-5 ${reveal.getRevealProps(6, "scale").staggerClass}`}
              style={reveal.getRevealProps(6, "scale").staggerStyle}
            >
              <CostTrajectoryPanel data={data.cost_trajectory} />
            </div>
          )}
        </>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   SUT SUB-COMPONENTS
   ═══════════════════════════════════════════════════════════════════════════ */

const TIER_COLORS: Record<string, string> = {
  "Very High": "#E74C3C",
  "High": "#E67E22",
  "Moderate": "#F39C12",
  "Low": "#2ECC71",
  "Minimal": "#27AE60",
};

function SUTCostCard({ sut }: { sut: SUTCostEstimate }) {
  const tierColor = TIER_COLORS[sut.cost_tier] ?? "#4FC3F7";

  return (
    <div
      className="frost-panel flex flex-col items-center justify-center gap-3 p-6"
      style={{ borderTop: `3px solid ${tierColor}` }}
    >
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        Estimated SUT Cost
      </p>
      <span className="text-3xl font-bold tracking-tight" style={{ color: tierColor }}>
        {sut.cost_mid.toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
        <span className="ml-1 text-base font-normal text-slate-400">TRY</span>
      </span>
      <span
        className="rounded-full px-3 py-0.5 text-xs font-semibold uppercase tracking-wider"
        style={{
          background: `${tierColor}22`,
          color: tierColor,
          border: `1px solid ${tierColor}44`,
        }}
      >
        {sut.cost_tier}
      </span>
      <p className="mt-1 text-center text-xs text-slate-400" style={{ maxWidth: 220 }}>
        {sut.cost_tier_label}
      </p>
      <div className="mt-2 w-full space-y-1 text-xs text-slate-400">
        <div className="flex justify-between">
          <span>Range</span>
          <span className="text-slate-300">
            {sut.cost_min.toLocaleString("tr-TR")} – {sut.cost_max.toLocaleString("tr-TR")} TRY
          </span>
        </div>
        <div className="flex justify-between">
          <span>Lab tests</span>
          <span className="text-slate-300">{sut.n_lab_tests}</span>
        </div>
        <div className="flex justify-between">
          <span>Visits</span>
          <span className="text-slate-300">{sut.n_visits}</span>
        </div>
        <div className="flex justify-between">
          <span>Prescriptions</span>
          <span className="text-slate-300">{sut.n_prescriptions}</span>
        </div>
        <div className="flex justify-between">
          <span>Procedures</span>
          <span className="text-slate-300">{sut.n_procedures}</span>
        </div>
      </div>
    </div>
  );
}

function SUTBreakdownChart({ sut }: { sut: SUTCostEstimate }) {
  const breakdownData = [
    { category: "Lab", min: sut.breakdown.lab.min, max: sut.breakdown.lab.max, mid: (sut.breakdown.lab.min + sut.breakdown.lab.max) / 2, color: "#4FC3F7" },
    { category: "Visits", min: sut.breakdown.visit.min, max: sut.breakdown.visit.max, mid: (sut.breakdown.visit.min + sut.breakdown.visit.max) / 2, color: "#2ECC71" },
    { category: "Rx", min: sut.breakdown.rx.min, max: sut.breakdown.rx.max, mid: (sut.breakdown.rx.min + sut.breakdown.rx.max) / 2, color: "#F39C12" },
    { category: "Procedures", min: sut.breakdown.procedure.min, max: sut.breakdown.procedure.max, mid: (sut.breakdown.procedure.min + sut.breakdown.procedure.max) / 2, color: "#E74C3C" },
  ];

  return (
    <div className="frost-panel p-5">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
        Cost Breakdown by Category
      </h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={breakdownData} margin={{ top: 8, right: 30, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
          <XAxis dataKey="category" tick={{ fill: CHART_COLORS.text, fontSize: 12 }} />
          <YAxis tick={{ fill: CHART_COLORS.text, fontSize: 11 }} />
          <Tooltip content={<ChartTooltipContent />} />
          <Bar dataKey="mid" radius={[4, 4, 0, 0]} maxBarSize={48} isAnimationActive animationDuration={900}>
            {breakdownData.map((entry, idx) => (
              <Cell key={idx} fill={entry.color} />
            ))}
            <LabelList
              dataKey="mid"
              position="top"
              fill={CHART_COLORS.text}
              fontSize={10}
              formatter={(v) => `${Number(v).toFixed(0)} TRY`}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function CostVaRPanel({ data }: { data: CostVaRData }) {
  // Build area chart data from the percentile distribution
  const distData = data.cost_distribution.map((cost, i) => ({
    percentile: i,
    cost,
  }));

  const varIdx = Math.round(data.confidence_level * 100);

  return (
    <div className="frost-panel p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
        Cost Value-at-Risk (Monte Carlo)
      </h3>
      <div className="mb-3 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-xs text-slate-400">VaR (95%)</p>
          <p className="text-lg font-bold text-amber-400">{data.var_amount.toLocaleString("tr-TR")} TRY</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">Expected</p>
          <p className="text-lg font-bold text-sky-400">{data.expected_cost.toLocaleString("tr-TR")} TRY</p>
        </div>
        <div>
          <p className="text-xs text-slate-400">CVaR (ES)</p>
          <p className="text-lg font-bold text-red-400">{data.cvar_amount.toLocaleString("tr-TR")} TRY</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={distData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
          <defs>
            <linearGradient id="costGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#4FC3F7" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#4FC3F7" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis
            dataKey="percentile"
            tick={{ fill: CHART_COLORS.text, fontSize: 10 }}
            tickFormatter={(v: number) => `${v}%`}
          />
          <YAxis tick={{ fill: CHART_COLORS.text, fontSize: 10 }} />
          <Tooltip content={<ChartTooltipContent />} />
          <ReferenceLine x={varIdx} stroke="#F39C12" strokeDasharray="4 4" label={{ value: `VaR ${data.confidence_level * 100}%`, fill: "#F39C12", fontSize: 10 }} />
          <Area type="monotone" dataKey="cost" stroke="#4FC3F7" fill="url(#costGrad)" strokeWidth={2} />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-2 flex justify-between text-xs text-slate-500">
        <span>P5: {data.cost_p5.toLocaleString("tr-TR")} TRY</span>
        <span>P50: {data.cost_p50.toLocaleString("tr-TR")} TRY</span>
        <span>P95: {data.cost_p95.toLocaleString("tr-TR")} TRY</span>
      </div>
    </div>
  );
}

function ReimbursementGapPanel({ data }: { data: ReimbursementGapData }) {
  const riskColor =
    data.risk_rating === "high" ? "#E74C3C" :
    data.risk_rating === "medium" ? "#F39C12" : "#2ECC71";

  const gapChartData = data.gaps.map((g) => ({
    category: g.category.charAt(0).toUpperCase() + g.category.slice(1),
    reimbursement: g.sut_reimbursement,
    gap: g.gap_amount,
    actual: g.estimated_actual_cost,
  }));

  return (
    <div className="frost-panel p-5">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
        Reimbursement Gap Analysis
      </h3>
      <div className="mb-3 flex items-center gap-4">
        <div className="text-center">
          <p className="text-xs text-slate-400">Coverage</p>
          <p className="text-lg font-bold" style={{ color: riskColor }}>
            {data.overall_coverage_pct.toFixed(1)}%
          </p>
        </div>
        <div className="text-center">
          <p className="text-xs text-slate-400">Total Gap</p>
          <p className="text-lg font-bold text-red-400">
            {data.total_gap.toLocaleString("tr-TR")} TRY
          </p>
        </div>
        <span
          className="ml-auto rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase"
          style={{
            background: `${riskColor}22`,
            color: riskColor,
            border: `1px solid ${riskColor}44`,
          }}
        >
          {data.risk_rating} risk
        </span>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={gapChartData} margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
          <XAxis dataKey="category" tick={{ fill: CHART_COLORS.text, fontSize: 11 }} />
          <YAxis tick={{ fill: CHART_COLORS.text, fontSize: 10 }} />
          <Tooltip content={<ChartTooltipContent />} />
          <Legend
            wrapperStyle={{ fontSize: 10, color: CHART_COLORS.text }}
          />
          <Bar dataKey="reimbursement" name="SUT Reimburse" fill="#4FC3F7" stackId="cost" radius={[0, 0, 0, 0]} maxBarSize={36} />
          <Bar dataKey="gap" name="Gap (Loss)" fill="#E74C3C" stackId="cost" radius={[4, 4, 0, 0]} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DRGPanel({ data }: { data: DRGSummaryData }) {
  return (
    <>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
        DRG Episode Cost Modeling
      </h3>
      <div className="mb-4 flex flex-wrap gap-6 text-sm">
        <div>
          <span className="text-slate-400">Episodes:</span>{" "}
          <span className="font-bold text-white">{data.n_episodes}</span>
        </div>
        <div>
          <span className="text-slate-400">Total DRG Cost:</span>{" "}
          <span className="font-bold text-sky-400">{data.total_drg_cost.toLocaleString("tr-TR")} TRY</span>
        </div>
        <div>
          <span className="text-slate-400">Mean/Episode:</span>{" "}
          <span className="font-bold text-white">{data.mean_episode_cost.toLocaleString("tr-TR")} TRY</span>
        </div>
        <div>
          <span className="text-slate-400">Costliest:</span>{" "}
          <span className="font-bold text-amber-400">{data.most_expensive_drg}</span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-left text-slate-400">
              <th className="pb-2 pr-3">#</th>
              <th className="pb-2 pr-3">ICD-10</th>
              <th className="pb-2 pr-3">Description</th>
              <th className="pb-2 pr-3 text-right">LOS</th>
              <th className="pb-2 pr-3 text-right">Lab</th>
              <th className="pb-2 pr-3 text-right">Visit</th>
              <th className="pb-2 pr-3 text-right">Rx</th>
              <th className="pb-2 pr-3 text-right">Proc</th>
              <th className="pb-2 text-right">Total</th>
            </tr>
          </thead>
          <tbody>
            {data.episodes.map((ep) => (
              <tr key={ep.episode_id} className="border-b border-white/5 hover:bg-white/[0.03]">
                <td className="py-1.5 pr-3 text-slate-500">{ep.episode_id + 1}</td>
                <td className="py-1.5 pr-3 font-mono text-sky-400">{ep.primary_icd10}</td>
                <td className="py-1.5 pr-3 text-slate-300">{ep.description}</td>
                <td className="py-1.5 pr-3 text-right text-slate-300">{ep.los_days}</td>
                <td className="py-1.5 pr-3 text-right text-slate-300">{ep.lab_cost.toLocaleString("tr-TR")}</td>
                <td className="py-1.5 pr-3 text-right text-slate-300">{ep.visit_cost.toLocaleString("tr-TR")}</td>
                <td className="py-1.5 pr-3 text-right text-slate-300">{ep.rx_cost.toLocaleString("tr-TR")}</td>
                <td className="py-1.5 pr-3 text-right text-slate-300">{ep.procedure_cost.toLocaleString("tr-TR")}</td>
                <td className="py-1.5 text-right font-semibold text-white">{ep.total_cost.toLocaleString("tr-TR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function CostTrajectoryPanel({ data }: { data: CostTrajectoryData }) {
  const trendColor =
    data.trend === "increasing" ? "#E74C3C" :
    data.trend === "decreasing" ? "#2ECC71" : "#F39C12";

  // Separate historical and forecast points
  const chartData = data.trajectory.map((pt) => ({
    period: pt.period.length > 12 ? pt.period.slice(-8) : pt.period,
    cumulative: pt.cumulative_cost,
    periodCost: pt.period_cost,
    isForecast: pt.period.startsWith("Forecast"),
  }));

  return (
    <>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-300">
        Cost Trajectory Forecast
      </h3>
      <div className="mb-4 flex flex-wrap gap-6 text-sm">
        <div>
          <span className="text-slate-400">Monthly Burn:</span>{" "}
          <span className="font-bold text-sky-400">{data.monthly_burn_rate.toLocaleString("tr-TR")} TRY/mo</span>
        </div>
        <div>
          <span className="text-slate-400">Projected Annual:</span>{" "}
          <span className="font-bold text-white">{data.projected_annual_cost.toLocaleString("tr-TR")} TRY</span>
        </div>
        <div>
          <span className="text-slate-400">Trend:</span>{" "}
          <span className="font-bold" style={{ color: trendColor }}>
            {data.trend.charAt(0).toUpperCase() + data.trend.slice(1)}
          </span>
        </div>
        <div>
          <span className="text-slate-400">Horizon:</span>{" "}
          <span className="font-bold text-white">{data.forecast_horizon_months} months</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 24 }}>
          <defs>
            <linearGradient id="trajGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#4FC3F7" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#4FC3F7" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
          <XAxis
            dataKey="period"
            tick={{ fill: CHART_COLORS.text, fontSize: 9 }}
            angle={-35}
            textAnchor="end"
            height={50}
          />
          <YAxis tick={{ fill: CHART_COLORS.text, fontSize: 10 }} />
          <Tooltip content={<ChartTooltipContent />} />
          <Area
            type="monotone"
            dataKey="cumulative"
            stroke="#4FC3F7"
            fill="url(#trajGrad)"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="periodCost"
            stroke="#F39C12"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="mt-1 flex gap-4 text-xs text-slate-500">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-sky-400" /> Cumulative Cost</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-400" /> Per-Period Cost</span>
      </div>
    </>
  );
}
