export type CueTone = "good" | "warn" | "bad" | "neutral";

export type MetricCue = {
  label: string;
  tone: CueTone;
  detail?: string;
};

function cue(label: string, tone: CueTone, detail?: string): MetricCue {
  return { label, tone, detail };
}

export function getCohortSizeCue(n: number): MetricCue {
  if (n >= 20) return cue("Robust cohort", "good", "Distribution metrics are less variance-sensitive.");
  if (n >= 10) return cue("Moderate cohort", "warn", "Interpret directional shifts with moderate caution.");
  return cue("Small cohort", "bad", "Summary statistics are high-variance.");
}

export function getHealthScoreCue(score: number): MetricCue {
  if (score >= 85) return cue("Within reference profile", "good", "Low aggregate physiologic deviation.");
  if (score >= 70) return cue("Mild deviation", "warn", "Monitor trend persistence.");
  if (score >= 55) return cue("Moderate burden", "warn", "Elevated follow-up requirement.");
  return cue("High physiologic burden", "bad", "Escalated review advised.");
}

export function getCompositeScoreCue(score: number): MetricCue {
  if (score >= 85) return cue("High composite quality", "good", "Multimodal profile is favorable.");
  if (score >= 70) return cue("Intermediate quality", "warn", "Track for downward drift.");
  if (score >= 55) return cue("At-risk profile", "warn", "Intervention prioritization may be needed.");
  return cue("High composite risk", "bad", "Urgent prioritization recommended.");
}

export function getDownsideVarCue(varPct: number): MetricCue {
  if (varPct < 10) return cue("Low downside tail", "good", "Near-term deterioration risk is limited.");
  if (varPct < 25) return cue("Moderate downside tail", "warn", "Monitor short-horizon volatility.");
  if (varPct < 40) return cue("Elevated downside tail", "warn", "Clinical review should be prioritized.");
  return cue("Severe downside tail", "bad", "High deterioration exposure under current regime.");
}

export function getECICue(score: number): MetricCue {
  if (score >= 75) return cue("Very High Cost tier (B/CCC)", "bad", "Expected cost intensity is in the top quartile.");
  if (score >= 60) return cue("High Cost tier (BB)", "warn", "Above-average resource utilization expected.");
  if (score >= 45) return cue("Above Average Cost (BBB)", "warn", "Moderate cost exposure; monitor trajectory.");
  if (score >= 30) return cue("Moderate Cost tier (A)", "neutral", "Cost profile within normal range.");
  if (score >= 15) return cue("Low Cost tier (AA)", "good", "Below-average expected cost intensity.");
  return cue("Minimal Cost tier (AAA)", "good", "Lowest expected cost intensity in cohort.");
}

export function getMeanECICue(meanEci: number): MetricCue {
  if (meanEci >= 65) return cue("High cohort cost exposure", "bad", `Mean ECI ${meanEci.toFixed(1)} — elevated resource demand across the cohort.`);
  if (meanEci >= 50) return cue("Moderate cohort cost", "warn", `Mean ECI ${meanEci.toFixed(1)} — typical distribution expected.`);
  if (meanEci >= 35) return cue("Contained cohort cost", "neutral", `Mean ECI ${meanEci.toFixed(1)} — cost exposure is manageable.`);
  return cue("Low cohort cost", "good", `Mean ECI ${meanEci.toFixed(1)} — cohort cost intensity is favorable.`);
}

export function getCriticalCountCue(nCritical: number): MetricCue {
  if (nCritical === 0) return cue("No active critical cases", "good", "No immediate critical-state burden.");
  if (nCritical <= 2) return cue("Limited critical burden", "warn", "Targeted escalation queue needed.");
  return cue("High critical burden", "bad", "Broad escalation queue required.");
}

export function getRxIntensityCue(totalRx: number, nPatients: number): MetricCue {
  const perPatient = nPatients > 0 ? totalRx / nPatients : 0;
  if (perPatient < 8) return cue("Low Rx intensity", "good", `${perPatient.toFixed(1)} prescriptions per patient.`);
  if (perPatient < 15) return cue("Moderate Rx intensity", "warn", `${perPatient.toFixed(1)} prescriptions per patient.`);
  return cue("High Rx intensity", "warn", `${perPatient.toFixed(1)} prescriptions per patient.`);
}

export function getRegimeCue(state: string): MetricCue {
  if (state === "Stable") return cue("Positive trend / low volatility", "good");
  if (state === "Recovering") return cue("Positive trend / high volatility", "warn");
  if (state === "Deteriorating") return cue("Negative trend / low volatility", "warn");
  if (state === "Critical") return cue("Negative trend / high volatility", "bad");
  return cue("Insufficient state evidence", "neutral");
}
