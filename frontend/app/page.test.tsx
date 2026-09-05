import { render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "./page";

vi.mock("next/cache", () => ({ revalidatePath: vi.fn() }));
afterEach(() => vi.unstubAllGlobals());

test("shows unavailable statistics when the API cannot be reached", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(await Home());
  expect(screen.getByText("Mission API unavailable")).toBeTruthy();
  const overview = screen.getByRole("region", { name: "Workspace overview" });
  expect(within(overview).getAllByText("—")).toHaveLength(3);
  expect(within(overview).queryByText("0")).toBeNull();
});

test("shows zero statistics for a successfully loaded empty workspace", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json([])));
  render(await Home());
  expect(screen.getByText("No research missions yet")).toBeTruthy();
  const overview = screen.getByRole("region", { name: "Workspace overview" });
  expect(within(overview).getAllByText("0")).toHaveLength(3);
});

test("counts total, running and completed missions from the API", async () => {
  const missions = ["created", "running", "completed"].map((status, index) => ({
    id: String(index), title: `Mission ${index}`, goal: "Research goal", status,
    created_at: "2026-09-04T06:00:00Z", updated_at: "2026-09-04T06:00:00Z",
  }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(missions)));
  render(await Home());
  for (const [label, value] of [["Total missions", "3"], ["Running", "1"], ["Completed", "1"]]) {
    const card = screen.getByText(label, { selector: "p" }).closest("article")!;
    expect(within(card).getByText(value)).toBeTruthy();
  }
  expect(screen.getByRole("heading", { name: "Mission 0" })).toBeTruthy();
});
