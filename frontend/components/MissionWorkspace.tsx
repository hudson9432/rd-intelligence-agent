"use client";

import {
  createContext,
  type FormEvent,
  type ReactNode,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ResearchMission } from "@/types/mission";
import { EmptyMissions } from "./EmptyMissions";
import styles from "../app/page.module.css";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const apiRequestTimeoutMs = 10_000;

type MissionContextValue = {
  missions: ResearchMission[];
  isLoading: boolean;
  isFormOpen: boolean;
  isSubmitting: boolean;
  error: string | null;
  toggleForm: () => void;
  createMission: (event: FormEvent<HTMLFormElement>) => Promise<void>;
};

const MissionContext = createContext<MissionContextValue | null>(null);

function useMissions() {
  const context = useContext(MissionContext);
  if (context === null) {
    throw new Error("Mission components must be rendered inside MissionProvider.");
  }
  return context;
}

function mergeMissions(
  currentMissions: ResearchMission[],
  loadedMissions: ResearchMission[],
) {
  const currentIds = new Set(currentMissions.map((mission) => mission.id));
  return [
    ...currentMissions,
    ...loadedMissions.filter((mission) => !currentIds.has(mission.id)),
  ];
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit = {},
) {
  const requestController = new AbortController();
  const abortRequest = () => requestController.abort();
  const timeoutId = window.setTimeout(abortRequest, apiRequestTimeoutMs);

  if (init.signal?.aborted) {
    abortRequest();
  } else {
    init.signal?.addEventListener("abort", abortRequest, { once: true });
  }

  try {
    return await fetch(input, { ...init, signal: requestController.signal });
  } finally {
    window.clearTimeout(timeoutId);
    init.signal?.removeEventListener("abort", abortRequest);
  }
}

export function MissionProvider({ children }: { children: ReactNode }) {
  const [missions, setMissions] = useState<ResearchMission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const hasCreatedMission = useRef(false);

  useEffect(() => {
    const controller = new AbortController();

    async function loadMissions() {
      try {
        const response = await fetchWithTimeout(`${apiBaseUrl}/missions`, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error("Unable to load missions.");
        }
        const loadedMissions: ResearchMission[] = await response.json();
        setMissions((currentMissions) =>
          mergeMissions(currentMissions, loadedMissions),
        );
      } catch {
        if (!controller.signal.aborted && !hasCreatedMission.current) {
          setLoadError("Backend is unavailable. Start the API and refresh this page.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    }

    void loadMissions();
    return () => controller.abort();
  }, []);

  async function createMission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setIsSubmitting(true);
    setSubmissionError(null);

    const formData = new FormData(form);
    const payload = {
      title: String(formData.get("title") ?? "").trim(),
      goal: String(formData.get("goal") ?? "").trim(),
    };

    try {
      const response = await fetchWithTimeout(`${apiBaseUrl}/missions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error("Unable to create mission.");
      }
      const mission: ResearchMission = await response.json();
      hasCreatedMission.current = true;
      setLoadError(null);
      setMissions((currentMissions) =>
        mergeMissions([mission], currentMissions),
      );
      form.reset();
      setIsFormOpen(false);
    } catch {
      setSubmissionError(
        "Mission could not be created. Check that the backend is running.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <MissionContext.Provider
      value={{
        missions,
        isLoading,
        isFormOpen,
        isSubmitting,
        error: submissionError ?? loadError,
        toggleForm: () => setIsFormOpen((isOpen) => !isOpen),
        createMission,
      }}
    >
      {children}
    </MissionContext.Provider>
  );
}

export function MissionControls() {
  const { createMission, error, isFormOpen, isSubmitting, toggleForm } =
    useMissions();

  return (
    <>
      <div className={styles.heroActions}>
        <button className={styles.primaryButton} type="button" onClick={toggleForm}>
          <span aria-hidden="true">＋</span>
          {isFormOpen ? "Close Form" : "New Research Mission"}
        </button>
        <span className={styles.buttonNote}>
          Mission API connected · create your first research mission.
        </span>
      </div>
      {isFormOpen && (
        <form className={styles.missionForm} onSubmit={createMission}>
          <label>
            Mission title
            <input
              name="title"
              required
              maxLength={200}
              placeholder="e.g. Evaluate multimodal RAG"
            />
          </label>
          <label>
            Research goal
            <textarea
              name="goal"
              required
              placeholder="What should the team investigate?"
            />
          </label>
          <button
            className={styles.submitButton}
            type="submit"
            disabled={isSubmitting}
          >
            {isSubmitting ? "Creating..." : "Create Mission"}
          </button>
        </form>
      )}
      {error && <p className={styles.errorMessage}>{error}</p>}
    </>
  );
}

export function MissionOverview() {
  const { missions } = useMissions();
  const activeMissionCount = missions.filter(
    (mission) => mission.status === "running",
  ).length;
  const activeMissionDetail =
    activeMissionCount === 0
      ? "No missions running"
      : `${activeMissionCount} ${activeMissionCount === 1 ? "mission" : "missions"} running`;
  const overview = [
    {
      label: "Active missions",
      value: activeMissionCount,
      detail: activeMissionDetail,
    },
    {
      label: "Evidence collected",
      value: 0,
      detail: "Evidence pipeline not connected",
    },
    { label: "Decisions ready", value: 0, detail: "Awaiting analysis" },
  ];

  return (
    <section className={styles.overview} aria-label="Workspace overview">
      {overview.map((item) => (
        <article className={styles.overviewItem} key={item.label}>
          <p>{item.label}</p>
          <strong>{item.value}</strong>
          <span>{item.detail}</span>
        </article>
      ))}
    </section>
  );
}

export function MissionList() {
  const { isLoading, missions } = useMissions();
  const missionCountLabel = `${missions.length} ${
    missions.length === 1 ? "mission" : "missions"
  }`;

  return (
    <section
      className={styles.missions}
      id="missions"
      aria-labelledby="recent-missions-title"
    >
      <div className={styles.sectionHeading}>
        <div>
          <p className={styles.sectionLabel}>Workspace</p>
          <h2 id="recent-missions-title">Recent missions</h2>
        </div>
        <span>{isLoading ? "Loading..." : missionCountLabel}</span>
      </div>
      <div className={styles.missionSurface}>
        {missions.length === 0 && !isLoading ? (
          <EmptyMissions />
        ) : (
          <div className={styles.missionList}>
            {missions.map((mission) => (
              <article className={styles.missionItem} key={mission.id}>
                <div>
                  <h3>{mission.title}</h3>
                  <p>{mission.goal}</p>
                </div>
                <span className={styles.missionStatus}>{mission.status}</span>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
