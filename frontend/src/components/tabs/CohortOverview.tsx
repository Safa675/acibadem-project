"use client";

import { useMemo } from "react";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import type { CohortData, ScatterPoint } from "@/lib/types";
import {
  RATING_COLORS,
  STATE_COLORS,
  BADGE_CLASS,
  RISK_TIER_EMOJI,
  RISK_TIER_COLORS,
  CHART_COLORS,
} from "@/lib/constants";
import MetricLabel from "@/components/ui/MetricLabel";
import InfoTooltip from "@/components/ui/InfoTooltip";
import MetricCue from "@/components/ui/MetricCue";
import Skeleton from "@/components/ui/Skeleton";
import {
  getCohortSizeCue,
  getHealthScoreCue,
  getMeanECICue,
  getCriticalCountCue,
  getRxIntensityCue,
  getDataCompletenessCue,
} from "@/lib/interpretation";
import useCountUp from "@/hooks/useCountUp";
import useStaggeredReveal from "@/hooks/useStaggeredReveal";

interface Props {
  data: CohortData | null;
  loading: boolean;
  onPageChange?: (page: number) => void;
}

/* ------------------------------------------------------------------ */
/*  Scatter tooltip                                                    */
/* ------------------------------------------------------------------ */
type ScatterTooltipProps = {
  active?: boolean;
  payload?: Array<{ payload: ScatterPoint }>;
};

