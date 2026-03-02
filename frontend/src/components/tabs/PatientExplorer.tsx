"use client";

import { useState, useMemo } from "react";
import type { PatientData } from "@/lib/types";
import { formatDate, nlpColor } from "@/lib/utils";
import {
  RATING_COLORS,
  STATE_COLORS,
  STATE_EMOJI,
  RISK_TIER_COLORS,
  RISK_TIER_EMOJI,
  CHART_COLORS,
} from "@/lib/constants";
import MetricLabel from "@/components/ui/MetricLabel";
import InfoTooltip from "@/components/ui/InfoTooltip";
import MetricCue from "@/components/ui/MetricCue";
import {
  getCompositeScoreCue,
  getRegimeCue,
  getHealthScoreCue,
  getDownsideVarCue,
  getCSICue,
} from "@/lib/interpretation";
import {
  ComposedChart,
  LineChart,
  BarChart,
  AreaChart,
  Line,
  Bar,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceArea,
  ReferenceLine,
  Cell,
} from "recharts";

/* ═══════════════════════════════════════════════════════════════════════════
   Props
   ═══════════════════════════════════════════════════════════════════════ */

interface Props {
  data: PatientData | null;
  loading: boolean;
}

/* ═══════════════════════════════════════════════════════════════════════════
   Helpers
   ═══════════════════════════════════════════════════════════════════════ */

/** Identify contiguous state bands from the regime timeline. */
function computeStateBands(
  timeline: PatientData["regime_timeline"],
): { x1: string; x2: string; state: string }[] {
  const bands: { x1: string; x2: string; state: string }[] = [];
  if (!timeline || timeline.length === 0) return bands;

  let currentState = timeline[0].state;
  let startDate = timeline[0].date;

  for (let i = 1; i < timeline.length; i++) {
    if (timeline[i].state !== currentState) {
      bands.push({
        x1: startDate,
        x2: timeline[i - 1].date,
        state: currentState ?? "Insufficient Data",
      });
      currentState = timeline[i].state;
      startDate = timeline[i].date;
    }
  }
  bands.push({
    x1: startDate,
    x2: timeline[timeline.length - 1].date,
    state: currentState ?? "Insufficient Data",
  });
  return bands;
}

