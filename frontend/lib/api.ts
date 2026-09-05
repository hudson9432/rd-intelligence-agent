/**
 * Typed client for the R&D Intelligence Agent backend.
 *
 * Every call is made from the server (Server Components and Server Actions),
 * so the browser never talks to FastAPI directly and CORS does not apply.
 *
 * Requests never throw on transport or HTTP failure. They resolve to an
 * `ApiResult` so a page can render a degraded state when the backend is
 * unreachable — including during `next build`, which prerenders with no
 * backend running.
 */

import type {
  AgentEvent,
  MissionCreateInput,
  ResearchMission,
} from "@/types/mission";

export const API_BASE_URL =
  process.env.API_BASE_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

/** Bounded so an unreachable backend cannot hang a render. */
const REQUEST_TIMEOUT_MS = 8000;

export interface ApiError {
  code: string;
  message: string;
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: ApiError };

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Normalize the several shapes FastAPI can put in `detail`: the structured
 * `{code, message}` this API raises, a 422 validation array, or a bare string.
 */
function parseError(status: number, payload: unknown): ApiError {
  const detail = isRecord(payload) ? payload.detail : undefined;

  if (isRecord(detail) && typeof detail.message === "string") {
    const code =
      typeof detail.code === "string" ? detail.code : `http_${status}`;
    return { code, message: detail.message };
  }

  if (typeof detail === "string") {
    return { code: `http_${status}`, message: detail };
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        isRecord(item) && typeof item.msg === "string" ? item.msg : null,
      )
      .filter((msg): msg is string => msg !== null);
    if (messages.length > 0) {
      return { code: "validation_error", message: messages.join("; ") };
    }
  }

  return { code: `http_${status}`, message: `Request failed (HTTP ${status}).` };
}

async function request<T>(
  path: string,
  { method = "GET", body }: RequestOptions = {},
): Promise<ApiResult<T>> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch (cause) {
    const timedOut = cause instanceof Error && cause.name === "TimeoutError";
    return {
      ok: false,
      error: {
        code: timedOut ? "backend_timeout" : "backend_unreachable",
        message: timedOut
          ? `The backend did not respond within ${REQUEST_TIMEOUT_MS / 1000}s.`
          : `Cannot reach the backend at ${API_BASE_URL}.`,
      },
    };
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    return { ok: false, error: parseError(response.status, payload) };
  }

  try {
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return {
      ok: false,
      error: {
        code: "invalid_response",
        message: "The backend returned a response that is not valid JSON.",
      },
    };
  }
}

export function listMissions(): Promise<ApiResult<ResearchMission[]>> {
  return request<ResearchMission[]>("/missions");
}

export function getMission(
  missionId: string,
): Promise<ApiResult<ResearchMission>> {
  return request<ResearchMission>(`/missions/${missionId}`);
}

export function listMissionEvents(
  missionId: string,
): Promise<ApiResult<AgentEvent[]>> {
  return request<AgentEvent[]>(`/missions/${missionId}/events`);
}

export function createMission(
  input: MissionCreateInput,
): Promise<ApiResult<ResearchMission>> {
  return request<ResearchMission>("/missions", {
    method: "POST",
    body: input,
  });
}
