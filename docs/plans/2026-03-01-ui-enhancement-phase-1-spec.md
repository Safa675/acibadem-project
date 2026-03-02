# UI Enhancement Phase 1 Spec

Date: 2026-03-01  
Scope: Desktop UI information architecture and technical labeling  
Language mode: Technical (clinical + quantitative risk terminology)

## 1) Goal

Define a single, implementation-ready specification for explanatory information labels (hover/focus tooltips) across the current dashboard UI. The output must eliminate ambiguity around metric meaning, computational basis, and interpretation.

This phase does not change visual styling or interaction mechanics beyond defining the label model and placement map.

## 2) Scope Boundaries

Included:
- Metric glossary and definitions for currently rendered UI surfaces.
- Tooltip content schema (required fields, optional fields, formatting constraints).
- Placement map by tab/component and target UI element.
- Acceptance criteria for implementation readiness.

Excluded:
- Mobile-first redesign.
- Final styling polish and animation refinement.
- Refactor of rendering/components.

## 3) Canonical Tooltip Schema

Every info label uses the following structured payload:

- `id`: stable key for engineering lookup.
- `title`: concise metric/field name.
- `definition`: what the metric represents.
- `formula`: computational expression or transformation.
- `interpretation`: how to read directionality/threshold.
- `range` (optional): expected numeric bounds.
- `source` (optional): upstream model/module name.

Content rules:
- Technical wording only; avoid generic prose.
- Keep `definition` <= 2 lines and `interpretation` <= 2 lines in desktop tooltip layout.
- Use deterministic symbols (`>=`, `<=`, `%`, `rho`, `sigma`, `p05`).

## 4) Glossary (Canonical Metric Definitions)

### 4.1 Cohort Overview (`frontend/src/components/tabs/CohortOverview.tsx`)

1. `cohort.n_patients`
- Definition: Count of unique monitored patients in current cohort snapshot.
- Formula: `n = |unique(patient_id)|`.
- Interpretation: Higher `n` expands cohort-level statistical stability.

2. `cohort.mean_health_score`
- Definition: Arithmetic mean of patient-level latest health index scores.
- Formula: `mean = (1/n) * sum(health_index_score_i)`.
- Range: `[0, 100]`.
- Interpretation: Larger values indicate better aggregate physiologic alignment with reference ranges.

3. `cohort.n_high_risk`
- Definition: Number of patients above configured high-risk threshold in composite risk framework.
- Formula: `count(composite risk condition == high-risk)`.
- Interpretation: Operational load indicator for prioritized review queue.

4. `cohort.n_critical`
- Definition: Number of patients currently in `Critical` regime state.
- Formula: `count(regime_state == Critical)`.
- Interpretation: Immediate escalation workload marker.

5. `cohort.total_rx`
- Definition: Sum of prescription records across cohort scope.
- Formula: `sum(n_prescriptions_i)`.
- Interpretation: Proxy for treatment intensity and care intervention volume.

6. `cohort.scatter.health_index_score`
- Definition: Patient-level health index on x-axis.
- Formula: Latest computed health score from lab/vital normalization pipeline.
- Range: `[0, 100]`.

7. `cohort.scatter.nlp_score`
- Definition: Normalized clinical text signal on y-axis.
- Formula: Weighted NLI composite normalized to dashboard scale.
- Range: `[0, 100]`.

8. `cohort.scatter.point_size`
- Definition: Marker radius encoding CSI burden magnitude.
- Formula: `r = clamp((csi_score / 8), min=4, max=14)`.
- Interpretation: Larger markers indicate higher severity burden.

9. `cohort.rating_distribution`
- Definition: Frequency distribution over credit-style risk ratings (AAA to B/CCC).
- Formula: `histogram(rating)`.
- Interpretation: Right-shift toward lower grades indicates deterioration in cohort quality profile.

10. `cohort.regime_distribution`
- Definition: Frequency distribution over regime states.
- Formula: `histogram(regime_state)`.
- Interpretation: Elevated `Critical + Deteriorating` mass indicates instability.

11. `cohort.var.downside_var_pct`
- Definition: Relative downside risk from Health VaR model.
- Formula: `VaR% = ((p05 - current_score) / max(current_score,1)) * 100`.
- Interpretation: More negative values imply greater expected downside tail risk.

12. `cohort.var.floor_score`
- Definition: 5th percentile terminal health score estimate.
- Formula: `p05` from Monte Carlo terminal distribution.
- Interpretation: Conservative downside floor under current return regime assumption.

### 4.2 Patient Explorer (`frontend/src/components/tabs/PatientExplorer.tsx`)

13. `patient.summary.composite_rating`
- Definition: Credit-style categorical tier derived from composite score thresholds.
- Formula: Threshold mapping over `composite_score`.