/** Skeleton block for loading state. */
function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-xl bg-white/[0.04] ${className}`}
    />
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   Component
   ═══════════════════════════════════════════════════════════════════════ */

export default function PatientExplorer({ data, loading }: Props) {
  const [notesOpen, setNotesOpen] = useState(false);

  const frostyTooltipStyle = {
    background: "var(--color-frost-tooltip-bg)",
    backdropFilter: "blur(12px)",
    WebkitBackdropFilter: "blur(12px)",
    border: "1px solid var(--color-frost-tooltip-border)",
    borderRadius: 12,
    boxShadow: "0 12px 30px rgba(4,7,14,0.38)",
    fontSize: 12,
  };

  /* ── Derived data ──────────────────────────────────────────────────── */

  const stateBands = useMemo(
    () => (data ? computeStateBands(data.regime_timeline) : []),
    [data],
  );

  const varFanChartData = useMemo(() => {
    if (!data?.var_fan) return null;
    const fan = data.var_fan;

    const historyPoints = fan.history_dates.map((d, i) => ({
      date: d,
      score: fan.history_scores[i],
      type: "history" as const,
    }));

    const futurePoints = fan.future_dates.map((d) => ({
      date: d,
      p05: fan.p05,
      p25: fan.p25,
      p50: fan.p50,
      p75: fan.p75,
      p95: fan.p95,
      type: "forecast" as const,
    }));

    // Bridge: last history point starts the forecast area
    const bridge =
      historyPoints.length > 0
        ? {
            date: historyPoints[historyPoints.length - 1].date,
            score: historyPoints[historyPoints.length - 1].score,
            p05: fan.p05,
            p25: fan.p25,
            p50: fan.p50,
            p75: fan.p75,
            p95: fan.p95,
            type: "bridge" as const,
          }
        : null;

    return {
      combined: [
        ...historyPoints,
        ...(bridge ? [bridge] : []),
        ...futurePoints,
      ],
      riskTier: fan.risk_tier,
      varPct: fan.var_pct,
    };
  }, [data]);

  const labEntries = useMemo(() => {
    if (!data?.lab_series) return [];
    return Object.entries(data.lab_series).slice(0, 5);
  }, [data]);

  /* ── Loading skeleton ──────────────────────────────────────────────── */

  if (loading) {
    return (
      <div className="space-y-6 p-4">
        <div className="loading-state">
          <div className="loading-spinner" />
          <p className="loading-state-text">Loading patient longitudinal profile…</p>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>

        <Skeleton className="h-56" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="empty-state">
        <p className="empty-state-text">No patient data loaded. Select a patient to continue analysis.</p>
      </div>
    );
  }

  const s = data.summary;
  const compositeCue = getCompositeScoreCue(s.composite_score);
  const regimeCue = getRegimeCue(s.regime_state);
  const healthCue = s.health_score != null ? getHealthScoreCue(s.health_score) : null;
  const varCue = s.downside_var_pct != null ? getDownsideVarCue(s.downside_var_pct) : null;
  const csiCue = s.csi_score != null ? getCSICue(s.csi_score) : null;

  /* ════════════════════════════════════════════════════════════════════
     Render
     ════════════════════════════════════════════════════════════════ */

  return (
    <div className="space-y-6 p-2 sm:p-4">
      {/* ── 1. Summary Metric Cards ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {/* Composite Rating */}
        <div className="frost-panel frost-kpi-card">
          <div
            className="metric-value"
            style={{ color: RATING_COLORS[s.rating] ?? "#B8C5D9" }}
          >
            {s.rating}
          </div>
          <div className="metric-label">
            <MetricLabel text="Composite Rating" metricId="patient.summary.composite_score" />
          </div>
          <MetricCue cue={compositeCue} showDetail={false} />
        </div>

        {/* Composite Score */}
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">
            {s.composite_score.toFixed(1)}
          </div>
          <div className="metric-label">
            <MetricLabel text="Composite Score" metricId="patient.summary.composite_score" />
          </div>
          <MetricCue cue={compositeCue} />
        </div>

        {/* Regime State */}
        <div className="frost-panel frost-kpi-card">
          <div
            className="metric-value text-lg"
            style={{ color: STATE_COLORS[s.regime_state] ?? "#B8C5D9" }}
          >
            {STATE_EMOJI[s.regime_state] ?? ""} {s.regime_state}
          </div>
          <div className="metric-label">
            <MetricLabel text="Regime State" metricId="patient.summary.regime_state" />
          </div>
          <MetricCue cue={regimeCue} />
        </div>

        {/* Health Score */}
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">
            {s.health_score != null ? s.health_score.toFixed(1) : "—"}
          </div>
          <div className="metric-label">
            <MetricLabel text="Health Score" metricId="cohort.mean_health_score" />
          </div>
          {healthCue && <MetricCue cue={healthCue} />}
        </div>

        {/* Downside VaR % */}
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">
            {s.downside_var_pct != null
              ? `${s.downside_var_pct.toFixed(1)}%`
              : "—"}
          </div>
          <div className="metric-label">
            <MetricLabel text="Downside VaR %" metricId="patient.summary.downside_var_pct" />
          </div>
          {varCue && <MetricCue cue={varCue} />}
        </div>

        {/* CSI Score */}
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">
            {s.csi_score != null ? s.csi_score.toFixed(2) : "—"}
          </div>
          <div className="metric-label">
            <MetricLabel text="CSI Score" metricId="patient.summary.csi_score" />
          </div>
          {csiCue && <MetricCue cue={csiCue} />}
        </div>
      </div>

      {/* ── 2. Demographics Row ──────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {[
          { label: "Age", value: s.age ?? "—" },
          { label: "Sex", value: s.sex ?? "—" },
          { label: "Comorbidities", value: s.n_comorbidities },
          { label: "Total Visits", value: s.total_visits ?? "—" },
          { label: "Lab Draws", value: s.n_lab_draws },
          { label: "Prescriptions", value: s.n_prescriptions },
        ].map((d) => (
          <div
            key={d.label}
            className="frost-panel px-4 py-4 text-center"
          >
            <div className="text-lg font-semibold text-text-primary">
              {d.value}
            </div>
            <div className="mt-0.5 text-xs font-medium uppercase tracking-wide text-text-muted">
              {d.label}
            </div>
          </div>
        ))}
      </div>

      {/* ── 3. Comorbidities Panel ───────────────────────────────────── */}
      {data.comorbidities.length > 0 && (
        <div className="frost-panel px-5 py-4">
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-text-muted">
            Comorbidities
          </h3>
          <p className="text-sm leading-relaxed text-text-secondary">
            {data.comorbidities
              .map((c) => (c.detail ? `${c.label} (${c.detail})` : c.label))
              .join(" \u2022 ")}
          </p>
        </div>
      )}

      {/* ── 4. Regime Timeline Chart ─────────────────────────────────── */}
      {data.regime_timeline.length > 0 && (
        <div className="frost-panel p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              Patient Regime &mdash; Health Trajectory
              <InfoTooltip metricId="patient.regime.timeline" />
            </span>
          </h3>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart
              data={data.regime_timeline}
              margin={{ top: 10, right: 20, bottom: 5, left: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={CHART_COLORS.grid}
              />
              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => formatDate(v)}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                minTickGap={40}
              />
              <YAxis
                domain={[0, 108]}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
              />
              <Tooltip
                contentStyle={frostyTooltipStyle}
                labelFormatter={(v: unknown) => formatDate(String(v))}
              />

              {/* State background bands */}
              {stateBands.map((band, i) => (
                <ReferenceArea
                  key={i}
                  x1={band.x1}
                  x2={band.x2}
                  fill={STATE_COLORS[band.state] ?? "#B0BEC5"}
                  fillOpacity={0.18}
                  strokeOpacity={0}
                />
              ))}

              {/* Prescription event lines */}
              {data.prescription_dates.map((d, i) => (
                <ReferenceLine
                  key={`rx-${i}`}
                  x={d}
                  stroke={CHART_COLORS.prescription}
                  strokeDasharray="4 3"
                  strokeWidth={1}
                />
              ))}

              {/* MA line */}
              <Line
                type="monotone"
                dataKey="ma"
                stroke="#9E9E9E"
                strokeDasharray="6 3"
                dot={false}
                strokeWidth={1.5}
                name="Moving Avg"
                connectNulls
              />

              {/* Health Score line */}
              <Line
                type="monotone"
                dataKey="health_score"
                stroke={CHART_COLORS.accent}
                dot={false}
                strokeWidth={2}
                name="Health Score"
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Legend for state bands */}
          <div className="mt-2 flex flex-wrap gap-3 pl-2">
            {Object.entries(STATE_COLORS).map(([state, color]) => (
              <span
                key={state}
                className="flex items-center gap-1.5 text-xs text-text-muted"
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: color }}
                />
                {state}
              </span>
            ))}
            <span className="flex items-center gap-1.5 text-xs text-text-muted">
              <span
                className="inline-block h-0.5 w-4"
                style={{
                  background: CHART_COLORS.prescription,
                  borderTop: "1px dashed",
                }}
              />
              Prescription
            </span>
          </div>
        </div>
      )}

      {/* ── 5. VaR Fan Chart ─────────────────────────────────────────── */}
      {varFanChartData && (
        <div className="frost-panel p-4">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              <span className="section-label-with-info">
                Health VaR &mdash; Monte Carlo Deterioration Forecast
                <InfoTooltip metricId="patient.var.fan" />
              </span>
            </h3>
            <span
              className="rounded-md px-2.5 py-1 text-xs font-semibold"
              style={{
                background: `${RISK_TIER_COLORS[varFanChartData.riskTier] ?? "#B0BEC5"}22`,
                color:
                  RISK_TIER_COLORS[varFanChartData.riskTier] ?? "#B0BEC5",
                border: `1px solid ${RISK_TIER_COLORS[varFanChartData.riskTier] ?? "#B0BEC5"}44`,
              }}
            >
              {RISK_TIER_EMOJI[varFanChartData.riskTier] ?? ""}{" "}
              {varFanChartData.riskTier} &mdash;{" "}
              {varFanChartData.varPct.toFixed(1)}% VaR
            </span>
          </div>

          <ResponsiveContainer width="100%" height={280}>
            <AreaChart
              data={varFanChartData.combined}
              margin={{ top: 10, right: 20, bottom: 5, left: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={CHART_COLORS.grid}
              />
              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => formatDate(v)}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                minTickGap={40}
              />
              <YAxis
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
              />
              <Tooltip
                contentStyle={frostyTooltipStyle}
                labelFormatter={(v: unknown) => formatDate(String(v))}
              />

              {/* p05 – p95 band */}
              <Area
                type="monotone"
                dataKey="p95"
                stroke="none"
                fill="rgba(79,195,247,0.18)"
                name="p95"
              />
              <Area
                type="monotone"
                dataKey="p05"
                stroke="none"
                fill="#0B0D14"
                name="p05"
              />

              {/* VaR floor */}
              <ReferenceLine
                y={data.var_fan!.p05}
                stroke={CHART_COLORS.negative}
                strokeDasharray="6 3"
                strokeWidth={1.5}
                label={{
                  value: `VaR floor ${data.var_fan!.p05.toFixed(0)}`,
                  fill: CHART_COLORS.negative,
                  fontSize: 11,
                  position: "insideBottomLeft",
                }}
              />

              {/* Median forecast line (dashed) */}
              <Line
                type="monotone"
                dataKey="p50"
                stroke={CHART_COLORS.accent}
                strokeDasharray="6 3"
                dot={false}
                strokeWidth={1.5}
                name="Median Forecast"
              />

              {/* Historical score line */}
              <Line
                type="monotone"
                dataKey="score"
                stroke={CHART_COLORS.accent}
                dot={false}
                strokeWidth={2}
                name="Historical"
                connectNulls
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── 6. NLP Bar Chart ─────────────────────────────────────────── */}
      {data.nlp_bars.length > 0 && (
        <div className="frost-panel p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              Turkish Clinical NLP &mdash; Visit-Level Language Signal
              <InfoTooltip metricId="patient.nlp.visit_signal" />
            </span>
          </h3>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart
              data={data.nlp_bars}
              margin={{ top: 10, right: 20, bottom: 5, left: 0 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke={CHART_COLORS.grid}
              />

              {/* Faint background bands */}
              <ReferenceArea
                y1={0}
                y2={1}
                fill={CHART_COLORS.positive}
                fillOpacity={0.04}
              />
              <ReferenceArea
                y1={-1}
                y2={0}
                fill={CHART_COLORS.negative}
                fillOpacity={0.04}
              />

              {/* Zero line */}
              <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" />

              <XAxis
                dataKey="date"
                tickFormatter={(v: string) => formatDate(v)}
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                minTickGap={40}
              />
              <YAxis
                stroke={CHART_COLORS.axis}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
              />
              <Tooltip
                contentStyle={frostyTooltipStyle}
                labelFormatter={(v: unknown) => formatDate(String(v))}
                formatter={(value: unknown) => [(Number(value)).toFixed(3), "NLP"]}
              />

              <Bar dataKey="nlp_composite" name="NLP Composite" radius={[3, 3, 0, 0]}>
                {data.nlp_bars.map((entry, i) => (
                  <Cell
                    key={i}
                    fill={
                      entry.nlp_composite < -0.05
                        ? CHART_COLORS.negative
                        : entry.nlp_composite < 0.05
                          ? CHART_COLORS.amber
                          : CHART_COLORS.positive
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── 7. NLI Transformer Scores Table ──────────────────────────── */}
      {data.nli_scores.length > 0 && (
        <div className="frost-panel p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              NLI Transformer Scores
              <InfoTooltip metricId="patient.nli.score" />
            </span>
          </h3>
          <div className="frost-panel frost-table-wrap">
            <table className="frost-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Text</th>
                  <th className="text-right">
                    <span className="section-label-with-info" style={{ justifyContent: "flex-end" }}>
                      NLI Score
                      <InfoTooltip metricId="patient.nli.score" />
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.nli_scores.map((row, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap">
                      {formatDate(row.date)}
                    </td>
                    <td>{row.source}</td>
                    <td
                      className="max-w-xs truncate"
                      title={row.text}
                    >
                      {row.text.length > 80
                        ? `${row.text.slice(0, 80)}...`
                        : row.text}
                    </td>
                    <td
                      className="text-right font-semibold"
                      style={{ color: nlpColor(row.nli_score) }}
                    >
                      {row.nli_score.toFixed(3)}
                    </td>
                  </tr>
                ))}

                {/* Footer average */}
                <tr className="border-t border-white/10">
                  <td
                    colSpan={3}
                    className="text-right text-xs font-semibold uppercase tracking-wide text-text-muted"
                  >
                    Overall Average
                  </td>
                  <td
                    className="text-right font-bold"
                    style={{
                      color: nlpColor(
                        data.nli_scores.reduce(
                          (a, r) => a + r.nli_score,
                          0,
                        ) / data.nli_scores.length,
                      ),
                    }}
                  >
                    {(
                      data.nli_scores.reduce(
                        (a, r) => a + r.nli_score,
                        0,
                      ) / data.nli_scores.length
                    ).toFixed(3)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── 8. Lab Time Series ───────────────────────────────────────── */}
      {labEntries.length > 0 && (
        <div className="frost-panel p-4">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            Laboratory Time-Series
          </h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {labEntries.map(([testName, series]) => {
              const chartData = series.dates.map((d, i) => ({
                date: d,
                value: series.values[i],
                refMin: series.ref_min,
                refMax: series.ref_max,
              }));

              return (
                <div
                  key={testName}
                  className="frost-panel rounded-xl p-4"
                >
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
                    {testName}
                  </div>
                  <ResponsiveContainer width="100%" height={160}>
                    <LineChart
                      data={chartData}
                      margin={{ top: 5, right: 10, bottom: 5, left: -10 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke={CHART_COLORS.grid}
                      />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(v: string) => formatDate(v)}
                        stroke={CHART_COLORS.axis}
                        tick={{ fill: CHART_COLORS.text, fontSize: 9 }}
                        minTickGap={30}
                      />
                      <YAxis
                        stroke={CHART_COLORS.axis}
                        tick={{ fill: CHART_COLORS.text, fontSize: 9 }}
                      />
                        <Tooltip
                          contentStyle={{ ...frostyTooltipStyle, fontSize: 11 }}
                          labelFormatter={(v: unknown) => formatDate(String(v))}
                        />

                      {/* Reference range band */}
                      {series.ref_min != null &&
                        series.ref_max != null && (
                          <ReferenceArea
                            y1={series.ref_min}
                            y2={series.ref_max}
                            fill="#2ECC71"
                            fillOpacity={0.08}
                            strokeOpacity={0}
                          />
                        )}

                      <Line
                        type="monotone"
                        dataKey="value"
                        stroke={CHART_COLORS.accent}
                        strokeWidth={1.5}
                        dot={{ r: 2, fill: CHART_COLORS.accent }}
                        name={testName}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── 9. Clinical Notes (Collapsible) ──────────────────────────── */}
      {data.clinical_notes.length > 0 && (
        <div className="frost-panel">
          <button
            onClick={() => setNotesOpen((o) => !o)}
            className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-white/[0.02]"
          >
            <h3 className="text-sm font-semibold uppercase tracking-wide text-text-muted">
              Clinical Notes ({data.clinical_notes.length})
            </h3>
            <span
              className="text-text-muted transition-transform"
              style={{
                transform: notesOpen ? "rotate(180deg)" : "rotate(0deg)",
              }}
            >
              &#9660;
            </span>
          </button>

          {notesOpen && (
            <div className="space-y-4 border-t border-white/[0.06] px-5 py-4">
              {data.clinical_notes.map((note, ni) => (
                <div key={ni}>
                  <div className="mb-1 text-xs font-semibold text-accent">
                    {formatDate(note.date)}
                  </div>
                  <div className="space-y-1.5">
                    {note.entries.map((entry, ei) => (
                      <div key={ei} className="text-sm text-text-secondary">
                        <span className="mr-1.5 inline-block rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                          {entry.source}
                        </span>
                        {entry.text}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
