"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, apiRequest, getWorkspace } from "@/lib/api";
import type { MissionWorkspaceData } from "@/types/workspace";
import { MissionResults } from "./MissionResults";
import styles from "./workspace.module.css";

export function MissionDetail({ missionId }: { missionId: string }) {
  const [workspace, setWorkspace] = useState<MissionWorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const runRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const data = await getWorkspace(missionId, controller.signal);
        if (controller.signal.aborted) return;
        setWorkspace(data);
        setError(null);
        if (data.mission.status === "running") timer = setTimeout(load, 3000);
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Unable to load mission.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [missionId, refresh]);

  useEffect(() => () => runRequest.current?.abort(), [missionId]);

  function refreshStatus() {
    setLoading(true);
    setRefresh((value) => value + 1);
  }

  async function startResearch() {
    if (starting || loading || error || workspace?.mission.status === "running") return;
    setStarting(true);
    const controller = new AbortController();
    runRequest.current = controller;
    try {
      await apiRequest(`/missions/${encodeURIComponent(missionId)}/run/async`, { method: "POST", signal: controller.signal });
      if (!controller.signal.aborted) refreshStatus();
    } catch (cause) {
      if (controller.signal.aborted) return;
      if (cause instanceof ApiError && cause.status === 409) {
        refreshStatus();
      } else {
        // Never retry a side-effectful POST: it may have been accepted already.
        setError(`${cause instanceof Error ? cause.message : "Unable to start research."} Refresh status to confirm whether the run started.`);
      }
    } finally {
      if (!controller.signal.aborted) setStarting(false);
    }
  }

  const running = workspace?.mission.status === "running";
  return (
    <main className={styles.page}>
      <Link href="/" className={styles.back}>Back to workspace</Link>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Research mission</p>
          <h1>{workspace?.mission.title ?? "Mission workspace"}</h1>
          {workspace && <p className={styles.goal}>{workspace.mission.goal}</p>}
        </div>
        <div className={styles.actions}>
          {workspace && <button className={styles.primary} onClick={startResearch}
            disabled={starting || loading || running || !!error}>
            {starting ? "Starting research..." : running ? "Research running" : workspace.mission.status === "created" ? "Start research" : "Run again"}
          </button>}
          <button className={styles.secondary} onClick={refreshStatus} disabled={loading || starting}>Refresh status</button>
        </div>
      </header>
      {loading && <p role="status">Loading mission...</p>}
      {error && <div className={styles.error} role="alert"><strong>Unable to refresh this mission</strong><p>{error}</p>
        {workspace && <p>Displayed data is from the last successful refresh.</p>}</div>}
      {workspace && <MissionResults workspace={workspace} />}
    </main>
  );
}