14. `patient.summary.composite_score`
- Definition: Weighted fusion of health index, NLP signal, and medication velocity score.
- Formula: `0.55*health + 0.30*nlp_norm + 0.15*med_score`.
- Range: `[0, 100]`.

15. `patient.summary.regime_state`
- Definition: Current state in trend-volatility 2x2 regime model.
- Formula: State assignment from `(health >= MA3)` and `(vol_percentile >= 60)`.

16. `patient.summary.downside_var_pct`
- Definition: Patient-specific Health VaR downside percentage.
- Formula: Same as cohort VaR% definition, applied per patient.

17. `patient.summary.csi_score`
- Definition: Clinical Severity Index aggregating six burden components.
- Formula: Weighted sum of normalized trend, volatility, critical fraction, NLP, Rx intensity, comorbidity burden.
- Range: `[0, 100]`.

18. `patient.regime.ma`
- Definition: Moving-average baseline for trajectory trend context.
- Formula: `MA3 = mean(last 3 health scores)`.

19. `patient.regime.rx_event_line`
- Definition: Vertical marker for prescription event dates.
- Formula: Each line corresponds to one dated prescription event.

20. `patient.var.fan_band`
- Definition: Forecast uncertainty envelope from Monte Carlo simulation.
- Formula: Percentile bands (`p05`, `p25`, `p50`, `p75`, `p95`).

21. `patient.nlp.visit_signal`
- Definition: Visit-level NLI composite score.
- Formula: Weighted confidence-damped zero-shot label aggregate.
- Range: `[-1, +1]`.
- Interpretation: Negative indicates deterioration signal; positive indicates recovery signal.

### 4.3 Outcome Predictor (`frontend/src/components/tabs/OutcomePredictor.tsx`)

22. `outcome.csi.gauge`
- Definition: Visual encoding of CSI score and tier.
- Formula: Needle angle is linear map from score in `[0,100]` to semicircle arc.

23. `outcome.feature_decomposition.value`
- Definition: Component contribution to CSI burden.
- Formula: Weighted component contribution in CSI points.

24. `outcome.cohort_ranking.csi_score`
- Definition: Patient CSI score relative to cohort peers.
- Formula: Ordered bars by patient CSI.

25. `outcome.spearman_r`
- Definition: Spearman rank correlation between feature and total visit count.
- Formula: `rho(feature, total_visits)`.
- Range: `[-1, +1]`.
- Interpretation: Sign indicates direction; magnitude indicates monotonic association strength.

### 4.4 Validation (`frontend/src/components/tabs/ValidationTab.tsx`)

26. `validation.statistic_value`
- Definition: Experiment-specific test statistic (e.g., Spearman rho).
- Formula: As defined per experiment hypothesis.

27. `validation.p_value`
- Definition: Probability of observing test statistic under null hypothesis.
- Formula: Derived from corresponding significance test.
- Interpretation: `p < 0.05` indicates nominal statistical significance.

28. `validation.n_samples`
- Definition: Effective sample count used in test.
- Formula: Number of valid paired observations post filtering.

29. `validation.passed`
- Definition: Boolean pass/fail status against experiment criterion.
- Formula: Rule-based flag from hypothesis-specific threshold logic.

## 5) Placement Map (Where to Attach Info Labels)

### Cohort Overview
- KPI card labels: all five KPI cards.
- Section headers: `Cohort Risk Scatter`, `Rating Distribution`, `Regime State Distribution`, `Patient Risk Rankings`, `Health VaR Summary`.
- Table column headers: `Composite Score`, `Health Index`, `NLP Score`, `CSI Score`, `Downside VaR %`, `VaR Floor Score`, `Risk Tier`.

### Patient Explorer
- Top summary cards: all six summary metrics.
- Section headers: Regime chart, VaR fan chart, NLP chart, NLI score table, Lab time-series.
- NLI table column header: `NLI Score`.

### Outcome Predictor
- Gauge title and score tier badge.
- Section headers: feature decomposition, cohort ranking, Spearman correlation panel.
- Correlation chart axis label/legend for Spearman rho semantics.

### Validation
- Summary table headers: statistic, p-value, n, passed.
- Experiment card metric labels and pass/fail icon semantics.

## 6) UX Behavior Contract for Labels

- Trigger: mouse hover + keyboard focus.
- Placement: right/top preference with viewport clamping.
- Delay: 100-150 ms show, 80-120 ms hide.
- Max width: ~320 px desktop.
- Dismissal: pointer leave, blur, Escape.

## 7) Acceptance Criteria (Phase 1 Complete)

- Every currently displayed core metric has a canonical technical definition.
- Every target UI surface has deterministic label placement mapping.
- Tooltip schema is uniform and implementation-ready.
- No unresolved naming collisions between tabs (same metric, same term).
- Spec is sufficient for direct implementation in phase 4 without re-discovery.

## 8) Phase 1 Deliverables

- This specification document.
- Updated task tracking in `tasks/todo.md`.
