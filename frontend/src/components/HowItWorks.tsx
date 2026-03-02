"use client";

import { useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function HowItWorks({ open, onClose }: Props) {
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="how-modal-overlay" role="dialog" aria-modal="true" aria-label="How ILAY Works" onClick={onClose}>
      <div className="how-modal frost-panel" onClick={(e) => e.stopPropagation()}>
        <div className="how-modal-head">
          <h2>How ILAY Works</h2>
          <button type="button" className="how-modal-close" onClick={onClose} aria-label="Close methodology panel">
            ×
          </button>
        </div>

        <div className="how-modal-content">
          <section>
            <h3>Finance-to-Healthcare Risk Analogy</h3>
            <p>
              ILAY adapts portfolio risk concepts to clinical trajectories. Patient health behaves like a dynamic asset,
              risk ratings mirror credit-style classes, and downside VaR estimates worst-case clinical deterioration
              under uncertainty.
            </p>
          </section>

          <section>
            <h3>Data Pipeline</h3>
            <p>
              MIMIC-IV records are transformed into longitudinal features, fused with NLP clinical-note signals,
              and fed into risk scoring modules that produce cohort dashboards, patient-level analytics, and
              explainable outcome predictors.
            </p>
            <ol>
              <li>MIMIC-IV extraction and cohort construction</li>
              <li>Feature engineering from labs, vitals, medications, and visit chronology</li>
              <li>Clinical NLP signal generation from narrative notes</li>
              <li>Composite risk scoring, VaR simulation, and regime detection</li>
              <li>Interactive analytics, validation outputs, and AI assistant support</li>
            </ol>
          </section>

          <section>
            <h3>Key Innovations</h3>
            <ul>
              <li>Probabilistic downside health risk (VaR-style) instead of static threshold checks</li>
              <li>Unified scoring model that blends structured and language-derived clinical signals</li>
              <li>Regime-state tracking to capture stability, recovery, and deterioration phases</li>
              <li>Judge-friendly explainability layer through dashboards, diagnostics, and chat guidance</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
