export type MissionStatus = "created" | "running" | "completed" | "failed";

export interface ResearchMission {
  id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  created_at: string;
  updated_at: string;
}
