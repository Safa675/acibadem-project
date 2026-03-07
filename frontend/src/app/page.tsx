"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import dynamic from "next/dynamic";
import { getPatients, getCohort, getPatient, getPatientOutcome, getValidation } from "@/lib/api";
import type {
  CohortData,
  PatientData,
  OutcomeData,
  ValidationData,
  PatientMeta,
  PatientFilters,
} from "@/lib/types";
const CohortOverview = dynamic(() => import("@/components/tabs/CohortOverview"), {
  loading: () => <div className="loading-state"><div className="loading-spinner" /></div>,
});
const PatientExplorer = dynamic(() => import("@/components/tabs/PatientExplorer"), {
  loading: () => <div className="loading-state"><div className="loading-spinner" /></div>,
});
const OutcomePredictor = dynamic(() => import("@/components/tabs/OutcomePredictor"), {
  loading: () => <div className="loading-state"><div className="loading-spinner" /></div>,
});
const ValidationTab = dynamic(() => import("@/components/tabs/ValidationTab"), {
  loading: () => <div className="loading-state"><div className="loading-spinner" /></div>,
});
import IlayChatbot from "@/components/IlayChatbot";
import LandingHero from "@/components/LandingHero";
import HowItWorks from "@/components/HowItWorks";
import Skeleton from "@/components/ui/Skeleton";

const TAB_LABELS = ["Cohort Overview", "Patient Health Explorer", "Patient Risk Explorer", "Validation"];
const CACHE_MAX_SIZE = 50;

