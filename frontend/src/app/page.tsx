"use client";

import { useState, useEffect, useCallback } from "react";
import { getPatients, getCohort, getPatient, getPatientOutcome, getValidation } from "@/lib/api";
import type { CohortData, PatientData, OutcomeData, ValidationData } from "@/lib/types";
import { TAB_BACKGROUNDS } from "@/lib/constants";
import CohortOverview from "@/components/tabs/CohortOverview";
import PatientExplorer from "@/components/tabs/PatientExplorer";
import OutcomePredictor from "@/components/tabs/OutcomePredictor";
import ValidationTab from "@/components/tabs/ValidationTab";
import IlayChatbot from "@/components/IlayChatbot";

const TAB_LABELS = ["Cohort Overview", "Patient Explorer", "Outcome Predictor", "Validation"];

export default function Home() {
  // ── Tab state ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState(0);

  // ── Data state ─────────────────────────────────────────────────────────
  const [patients, setPatients] = useState<number[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<number | null>(null);
  const [cohortData, setCohortData] = useState<CohortData | null>(null);
  const [patientData, setPatientData] = useState<PatientData | null>(null);
  const [outcomeData, setOutcomeData] = useState<OutcomeData | null>(null);
  const [validationData, setValidationData] = useState<ValidationData | null>(null);

  // ── Loading state ──────────────────────────────────────────────────────
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingCohort, setLoadingCohort] = useState(true);
  const [loadingPatient, setLoadingPatient] = useState(false);
  const [loadingOutcome, setLoadingOutcome] = useState(false);
  const [loadingValidation, setLoadingValidation] = useState(false);

  // ── Error state ────────────────────────────────────────────────────────
  const [error, setError] = useState<string | null>(null);

  // ── Initial load: patients → cohort → auto-select first ────────────────
  useEffect(() => {
    let cancelled = false;

    async function init() {
      try {
        setLoadingPatients(true);
        const pRes = await getPatients();
        if (cancelled) return;
        setPatients(pRes.patients);

        setLoadingCohort(true);
        const cRes = await getCohort();
        if (cancelled) return;
        setCohortData(cRes);
        setLoadingCohort(false);

        if (pRes.patients.length > 0) {
          setSelectedPatientId(pRes.patients[0]);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load initial data");
        }
      } finally {
        if (!cancelled) {
          setLoadingPatients(false);
          setLoadingCohort(false);
        }
      }
    }

    init();
    return () => { cancelled = true; };
  }, []);

  // ── When selected patient changes: fetch patient + outcome ─────────────
  useEffect(() => {
    if (selectedPatientId === null) return;
    let cancelled = false;

    async function fetchPatientDetails() {
      try {
        setLoadingPatient(true);
        setLoadingOutcome(true);
        setPatientData(null);
        setOutcomeData(null);

        const [pData, oData] = await Promise.all([
          getPatient(selectedPatientId!),
          getPatientOutcome(selectedPatientId!),
        ]);

        if (cancelled) return;
        setPatientData(pData);
        setOutcomeData(oData);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to fetch patient details:", err);
        }
      } finally {
        if (!cancelled) {
          setLoadingPatient(false);
          setLoadingOutcome(false);
        }
      }
    }

    fetchPatientDetails();
    return () => { cancelled = true; };
  }, [selectedPatientId]);

  // ── Lazy-load validation data when tab 3 is selected ───────────────────
  useEffect(() => {
    if (activeTab !== 3 || validationData !== null) return;
    let cancelled = false;

    async function fetchValidation() {
      try {
        setLoadingValidation(true);
        const vData = await getValidation();
        if (cancelled) return;
        setValidationData(vData);
      } catch (err) {
        if (!cancelled) {
          console.error("Failed to fetch validation data:", err);
        }
      } finally {
        if (!cancelled) {
          setLoadingValidation(false);
        }
      }
    }

    fetchValidation();
    return () => { cancelled = true; };
  }, [activeTab, validationData]);

  // ── Handlers ───────────────────────────────────────────────────────────
  const handlePatientChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedPatientId(Number(e.target.value));
  }, []);

  const handleTabChange = useCallback((idx: number) => {
    setActiveTab(idx);
  }, []);

  const handleTabKeyDown = useCallback((e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      setActiveTab((idx + 1) % TAB_LABELS.length);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      setActiveTab((idx - 1 + TAB_LABELS.length) % TAB_LABELS.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveTab(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveTab(TAB_LABELS.length - 1);
    }
  }, []);

  // ── Error screen ───────────────────────────────────────────────────────
  if (error) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#0B0D14", color: "#E74C3C" }}>
        <div className="glass" style={{ padding: 40, maxWidth: 480, textAlign: "center" }}>
          <h2 style={{ fontSize: "1.4rem", marginBottom: 12, fontWeight: 700 }}>Connection Error</h2>
          <p style={{ color: "#B8C5D9", fontSize: "0.95rem" }}>{error}</p>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: 20, padding: "10px 28px", borderRadius: 8, background: "#4FC3F7", color: "#0B0D14", fontWeight: 700, border: "none", cursor: "pointer" }}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <>
      {/* ── Background overlay ──────────────────────────────────────────── */}
      <div
        className="bg-overlay"
        style={{ backgroundImage: `url(${TAB_BACKGROUNDS[activeTab]})` }}
      />

      {/* ── Main content (above overlay) ────────────────────────────────── */}
      <div className="app-shell">
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header className="app-header">
          {/* Brand */}
          <div className="app-brand">
            <img
              src="/images/ilay_avatar_cropped.png"
              alt="ILAY Avatar"
              className="app-brand-avatar"
            />
            <div>
              <div className="app-brand-title">
                ILAY
              </div>
              <div className="app-brand-subtitle">
                AI Clinical Risk Intelligence &mdash; ACUHIT 2026 &mdash; Acibadem University
              </div>
            </div>
          </div>

          {/* Patient selector */}
          <div className="app-filter">
            <label
              htmlFor="patient-select"
              className="app-filter-label"
            >
              Patient
            </label>
            <select
              id="patient-select"
              className="glass app-select"
              value={selectedPatientId ?? ""}
              onChange={handlePatientChange}
              disabled={loadingPatients}
            >
              {loadingPatients ? (
                <option>Loading…</option>
              ) : (
                patients.map((pid) => (
                  <option key={pid} value={pid} style={{ background: "#1A1D27", color: "#E8E8E8" }}>
                    Patient {pid}
                  </option>
                ))
              )}
            </select>
          </div>
        </header>

        {/* ── Tab bar ─────────────────────────────────────────────────────── */}
        <nav className="glass app-tabs" role="tablist" aria-label="Dashboard tabs">
          {TAB_LABELS.map((label, idx) => (
            <button
              key={label}
              onClick={() => handleTabChange(idx)}
              className={`app-tab-button ${activeTab === idx ? "tab-active" : ""}`}
              role="tab"
              aria-selected={activeTab === idx}
              aria-controls={`panel-${idx}`}
              id={`tab-${idx}`}
              tabIndex={activeTab === idx ? 0 : -1}
              onKeyDown={(e) => handleTabKeyDown(e, idx)}
            >
              {label}
            </button>
          ))}
        </nav>

        {/* ── Tab content ─────────────────────────────────────────────────── */}
        <main className="frost-canvas app-main" role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
          <div key={activeTab} className="tab-panel-animate">
            {activeTab === 0 && (
              <CohortOverview
                data={cohortData}
                loading={loadingCohort}
              />
            )}

            {activeTab === 1 && (
              <PatientExplorer
                data={patientData}
                loading={loadingPatient}
              />
            )}

            {activeTab === 2 && (
              <OutcomePredictor
                data={outcomeData}
                loading={loadingOutcome}
                selectedPatientId={selectedPatientId ?? 0}
              />
            )}

            {activeTab === 3 && (
              <ValidationTab
                data={validationData}
                loading={loadingValidation}
              />
            )}
          </div>
        </main>
      </div>

      {/* ── Floating chatbot ────────────────────────────────────────────── */}
      {selectedPatientId !== null && (
        <IlayChatbot patientId={selectedPatientId} />
      )}
    </>
  );
}
