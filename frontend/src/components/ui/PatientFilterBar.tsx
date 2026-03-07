"use client";

import { useMemo } from "react";
import type { PatientMeta, PatientFilters } from "@/lib/types";
import MetricLabel from "@/components/ui/MetricLabel";

const COMORBIDITY_CONDITION_OPTIONS = [
  { key: "hypertension", label: "Hypertension" },
  { key: "cardiovascular", label: "Cardiovascular" },
  { key: "diabetes", label: "Diabetes" },
  { key: "hematologic", label: "Hematologic" },
  { key: "other_chronic", label: "Other Chronic" },
  { key: "surgery_history", label: "Surgery History" },
] as const;

interface PatientFilterBarProps {
  filters: PatientFilters;
  onFiltersChange: (filters: PatientFilters) => void;
  patientMeta: PatientMeta[];
  /** Optional id prefix to avoid duplicate DOM IDs when rendered in multiple tabs */
  idPrefix?: string;
}

export default function PatientFilterBar({
  filters,
  onFiltersChange,
  patientMeta,
  idPrefix = "explorer",
}: PatientFilterBarProps) {
  const genderFilter = filters.gender;
  const doctorFilter = filters.doctor;
  const selectedComorbidityConditions = filters.comorbidityConditions;
  const ageMinInput = filters.ageMin;
  const ageMaxInput = filters.ageMax;
  const weightMinInput = filters.weightMin;
  const weightMaxInput = filters.weightMax;

  const doctorOptions = useMemo(() => {
    const vals = new Set<string>();
    patientMeta.forEach((meta) => {
      const code = meta.doctor_code?.trim();
      if (code) vals.add(code);
    });
    return Array.from(vals).sort((a, b) => a.localeCompare(b));
  }, [patientMeta]);

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
    onFiltersChange({ ...filters, comorbidityConditions: next });
  };

  // Validation
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

  return (
    <>
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
            id={`${idPrefix}-gender-filter`}
            className="explorer-filter-select"
            value={genderFilter}
            onChange={(e) =>
              onFiltersChange({ ...filters, gender: e.target.value })
            }
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
            id={`${idPrefix}-doctor-filter`}
            className="explorer-filter-select"
            value={doctorFilter}
            onChange={(e) =>
              onFiltersChange({ ...filters, doctor: e.target.value })
            }
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
              id={`${idPrefix}-age-min`}
              className="explorer-filter-input"
              type="number"
              min={0}
              value={ageMinInput}
              onChange={(e) =>
                onFiltersChange({ ...filters, ageMin: e.target.value })
              }
              placeholder="Min"
            />
            <span className="explorer-filter-range-sep">-</span>
            <input
              id={`${idPrefix}-age-max`}
              className="explorer-filter-input"
              type="number"
              min={0}
              value={ageMaxInput}
              onChange={(e) =>
                onFiltersChange({ ...filters, ageMax: e.target.value })
              }
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
              id={`${idPrefix}-weight-min`}
              className="explorer-filter-input"
              type="number"
              min={0}
              step="0.1"
              value={weightMinInput}
              onChange={(e) =>
                onFiltersChange({ ...filters, weightMin: e.target.value })
              }
              placeholder="Min"
            />
            <span className="explorer-filter-range-sep">-</span>
            <input
              id={`${idPrefix}-weight-max`}
              className="explorer-filter-input"
              type="number"
              min={0}
              step="0.1"
              value={weightMaxInput}
              onChange={(e) =>
                onFiltersChange({ ...filters, weightMax: e.target.value })
              }
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
              const inputId = `${idPrefix}-comorb-${option.key}`;
              return (
                <label
                  key={option.key}
                  htmlFor={inputId}
                  className="explorer-filter-checkbox-label"
                >
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
          Invalid filter input: use numeric bounds and keep min less than or
          equal to max.
        </p>
      )}
    </>
  );
}
