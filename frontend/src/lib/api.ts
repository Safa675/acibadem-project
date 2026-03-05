import type { CohortData, PatientData, OutcomeData, ValidationData, ChatMessage } from "./types";

function resolveApiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, "");
  }

  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }

  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return "http://localhost:8000";
  }

  return window.location.origin;
}

const API_BASE = resolveApiBase();

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
  } catch {
    throw new Error(`Could not reach API at ${API_BASE}${path}`);
  }
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
  patientId: number,
  onToken: (token: string) => void
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, patient_id: patientId }),
    });
  } catch {
    throw new Error(`Could not reach API at ${API_BASE}/api/chat`);
  }

  if (!res.ok) {
    const body = await res.text().catch(() => "");
    console.error(`[ILAY Chat] API error ${res.status}: ${body.slice(0, 300)}`);
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const data = line.slice(6);
      if (data === "[DONE]") return;
      try {
        onToken(JSON.parse(data));
      } catch {
        // Fallback for non-JSON data (e.g. plain error strings)
        onToken(data);
      }
    }
  }
}
