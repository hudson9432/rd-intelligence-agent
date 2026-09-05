export function EmptyMissions() {
  return (
    <div className="empty-state">
      <div className="empty-icon" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <h3>No research missions yet</h3>
      <p>
        Create a research mission to start building an evidence-backed workspace.
      </p>
    </div>
  );
}
