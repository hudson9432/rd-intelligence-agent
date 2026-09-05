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
        Create your first mission above. Evidence, opportunity ranking, and PoC
        plans will appear here as the agent workflow is wired up.
      </p>
    </div>
  );
}
