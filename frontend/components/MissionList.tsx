import type { ResearchMission } from "@/types/mission";
import { MISSION_STATUS_LABELS } from "@/types/mission";
import styles from "./mission.module.css";

interface MissionListProps {
  missions: ResearchMission[];
}

/** Fixed locale and UTC keep server and client markup identical. */
const formatCreatedAt = (value: string): string => {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown date";
  }
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(parsed);
};

export function MissionList({ missions }: MissionListProps) {
  return (
    <ul className={styles.missionList}>
      {missions.map((mission) => (
        <li className={styles.missionItem} key={mission.id}>
          <div className={styles.missionMain}>
            <h3>{mission.title}</h3>
            <p>{mission.goal}</p>
          </div>
          <div className={styles.missionMeta}>
            <span
              className={styles.statusBadge}
              data-status={mission.status}
            >
              {MISSION_STATUS_LABELS[mission.status] ?? mission.status}
            </span>
            <time dateTime={mission.created_at}>
              {formatCreatedAt(mission.created_at)} UTC
            </time>
          </div>
        </li>
      ))}
    </ul>
  );
}
