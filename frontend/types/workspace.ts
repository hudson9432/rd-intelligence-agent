import type { ResearchMission } from "./mission";

export interface SourceDocument {
  id: string; mission_id: string; source_type: string; title: string; url: string;
  published_at: string | null; authors_json: string[]; raw_summary: string | null;
  content: string | null; content_hash: string; created_at: string;
}
export interface EvidenceCard {
  id: string; mission_id: string; source_id: string; problem: string | null;
  method: string | null; benchmark: string | null; result: string | null;
  limitation: string | null; technology_tags_json: string[];
  evidence_snippets_json: string[]; relevance_score: number;
  extraction_confidence: number; created_at: string;
}
export interface Opportunity {
  id: string; mission_id: string; name: string; description: string;
  related_evidence_ids_json: string[]; novelty: number; technical_maturity: number;
  implementation_difficulty: number; goal_alignment: number; poc_feasibility: number;
  evidence_strength: number; overall_score: number; rationale: string; created_at: string;
}
export interface AgentEvent {
  id: string; mission_id: string; agent_name: string; event_type: string;
  message: string; metadata: Record<string, unknown>; created_at: string;
}
export interface ClaimAssessment {
  direction_id: string; claim_id: string; statement: string; is_core: boolean;
  supporting_evidence_ids: string[]; opposing_evidence_ids: string[];
  support_strength: number; counterevidence_strength: number | null;
  poc_testability: number | null; verdict: "supported" | "contested" | "unknown" | "refuted";
  resolution_status: "resolved" | "poc_testable" | "research_gap" | "fatal";
  rationale: string;
}
export interface PocCandidate {
  direction_id: string; title: string; hypothesis: string; evidence_ids: string[];
  evidence_coverage: number; claim_assessments: ClaimAssessment[]; unresolved_questions: string[];
}
export interface RunSummary {
  iterations_used: number; evidence_count: number; query_history: string[];
  handoff_status: "ready_for_poc" | "research_required" | "no_viable_direction" | null;
  decision: {
    recommendation: "proceed_with_poc" | "do_not_proceed";
    rationale: string; selected_direction_id: string | null;
  } | null;
  poc_candidates: PocCandidate[];
}
export interface ActionTask {
  id: string; title: string; description: string; priority: string;
  addresses: string; estimated_hours: number; dependencies: string[]; status: string;
}
export interface ActionPlan {
  id: string; mission_id: string; title: string; summary: string; tasks_json: ActionTask[];
  success_metrics_json: string[]; estimated_effort: string; created_at: string;
}
export interface MissionWorkspaceData {
  mission: ResearchMission; sources: SourceDocument[]; evidence: EvidenceCard[];
  opportunities: Opportunity[]; events: AgentEvent[]; run_started_at: string | null;
  summary: RunSummary | null; action_plan: ActionPlan | null; error: string | null;
}
