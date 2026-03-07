"use client";

import { useEffect, useState } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

const PHASES = [
  {
    number: "01",
    title: "Data Extraction & Cohort Construction",
    description:
      "Raw clinical records are extracted from the MIMIC-IV dataset: laboratory results, vital signs, prescription histories, visit chronologies, and ICD diagnostic codes. Patients are aligned on a temporal axis and filtered into a clinically coherent cohort.",
    details: [
      "50,000+ patient records with longitudinal clinical data",
      "Temporal alignment across labs, vitals, prescriptions, and visits",
      "ICD-code-based comorbidity extraction and grouping",
      "Data completeness scoring per patient for quality assurance",
    ],
    feedsInto: "All downstream modules",
    accent: "#4FC3F7",
  },
  {
    number: "02",
    title: "NLP Clinical Text Analysis",
    description:
      "Unstructured clinical narratives — doctor notes, nursing observations, discharge summaries — are scored using a transformer-based Natural Language Inference (NLI) model. Each text fragment receives a sentiment score from -1 (negative/deteriorating) to +1 (positive/improving).",
    details: [
      "Per-text NLI classification with -1 to +1 scoring",
      "Source-level aggregation (doctor notes vs. nursing vs. discharge)",
      "Temporal trend analysis: first-half vs. second-half trajectory",
      "Per-visit composite NLP signal for fusion with structured data",
    ],
    feedsInto: "Patient Health Explorer: NLP Scoring Overview + NLI Scores Table",
    accent: "#2ECC71",
  },
  {
    number: "03",
    title: "Health Index Construction",
    description:
      "A per-visit Health Index is computed from normalized laboratory values, vital signs, and diagnostic signals. A regime detection algorithm classifies each patient's trajectory into clinical states: Stable, Recovering, Deteriorating, or Critical.",
    details: [
      "Multi-feature health index from labs + vitals + diagnostics",
      "HMM-inspired state classification with transition probabilities",
      "4 regime states: Stable, Recovering, Deteriorating, Critical",
      "Temporal health timeline with state-annotated milestones",
    ],
    feedsInto: "Patient Health Explorer: Health Timeline + Regime States",
    accent: "#F39C12",
  },
  {
    number: "04",
    title: "Composite Scoring & Risk Rating",
    description:
      "Multi-modal fusion combines the Health Index (70%) and NLP signal (30%) into a single composite risk score per patient. A credit-style rating system (AAA to B/CCC) stratifies patients. The Expected Cost Intensity (ECI) module scores resource utilization from visit, medication, and diagnostic patterns.",
    details: [
      "Weighted fusion: 70% Health Index + 30% NLP signal",
      "6-tier credit-style rating: AAA, AA, A, BBB, BB, B/CCC",
      "ECI scoring from 4 percentile-ranked cost drivers",
      "Cohort-wide ranking and percentile positioning",
    ],
    feedsInto: "Cohort Overview: Risk Rankings + KPI Cards",
    accent: "#E67E22",
  },
  {
    number: "05",
    title: "Value-at-Risk Simulation",
    description:
      "Monte Carlo simulation estimates downside health trajectory risk, adapted from financial VaR methodology. Bayesian-shrunk returns with per-step caps prevent catastrophic compounding from sparse data. The 5th-percentile VaR and absolute floor quantify worst-case scenarios.",
    details: [
      "Monte Carlo resampling with 500 simulation paths",
      "Bayesian shrinkage toward zero-return prior for sparse data",
      "Per-step return cap of \u00B130% to prevent compounding artifacts",
      "Risk tier classification: GREEN / YELLOW / ORANGE / RED",
    ],
    feedsInto: "Cohort Overview: VaR Table + Patient Risk Explorer: VaR Fan Chart",
    accent: "#E74C3C",
  },
  {
    number: "06",
    title: "Validation & Interactive Dashboard",
    description:
      "The scoring system is cross-validated against established clinical benchmarks (Charlson Comorbidity Index, APACHE-style severity metrics) with statistical significance testing. Results are presented through a 4-tab interactive dashboard with an AI chatbot for clinical Q&A.",
    details: [
      "Spearman/Pearson correlation against Charlson and APACHE benchmarks",
      "Bootstrap confidence intervals and p-value significance testing",
      "4 interactive tabs: Cohort, Health Explorer, Risk Explorer, Validation",
      "AI chatbot with cohort-level and patient-level clinical Q&A",
    ],
    feedsInto: "Validation Tab + AI Clinical Assistant",
    accent: "#9B59B6",
  },
];

