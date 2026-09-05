import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { MissionDetail } from "./MissionDetail";
import { workspace, completedWorkspace } from "@/tests/workspace-fixture";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

test("starts a mission asynchronously and refreshes its outcome", async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(Response.json(workspace))
    .mockResolvedValueOnce(Response.json({ status: "accepted" }, { status: 202 }))
    .mockResolvedValueOnce(Response.json(completedWorkspace));
  vi.stubGlobal("fetch", fetchMock);
  render(<MissionDetail missionId="mission-1" />);
  await userEvent.click(await screen.findByRole("button", { name: "Start research" }));
  expect(await screen.findByText("Test rationale")).toBeTruthy();
  expect(screen.getByText("Test success criterion")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Synthetic source" }).getAttribute("href")).toBe("https://example.com/test");
  expect(fetchMock.mock.calls[1][0]).toContain("/missions/mission-1/run/async");
  expect(fetchMock.mock.calls[1][1].method).toBe("POST");
});

test("a failed run request requires a status refresh before another attempt", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(Response.json(workspace))
    .mockRejectedValueOnce(new Error("offline")));
  render(<MissionDetail missionId="mission-1" />);
  await userEvent.click(await screen.findByRole("button", { name: "Start research" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Start research" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("button", { name: "Refresh status" })).toBeTruthy();
});

test("reports unavailable data and permits retry", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce(Response.json(workspace)));
  render(<MissionDetail missionId="mission-1" />);
  await userEvent.click(await screen.findByRole("button", { name: "Refresh status" }));
  expect(await screen.findByRole("heading", { name: "Test mission" })).toBeTruthy();
});

test("polls while running and stops after completion", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(Response.json({ ...workspace, mission: { ...workspace.mission, status: "running" } }))
    .mockResolvedValueOnce(Response.json({ ...workspace, mission: { ...workspace.mission, status: "running" } }))
    .mockResolvedValueOnce(Response.json(completedWorkspace));
  vi.stubGlobal("fetch", fetchMock);
  render(<MissionDetail missionId="mission-1" />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(await screen.findByText("Test rationale")).toBeTruthy();
  const calls = fetchMock.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000); });
  expect(fetchMock).toHaveBeenCalledTimes(calls);
});

test("stops polling after a refresh failure", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(Response.json({ ...workspace, mission: { ...workspace.mission, status: "running" } }))
    .mockRejectedValueOnce(new Error("offline"));
  vi.stubGlobal("fetch", fetchMock);
  render(<MissionDetail missionId="mission-1" />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(await screen.findByRole("alert")).toBeTruthy();
  await act(async () => { await vi.advanceTimersByTimeAsync(12_000); });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("cancels an in-flight request on unmount", async () => {
  const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}));
  vi.stubGlobal("fetch", fetchMock);
  const view = render(<MissionDetail missionId="mission-1" />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  const signal = fetchMock.mock.calls[0][1].signal;
  view.unmount();
  expect(signal.aborted).toBe(true);
});
