"use client";

import { useEffect, useRef } from "react";
import type { MissionWorkspaceData } from "@/types/workspace";
import styles from "./workspace.module.css";

// Following the log is a convenience, never a requirement. Where the platform
// does not provide programmatic scrolling the page simply does not follow,
// rather than taking the whole results view down with it.
function follow(target: Element | null | undefined, block: ScrollLogicalPosition) {
  if (typeof target?.scrollIntoView !== "function") return;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block });
}

function sourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch { return undefined; }
}

function EvidenceLinks({ ids }: { ids: string[] }) {
  return <span className={styles.references}>{ids.length ? ids.map((id) => (
    <a key={id} href={`#evidence-${id}`}>Evidence {id}</a>
  )) : "No evidence cited"}</span>;
}

function TextList({ values, empty = "Not recorded" }: { values: string[]; empty?: string }) {
  return values.length ? <ul>{values.map((value, index) => <li key={`${index}-${value}`}>{value}</li>)}</ul> : <p className={styles.muted}>{empty}</p>;
}

export function MissionResults({ workspace }: { workspace: MissionWorkspaceData }) {
  const { mission, sources, evidence, opportunities, summary, action_plan: plan, events } = workspace;
  const running = mission.status === "running";
  const timelineRef = useRef<HTMLOListElement>(null);
  const followRef = useRef(true);

  // Following the log must yield to the reader. Once they scroll up to look at
  // something, arriving events stop dragging the page back down; scrolling to
  // the bottom again resumes the follow.
  useEffect(() => {
    function onScroll() {
      const doc = document.documentElement;
      followRef.current = window.innerHeight + window.scrollY >= doc.scrollHeight - 160;
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // A run starting only re-arms the follow; moving the page before the first
  // event exists would jump to an empty log.
  useEffect(() => {
    if (running) followRef.current = true;
  }, [running]);

  useEffect(() => {
    // The list also holds the in-progress indicator, so an empty run would
    // otherwise scroll to that instead of waiting for real activity.
    if (!running || !followRef.current || !events.length) return;
    follow(timelineRef.current?.lastElementChild, "center");
  }, [events.length, running]);

  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const currentEvents = workspace.run_started_at
    ? events.filter((event) => Date.parse(event.created_at) >= Date.parse(workspace.run_started_at!)) : [];
  const latestEvent = currentEvents.at(-1);
  const selectedId = summary?.decision?.selected_direction_id;
  const selected = summary?.poc_candidates.find((candidate) => candidate.direction_id === selectedId);
  const outcome = mission.status === "running" ? "Research in progress"
    : mission.status === "failed" ? "Research failed"
      : summary?.handoff_status === "no_viable_direction" ? "No viable direction"
        : summary?.decision?.recommendation === "proceed_with_poc" ? "Proceed with PoC"
          : summary?.decision?.recommendation === "do_not_proceed" ? "Do not proceed"
            : mission.status === "completed" ? "Research completed" : "Ready to start";
  return (
    <>
      <section className={styles.outcome} aria-label="Research status" aria-live="polite">
        <div><span className={styles.badge} data-status={mission.status}>{mission.status}</span><h2>{outcome}</h2>
          {workspace.error && <p className={styles.failure}>{workspace.error}</p>}
          {mission.status === "running" && <p>Progress refreshes every 3 seconds. You can leave this page and return later.</p>}
          {mission.status === "created" && <p>Start research to collect evidence, evaluate directions and prepare a PoC plan.</p>}
          {latestEvent && <p className={styles.muted}>Latest update: {latestEvent.message}</p>}
        </div>
        <dl className={styles.stats}>
          <div><dt>Saved sources</dt><dd>{sources.length}</dd></div>
          <div><dt>Saved evidence</dt><dd>{evidence.length}</dd></div>
          <div><dt>Re-search rounds</dt><dd>{summary?.iterations_used ?? "—"}</dd></div>
        </dl>
      </section>
      <nav className={styles.navigation} aria-label="Mission results">
        <a href="#evidence">Evidence ({evidence.length})</a><a href="#decision">Decision</a>
        <a href="#plan">PoC plan</a><a href="#activity">Activity ({events.length})</a>
      </nav>

      <section className={styles.section} id="evidence" aria-labelledby="evidence-title">
        <p className={styles.eyebrow}>Research & evidence</p><h2 id="evidence-title">Saved evidence</h2>
        <p className={styles.muted}>Sources and evidence saved for this mission, including earlier runs. Unknown fields are not inferred.</p>
        {!evidence.length && <p className={styles.empty}>No evidence has been saved yet.</p>}
        <div className={styles.cards}>
          {evidence.map((card) => {
            const source = sourceById.get(card.source_id);
            return <article className={styles.card} id={`evidence-${card.id}`} key={card.id}>
              <span className={styles.badge}>{source?.source_type ?? "Source unavailable"}</span>
              <h3>{source?.title ?? card.problem ?? "Evidence"}</h3>
              <p className={styles.id}>Evidence {card.id} · Source <a href={`#source-${card.source_id}`}>{card.source_id}</a></p>
              <dl className={styles.fields}>
                {([ ["Problem", card.problem], ["Method", card.method], ["Benchmark", card.benchmark],
                  ["Result", card.result], ["Limitation", card.limitation] ] as const).map(([label, value]) => (
                  <div key={label}><dt>{label}</dt><dd>{value ?? "Not reported"}</dd></div>
                ))}
              </dl>
              <div className={styles.tags}>{card.technology_tags_json.map((tag) => <span key={tag}>{tag}</span>)}</div>
              <details><summary>Source excerpts ({card.evidence_snippets_json.length})</summary>
                {card.evidence_snippets_json.map((snippet, index) => <blockquote key={index}>{snippet}</blockquote>)}
              </details>
              <p className={styles.muted}>Relevance {Math.round(card.relevance_score * 100)}% · Extraction confidence {Math.round(card.extraction_confidence * 100)}%</p>
            </article>;
          })}
        </div>
        <h3 className={styles.subheading}>Sources ({sources.length})</h3>
        {!sources.length && <p className={styles.muted}>No sources saved yet.</p>}
        <div className={styles.sources}>{sources.map((source) => <article key={source.id} id={`source-${source.id}`}>
          <h4>{sourceUrl(source.url) ? <a href={sourceUrl(source.url)} target="_blank" rel="noopener noreferrer">{source.title}</a> : source.title}</h4>
          <p className={styles.muted}>{source.source_type} · {source.authors_json.join(", ") || "Authors not recorded"}</p>
          <p className={styles.id}>Source {source.id}</p>
          {source.raw_summary && <details><summary>Summary</summary><p>{source.raw_summary}</p></details>}
        </article>)}</div>
      </section>

      <section className={styles.section} id="decision" aria-labelledby="decision-title">
        <p className={styles.eyebrow}>Evaluate & decide</p><h2 id="decision-title">Decision and alternatives</h2>
        {summary?.decision ? <div className={styles.callout}>
          <h3>{summary.decision.recommendation === "proceed_with_poc" ? "Proceed with PoC" : "Do not proceed"}</h3>
          <p>{summary.decision.rationale}</p>
          {selectedId && <p>Selected direction: <a href={`#direction-${selectedId}`}>{selected?.title ?? selectedId}</a></p>}
        </div> : <p className={styles.empty}>{mission.status === "failed" ? "This run failed. No current decision is available." : "No decision is available for the current run yet."}</p>}
        {opportunities.length > 0 && <>
          <p className={styles.muted}>Scores are computed by the backend. Overall score reflects merit relative to difficulty; it is not a probability of success. Dimensions use a 1–5 scale.</p>
          <div className={styles.tableScroll}><table>
            <caption>Candidate scores</caption><thead><tr><th>Direction</th><th>Overall /100</th><th>Novelty</th><th>Maturity</th><th>Difficulty</th><th>Goal alignment</th><th>PoC feasibility</th><th>Evidence strength</th></tr></thead>
            <tbody>{opportunities.map((item) => <tr key={item.id}>
              <th scope="row"><a href={`#opportunity-${item.id}`}>{item.name}</a></th>
              <td>{item.overall_score.toFixed(1)}</td><td>{item.novelty}</td><td>{item.technical_maturity}</td>
              <td>{item.implementation_difficulty}</td><td>{item.goal_alignment}</td><td>{item.poc_feasibility}</td><td>{item.evidence_strength}</td>
            </tr>)}</tbody>
          </table></div>
          {opportunities.map((item) => <details className={styles.card} key={item.id} id={`opportunity-${item.id}`}>
            <summary>{item.name} — scoring rationale</summary><p>{item.description}</p><p>{item.rationale}</p>
            <EvidenceLinks ids={item.related_evidence_ids_json} />
          </details>)}
        </>}
        {summary?.poc_candidates.map((candidate) => <article className={styles.card} key={candidate.direction_id} id={`direction-${candidate.direction_id}`}>
          <h3>{candidate.title}{selectedId === candidate.direction_id ? " · Selected" : ""}</h3>
          <p>{candidate.hypothesis}</p><p className={styles.muted}>Evidence coverage: {Math.round(candidate.evidence_coverage * 100)}%</p>
          <EvidenceLinks ids={candidate.evidence_ids} />
          <h4>Open questions</h4><TextList values={candidate.unresolved_questions} empty="No open questions recorded." />
          <details><summary>Claim assessments ({candidate.claim_assessments.length})</summary>
            {candidate.claim_assessments.map((claim) => <div className={styles.claim} key={claim.claim_id}>
              <h4>{claim.statement}</h4><p>{claim.verdict} · {claim.is_core ? "Core claim" : "Supporting claim"}</p>
              <p>{claim.rationale}</p><p>Supporting evidence</p><EvidenceLinks ids={claim.supporting_evidence_ids} />
              <p>Opposing evidence</p><EvidenceLinks ids={claim.opposing_evidence_ids} />
            </div>)}
          </details>
        </article>)}
      </section>

      <section className={styles.section} id="plan" aria-labelledby="plan-title">
        <p className={styles.eyebrow}>Act</p><h2 id="plan-title">PoC action plan</h2>
        {!plan ? <p className={styles.empty}>{summary?.decision?.recommendation === "do_not_proceed" ? "No PoC plan: the decision is not to proceed." : "No PoC plan is available for the current run."}</p> : <>
          <h3>{plan.title}</h3><p>{plan.summary}</p><p className={styles.badge}>Estimated effort: {plan.estimated_effort}</p>
          <h3 className={styles.subheading}>Success criteria</h3><TextList values={plan.success_metrics_json} />
          <ol className={styles.tasks}>{plan.tasks_json.map((task) => <li key={task.id} id={`task-${task.id}`}>
            <h3>{task.title}</h3><p>{task.description}</p><div className={styles.tags}>
              <span>{task.priority} priority</span><span>{task.estimated_hours} hours</span><span>{task.status}</span><span>Addresses: {task.addresses}</span>
            </div><p>Dependencies: {task.dependencies.length ? task.dependencies.map((id) => <a className={styles.dependency} key={id} href={`#task-${id}`}>{plan.tasks_json.find((other) => other.id === id)?.title ?? id}</a>) : "None"}</p>
          </li>)}</ol>
        </>}
      </section>

      <section className={styles.section} id="activity" aria-labelledby="activity-title">
        <p className={styles.eyebrow}>Agent activity</p><h2 id="activity-title">Execution history</h2>
        {summary && <details><summary>Search queries ({summary.query_history.length})</summary><TextList values={summary.query_history} /></details>}
        {!events.length && <p className={styles.empty}>No activity recorded yet.</p>}
        <ol className={styles.timeline} ref={timelineRef} aria-live={running ? "polite" : "off"}>{events.map((event, index) => <li key={event.id} className={running && index === events.length - 1 ? styles.newest : undefined}>
          <div><span className={styles.badge}>{event.agent_name}</span><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString("en-GB", { timeZone: "UTC" })} UTC</time></div>
          <p>{event.message}</p><span className={styles.muted}>{event.event_type.replaceAll("_", " ")}</span>
          {Array.isArray(event.metadata.queries) && <TextList values={event.metadata.queries.filter((value): value is string => typeof value === "string")} />}
        </li>)}
        {running && <li className={styles.working} aria-hidden="true"><span /><span /><span /></li>}</ol>
      </section>
    </>
  );
}
