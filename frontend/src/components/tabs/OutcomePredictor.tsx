"use client";

import React from "react";
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
import type { OutcomeData } from "@/lib/types";
import { ACCENT, CHART_COLORS } from "@/lib/constants";
import { csiColor } from "@/lib/utils";
import InfoTooltip from "@/components/ui/InfoTooltip";
import MetricCue from "@/components/ui/MetricCue";
import { getCSICue } from "@/lib/interpretation";
import useStaggeredReveal from "@/hooks/useStaggeredReveal";

interface Props {
  data: OutcomeData | null;
  loading: boolean;
  selectedPatientId: number;
}

/* ---------- CSI Gauge (SVG semicircle) ---------- */

function CSIGauge({ score, tier }: { score: number; tier: string }) {
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
        {tier}
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
        Clinical Assessment Narrative
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

export default function OutcomePredictor({ data, loading, selectedPatientId }: Props) {
  const reveal = useStaggeredReveal(4, { baseDelayMs: 40, stepMs: 140, threshold: 0.15 });

  if (loading) {
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

  return (
    <div className="space-y-8">
      {/* ---- Row 1: Gauge + Narrative ---- */}
      <div
        {...reveal.getRevealProps(0, "scale").staggerAttrs}
        className={`grid gap-6 lg:grid-cols-[280px_1fr] ${reveal.getRevealProps(0, "scale").staggerClass}`}
        style={reveal.getRevealProps(0, "scale").staggerStyle}
      >
        {/* CSI Gauge */}
        <div className="frost-panel flex flex-col items-center justify-center p-6">
          <CSIGauge score={data.csi.score} tier={data.csi.tier} />
          <MetricCue cue={getCSICue(data.csi.score)} />
        </div>
        {/* Narrative */}
        <NarrativePanel narrative={data.narrative} />
      </div>

      {/* ---- CSI Feature Decomposition ---- */}
      <div
        {...reveal.getRevealProps(1, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(1, "scale").staggerClass}`}
        style={reveal.getRevealProps(1, "scale").staggerStyle}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
          <span className="section-label-with-info">
            CSI Feature Decomposition
            <InfoTooltip metricId="outcome.feature_decomposition" />
          </span>
        </h3>
        <ResponsiveContainer width="100%" height={Math.max(220, data.feature_bar.length * 36)}>
          <BarChart
            data={data.feature_bar}
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
              dataKey="feature"
              type="category"
              width={140}
              tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
            />
            <Tooltip content={<ChartTooltipContent />} />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive animationDuration={980} animationBegin={140}>
              {data.feature_bar.map((entry, idx) => (
                <Cell key={idx} fill={csiColor(entry.value)} />
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

      {/* ---- CSI Cohort Ranking ---- */}
      <div
        {...reveal.getRevealProps(2, "scale").staggerAttrs}
        className={`frost-panel p-5 ${reveal.getRevealProps(2, "scale").staggerClass}`}
        style={reveal.getRevealProps(2, "scale").staggerStyle}
      >
        <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-slate-300">
          <span className="section-label-with-info">
            CSI Cohort Ranking
            <InfoTooltip metricId="outcome.cohort_ranking" />
          </span>
        </h3>
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
            <Bar dataKey="csi_score" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive animationDuration={1050} animationBegin={180}>
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
        <ResponsiveContainer
          width="100%"
          height={Math.max(220, data.feature_correlations.length * 36)}
        >
          <BarChart
            data={data.feature_correlations}
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
              dataKey="feature"
              type="category"
              width={140}
              tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
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
