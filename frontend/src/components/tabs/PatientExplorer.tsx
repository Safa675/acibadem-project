"use client";

import { useState, useMemo, memo, type ChangeEvent } from "react";
import type { PatientData, PatientMeta, PatientFilters } from "@/lib/types";
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
import Skeleton from "@/components/ui/Skeleton";
import PatientSearch from "@/components/ui/PatientSearch";
import {
  getCompositeScoreCue,
  getRegimeCue,
  getHealthScoreCue,
  getDownsideVarCue,
  getECICue,
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
import useStaggeredReveal from "@/hooks/useStaggeredReveal";

/* ═══════════════════════════════════════════════════════════════════════════
   Props
   ═══════════════════════════════════════════════════════════════════════ */

interface Props {
  data: PatientData | null;
  loading: boolean;
  switching: boolean;
  patients: string[];
  filteredPatients: string[];
  patientMeta: PatientMeta[];
  selectedPatientId: string | null;
  onPatientChange: (e: ChangeEvent<HTMLSelectElement>) => void;
  onPatientSelect: (patientId: string | null) => void;
  loadingPatients: boolean;
  filters: PatientFilters;
  onFiltersChange: (filters: PatientFilters) => void;
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

const COMORBIDITY_CONDITION_OPTIONS = [
  { key: "hypertension", label: "Hypertension" },
  { key: "cardiovascular", label: "Cardiovascular" },
  { key: "diabetes", label: "Diabetes" },
  { key: "hematologic", label: "Hematologic" },
  { key: "other_chronic", label: "Other Chronic" },
  { key: "surgery_history", label: "Surgery History" },
] as const;

/* ═══════════════════════════════════════════════════════════════════════════
   Memoized chart sub-components — prevent re-render when unrelated state changes
   ═══════════════════════════════════════════════════════════════════════ */

const RegimeTimelineChart = memo(function RegimeTimelineChart({
  data,
  stateBands,
  prescriptionDates,
  frostyTooltipStyle,
}: {
  data: PatientData;
  stateBands: { x1: string; x2: string; state: string }[];
  prescriptionDates: string[];
  frostyTooltipStyle: React.CSSProperties;
}) {
  return (
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
        {prescriptionDates.map((d, i) => (
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
          isAnimationActive={false}
        />

        {/* Health Score line */}
        <Line
          type="monotone"
          dataKey="health_score"
          stroke={CHART_COLORS.accent}
          dot={false}
          strokeWidth={2}
          name="Health Score"
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
});

const VarFanChart = memo(function VarFanChart({
  chartData,
  varFan,
  frostyTooltipStyle,
}: {
  chartData: Array<Record<string, unknown>>;
  varFan: NonNullable<PatientData["var_fan"]>;
  frostyTooltipStyle: React.CSSProperties;
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart
        data={chartData}
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
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="p05"
          stroke="none"
          fill="#0B0D14"
          name="p05"
          isAnimationActive={false}
        />

        {/* VaR floor */}
        <ReferenceLine
          y={varFan.p05}
          stroke={CHART_COLORS.negative}
          strokeDasharray="6 3"
          strokeWidth={1.5}
          label={{
            value: `VaR floor ${varFan.p05.toFixed(0)}`,
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
          isAnimationActive={false}
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
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
});

const NlpBarChart = memo(function NlpBarChart({
  nlpBars,
  frostyTooltipStyle,
}: {
  nlpBars: PatientData["nlp_bars"];
  frostyTooltipStyle: React.CSSProperties;
}) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart
        data={nlpBars}
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

        <Bar dataKey="nlp_composite" name="NLP Composite" radius={[3, 3, 0, 0]} isAnimationActive={false}>
          {nlpBars.map((entry, i) => (
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
  );
});

const LabSeriesChart = memo(function LabSeriesChart({
  testName,
  series,
  frostyTooltipStyle,
}: {
  testName: string;
  series: { dates: string[]; values: number[]; ref_min: number | null; ref_max: number | null };
  frostyTooltipStyle: React.CSSProperties;
}) {
  const chartData = series.dates.map((d, i) => ({
    date: d,
    value: series.values[i],
    refMin: series.ref_min,
    refMax: series.ref_max,
  }));
  return (
    <div className="frost-panel rounded-xl p-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-text-muted">
        {testName}
      </div>
      <div role="img" aria-label={`Line chart for ${testName} laboratory values over time`}>
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
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
});

/* ═══════════════════════════════════════════════════════════════════════════
   Component
   ═══════════════════════════════════════════════════════════════════════ */

export default function PatientExplorer({
  data,
  loading,
  switching,
  patients,
  filteredPatients,
  patientMeta,
  selectedPatientId,
  onPatientChange,
  onPatientSelect,
  loadingPatients,
  filters,
  onFiltersChange,
}: Props) {
  const [notesOpen, setNotesOpen] = useState(false);
  const [nliSourceFilter, setNliSourceFilter] = useState<string>("ALL");
  const [nliVisibleCount, setNliVisibleCount] = useState(20);
  const [nliRequestedCount, setNliRequestedCount] = useState("20");
  const genderFilter = filters.gender;
  const doctorFilter = filters.doctor;
  const selectedComorbidityConditions = filters.comorbidityConditions;
  const ageMinInput = filters.ageMin;
  const ageMaxInput = filters.ageMax;
  const weightMinInput = filters.weightMin;
  const weightMaxInput = filters.weightMax;
  const metricReveal = useStaggeredReveal(6, { stepMs: 100, threshold: 0.2 });
  const demographicReveal = useStaggeredReveal(6, { baseDelayMs: 50, stepMs: 70, threshold: 0.2 });
  const sectionReveal = useStaggeredReveal(8, { baseDelayMs: 120, stepMs: 120, threshold: 0.14 });

  const frostyTooltipStyle = {
    background: "var(--color-frost-tooltip-bg)",
    backdropFilter: "blur(12px)",
    WebkitBackdropFilter: "blur(12px)",
    border: "1px solid var(--color-frost-tooltip-border)",
    borderRadius: 12,
    boxShadow: "0 12px 30px rgba(2,5,10,0.55)",
    fontSize: 12,
  };

  /* ── Derived data ──────────────────────────────────────────────────── */

  const metaByPatientId = useMemo(
    () => new Map(patientMeta.map((m) => [m.patient_id, m])),
    [patientMeta],
  );

  const doctorOptions = useMemo(() => {
    const vals = new Set<string>();
    patientMeta.forEach((meta) => {
      const code = meta.doctor_code?.trim();
      if (code) vals.add(code);
    });
    return Array.from(vals).sort((a, b) => a.localeCompare(b));
  }, [patientMeta]);

  const ageMin = ageMinInput.trim() === "" ? null : Number(ageMinInput);
  const ageMax = ageMaxInput.trim() === "" ? null : Number(ageMaxInput);
  const weightMin = weightMinInput.trim() === "" ? null : Number(weightMinInput);
  const weightMax = weightMaxInput.trim() === "" ? null : Number(weightMaxInput);

  const hasInvalidAgeNumber =
    ageMinInput.trim() !== "" && !Number.isFinite(ageMin);
  const hasInvalidAgeNumberMax =
    ageMaxInput.trim() !== "" && !Number.isFinite(ageMax);
  const hasInvalidWeightNumber =
    weightMinInput.trim() !== "" && !Number.isFinite(weightMin);
  const hasInvalidWeightNumberMax =
    weightMaxInput.trim() !== "" && !Number.isFinite(weightMax);

  const hasInvalidRange =
    (ageMin != null && ageMax != null && ageMin > ageMax) ||
    (weightMin != null && weightMax != null && weightMin > weightMax);

  const hasFilterValidationError =
    hasInvalidAgeNumber ||
    hasInvalidAgeNumberMax ||
    hasInvalidWeightNumber ||
    hasInvalidWeightNumberMax ||
    hasInvalidRange;


  const selectedPatientInFilter =
    selectedPatientId != null && filteredPatients.includes(selectedPatientId);
  const patientSelectValue =
    selectedPatientInFilter && selectedPatientId != null
      ? selectedPatientId
      : "";

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

  const nliSources = useMemo(() => {
    if (!data?.nli_scores) return [];
    return Array.from(new Set(data.nli_scores.map((row) => row.source))).sort();
  }, [data]);

  const filteredNliScores = useMemo(() => {
    if (!data?.nli_scores) return [];
    if (nliSourceFilter === "ALL") return data.nli_scores;
    return data.nli_scores.filter((row) => row.source === nliSourceFilter);
  }, [data, nliSourceFilter]);

  const visibleNliCount =
    filteredNliScores.length === 0
      ? 0
      : Math.min(Math.max(1, nliVisibleCount), filteredNliScores.length);
  const visibleNliRows = filteredNliScores.slice(0, visibleNliCount);

  const resetFilters = () => {
    onFiltersChange({
      gender: "ALL",
      doctor: "ALL",
      comorbidityConditions: [],
      ageMin: "",
      ageMax: "",
      weightMin: "",
      weightMax: "",
    });
  };

  const toggleComorbidityCondition = (conditionKey: string) => {
    const prev = filters.comorbidityConditions;
    const next = prev.includes(conditionKey)
      ? prev.filter((key) => key !== conditionKey)
      : [...prev, conditionKey];
    onFiltersChange({...filters, comorbidityConditions: next});
  };

  /* ── Loading skeleton ──────────────────────────────────────────────── */

  if (loading && !data) {
    return (
      <div className="space-y-6 p-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} variant="card" className="h-24" />
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} variant="block" className="h-16" />
          ))}
        </div>

        <Skeleton variant="card" className="h-44" />
        <Skeleton variant="card" className="h-72" />
        <div className="grid gap-4 sm:grid-cols-2">
          <Skeleton variant="card" className="h-56" />
          <Skeleton variant="card" className="h-56" />
        </div>
        <Skeleton variant="card" className="h-60" />
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
  const eciCue = s.eci_score != null ? getECICue(s.eci_score) : null;
  const hasCriticalVar = s.downside_var_pct != null && s.downside_var_pct > 70;
  const hasCriticalRating = /CCC|CC|C|D/.test(s.rating) || s.rating === "B/CCC";

  /* ════════════════════════════════════════════════════════════════════
     Render
     ════════════════════════════════════════════════════════════════ */

  return (
    <div className="relative space-y-6 p-2 sm:p-4">
      <div className="tab-intro tab-intro-frost frost-panel">
        <div className="tab-intro-header-row">
          <div>
            <h2 className="tab-intro-title">Patient Health Explorer</h2>
            <p className="tab-intro-subtitle">
              Longitudinal risk trajectory, clinical language signals, and individualized context for selected patient.
            </p>
          </div>
          <div className="app-filter tab-inline-filter" style={{ minWidth: 220 }}>
            <label htmlFor="patient-search-explorer" className="app-filter-label">
              Patient
            </label>
            <PatientSearch
              id="patient-search-explorer"
              selectedPatientId={selectedPatientId}
              onSelect={(pid) => onPatientSelect(pid)}
              disabled={loadingPatients}
              placeholder="Search patient ID..."
            />
          </div>
        </div>

        <div className="explorer-filter-bar">
          <div className="explorer-filter-field">
            <span className="explorer-filter-label-row">
              <MetricLabel
                text="Gender"
                metricId="explorer.filter.gender"
                className="explorer-filter-label-metric"
              />
            </span>
            <select
              id="explorer-gender-filter"
              className="explorer-filter-select"
              value={genderFilter}
              onChange={(e) => onFiltersChange({...filters, gender: e.target.value})}
            >
              <option value="ALL">All</option>
              <option value="K">Female</option>
              <option value="E">Male</option>
            </select>
          </div>

          <div className="explorer-filter-field">
            <span className="explorer-filter-label-row">
              <MetricLabel
                text="Doctor"
                metricId="explorer.filter.doctor_code"
                className="explorer-filter-label-metric"
              />
            </span>
            <select
              id="explorer-doctor-filter"
              className="explorer-filter-select"
              value={doctorFilter}
              onChange={(e) => onFiltersChange({...filters, doctor: e.target.value})}
            >
              <option value="ALL">All</option>
              {doctorOptions.map((doctorCode) => (
                <option key={doctorCode} value={doctorCode}>
                  {doctorCode}
                </option>
              ))}
            </select>
          </div>

          <div className="explorer-filter-field explorer-filter-field-range">
            <span className="explorer-filter-label-row">
              <MetricLabel
                text="Age"
                metricId="explorer.filter.age_range"
                className="explorer-filter-label-metric"
              />
            </span>
            <div className="explorer-filter-range">
              <input
                id="explorer-age-min"
                className="explorer-filter-input"
                type="number"
                min={0}
                value={ageMinInput}
                onChange={(e) => onFiltersChange({...filters, ageMin: e.target.value})}
                placeholder="Min"
              />
              <span className="explorer-filter-range-sep">-</span>
              <input
                id="explorer-age-max"
                className="explorer-filter-input"
                type="number"
                min={0}
                value={ageMaxInput}
                onChange={(e) => onFiltersChange({...filters, ageMax: e.target.value})}
                placeholder="Max"
              />
            </div>
          </div>

          <div className="explorer-filter-field explorer-filter-field-range">
            <span className="explorer-filter-label-row">
              <MetricLabel
                text="Weight (kg)"
                metricId="explorer.filter.weight_range"
                className="explorer-filter-label-metric"
              />
            </span>
            <div className="explorer-filter-range">
              <input
                id="explorer-weight-min"
                className="explorer-filter-input"
                type="number"
                min={0}
                step="0.1"
                value={weightMinInput}
                onChange={(e) => onFiltersChange({...filters, weightMin: e.target.value})}
                placeholder="Min"
              />
              <span className="explorer-filter-range-sep">-</span>
              <input
                id="explorer-weight-max"
                className="explorer-filter-input"
                type="number"
                min={0}
                step="0.1"
                value={weightMaxInput}
                onChange={(e) => onFiltersChange({...filters, weightMax: e.target.value})}
                placeholder="Max"
              />
            </div>
          </div>

          <div className="explorer-filter-field explorer-filter-field-comorb">
            <span className="explorer-filter-label-row">
              <MetricLabel
                text="Comorbidities"
                metricId="explorer.filter.comorbidities"
                className="explorer-filter-label-metric"
              />
            </span>
            <div className="explorer-filter-checkboxes">
              {COMORBIDITY_CONDITION_OPTIONS.map((option) => {
                const inputId = `explorer-comorb-${option.key}`;
                return (
                  <label key={option.key} htmlFor={inputId} className="explorer-filter-checkbox-label">
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={selectedComorbidityConditions.includes(option.key)}
                      onChange={() => toggleComorbidityCondition(option.key)}
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          </div>

          <button
            type="button"
            className="explorer-filter-reset"
            onClick={resetFilters}
          >
            Reset Filters
          </button>
        </div>

        {hasFilterValidationError && (
          <p className="explorer-filter-message explorer-filter-message-error">
            Invalid filter input: use numeric bounds and keep min less than or equal to max.
          </p>
        )}
        {!hasFilterValidationError && filteredPatients.length === 0 && !loadingPatients && (
          <p className="explorer-filter-message">
            No patients match current filters.
          </p>
        )}
      </div>

      {switching && (
        <div className="tab-switch-overlay" aria-live="polite" aria-busy="true">
          <div className="tab-switch-chip">
            <span className="loading-spinner tab-switch-spinner" />
            <span>Loading selected patient data…</span>
          </div>
        </div>
      )}

      {/* ── 1. Summary Metric Cards ──────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {/* Composite Rating */}
        {(() => {
          const reveal = metricReveal.getRevealProps(0, "fade");
          return (
        <div
          {...reveal.staggerAttrs}
          className={`frost-panel frost-kpi-card ${reveal.staggerClass} ${hasCriticalRating ? "metric-pulse-glow-red" : ""}`}
          style={reveal.staggerStyle}
        >
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
          );
        })()}

        {/* Composite Score */}
        {(() => {
          const reveal = metricReveal.getRevealProps(1, "fade");
          return (
        <div {...reveal.staggerAttrs} className={`frost-panel frost-kpi-card ${reveal.staggerClass}`} style={reveal.staggerStyle}>
          <div className="metric-value">
            {s.composite_score.toFixed(1)}
          </div>
          <div className="metric-label">
            <MetricLabel text="Composite Score" metricId="patient.summary.composite_score" />
          </div>
          <MetricCue cue={compositeCue} />
        </div>
          );
        })()}

        {/* Regime State */}
        {(() => {
          const reveal = metricReveal.getRevealProps(2, "fade");
          return (
        <div
          {...reveal.staggerAttrs}
          className={`frost-panel frost-kpi-card regime-glow ${reveal.staggerClass}`}
          style={{ ...reveal.staggerStyle, ["--regime-glow-color" as string]: STATE_COLORS[s.regime_state] ?? "#B8C5D9" }}
        >
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
          );
        })()}

        {/* Health Score */}
        {(() => {
          const reveal = metricReveal.getRevealProps(3, "fade");
          return (
        <div {...reveal.staggerAttrs} className={`frost-panel frost-kpi-card ${reveal.staggerClass}`} style={reveal.staggerStyle}>
          <div className="metric-value">
            {s.health_score != null ? s.health_score.toFixed(1) : "—"}
          </div>
          <div className="metric-label">
            <MetricLabel text="Health Score" metricId="cohort.mean_health_score" />
          </div>
          {healthCue && <MetricCue cue={healthCue} />}
        </div>
          );
        })()}

        {/* Downside VaR % */}
        {(() => {
          const reveal = metricReveal.getRevealProps(4, "fade");
          return (
        <div
          {...reveal.staggerAttrs}
          className={`frost-panel frost-kpi-card ${reveal.staggerClass} ${hasCriticalVar ? "metric-pulse-glow-red" : ""}`}
          style={reveal.staggerStyle}
        >
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
          );
        })()}

        {/* ECI Score */}
        {(() => {
          const reveal = metricReveal.getRevealProps(5, "fade");
          return (
        <div {...reveal.staggerAttrs} className={`frost-panel frost-kpi-card ${reveal.staggerClass}`} style={reveal.staggerStyle}>
          <div className="metric-value">
            {s.eci_score != null ? s.eci_score.toFixed(1) : "—"}
          </div>
          <div className="metric-label">
            <MetricLabel text="ECI Score" metricId="patient.summary.eci_score" />
          </div>
          {eciCue && <MetricCue cue={eciCue} />}
        </div>
          );
        })()}
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
        ].map((d, idx) => {
          const reveal = demographicReveal.getRevealProps(idx, "fade");
          return (
          <div
            key={d.label}
            {...reveal.staggerAttrs}
            className={`frost-panel px-4 py-4 text-center ${reveal.staggerClass}`}
            style={reveal.staggerStyle}
          >
            <div className="text-lg font-semibold text-text-primary">
              {d.value}
            </div>
            <div className="mt-0.5 text-xs font-medium uppercase tracking-wide text-text-muted">
              {d.label}
            </div>
          </div>
          );
        })}
      </div>

      <div className="section-separator" />

      {/* ── 3. Comorbidities Panel ───────────────────────────────────── */}
      {data.comorbidities.length > 0 && (
        <div
          {...sectionReveal.getRevealProps(0, "scale").staggerAttrs}
          className={`frost-panel px-5 py-4 ${sectionReveal.getRevealProps(0, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(0, "scale").staggerStyle}
        >
          <h3 className="section-heading-accent mb-2 text-sm font-semibold uppercase tracking-wide text-text-muted">
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
        <div
          {...sectionReveal.getRevealProps(1, "scale").staggerAttrs}
          className={`frost-panel p-4 ${sectionReveal.getRevealProps(1, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(1, "scale").staggerStyle}
        >
          <h3 className="section-heading-accent mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              Patient Regime &mdash; Health Trajectory
              <InfoTooltip metricId="patient.regime.timeline" />
            </span>
          </h3>
          <div role="img" aria-label="Timeline chart showing patient health score trajectory, state bands, and prescription events">
          <RegimeTimelineChart data={data} stateBands={stateBands} prescriptionDates={data.prescription_dates} frostyTooltipStyle={frostyTooltipStyle} />
          </div>

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

      <div className="section-separator" />

      {/* ── 5. VaR Fan Chart ─────────────────────────────────────────── */}
      {varFanChartData && (
        <div
          {...sectionReveal.getRevealProps(2, "scale").staggerAttrs}
          className={`frost-panel p-4 ${sectionReveal.getRevealProps(2, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(2, "scale").staggerStyle}
        >
          <div className="mb-3 flex items-center justify-between">
            <h3 className="section-heading-accent text-sm font-semibold uppercase tracking-wide text-text-muted">
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

          <div role="img" aria-label="Area chart showing historical score and forecast downside VaR fan range">
          <VarFanChart chartData={varFanChartData.combined} varFan={data.var_fan!} frostyTooltipStyle={frostyTooltipStyle} />
          </div>
        </div>
      )}

      {/* ── 6. NLP Bar Chart ─────────────────────────────────────────── */}
      {data.nlp_bars.length > 0 && (
        <div
          {...sectionReveal.getRevealProps(3, "scale").staggerAttrs}
          className={`frost-panel p-4 ${sectionReveal.getRevealProps(3, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(3, "scale").staggerStyle}
        >
          <h3 className="section-heading-accent mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              Turkish Clinical NLP &mdash; Visit-Level Language Signal
              <InfoTooltip metricId="patient.nlp.visit_signal" />
            </span>
          </h3>
          <div role="img" aria-label="Bar chart showing visit-level NLP composite signal over time">
          <NlpBarChart nlpBars={data.nlp_bars} frostyTooltipStyle={frostyTooltipStyle} />
          </div>
          <div className="chart-legend-inline" aria-label="NLP signal legend">
            <span className="chart-legend-label"><span className="chart-legend-swatch" style={{ backgroundColor: CHART_COLORS.positive }} /> Positive Signal</span>
            <span className="chart-legend-label"><span className="chart-legend-swatch" style={{ backgroundColor: CHART_COLORS.amber }} /> Neutral Signal</span>
            <span className="chart-legend-label"><span className="chart-legend-swatch" style={{ backgroundColor: CHART_COLORS.negative }} /> Negative Signal</span>
          </div>
        </div>
      )}

      <div className="section-separator" />

      {/* ── 7. NLI Transformer Scores Table ──────────────────────────── */}
      {data.nli_scores.length > 0 && (
        <div
          {...sectionReveal.getRevealProps(4, "scale").staggerAttrs}
          className={`frost-panel p-4 ${sectionReveal.getRevealProps(4, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(4, "scale").staggerStyle}
        >
          <h3 className="section-heading-accent mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            <span className="section-label-with-info">
              NLI Transformer Scores
              <InfoTooltip metricId="patient.nli.score" />
            </span>
          </h3>

          <div className="nli-toolbar">
            <div className="nli-toolbar-group">
              <label className="nli-toolbar-label" htmlFor="nli-source-filter">Source</label>
              <select
                id="nli-source-filter"
                className="nli-toolbar-select"
                value={nliSourceFilter}
                onChange={(e) => {
                  setNliSourceFilter(e.target.value);
                  setNliVisibleCount(20);
                  setNliRequestedCount("20");
                }}
              >
                <option value="ALL">All Sources</option>
                {nliSources.map((source) => (
                  <option key={source} value={source}>{source}</option>
                ))}
              </select>
            </div>

            <div className="nli-toolbar-group">
              <label className="nli-toolbar-label" htmlFor="nli-show-count">Show N</label>
              <input
                id="nli-show-count"
                className="nli-toolbar-input"
                type="number"
                min={1}
                max={Math.max(1, filteredNliScores.length)}
                value={nliRequestedCount}
                onChange={(e) => {
                  const raw = e.target.value;
                  setNliRequestedCount(raw);
                  const parsed = Number(raw);
                  if (!Number.isFinite(parsed)) return;
                  const next = Math.min(Math.max(1, Math.floor(parsed)), Math.max(1, filteredNliScores.length));
                  setNliVisibleCount(next);
                }}
              />
            </div>
          </div>

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
                {visibleNliRows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-6 text-center text-sm text-slate-400">
                      No NLI rows match the selected source filter.
                    </td>
                  </tr>
                ) : visibleNliRows.map((row, i) => (
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
                      color: visibleNliRows.length
                        ? nlpColor(
                            visibleNliRows.reduce((a, r) => a + r.nli_score, 0) /
                              visibleNliRows.length,
                          )
                        : "#9db3cc",
                    }}
                  >
                    {visibleNliRows.length
                      ? (
                          visibleNliRows.reduce((a, r) => a + r.nli_score, 0) /
                          visibleNliRows.length
                        ).toFixed(3)
                      : "—"}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {visibleNliCount < filteredNliScores.length && (
            <button
              type="button"
              className="nli-load-more"
              onClick={() => {
                const next = Math.min(nliVisibleCount + 20, filteredNliScores.length);
                setNliVisibleCount(next);
                setNliRequestedCount(String(next));
              }}
            >
              Load More ({filteredNliScores.length - visibleNliCount} remaining)
            </button>
          )}
        </div>
      )}

      {/* ── 8. Lab Time Series ───────────────────────────────────────── */}
      {labEntries.length > 0 && (
        <div
          {...sectionReveal.getRevealProps(5, "scale").staggerAttrs}
          className={`frost-panel p-4 ${sectionReveal.getRevealProps(5, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(5, "scale").staggerStyle}
        >
          <h3 className="section-heading-accent mb-3 text-sm font-semibold uppercase tracking-wide text-text-muted">
            Laboratory Time-Series
          </h3>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {labEntries.map(([testName, series]) => (
              <LabSeriesChart key={testName} testName={testName} series={series} frostyTooltipStyle={frostyTooltipStyle} />
            ))}
          </div>
        </div>
      )}

      {/* ── 9. Clinical Notes (Collapsible) ──────────────────────────── */}
      {data.clinical_notes.length > 0 && (
        <div
          {...sectionReveal.getRevealProps(6, "scale").staggerAttrs}
          className={`frost-panel ${sectionReveal.getRevealProps(6, "scale").staggerClass}`}
          style={sectionReveal.getRevealProps(6, "scale").staggerStyle}
        >
          <button
            onClick={() => setNotesOpen((o) => !o)}
            className="focus-ringable flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-white/[0.02]"
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
