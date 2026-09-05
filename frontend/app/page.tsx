import { EmptyMissions } from "@/components/EmptyMissions";
import styles from "./page.module.css";

// Mission data is per-request and must never be baked into the build, which
// runs with no backend available.
export const dynamic = "force-dynamic";

const workflow = ["Research", "Evidence", "Evaluate", "Decide", "Act"];

const overview = [
  { label: "Active missions", value: "0", detail: "No missions running" },
  { label: "Evidence collected", value: "0", detail: "Across all missions" },
  { label: "Decisions ready", value: "0", detail: "Awaiting analysis" },
];

export default async function Home() {
  const result = await listMissions();
  const missions = result.ok ? result.data : [];
  const overview = buildOverview(missions);

  return (
    <MissionProvider>
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
              disabled
              title="Mission creation will be enabled in the frontend workflow phase."
            >
              <span aria-hidden="true">＋</span>
              New Research Mission
            </button>
            <span className={styles.buttonNote}>
              Mission API ready · dashboard integration is planned.
            </span>
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
            <strong>{item.value}</strong>
            <span>{item.detail}</span>
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
          <span>0 missions</span>
        </div>
        <div className={styles.missionSurface}>
          <EmptyMissions />
        </div>
      </section>
    </main>
  );
}