function ScatterTooltipContent({ active, payload }: ScatterTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="frost-tooltip" style={{ padding: "8px 12px", color: "#fff", fontSize: 13 }}>
      <p style={{ margin: 0, fontWeight: 600 }}>Patient #{d.patient_id}</p>
      <p style={{ margin: "2px 0" }}>Health Index: {d.health_index_score}</p>
      <p style={{ margin: "2px 0" }}>NLP Score: {d.nlp_score}</p>
      <p style={{ margin: "2px 0" }}>
        Rating:{" "}
        <span style={{ color: RATING_COLORS[d.rating] ?? "#ccc" }}>
          {d.rating}
        </span>
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Pie tooltip (shared)                                               */
/* ------------------------------------------------------------------ */
type PieTooltipProps = {
  active?: boolean;
  payload?: Array<{ name: string; value: number }>;
};

function PieTooltipContent({ active, payload }: PieTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0];
  return (
    <div className="frost-tooltip" style={{ padding: "8px 12px", color: "#fff", fontSize: 13 }}>
      <p style={{ margin: 0 }}>
        {d.name}: <strong>{d.value}</strong>
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Loading skeleton                                                   */
/* ------------------------------------------------------------------ */
function LoadingSkeleton() {
  return (
    <div className="tab-content-inner">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16, marginBottom: 28 }}>
        {Array.from({ length: 5 }).map((_, idx) => (
          <Skeleton key={idx} variant="card" className="h-[126px] rounded-[14px]" />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginBottom: 28 }}>
        <Skeleton variant="card" className="h-[392px] rounded-[14px]" />
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <Skeleton variant="card" className="h-[184px] rounded-[14px]" />
          <Skeleton variant="card" className="h-[184px] rounded-[14px]" />
        </div>
      </div>

      <Skeleton variant="card" className="h-[280px] rounded-[14px] mb-6" />
      <Skeleton variant="card" className="h-[260px] rounded-[14px]" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  VaR colour helpers — discrete bins                                */
/* ------------------------------------------------------------------ */
function varPctColor(pct: number): string {
  const v = Math.max(0, pct);
  if (v === 0) return "#2ECC71";
  if (v <= 5) return "#A3E635";
  if (v <= 15) return "#FACC15";
  if (v <= 35) return "#FB923C";
  return "#EF4444";
}

function floorScoreColor(score: number): string {
  const s = Math.max(0, Math.min(100, score));
  if (s <= 20) return "#DC2626";
  if (s <= 40) return "#F97316";
  if (s <= 60) return "#FACC15";
  if (s <= 80) return "#84CC16";
  return "#22C55E";
}

/* ================================================================== */
/*  Main component                                                     */
/* ================================================================== */
export default function CohortOverview({ data, loading, onPageChange }: Props) {
  const kpi = data?.kpi ?? {
    n_patients: 0,
    mean_score: 0,
    mean_eci: 0,
    n_critical: 0,
    total_rx: 0,
  };
  const composites = data?.composites ?? [];
  const compositesPagination = data?.composites_pagination ?? null;
  const var_summary = data?.var_summary ?? [];
  const varPagination = data?.var_pagination ?? null;
  const rating_distribution = data?.rating_distribution ?? {};
  const rating_intervals = data?.rating_intervals ?? [];
  const regime_distribution = data?.regime_distribution ?? {};
  const scatter_data = data?.scatter_data ?? [];
  const scatter_total = data?.scatter_total ?? scatter_data.length;

  /* ---- derived data ---- */
  const ratingPieData = useMemo(() =>
    Object.entries(rating_distribution).map(([name, value], idx) => ({
      name,
      value,
      patternId: `rating-pattern-${idx}`,
    })),
    [rating_distribution],
  );

  const regimePieData = useMemo(() =>
    Object.entries(regime_distribution).map(([name, value], idx) => ({
      name,
      value,
      patternId: `regime-pattern-${idx}`,
    })),
    [regime_distribution],
  );

  const ratingIntervalByName = new Map(
    rating_intervals.map((interval) => [interval.rating, interval.label]),
  );

  const ratingLegendData = useMemo(() => {
    const order = ["AAA", "AA", "A", "BBB", "BB", "B/CCC"];
    return order
      .filter((name) => Object.prototype.hasOwnProperty.call(rating_distribution, name))
      .map((name) => ({
        name,
        displayName: ratingIntervalByName.has(name)
          ? `${name} (${ratingIntervalByName.get(name)})`
          : name,
        value: rating_distribution[name] ?? 0,
        color: RATING_COLORS[name] ?? CHART_COLORS.neutral,
      }));
  }, [rating_distribution, ratingIntervalByName]);

  const regimeLegendData = useMemo(() =>
    Object.entries(regime_distribution).map(([name, value]) => ({
      name,
      value,
      color: STATE_COLORS[name] ?? CHART_COLORS.neutral,
    })),
    [regime_distribution],
  );

  // Composites are pre-sorted by the API (server-side sort + pagination)
  const sortedComposites = composites;

  const cohortSizeCue = getCohortSizeCue(kpi.n_patients);
  const meanScoreCue = getHealthScoreCue(kpi.mean_score);
  const meanEciCue = getMeanECICue(kpi.mean_eci);
  const criticalCue = getCriticalCountCue(kpi.n_critical);
  const rxIntensityCue = getRxIntensityCue(kpi.total_rx, kpi.n_patients);
  const dataCompletenessCue = getDataCompletenessCue(kpi.mean_data_completeness ?? 50);

  const animatedPatients = useCountUp(kpi.n_patients, 1050, 0, !!data && !loading);
  const animatedMeanScore = useCountUp(kpi.mean_score, 1150, 1, !!data && !loading);
  const animatedMeanEci = useCountUp(kpi.mean_eci, 1000, 1, !!data && !loading);
  const animatedCritical = useCountUp(kpi.n_critical, 1000, 0, !!data && !loading);
  const animatedTotalRx = useCountUp(kpi.total_rx, 1100, 0, !!data && !loading);
  const animatedCompleteness = useCountUp(kpi.mean_data_completeness ?? 50, 1000, 1, !!data && !loading);

  const kpiReveal = useStaggeredReveal(6, { stepMs: 100, threshold: 0.2 });
  const chartReveal = useStaggeredReveal(3, { baseDelayMs: 80, stepMs: 150, threshold: 0.15 });

  const kpiCards = [
    {
      value: Math.round(animatedPatients).toString(),
      label: "Monitored Patients",
      metricId: "cohort.n_patients",
      cue: cohortSizeCue,
    },
    {
      value: animatedMeanScore.toFixed(1),
      label: "Mean Health Score",
      metricId: "cohort.mean_health_score",
      cue: meanScoreCue,
    },
    {
      value: animatedMeanEci.toFixed(1),
      label: "Mean ECI Score",
      metricId: "cohort.mean_eci",
      cue: meanEciCue,
    },
    {
      value: Math.round(animatedCritical).toString(),
      label: "Critical State Now",
      metricId: "cohort.n_critical",
      cue: criticalCue,
    },
    {
      value: Math.round(animatedTotalRx).toString(),
      label: "Total Prescriptions",
      metricId: "cohort.total_rx",
      cue: rxIntensityCue,
    },
    {
      value: `${animatedCompleteness.toFixed(1)}%`,
      label: "Data Completeness",
      metricId: "cohort.mean_data_completeness",
      cue: dataCompletenessCue,
    },
  ];

  const scatterByRating = useMemo(() => {
    const grouped: Record<string, typeof scatter_data> = {};
    scatter_data.forEach((pt) => {
      (grouped[pt.rating] ??= []).push(pt);
    });
    return grouped;
  }, [scatter_data]);

  if (loading || !data) return <LoadingSkeleton />;

  /* ---- render ---- */
  return (
    <div className="tab-content-inner">
      {/* ── Title ── */}
      <div className="tab-intro tab-intro-frost frost-panel">
        <h2 className="tab-intro-title">Cohort Overview</h2>
        <p className="tab-intro-subtitle">Real-time risk intelligence across all monitored patients.</p>
      </div>

      {/* ── KPI Cards ── */}
      <div
        className="kpi-grid"
        style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16, marginBottom: 24 }}
        aria-live="polite"
        aria-atomic="true"
      >
        {kpiCards.map((card, idx) => {
          const reveal = kpiReveal.getRevealProps(idx, "fade");
          return (
            <div
              key={card.metricId}
              {...reveal.staggerAttrs}
              className={`frost-panel frost-kpi-card ${reveal.staggerClass}`}
              style={reveal.staggerStyle}
            >
              <div className="metric-value">{card.value}</div>
              <div className="metric-label">
                <MetricLabel text={card.label} metricId={card.metricId} />
              </div>
              <MetricCue cue={card.cue} />
            </div>
          );
        })}
      </div>

      {/* ── Charts Row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginBottom: 24 }}>
        {/* Left – Scatter */}
        {(() => {
          const reveal = chartReveal.getRevealProps(0, "scale");
          return (
        <div {...reveal.staggerAttrs} className={`frost-panel ${reveal.staggerClass}`} style={{ ...reveal.staggerStyle, padding: 16 }}>
          <h3 className="section-heading-accent" style={{ margin: "0 0 12px", fontSize: 15, color: "#fff" }}>
            <span className="section-label-with-info">
              Cohort Risk Scatter
              {scatter_total > scatter_data.length && (
                <span style={{ fontSize: 11, color: "#8892A4", fontWeight: 400, marginLeft: 8 }}>
                  (showing {scatter_data.length.toLocaleString()} of {scatter_total.toLocaleString()})
                </span>
              )}
              <InfoTooltip metricId="cohort.scatter" />
            </span>
          </h3>
          <div role="img" aria-label="Scatter chart showing health index versus NLP score by patient rating">
          <ResponsiveContainer width="100%" height={360}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
              <CartesianGrid stroke={CHART_COLORS.grid} />
              <XAxis
                type="number"
                dataKey="health_index_score"
                name="Health Index"
                domain={[0, 100]}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                stroke={CHART_COLORS.axis}
                label={{ value: "Health Index Score", position: "insideBottom", offset: -4, fill: CHART_COLORS.text, fontSize: 12 }}
              />
              <YAxis
                type="number"
                dataKey="nlp_score"
                name="NLP Score"
                domain={[0, 100]}
                tick={{ fill: CHART_COLORS.text, fontSize: 11 }}
                stroke={CHART_COLORS.axis}
                label={{ value: "NLP Score", angle: -90, position: "insideLeft", fill: CHART_COLORS.text, fontSize: 12 }}
              />
              <Tooltip content={<ScatterTooltipContent />} />
              {Object.entries(scatterByRating).map(([rating, points]) => (
                <Scatter
                  key={rating}
                  name={rating}
                  data={points}
                  fill={RATING_COLORS[rating] ?? CHART_COLORS.neutral}
                  isAnimationActive={false}
                >
                  {points.map((pt, i) => (
                    <Cell
                      key={i}
                      r={Math.max(4, Math.min(14, (pt.eci_score ?? 50) / 8))}
                    />
                  ))}
                </Scatter>
              ))}
            </ScatterChart>
          </ResponsiveContainer>
          </div>
        </div>
          );
        })()}

        {/* Right – Pie charts stacked */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Rating Distribution */}
          {(() => {
            const reveal = chartReveal.getRevealProps(1, "scale");
            return (
          <div {...reveal.staggerAttrs} className={`frost-panel ${reveal.staggerClass}`} style={{ ...reveal.staggerStyle, padding: 16, flex: 1 }}>
            <h3 className="section-heading-accent" style={{ margin: "0 0 8px", fontSize: 15, color: "#fff" }}>
              <span className="section-label-with-info">
                Rating Distribution
                <InfoTooltip metricId="cohort.rating_distribution" />
              </span>
            </h3>
            <div className="pie-panel-layout">
              <div className="pie-panel-chart">
                <div role="img" aria-label="Pie chart showing cohort rating distribution">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <defs>
                      {ratingPieData.map((entry) => (
                        <pattern
                          key={entry.patternId}
                          id={entry.patternId}
                          width="8"
                          height="8"
                          patternUnits="userSpaceOnUse"
                          patternTransform="rotate(45)"
                        >
                          <rect width="8" height="8" fill={RATING_COLORS[entry.name] ?? CHART_COLORS.neutral} />
                          <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(255,255,255,0.32)" strokeWidth="1" />
                        </pattern>
                      ))}
                    </defs>
                    <Pie
                      data={ratingPieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={36}
                      outerRadius={62}
                      paddingAngle={2}
                      stroke="none"
                      isAnimationActive
                      animationDuration={900}
                      animationBegin={140}
                    >
                      {ratingPieData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={`url(#${entry.patternId})`}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<PieTooltipContent />} />
                  </PieChart>
                </ResponsiveContainer>
                </div>
              </div>
              <ul className="chart-legend" aria-label="Rating distribution legend">
                {ratingLegendData.map((item) => (
                  <li key={item.name} className="chart-legend-item">
                    <span className="chart-legend-label">
                      <span className="chart-legend-swatch" style={{ backgroundColor: item.color }} />
                      {item.displayName}
                    </span>
                    <span className="chart-legend-count">{item.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
            );
          })()}

          {/* Regime State Distribution */}
          {(() => {
            const reveal = chartReveal.getRevealProps(2, "scale");
            return (
          <div {...reveal.staggerAttrs} className={`frost-panel ${reveal.staggerClass}`} style={{ ...reveal.staggerStyle, padding: 16, flex: 1 }}>
            <h3 className="section-heading-accent" style={{ margin: "0 0 8px", fontSize: 15, color: "#fff" }}>
              <span className="section-label-with-info">
                Regime State Distribution
                <InfoTooltip metricId="cohort.regime_distribution" />
              </span>
            </h3>
            <div className="pie-panel-layout">
              <div className="pie-panel-chart">
                <div role="img" aria-label="Pie chart showing regime state distribution">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <defs>
                      {regimePieData.map((entry) => (
                        <pattern
                          key={entry.patternId}
                          id={entry.patternId}
                          width="9"
                          height="9"
                          patternUnits="userSpaceOnUse"
                        >
                          <rect width="9" height="9" fill={STATE_COLORS[entry.name] ?? CHART_COLORS.neutral} />
                          <circle cx="3" cy="3" r="1.2" fill="rgba(255,255,255,0.36)" />
                          <circle cx="8" cy="8" r="1.2" fill="rgba(255,255,255,0.36)" />
                        </pattern>
                      ))}
                    </defs>
                    <Pie
                      data={regimePieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={62}
                      paddingAngle={2}
                      stroke="none"
                      isAnimationActive
                      animationDuration={950}
                      animationBegin={300}
                    >
                      {regimePieData.map((entry) => (
                        <Cell
                          key={entry.name}
                          fill={`url(#${entry.patternId})`}
                        />
                      ))}
                    </Pie>
                    <Tooltip content={<PieTooltipContent />} />
                  </PieChart>
                </ResponsiveContainer>
                </div>
              </div>
              <ul className="chart-legend" aria-label="Regime distribution legend">
                {regimeLegendData.map((item) => (
                  <li key={item.name} className="chart-legend-item">
                    <span className="chart-legend-label">
                      <span className="chart-legend-swatch" style={{ backgroundColor: item.color }} />
                      {item.name}
                    </span>
                    <span className="chart-legend-count">{item.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
            );
          })()}
        </div>
      </div>

      {/* ── Patient Risk Rankings Table ── */}
      <h3 style={{ margin: "0 0 12px", color: "#fff" }}>
        <span className="section-label-with-info">
          Patient Risk Rankings
          <InfoTooltip metricId="patient.summary.composite_score" />
        </span>
      </h3>
      <div className="frost-panel frost-table-wrap" style={{ marginBottom: 24 }}>
        <table className="frost-table">
          <thead>
            <tr>
              <th>Patient ID</th>
              <th>Rating</th>
              <th>
                <span className="section-label-with-info">
                  Composite Score
                  <InfoTooltip metricId="patient.summary.composite_score" />
                </span>
              </th>
              <th>Health Index</th>
              <th>NLP Score</th>
              <th>
                <span className="section-label-with-info">
                  ECI Score
                  <InfoTooltip metricId="patient.summary.eci_score" />
                </span>
              </th>
              <th>ECI Rating</th>
              <th>Data Quality</th>
              <th>Rx Count</th>
            </tr>
          </thead>
          <tbody>
            {sortedComposites.map((row) => (
              <tr key={row.patient_id}>
                <td>{row.patient_id}</td>
                <td>
                  <span className={`badge ${BADGE_CLASS[row.rating] ?? ""}`}>
                    {row.rating}
                  </span>
                </td>
                <td>{row.composite_score.toFixed(2)}</td>
                <td>{row.health_index_score.toFixed(1)}</td>
                <td>{row.nlp_score.toFixed(1)}</td>
                <td>{row.eci_score != null ? row.eci_score.toFixed(1) : "—"}</td>
                <td>{row.eci_rating ?? "—"}</td>
                <td>
                  <span
                    className="badge"
                    style={{
                      background:
                        (row.data_completeness ?? 50) >= 80
                          ? "rgba(46,204,113,0.15)"
                          : (row.data_completeness ?? 50) >= 50
                            ? "rgba(250,204,21,0.15)"
                            : "rgba(239,68,68,0.15)",
                      color:
                        (row.data_completeness ?? 50) >= 80
                          ? "#2ECC71"
                          : (row.data_completeness ?? 50) >= 50
                            ? "#FACC15"
                            : "#EF4444",
                    }}
                  >
                    {row.data_completeness != null
                      ? `${row.data_completeness.toFixed(0)}%`
                      : "—"}
                  </span>
                </td>
                <td>{row.n_prescriptions ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Pagination Controls ── */}
      {compositesPagination && compositesPagination.total_pages > 1 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 16,
            margin: "12px 0 24px",
            fontSize: "0.85rem",
            color: "#B8C5D9",
          }}
        >
          <button
            className="glass"
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid rgba(255,255,255,0.08)",
              color: compositesPagination.page <= 1 ? "#555" : "#4FC3F7",
              cursor: compositesPagination.page <= 1 ? "not-allowed" : "pointer",
              background: "rgba(26,29,39,0.6)",
              fontWeight: 600,
              fontSize: "0.82rem",
            }}
            disabled={compositesPagination.page <= 1}
            onClick={() => onPageChange?.(compositesPagination.page - 1)}
          >
            Previous
          </button>
          <span>
            Page <strong style={{ color: "#fff" }}>{compositesPagination.page}</strong> of{" "}
            <strong style={{ color: "#fff" }}>{compositesPagination.total_pages}</strong>
            <span style={{ marginLeft: 8, fontSize: "0.78rem", color: "#8892A4" }}>
              ({compositesPagination.total} patients)
            </span>
          </span>
          <button
            className="glass"
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid rgba(255,255,255,0.08)",
              color:
                compositesPagination.page >= compositesPagination.total_pages
                  ? "#555"
                  : "#4FC3F7",
              cursor:
                compositesPagination.page >= compositesPagination.total_pages
                  ? "not-allowed"
                  : "pointer",
              background: "rgba(26,29,39,0.6)",
              fontWeight: 600,
              fontSize: "0.82rem",
            }}
            disabled={compositesPagination.page >= compositesPagination.total_pages}
            onClick={() => onPageChange?.(compositesPagination.page + 1)}
          >
            Next
          </button>
        </div>
      )}

      {/* ── Health VaR Summary Table ── */}
      <h3 style={{ margin: "0 0 12px", color: "#fff" }}>
        <span className="section-label-with-info">
          Health VaR Summary
          <InfoTooltip metricId="cohort.var.downside_var_pct" />
        </span>
      </h3>
      <div className="frost-panel frost-table-wrap">
        <table className="frost-table">
          <thead>
            <tr>
              <th>Patient ID</th>
              <th>Current Score</th>
              <th>
                <span className="section-label-with-info">
                  Downside VaR %
                  <InfoTooltip metricId="cohort.var.downside_var_pct" />
                </span>
              </th>
              <th>
                <span className="section-label-with-info">
                  VaR Floor Score
                  <InfoTooltip metricId="cohort.var.floor_score" />
                </span>
              </th>
              <th>
                <span className="section-label-with-info">
                  Risk Tier
                  <InfoTooltip metricId="cohort.var.risk_tier" />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {var_summary.map((row) => (
              <tr key={row.patient_id}>
                <td>{row.patient_id}</td>
                <td>{row.current_score.toFixed(1)}</td>
                <td>
                  <span style={{ color: varPctColor(row.downside_var_pct), fontWeight: 600 }}>
                    {row.downside_var_pct.toFixed(1)}%
                  </span>
                </td>
                <td>
                  <span style={{ color: floorScoreColor(row.health_var_score), fontWeight: 600 }}>
                    {row.health_var_score.toFixed(1)}
                  </span>
                </td>
                <td>
                  <span
                    style={{
                      color: RISK_TIER_COLORS[row.risk_tier] ?? CHART_COLORS.text,
                    }}
                  >
                    {RISK_TIER_EMOJI[row.risk_tier] ?? ""} {row.risk_tier}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── VaR Pagination Controls ── */}
      {varPagination && varPagination.total_pages > 1 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 16,
            margin: "12px 0 0",
            fontSize: "0.85rem",
            color: "#B8C5D9",
          }}
        >
          <button
            className="glass"
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid rgba(255,255,255,0.08)",
              color: varPagination.page <= 1 ? "#555" : "#4FC3F7",
              cursor: varPagination.page <= 1 ? "not-allowed" : "pointer",
              background: "rgba(26,29,39,0.6)",
              fontWeight: 600,
              fontSize: "0.82rem",
            }}
            disabled={varPagination.page <= 1}
            onClick={() => onPageChange?.(varPagination.page - 1)}
          >
            Previous
          </button>
          <span>
            Page <strong style={{ color: "#fff" }}>{varPagination.page}</strong> of{" "}
            <strong style={{ color: "#fff" }}>{varPagination.total_pages}</strong>
            <span style={{ marginLeft: 8, fontSize: "0.78rem", color: "#8892A4" }}>
              ({varPagination.total} patients)
            </span>
          </span>
          <button
            className="glass"
            style={{
              padding: "6px 16px",
              borderRadius: 6,
              border: "1px solid rgba(255,255,255,0.08)",
              color:
                varPagination.page >= varPagination.total_pages
                  ? "#555"
                  : "#4FC3F7",
              cursor:
                varPagination.page >= varPagination.total_pages
                  ? "not-allowed"
                  : "pointer",
              background: "rgba(26,29,39,0.6)",
              fontWeight: 600,
              fontSize: "0.82rem",
            }}
            disabled={varPagination.page >= varPagination.total_pages}
            onClick={() => onPageChange?.(varPagination.page + 1)}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
