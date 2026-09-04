import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import Home from "./page";
import type { ResearchMission } from "@/types/mission";

const createdMission: ResearchMission = {
  id: "9cfcf6e8-7bc7-4684-8ba4-55706c8bd98a",
  title: "Evaluate multimodal RAG",
  goal: "Compare retrieval quality and implementation cost.",
  status: "created",
  created_at: "2026-09-04T06:00:00Z",
  updated_at: "2026-09-04T06:00:00Z",
};

const runningMission: ResearchMission = {
  ...createdMission,
  id: "53e0928d-05ed-477c-98a0-9eab3ee2c7a7",
  status: "running",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("mission workspace", () => {
  test("closes and clears the form after the API creates a mission", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(createdMission, 201));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<Home />);
    await screen.findByText("No research missions yet");

    await user.click(screen.getByRole("button", { name: /new research mission/i }));
    await user.type(screen.getByLabelText("Mission title"), createdMission.title);
    await user.type(screen.getByLabelText("Research goal"), createdMission.goal);
    await user.click(screen.getByRole("button", { name: "Create Mission" }));

    expect(await screen.findByRole("heading", { name: createdMission.title })).toBeTruthy();
    expect(screen.getByText("1 mission")).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "Create Mission" })).toBeNull();
    });
    expect(screen.queryByText(/mission could not be created/i)).toBeNull();
  });

  test("keeps the form open and reports an API creation failure", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ detail: "Internal error" }, 500));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<Home />);
    await screen.findByText("No research missions yet");

    await user.click(screen.getByRole("button", { name: /new research mission/i }));
    await user.type(screen.getByLabelText("Mission title"), createdMission.title);
    await user.type(screen.getByLabelText("Research goal"), createdMission.goal);
    await user.click(screen.getByRole("button", { name: "Create Mission" }));

    expect(await screen.findByText(/mission could not be created/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Create Mission" })).toBeTruthy();
    expect((screen.getByLabelText("Mission title") as HTMLInputElement).value).toBe(
      createdMission.title,
    );
    expect((screen.getByLabelText("Research goal") as HTMLTextAreaElement).value).toBe(
      createdMission.goal,
    );
  });

  test("does not report mission count as collected evidence", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([createdMission])));

    render(<Home />);
    await screen.findByRole("heading", { name: createdMission.title });

    const evidenceCard = screen.getByText("Evidence collected").closest("article");
    expect(evidenceCard).not.toBeNull();
    expect(within(evidenceCard!).getByText("0")).toBeTruthy();
  });

  test("describes the number of running missions", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse([runningMission])));

    render(<Home />);
    await screen.findByRole("heading", { name: runningMission.title });

    const activeCard = screen.getByText("Active missions").closest("article");
    expect(activeCard).not.toBeNull();
    expect(within(activeCard!).getByText("1 mission running")).toBeTruthy();
  });

  test("keeps a newly created mission when the initial request finishes later", async () => {
    let resolveInitialRequest: ((response: Response) => void) | undefined;
    const initialRequest = new Promise<Response>((resolve) => {
      resolveInitialRequest = resolve;
    });
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce(jsonResponse(createdMission, 201));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<Home />);
    await user.click(screen.getByRole("button", { name: /new research mission/i }));
    await user.type(screen.getByLabelText("Mission title"), createdMission.title);
    await user.type(screen.getByLabelText("Research goal"), createdMission.goal);
    await user.click(screen.getByRole("button", { name: "Create Mission" }));
    expect(await screen.findByRole("heading", { name: createdMission.title })).toBeTruthy();

    resolveInitialRequest?.(jsonResponse([]));

    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
      expect(screen.getByRole("heading", { name: createdMission.title })).toBeTruthy();
    });
  });

  test("does not show a stale loading error after a mission is created", async () => {
    let rejectInitialRequest: ((reason: Error) => void) | undefined;
    const initialRequest = new Promise<Response>((_, reject) => {
      rejectInitialRequest = reject;
    });
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockReturnValueOnce(initialRequest)
      .mockResolvedValueOnce(jsonResponse(createdMission, 201));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(<Home />);
    await user.click(screen.getByRole("button", { name: /new research mission/i }));
    await user.type(screen.getByLabelText("Mission title"), createdMission.title);
    await user.type(screen.getByLabelText("Research goal"), createdMission.goal);
    await user.click(screen.getByRole("button", { name: "Create Mission" }));
    expect(await screen.findByRole("heading", { name: createdMission.title })).toBeTruthy();

    rejectInitialRequest?.(new Error("Connection failed"));

    await waitFor(() => {
      expect(screen.queryByText("Loading...")).toBeNull();
    });
    expect(screen.queryByText(/backend is unavailable/i)).toBeNull();
  });

  test("stops loading and reports when the API request times out", async () => {
    vi.useFakeTimers();
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((_input, init) => {
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener(
            "abort",
            () => reject(new DOMException("Timed out", "AbortError")),
            { once: true },
          );
        });
      }),
    );

    render(<Home />);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000);
    });

    expect(screen.queryByText("Loading...")).toBeNull();
    expect(screen.getByText(/backend is unavailable/i)).toBeTruthy();
  });
});
