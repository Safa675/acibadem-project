import type { CohortData, PatientData, OutcomeData, ValidationData, ChatMessage } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export async function getPatients(): Promise<{ patients: number[] }> {
  return fetchJSON("/api/patients");
}

export async function getCohort(): Promise<CohortData> {
  return fetchJSON<CohortData>("/api/cohort");
}

export async function getPatient(patientId: number): Promise<PatientData> {
  return fetchJSON<PatientData>(`/api/patient/${patientId}`);
}

export async function getPatientOutcome(patientId: number): Promise<OutcomeData> {
  return fetchJSON<OutcomeData>(`/api/patient/${patientId}/outcome`);
}

export async function getValidation(): Promise<ValidationData> {
  return fetchJSON<ValidationData>("/api/validation");
}

export async function sendChatMessage(
  messages: ChatMessage[],
  patientId: number
): Promise<{ reply: string }> {
  return fetchJSON("/api/chat", {
    method: "POST",
    body: JSON.stringify({ messages, patient_id: patientId }),
  });
}
