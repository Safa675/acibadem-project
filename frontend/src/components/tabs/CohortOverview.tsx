"use client";

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
import {
  getCohortSizeCue,
  getHealthScoreCue,
  getHighRiskLoadCue,
  getCriticalCountCue,
  getRxIntensityCue,
} from "@/lib/interpretation";

interface Props {
  data: CohortData | null;
  loading: boolean;
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
    <div className="frost-panel" style={{ padding: "8px 12px", color: "#fff", fontSize: 13 }}>
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
    <div className="frost-panel" style={{ padding: "8px 12px", color: "#fff", fontSize: 13 }}>
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
      <div className="loading-state">
        <div className="loading-spinner" />
        <p className="loading-state-text">Loading cohort analytics…</p>
      </div>
    </div>
  );
}

/* ================================================================== */
/*  Main component                                                     */
/* ================================================================== */
export default function CohortOverview({ data, loading }: Props) {
  if (loading || !data) return <LoadingSkeleton />;

  const { kpi, composites, var_summary, rating_distribution, regime_distribution, scatter_data } =
    data;

  /* ---- derived data ---- */
  const ratingPieData = Object.entries(rating_distribution).map(([name, value]) => ({
    name,
    value,
  }));

  const regimePieData = Object.entries(regime_distribution).map(([name, value]) => ({
    name,
    value,
  }));

  const sortedComposites = [...composites].sort(
    (a, b) => b.composite_score - a.composite_score,
  );

  const cohortSizeCue = getCohortSizeCue(kpi.n_patients);
  const meanScoreCue = getHealthScoreCue(kpi.mean_score);
  const highRiskCue = getHighRiskLoadCue(kpi.n_high_risk, kpi.n_patients);
  const criticalCue = getCriticalCountCue(kpi.n_critical);
  const rxIntensityCue = getRxIntensityCue(kpi.total_rx, kpi.n_patients);

  const scatterByRating: Record<string, typeof scatter_data> = {};
  scatter_data.forEach((pt) => {
    (scatterByRating[pt.rating] ??= []).push(pt);
  });

  /* ---- render ---- */
  return (
    <div className="tab-content-inner">
      {/* ── Title ── */}
      <h2 style={{ margin: 0 }}>Cohort Overview</h2>
      <p style={{ color: CHART_COLORS.text, marginTop: 4, marginBottom: 24 }}>
        Real-time risk intelligence across all monitored patients.
      </p>

      {/* ── KPI Cards ── */}
      <div className="kpi-grid" style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16, marginBottom: 32 }}>
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">{kpi.n_patients}</div>
          <div className="metric-label">
            <MetricLabel text="Monitored Patients" metricId="cohort.n_patients" />
          </div>
          <MetricCue cue={cohortSizeCue} />
        </div>
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">{kpi.mean_score.toFixed(1)}</div>
          <div className="metric-label">
            <MetricLabel text="Mean Health Score" metricId="cohort.mean_health_score" />
          </div>
          <MetricCue cue={meanScoreCue} />
        </div>
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">{kpi.n_high_risk}</div>
          <div className="metric-label">
            <MetricLabel text="High-Risk Patients" metricId="cohort.n_high_risk" />
          </div>
          <MetricCue cue={highRiskCue} />
        </div>
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">{kpi.n_critical}</div>
          <div className="metric-label">
            <MetricLabel text="Critical State Now" metricId="cohort.n_critical" />
          </div>
          <MetricCue cue={criticalCue} />
        </div>
        <div className="frost-panel frost-kpi-card">
          <div className="metric-value">{kpi.total_rx}</div>
          <div className="metric-label">
            <MetricLabel text="Total Prescriptions" metricId="cohort.total_rx" />
          </div>
          <MetricCue cue={rxIntensityCue} />
        </div>
      </div>

      {/* ── Charts Row ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginBottom: 32 }}>
        {/* Left – Scatter */}
        <div className="frost-panel" style={{ padding: 16 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 15, color: "#fff" }}>
            <span className="section-label-with-info">
              Cohort Risk Scatter
              <InfoTooltip metricId="cohort.scatter" />
            </span>
          </h3>
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
                >
                  {points.map((pt, i) => (
                    <Cell
                      key={i}
                      r={Math.max(4, Math.min(14, (pt.csi_score ?? 50) / 8))}
                    />
                  ))}
                </Scatter>
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {/* Right – Pie charts stacked */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {/* Rating Distribution */}
          <div className="frost-panel" style={{ padding: 16, flex: 1 }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 15, color: "#fff" }}>
              <span className="section-label-with-info">
                Rating Distribution
                <InfoTooltip metricId="cohort.rating_distribution" />
              </span>
            </h3>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
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
                >
                  {ratingPieData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={RATING_COLORS[entry.name] ?? CHART_COLORS.neutral}
                    />
                  ))}
                </Pie>
                <Tooltip content={<PieTooltipContent />} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Regime State Distribution */}
          <div className="frost-panel" style={{ padding: 16, flex: 1 }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 15, color: "#fff" }}>
              <span className="section-label-with-info">
                Regime State Distribution
                <InfoTooltip metricId="cohort.regime_distribution" />
              </span>
            </h3>
            <ResponsiveContainer width="100%" height={160}>
              <PieChart>
                <Pie
                  data={regimePieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={62}
                  paddingAngle={2}
                  stroke="none"
                >
                  {regimePieData.map((entry) => (
                    <Cell
                      key={entry.name}
                      fill={STATE_COLORS[entry.name] ?? CHART_COLORS.neutral}
                    />
                  ))}
                </Pie>
                <Tooltip content={<PieTooltipContent />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ── Patient Risk Rankings Table ── */}
      <h3 style={{ margin: "0 0 12px", color: "#fff" }}>
        <span className="section-label-with-info">
          Patient Risk Rankings
          <InfoTooltip metricId="patient.summary.composite_score" />
        </span>
      </h3>
      <div className="frost-panel frost-table-wrap" style={{ marginBottom: 32 }}>
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
                  CSI Score
                  <InfoTooltip metricId="patient.summary.csi_score" />
                </span>
              </th>
              <th>CSI Tier</th>
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
                <td>{row.csi_score != null ? row.csi_score.toFixed(1) : "—"}</td>
                <td>{row.csi_tier ?? "—"}</td>
                <td>{row.n_prescriptions ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
              <th>Risk Tier</th>
            </tr>
          </thead>
          <tbody>
            {var_summary.map((row) => (
              <tr key={row.patient_id}>
                <td>{row.patient_id}</td>
                <td>{row.current_score.toFixed(1)}</td>
                <td>{row.downside_var_pct.toFixed(1)}%</td>
                <td>{row.health_var_score.toFixed(1)}</td>
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
    </div>
  );
}
