"use client";

import { FormEvent, useEffect, useState } from "react";
import { EmptyMissions } from "@/components/EmptyMissions";
import styles from "./page.module.css";

const workflow = ["Research", "Evidence", "Evaluate", "Decide", "Act"];
const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

type MissionStatus = "created" | "running" | "completed" | "failed";

type ResearchMission = {
  id: string;
  title: string;
  goal: string;
  status: MissionStatus;
  created_at: string;
  updated_at: string;
};

const overview = [
  { label: "Active missions", value: "0", detail: "No missions running" },
  { label: "Evidence collected", value: "0", detail: "Across all missions" },
  { label: "Decisions ready", value: "0", detail: "Awaiting analysis" },
];

export default function Home() {
  const [missions, setMissions] = useState<ResearchMission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadMissions() {
      try {
        const response = await fetch(`${apiBaseUrl}/missions`);
        if (!response.ok) {
          throw new Error("Unable to load missions.");
        }
        setMissions(await response.json());
      } catch {
        setError("Backend is unavailable. Start the API and refresh this page.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadMissions();
  }, []);

  async function createMission(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const formData = new FormData(event.currentTarget);
    const payload = {
      title: String(formData.get("title") ?? "").trim(),
      goal: String(formData.get("goal") ?? "").trim(),
    };

    try {
      const response = await fetch(`${apiBaseUrl}/missions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        throw new Error("Unable to create mission.");
      }
      const mission: ResearchMission = await response.json();
      setMissions((currentMissions) => [mission, ...currentMissions]);
      event.currentTarget.reset();
      setIsFormOpen(false);
    } catch {
      setError("Mission could not be created. Check that the backend is running.");
    } finally {
      setIsSubmitting(false);
    }
  }

  const activeMissionCount = missions.filter(
    (mission) => mission.status === "running",
  ).length;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <a
          className={styles.brand}
          href="#top"
          aria-label="R&D Intelligence Agent home"
        >
          <span className={styles.brandMark} aria-hidden="true">
            RI
          </span>
          <span>R&D Intelligence Agent</span>
        </a>
        <nav className={styles.navigation} aria-label="Main navigation">
          <a className={styles.activeNavLink} href="#missions">
            Workspace
          </a>
          <a href="#workflow">How it works</a>
          <span className={styles.phaseBadge}>Hackathon Preview</span>
        </nav>
      </header>

      <section className={styles.hero} id="top">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Evidence-backed technology strategy</p>
          <h1>Turn research goals into decisions your team can act on.</h1>
          <p className={styles.summary}>
            Coordinate specialized agents to discover evidence, challenge
            assumptions, rank R&D opportunities, and prepare a focused PoC plan.
          </p>
          <div className={styles.heroActions}>
            <button
              className={styles.primaryButton}
              type="button"
              onClick={() => setIsFormOpen((isOpen) => !isOpen)}
            >
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
                <input name="title" required maxLength={200} placeholder="e.g. Evaluate multimodal RAG" />
              </label>
              <label>
                Research goal
                <textarea name="goal" required placeholder="What should the team investigate?" />
              </label>
              <button className={styles.submitButton} type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Creating..." : "Create Mission"}
              </button>
            </form>
          )}
          {error && <p className={styles.errorMessage}>{error}</p>}
        </div>

        <aside
          className={styles.workflowCard}
          id="workflow"
          aria-label="Product workflow"
        >
          <div className={styles.cardHeader}>
            <span>Intelligence workflow</span>
            <span className={styles.liveDot}>Ready</span>
          </div>
          <ol className={styles.workflowList}>
            {workflow.map((step, index) => (
              <li key={step}>
                <span className={styles.stepNumber}>
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span>{step}</span>
                {index < workflow.length - 1 && (
                  <span className={styles.arrow} aria-hidden="true">
                    →
                  </span>
                )}
              </li>
            ))}
          </ol>
          <p>
            Built for R&D leads, product managers, and technical strategy teams.
          </p>
        </aside>
      </section>

      <section className={styles.overview} aria-label="Workspace overview">
        {overview.map((item, index) => (
          <article className={styles.overviewItem} key={item.label}>
            <p>{item.label}</p>
            <strong>{index === 0 ? activeMissionCount : index === 1 ? missions.length : item.value}</strong>
            <span>{index === 0 && activeMissionCount === 0 ? "No missions running" : item.detail}</span>
          </article>
        ))}
      </section>

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
          <span>{isLoading ? "Loading..." : `${missions.length} missions`}</span>
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
    </main>
  );
}
