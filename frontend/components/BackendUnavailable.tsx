import styles from "./mission.module.css";

interface BackendUnavailableProps {
  message: string;
}

/**
 * Shown when the mission API cannot be reached — including during a
 * production build, which prerenders with no backend running.
 */
export function BackendUnavailable({ message }: BackendUnavailableProps) {
  return (
    <div className={styles.unavailable} role="status">
      <h3>Mission API unavailable</h3>
      <p>{message}</p>
      <p className={styles.unavailableHint}>
        Start the backend with{" "}
        <code>uvicorn app.main:app --reload --port 8000</code> from{" "}
        <code>backend/</code>, then reload this page.
      </p>
    </div>
  );
}
