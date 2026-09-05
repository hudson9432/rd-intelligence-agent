import { afterEach, expect, test, vi } from "vitest";
import { ApiError, apiRequest } from "./api";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

test("preserves structured backend errors without retrying a POST", async () => {
  const fetchMock = vi.fn().mockResolvedValue(Response.json({ detail: {
    code: "workflow_already_running", message: "Already running",
  } }, { status: 409 }));
  vi.stubGlobal("fetch", fetchMock);
  await expect(apiRequest("/missions/id/run/async", { method: "POST" })).rejects.toMatchObject({
    status: 409, message: "Already running",
  });
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test("times out a hung request", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn().mockImplementation((_url, init) => new Promise((_, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  })));
  const result = apiRequest("/missions");
  const assertion = expect(result).rejects.toThrow("timed out");
  await vi.advanceTimersByTimeAsync(10_000);
  await assertion;
});

test("rejects invalid JSON with a readable message", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("not json")));
  await expect(apiRequest("/missions")).rejects.toBeInstanceOf(ApiError);
});
