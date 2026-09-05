import { BackendUnavailable } from "@/components/BackendUnavailable";
import { EmptyMissions } from "@/components/EmptyMissions";
import { MissionList } from "@/components/MissionList";
import { NewMissionForm } from "@/components/NewMissionForm";
import { listMissions } from "@/lib/api";
import type { ResearchMission } from "@/types/mission";
import styles from "./page.module.css";

// Mission data is per-request and must never be baked into the build, which
// runs with no backend available.
export const dynamic = "force-dynamic";

const workflow = ["Research", "Evidence", "Evaluate", "Decide", "Act"];

function buildOverview(missions: ResearchMission[]) {
  const running = missions.filter(
    (mission) => mission.status === "running",
  ).length;
  const completed = missions.filter(
    (mission) => mission.status === "completed",
  ).length;

  return [
    {
      label: "Total missions",
      value: String(missions.length),
      detail: missions.length === 1 ? "1 mission created" : "Created to date",
    },
    {
      label: "Running",
      value: String(running),
      detail: running === 0 ? "No missions running" : "Currently in progress",
    },
    {
      label: "Completed",
      value: String(completed),
      detail: completed === 0 ? "None finished yet" : "Ready to review",
    },
  ];
}

export default async function Home() {
  const result = await listMissions();
  const missions = result.ok ? result.data : [];
  const overview = buildOverview(missions);

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
            <NewMissionForm triggerClassName={styles.primaryButton} />
          </div>
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
        {overview.map((item) => (
          <article className={styles.overviewItem} key={item.label}>
            <p>{item.label}</p>
            <strong>{result.ok ? item.value : "—"}</strong>
            <span>{result.ok ? item.detail : "Unavailable"}</span>
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
          <span>
            {result.ok
              ? `${missions.length} ${missions.length === 1 ? "mission" : "missions"}`
              : "Unavailable"}
          </span>
        </div>
        <div className={styles.missionSurface}>
          {!result.ok ? (
            <BackendUnavailable message={result.error.message} />
          ) : missions.length === 0 ? (
            <EmptyMissions />
          ) : (
            <MissionList missions={missions} />
          )}
        </div>
      </section>
    </main>
  );
}