export default function HowItWorks({ open, onClose }: Props) {
  const [activePhase, setActivePhase] = useState(0);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  useEffect(() => {
    if (open) setActivePhase(0);
  }, [open]);

  if (!open) return null;

  const phase = PHASES[activePhase];

  return (
    <div className="how-modal-overlay" role="dialog" aria-modal="true" aria-label="How ILAY Works" onClick={onClose}>
      <div className="how-modal frost-panel" onClick={(e) => e.stopPropagation()}>
        <div className="how-modal-head">
          <h2>How ILAY Works</h2>
          <div className="how-phase-counter">
            {activePhase + 1} / {PHASES.length}
          </div>
          <button type="button" className="how-modal-close" onClick={onClose} aria-label="Close methodology panel">
            &times;
          </button>
        </div>

        <div className="how-modal-content">
          {/* ── Phase navigation (vertical stepper) ── */}
          <div className="how-stepper-layout">
            <nav className="how-phase-nav" aria-label="Pipeline phases">
              {PHASES.map((p, idx) => (
                <button
                  key={p.number}
                  type="button"
                  className={`how-phase-nav-item ${idx === activePhase ? "is-active" : ""} ${idx < activePhase ? "is-past" : ""}`}
                  onClick={() => setActivePhase(idx)}
                  aria-current={idx === activePhase ? "step" : undefined}
                >
                  <span
                    className="how-phase-dot"
                    style={{ borderColor: idx === activePhase ? p.accent : undefined, background: idx === activePhase ? p.accent : undefined }}
                  >
                    {p.number}
                  </span>
                  <span className="how-phase-nav-label">{p.title}</span>
                </button>
              ))}
              <div className="how-phase-line" aria-hidden="true" />
            </nav>

            {/* ── Active phase detail ── */}
            <div className="how-phase-detail" key={activePhase}>
              <div className="how-phase-header">
                <span className="how-phase-badge" style={{ background: phase.accent }}>
                  Phase {phase.number}
                </span>
                <h3 className="how-phase-title">{phase.title}</h3>
              </div>

              <p className="how-phase-description">{phase.description}</p>

              <div className="how-phase-details-grid">
                {phase.details.map((detail, i) => (
                  <div key={i} className="how-phase-detail-item">
                    <span className="how-phase-detail-bullet" style={{ background: phase.accent }} />
                    <span>{detail}</span>
                  </div>
                ))}
              </div>

              <div className="how-phase-feeds">
                <span className="how-phase-feeds-label">Powers</span>
                <span className="how-phase-feeds-value">{phase.feedsInto}</span>
              </div>

              {/* ── Navigation buttons ── */}
              <div className="how-phase-nav-buttons">
                <button
                  type="button"
                  className="how-phase-btn"
                  onClick={() => setActivePhase(Math.max(0, activePhase - 1))}
                  disabled={activePhase === 0}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="how-phase-btn how-phase-btn-primary"
                  onClick={() => {
                    if (activePhase < PHASES.length - 1) {
                      setActivePhase(activePhase + 1);
                    } else {
                      onClose();
                    }
                  }}
                  style={activePhase < PHASES.length - 1 ? {} : { background: "rgba(46, 204, 113, 0.2)", borderColor: "rgba(46, 204, 113, 0.4)", color: "#2ECC71" }}
                >
                  {activePhase < PHASES.length - 1 ? "Next Phase" : "Got It"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
