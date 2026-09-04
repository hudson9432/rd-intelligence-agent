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
        Your evidence-backed research missions will appear here once the
        workflow API is connected.
      </p>
    </div>
  );
}
