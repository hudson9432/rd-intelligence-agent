import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MissionResults } from "./MissionResults";
import { workspace, completedWorkspace } from "@/tests/workspace-fixture";
import type { AgentEvent, MissionWorkspaceData } from "@/types/workspace";

function event(id: string, message: string): AgentEvent {
  return { id, mission_id: "mission-1", agent_name: "search", event_type: "queries_generated",
    message, metadata: {}, created_at: "2026-09-05T00:00:00Z" };
}

function running(events: AgentEvent[]): MissionWorkspaceData {
  return { ...workspace, mission: { ...workspace.mission, status: "running" },
    run_started_at: "2026-09-05T00:00:00Z", events };
}

let scrollIntoView: ReturnType<typeof vi.fn>;

beforeEach(() => {
  scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView as unknown as Element["scrollIntoView"];
});
afterEach(() => { vi.restoreAllMocks(); });

test("follows the newest entry while a run is in progress", () => {
  const { rerender } = render(<MissionResults workspace={running([event("event-1", "First step")])} />);
  scrollIntoView.mockClear();

  rerender(<MissionResults workspace={running([event("event-1", "First step"), event("event-2", "Second step")])} />);

  expect(scrollIntoView).toHaveBeenCalled();
  expect(screen.getByText("Second step")).toBeTruthy();
});

test("waits for the first event before moving the page", () => {
  const { rerender } = render(<MissionResults workspace={workspace} />);
  scrollIntoView.mockClear();

  // The run has started but produced nothing yet: there is nothing to move to.
  rerender(<MissionResults workspace={running([])} />);

  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("shows work in progress only while the run is live", () => {
  const { container, rerender } = render(<MissionResults workspace={running([event("event-1", "First step")])} />);
  expect(container.querySelector("[aria-hidden='true']")).toBeTruthy();

  rerender(<MissionResults workspace={completedWorkspace} />);

  expect(container.querySelector("[aria-hidden='true']")).toBeNull();
});

test("leaves the page alone once the run is over", () => {
  const { rerender } = render(<MissionResults workspace={completedWorkspace} />);
  scrollIntoView.mockClear();

  rerender(<MissionResults workspace={{ ...completedWorkspace, events: [event("event-1", "Finished step")] }} />);

  expect(scrollIntoView).not.toHaveBeenCalled();
});

test("renders without programmatic scrolling available", () => {
  // Not every environment implements scrollIntoView; losing it must cost the
  // follow behaviour only, never the results themselves.
  Element.prototype.scrollIntoView = undefined as unknown as Element["scrollIntoView"];

  render(<MissionResults workspace={running([event("event-1", "First step")])} />);

  expect(screen.getByText("First step")).toBeTruthy();
});

test("shows which claim or critique question each PoC task addresses", () => {
  render(<MissionResults workspace={completedWorkspace} />);

  expect(screen.getByText("Addresses: claim-1")).toBeTruthy();
});
