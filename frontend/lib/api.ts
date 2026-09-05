import type { MissionWorkspaceData } from "@/types/workspace";

export const apiBaseUrl = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message: string, public readonly status = 0) { super(message); }
}

/** Bounds reads as well as headers; caller cancellation always wins. */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 10_000);
  init.signal?.addEventListener("abort", abort, { once: true });
  if (init.signal?.aborted) abort();
  try {
    const response = await fetch(`${apiBaseUrl}${path}`, {
      ...init, cache: "no-store", signal: controller.signal,
    });
    const payload: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
      const message = typeof detail === "string" ? detail
        : detail && typeof detail === "object" && "message" in detail && typeof detail.message === "string"
          ? detail.message : `Request failed (HTTP ${response.status}).`;
      throw new ApiError(message, response.status);
    }
    if (payload === null) throw new ApiError("The API returned an invalid response.");
    return payload as T;
  } catch (error) {
    if (init.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (timedOut) throw new ApiError("The request timed out. Refresh status before trying again.");
    if (error instanceof ApiError) throw error;
    throw new ApiError("Cannot reach the API. Check the connection and refresh status.");
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", abort);
  }
}

export async function getWorkspace(missionId: string, signal: AbortSignal): Promise<MissionWorkspaceData> {
  const data = await apiRequest<MissionWorkspaceData>(`/missions/${encodeURIComponent(missionId)}/workspace`, { signal });
  if (!data || !data.mission || data.mission.id !== missionId ||
      !["created", "running", "completed", "failed"].includes(data.mission.status) ||
      ![data.sources, data.evidence, data.opportunities, data.events].every(Array.isArray)) {
    throw new ApiError("The API returned an invalid workspace response.");
  }
  return data;
}
