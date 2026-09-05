import type { MissionWorkspaceData } from "@/types/workspace";

// Synthetic UI fixture; never presented as a real research source.
export const workspace: MissionWorkspaceData = {
  mission: { id: "mission-1", title: "Test mission", goal: "Evaluate a test hypothesis",
    status: "created", created_at: "2026-09-05T00:00:00Z", updated_at: "2026-09-05T00:00:00Z" },
  sources: [], evidence: [], opportunities: [], events: [], run_started_at: null,
  summary: null, action_plan: null, error: null,
};

export const completedWorkspace: MissionWorkspaceData = {
  ...workspace, mission: { ...workspace.mission, status: "completed" },
  sources: [{ id: "source-1", mission_id: "mission-1", title: "Synthetic source", url: "https://example.com/test",
    source_type: "arxiv", published_at: null, authors_json: [], raw_summary: null,
    content: "Synthetic excerpt", content_hash: "a".repeat(64), created_at: "2026-09-05T00:00:00Z" }],
  evidence: [{ id: "evidence-1", mission_id: "mission-1", source_id: "source-1", problem: "Test problem",
    method: "Test method", benchmark: null, result: null, limitation: "Test limitation",
    technology_tags_json: [], evidence_snippets_json: ["Synthetic excerpt"], relevance_score: 0.8,
    extraction_confidence: 0.7, created_at: "2026-09-05T00:00:00Z" }],
  summary: { iterations_used: 0, evidence_count: 1, query_history: ["test query"],
    handoff_status: "ready_for_poc", poc_candidates: [],
    decision: { recommendation: "proceed_with_poc", rationale: "Test rationale", selected_direction_id: "direction-1" } },
  action_plan: { id: "plan-1", mission_id: "mission-1", title: "Synthetic PoC", summary: "Test plan",
    estimated_effort: "2 hours", success_metrics_json: ["Test success criterion"], created_at: "2026-09-05T00:00:00Z",
    tasks_json: [{ id: "task-1", title: "Test task", description: "Check the hypothesis", priority: "high",
      addresses: "claim-1", estimated_hours: 2, status: "pending", dependencies: [] }] },
};
