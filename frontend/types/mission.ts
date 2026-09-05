export type MissionStatus = "created" | "running" | "completed" | "failed";

export interface ResearchMission {
  id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRunAccepted {
  mission_id: string;
  status: "accepted";
  message: string;
  mission_url: string;
  events_url: string;
  result_url: string;
}

export interface SourceDocument {
  id: string;
  mission_id: string;
  source_type: string;
  title: string;
  url: string;
  published_at: string | null;
  authors_json: string[];
  raw_summary: string | null;
  content: string | null;
  content_hash: string;
  created_at: string;
}

export interface EvidenceCard {
  id: string;
  mission_id: string;
  source_id: string;
  problem: string | null;
  method: string | null;
  benchmark: string | null;
  result: string | null;
  limitation: string | null;
  technology_tags_json: string[];
  evidence_snippets_json: string[];
  relevance_score: number;
  extraction_confidence: number;
  created_at: string;
}

export type EvidenceExclusionReason =
  | "low_relevance"
  | "low_extraction_confidence";

export interface EvidenceEligibility {
  evidence_id: string;
  quality_score: number;
  eligible: boolean;
  challenge_eligible: boolean;
  exclusion_reasons: EvidenceExclusionReason[];
}

export interface EvidenceSufficiencyReport {
  sufficient: boolean;
  total_evidence_count: number;
  effective_evidence_count: number;
  challenge_evidence_count: number;
  independent_source_count: number;
  result_bearing_count: number;
  limitation_bearing_count: number;
  minimum_effective_evidence: number;
  minimum_independent_sources: number;
  minimum_relevance: number;
  minimum_challenge_relevance: number;
  minimum_extraction_confidence: number;
  assessments: EvidenceEligibility[];
  missing_requirements: string[];
}

export type ClaimVerdict = "supported" | "contested" | "unknown" | "refuted";
export type ClaimResolutionStatus =
  | "resolved"
  | "poc_testable"
  | "research_gap"
  | "fatal";

export interface EvaluatedClaim {
  direction_id: string;
  claim_id: string;
  statement: string;
  is_core: boolean;
  supporting_evidence_ids: string[];
  opposing_evidence_ids: string[];
  support_strength: number;
  counterevidence_strength: number | null;
  poc_testability: number | null;
  verdict: ClaimVerdict;
  resolution_status: ClaimResolutionStatus;
  rationale: string;
}

export interface PocCandidate {
  direction_id: string;
  title: string;
  hypothesis: string;
  evidence_ids: string[];
  evidence_coverage: number;
  claim_assessments: EvaluatedClaim[];
  unresolved_questions: string[];
}

export interface TargetedResearchRequest {
  queries: string[];
  direction_ids: string[];
  claim_ids: string[];
  reason: string;
}

export interface PhaseCHandoff {
  status: "ready_for_poc" | "research_required" | "no_viable_direction";
  poc_candidates: PocCandidate[];
  claim_assessments: EvaluatedClaim[];
  research_request: TargetedResearchRequest | null;
  evidence_sufficiency: EvidenceSufficiencyReport | null;
  reason: string;
}

export interface ClaimVerdictCounts {
  supported: number;
  contested: number;
  unknown: number;
  refuted: number;
}

export interface AuditFinding {
  severity: "warning" | "blocker";
  code: string;
  message: string;
}

export interface MissionAuditReport {
  status: "pass" | "needs_review" | "insufficient";
  phase_c_status: string;
  phase_c_reason: string;
  evidence_sufficiency: EvidenceSufficiencyReport | null;
  support_eligible_evidence_ids: string[];
  challenge_eligible_evidence_ids: string[];
  challenge_only_evidence_ids: string[];
  accepted_evidence_ids: string[];
  excluded_evidence: EvidenceEligibility[];
  supporting_evidence_ids: string[];
  opposing_evidence_ids: string[];
  claim_verdict_counts: ClaimVerdictCounts;
  unresolved_questions: string[];
  highest_opportunity_score: number | null;
  findings: AuditFinding[];
}

export interface TechnologyOpportunity {
  id: string;
  mission_id: string;
  name: string;
  description: string;
  related_evidence_ids_json: string[];
  novelty: number;
  technical_maturity: number;
  implementation_difficulty: number;
  goal_alignment: number;
  poc_feasibility: number;
  evidence_strength: number;
  overall_score: number;
  rationale: string;
  created_at: string;
}

export interface CoverageReport {
  id: string;
  mission_id: string;
  overall_score: number;
  sufficient: boolean;
  dimension_status_json: Record<string, "absent" | "weak" | "adequate">;
  missing_evidence_json: string[];
  unsupported_claims_json: string[];
  suggested_queries_json: string[];
  iteration: number;
  created_at: string;
}

export interface ActionTask {
  id: string;
  title: string;
  description: string;
  addresses: string;
  priority: string;
  estimated_hours: number;
  dependencies: string[];
  status: string;
}

export interface ActionPlan {
  id: string;
  mission_id: string;
  title: string;
  summary: string;
  tasks_json: ActionTask[];
  success_metrics_json: string[];
  estimated_effort: string;
  created_at: string;
}

export interface WorkflowDecision {
  recommendation: "proceed_with_poc" | "do_not_proceed";
  rationale: string;
  selected_direction_id: string | null;
}

export interface MissionResult {
  mission: ResearchMission;
  sources: SourceDocument[];
  evidence: EvidenceCard[];
  handoff: PhaseCHandoff | null;
  audit: MissionAuditReport | null;
  opportunities: TechnologyOpportunity[];
  decision: WorkflowDecision | null;
  coverage_report: CoverageReport | null;
  action_plan: ActionPlan | null;
}
