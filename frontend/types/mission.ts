/** Mirrors `backend/app/schemas/research_mission.py` and `agent_event.py`. */

export type MissionStatus = "created" | "running" | "completed" | "failed";

export interface ResearchMission {
  id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  created_at: string;
  updated_at: string;
}

/** Request body accepted by `POST /missions`. */
export interface MissionCreateInput {
  title: string;
  goal: string;
}

export interface AgentEvent {
  id: string;
  mission_id: string;
  agent_name: string;
  event_type: string;
  message: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export const MISSION_STATUS_LABELS: Record<MissionStatus, string> = {
  created: "Created",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
};