export default function Home() {
  const [showDashboard, setShowDashboard] = useState(false);
  const [showHowItWorks, setShowHowItWorks] = useState(false);
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // ── Tab state ──────────────────────────────────────────────────────────
  const [activeTab, setActiveTab] = useState(0);

  // ── Data state ─────────────────────────────────────────────────────────
  const [patients, setPatients] = useState<string[]>([]);
  const [patientMeta, setPatientMeta] = useState<PatientMeta[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [cohortData, setCohortData] = useState<CohortData | null>(null);
  const [patientData, setPatientData] = useState<PatientData | null>(null);
  const [outcomeData, setOutcomeData] = useState<OutcomeData | null>(null);
  const [validationData, setValidationData] = useState<ValidationData | null>(null);
  const patientCacheRef = useRef<Map<string, PatientData>>(new Map());
  const outcomeCacheRef = useRef<Map<string, OutcomeData>>(new Map());
  const patientFetchAbortRef = useRef<AbortController | null>(null);
  const outcomeFetchAbortRef = useRef<AbortController | null>(null);

  // ── Loading state ──────────────────────────────────────────────────────
  const [loadingPatients, setLoadingPatients] = useState(true);
  const [loadingCohort, setLoadingCohort] = useState(true);
  const [loadingPatient, setLoadingPatient] = useState(false);
  const [loadingOutcome, setLoadingOutcome] = useState(false);
  const [loadingValidation, setLoadingValidation] = useState(false);

  // ── Error state ────────────────────────────────────────────────────────
  const [error, setError] = useState<string | null>(null);

  // ── Shared patient filters (synced between Health Explorer & Risk Explorer) ──
  const DEFAULT_FILTERS: PatientFilters = {
    gender: "ALL",
    doctor: "ALL",
    comorbidityConditions: [],
    ageMin: "",
    ageMax: "",
    weightMin: "",
    weightMax: "",
  };
  const [filters, setFilters] = useState<PatientFilters>(DEFAULT_FILTERS);

  const metaByPatientId = useMemo(
    () => new Map(patientMeta.map((m) => [m.patient_id, m])),
    [patientMeta],
  );

  const filteredPatients = useMemo(() => {
    const ageMin = filters.ageMin.trim() === "" ? null : Number(filters.ageMin);
    const ageMax = filters.ageMax.trim() === "" ? null : Number(filters.ageMax);
    const weightMin = filters.weightMin.trim() === "" ? null : Number(filters.weightMin);
    const weightMax = filters.weightMax.trim() === "" ? null : Number(filters.weightMax);

    const hasInvalid =
      (filters.ageMin.trim() !== "" && !Number.isFinite(ageMin)) ||
      (filters.ageMax.trim() !== "" && !Number.isFinite(ageMax)) ||
      (filters.weightMin.trim() !== "" && !Number.isFinite(weightMin)) ||
      (filters.weightMax.trim() !== "" && !Number.isFinite(weightMax)) ||
      (ageMin != null && ageMax != null && ageMin > ageMax) ||
      (weightMin != null && weightMax != null && weightMin > weightMax);

    if (hasInvalid) return [];

    return patients.filter((pid) => {
      const meta = metaByPatientId.get(pid);
      const sexCode = meta?.sex?.trim().toUpperCase() ?? "";

      if (filters.gender !== "ALL" && sexCode !== filters.gender) return false;

      const patientDoctorCode = meta?.doctor_code?.trim() ?? "";
      if (filters.doctor !== "ALL" && patientDoctorCode !== filters.doctor) return false;

      if (filters.comorbidityConditions.length > 0) {
        const conditionSet = new Set(meta?.comorbidity_conditions ?? []);
        for (const cond of filters.comorbidityConditions) {
          if (!conditionSet.has(cond)) return false;
        }
      }

      if (ageMin != null || ageMax != null) {
        if (meta?.age == null) return false;
        if (ageMin != null && meta.age < ageMin) return false;
        if (ageMax != null && meta.age > ageMax) return false;
      }

      if (weightMin != null || weightMax != null) {
        if (meta?.weight_kg == null) return false;
        if (weightMin != null && meta.weight_kg < weightMin) return false;
        if (weightMax != null && meta.weight_kg > weightMax) return false;
      }

      return true;
    });
  }, [patients, filters, metaByPatientId]);

  // ── Initial load: patients → cohort → auto-select first ────────────────
  useEffect(() => {
    if (!showDashboard) return;
    let cancelled = false;

    async function init() {
      try {
        setLoadingPatients(true);
        const pRes = await getPatients();
        if (cancelled) return;
        setPatients(pRes.patients);
        if (pRes.patient_meta) {
          setPatientMeta(pRes.patient_meta);
        }

        setLoadingCohort(true);
        const cRes = await getCohort({ sort_by: "data_completeness", order: "desc", per_page: 20 });
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
  }, [showDashboard]);

  // ── Auto-select first filtered patient when current selection is outside filter ──
  useEffect(() => {
    if (loadingPatients || filteredPatients.length === 0) return;
    if (selectedPatientId == null || !filteredPatients.includes(selectedPatientId)) {
      setSelectedPatientId(filteredPatients[0]);
    }
  }, [filteredPatients, selectedPatientId, loadingPatients]);

  // ── When selected patient changes: fetch Patient Explorer payload ───────
  useEffect(() => {
    if (!showDashboard || activeTab !== 1 || selectedPatientId === null) return;
    const pid = selectedPatientId;
    patientFetchAbortRef.current?.abort();
    const controller = new AbortController();
    patientFetchAbortRef.current = controller;

    async function fetchPatientDetails() {
      const cached = patientCacheRef.current.get(pid);
      if (cached) {
        setPatientData(cached);
        setLoadingPatient(false);
        return;
      }

      try {
        setLoadingPatient(true);
        const pData = await getPatient(pid, { signal: controller.signal });
        if (controller.signal.aborted) return;
        cachePut(patientCacheRef.current, pid, pData);
        setPatientData(pData);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          console.error("Failed to fetch patient explorer data:", err);
        }
      } finally {
        if (patientFetchAbortRef.current === controller) {
          setLoadingPatient(false);
          patientFetchAbortRef.current = null;
        }
      }
    }

    fetchPatientDetails();
    return () => {
      controller.abort();
      if (patientFetchAbortRef.current === controller) {
        patientFetchAbortRef.current = null;
      }
    };
  }, [activeTab, selectedPatientId, showDashboard]);

  // ── Fetch Outcome Predictor payload only when tab is active ────────────
  useEffect(() => {
    if (!showDashboard || activeTab !== 2 || selectedPatientId === null) return;
    const pid = selectedPatientId;
    outcomeFetchAbortRef.current?.abort();
    const controller = new AbortController();
    outcomeFetchAbortRef.current = controller;

    async function fetchOutcomeDetails() {
      const cached = outcomeCacheRef.current.get(pid);
      if (cached) {
        setOutcomeData(cached);
        setLoadingOutcome(false);
        return;
      }

      try {
        setLoadingOutcome(true);
        const oData = await getPatientOutcome(pid, { signal: controller.signal });
        if (controller.signal.aborted) return;
        cachePut(outcomeCacheRef.current, pid, oData);
        setOutcomeData(oData);
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          console.error("Failed to fetch outcome predictor data:", err);
        }
      } finally {
        if (outcomeFetchAbortRef.current === controller) {
          setLoadingOutcome(false);
          outcomeFetchAbortRef.current = null;
        }
      }
    }

    fetchOutcomeDetails();
    return () => {
      controller.abort();
      if (outcomeFetchAbortRef.current === controller) {
        outcomeFetchAbortRef.current = null;
      }
    };
  }, [activeTab, selectedPatientId, showDashboard]);

  // ── Bounded cache: evict oldest when exceeding CACHE_MAX_SIZE ────────────
  const cachePut = useCallback(<T,>(cache: Map<string, T>, key: string, value: T) => {
    cache.set(key, value);
    if (cache.size > CACHE_MAX_SIZE) {
      const oldest = cache.keys().next().value;
      if (oldest !== undefined) cache.delete(oldest);
    }
  }, []);

  // ── Lazy-load validation data when tab 3 is selected ───────────────────
  useEffect(() => {
    if (!showDashboard || activeTab !== 3 || validationData !== null) return;
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
  }, [activeTab, validationData, showDashboard]);

  // ── Handlers ───────────────────────────────────────────────────────────
  const handlePatientChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const raw = e.target.value;
    if (raw === "") return;
    setSelectedPatientId(raw);
  }, []);

  const handlePatientSelect = useCallback((nextPatientId: string | null) => {
    if (nextPatientId == null) return;
    setSelectedPatientId(nextPatientId);
  }, []);

  const handleCohortPageChange = useCallback(async (page: number) => {
    try {
      setLoadingCohort(true);
      const cRes = await getCohort({ page, sort_by: "data_completeness", order: "desc", per_page: 20 });
      setCohortData(cRes);
    } catch (err) {
      console.error("Failed to fetch cohort page:", err);
    } finally {
      setLoadingCohort(false);
    }
  }, []);

  const handleTabChange = useCallback((idx: number) => {
    setActiveTab(idx);
  }, []);

  const handleTabKeyDown = useCallback((e: React.KeyboardEvent<HTMLButtonElement>, idx: number) => {
    const focusTab = (nextIdx: number) => {
      setActiveTab(nextIdx);
      requestAnimationFrame(() => {
        tabRefs.current[nextIdx]?.focus();
      });
    };

    if (e.key === "ArrowRight") {
      e.preventDefault();
      focusTab((idx + 1) % TAB_LABELS.length);
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      focusTab((idx - 1 + TAB_LABELS.length) % TAB_LABELS.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusTab(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusTab(TAB_LABELS.length - 1);
    }
  }, []);

  useEffect(() => {
    if (!showDashboard) return;
    // Background is now pure CSS gradient — no image preloading needed
  }, [showDashboard]);

  // ── Error screen ───────────────────────────────────────────────────────
  if (!showDashboard) {
    return <LandingHero onEnter={() => setShowDashboard(true)} />;
  }

  const isInitialBootstrap = loadingPatients || (loadingCohort && cohortData === null);
  const isPatientSwitching = loadingPatient && patientData !== null;
  const isOutcomeSwitching = loadingOutcome && outcomeData !== null;

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
    <div className="dashboard-enter">
      {/* ── Background overlay ──────────────────────────────────────────── */}
      <div className="bg-overlay" />

      {/* ── Main content (above overlay) ────────────────────────────────── */}
      <div className="app-shell">
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header className="app-header">
          {/* Brand */}
          <div className="app-brand">
            <img
              src="/images/j2.png"
              alt="ILAY Logo"
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
            <button
              type="button"
              className="glass app-how-button"
              onClick={() => setShowHowItWorks(true)}
            >
              How It Works
            </button>
          </div>

        </header>

        {/* ── Tab bar ─────────────────────────────────────────────────────── */}
        <nav className="glass app-tabs" role="tablist" aria-label="Dashboard tabs">
          {TAB_LABELS.map((label, idx) => (
            <button
              key={label}
              onClick={() => handleTabChange(idx)}
              className={`app-tab-button ${activeTab === idx ? "tab-active" : ""}`}
              ref={(el) => {
                tabRefs.current[idx] = el;
              }}
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
          {isInitialBootstrap ? (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, idx) => (
                  <Skeleton key={idx} variant="card" className="h-[114px]" />
                ))}
              </div>
              <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
                <Skeleton variant="card" className="h-[320px]" />
                <div className="space-y-4">
                  <Skeleton variant="card" className="h-[152px]" />
                  <Skeleton variant="card" className="h-[152px]" />
                </div>
              </div>
              <Skeleton variant="card" className="h-[240px]" />
            </div>
          ) : (
            <div key={activeTab} className="tab-panel-animate">
              {activeTab === 0 && (
                <CohortOverview
                  data={cohortData}
                  loading={loadingCohort}
                  onPageChange={handleCohortPageChange}
                />
              )}

              {activeTab === 1 && (
                <PatientExplorer
                  data={patientData}
                  loading={loadingPatient}
                  switching={isPatientSwitching}
                  patients={patients}
                  filteredPatients={filteredPatients}
                  patientMeta={patientMeta}
                  selectedPatientId={selectedPatientId}
                  onPatientChange={handlePatientChange}
                  onPatientSelect={handlePatientSelect}
                  loadingPatients={loadingPatients}
                  filters={filters}
                  onFiltersChange={setFilters}
                />
              )}

              {activeTab === 2 && (
                <OutcomePredictor
                  data={outcomeData}
                  loading={loadingOutcome}
                  switching={isOutcomeSwitching}
                  selectedPatientId={selectedPatientId}
                  patients={patients}
                  filteredPatients={filteredPatients}
                  patientMeta={patientMeta}
                  onPatientChange={handlePatientChange}
                  onPatientSelect={handlePatientSelect}
                  loadingPatients={loadingPatients}
                  filters={filters}
                  onFiltersChange={setFilters}
                />
              )}

              {activeTab === 3 && (
                <ValidationTab
                  data={validationData}
                  loading={loadingValidation}
                />
              )}
            </div>
          )}
        </main>

        <footer className="app-footer">
          ILAY &mdash; AI Clinical Risk Intelligence &mdash; ACUHIT 2026 &mdash; Acibadem University
        </footer>
      </div>

      {/* ── Floating chatbot ────────────────────────────────────────────── */}
      {selectedPatientId !== null && (
        <IlayChatbot
          patientId={selectedPatientId}
          activeTabLabel={TAB_LABELS[activeTab]}
        />
      )}

      <HowItWorks open={showHowItWorks} onClose={() => setShowHowItWorks(false)} />
    </div>
  );
}
