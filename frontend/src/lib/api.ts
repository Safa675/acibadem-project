import type {
  CohortData,
  PatientData,
  OutcomeData,
  ValidationData,
  ChatMessage,
  PatientSearchResponse,
  PatientMeta,
} from "./types";

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

export async function getPatients(): Promise<{ patients: string[]; total: number; patient_meta: PatientMeta[] }> {
  return fetchJSON("/api/patients");
}

export async function searchPatients(
  q: string,
  limit: number = 20
): Promise<PatientSearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) });
  return fetchJSON<PatientSearchResponse>(`/api/patients/search?${params}`);
}

export interface CohortParams {
  page?: number;
  per_page?: number;
  sort_by?: string;
  order?: "asc" | "desc";
  rating?: string;
  regime?: string;
}

export async function getCohort(params: CohortParams = {}): Promise<CohortData> {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.per_page) qs.set("per_page", String(params.per_page));
  if (params.sort_by) qs.set("sort_by", params.sort_by);
  if (params.order) qs.set("order", params.order);
  if (params.rating) qs.set("rating", params.rating);
  if (params.regime) qs.set("regime", params.regime);
  const query = qs.toString();
  return fetchJSON<CohortData>(`/api/cohort${query ? `?${query}` : ""}`);
}

export async function getPatient(patientId: string, options?: RequestInit): Promise<PatientData> {
  return fetchJSON<PatientData>(`/api/patient/${patientId}`, options);
}

export async function getPatientOutcome(patientId: string, options?: RequestInit): Promise<OutcomeData> {
  return fetchJSON<OutcomeData>(`/api/patient/${patientId}/outcome`, options);
}

export async function getValidation(): Promise<ValidationData> {
  return fetchJSON<ValidationData>("/api/validation");
}

export async function sendChatMessage(
  messages: ChatMessage[],
  patientId: string,
  activeTab: string,
  onToken: (token: string) => void
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages,
        patient_id: patientId,
        active_tab: activeTab,
      }),
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
