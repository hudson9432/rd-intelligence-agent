import {
  MissionControls,
  MissionList,
  MissionOverview,
  MissionProvider,
} from "@/components/MissionWorkspace";
import styles from "./page.module.css";

const workflow = ["Research", "Evidence", "Evaluate", "Decide", "Act"];

export default function Home() {
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
            <MissionControls />
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

        <MissionOverview />
        <MissionList />
      </main>
    </MissionProvider>
  );
}
