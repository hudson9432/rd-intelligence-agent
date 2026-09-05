# Mission workspace integration

Approved scope: retain the dashboard design and expose mission execution, progress,
sources/evidence, candidate scores/decision and PoC tasks. Add only the read API
needed to make persisted results available. Calendar execution is out of scope.

Use the current client-component architecture and `NEXT_PUBLIC_API_URL` setting.
Add `/missions/[id]` with an asynchronous run button. Poll a single aggregate
`GET /missions/{id}/workspace` response every three seconds while running; stop
on completion/failure, unmount, or request failure. Offer explicit retry after
transport failure and never automatically retry a run POST. Preserve uncertainty
after a POST timeout: reload status before allowing another run.

The read service composes existing repositories and validated schemas; agents
and persistence models remain unchanged. Mission sources/evidence are cumulative
and labeled as saved mission records. Events retain history. Current decisions
and plans must not be inferred from older runs; running/failed missions must not
show an earlier plan as their current outcome. Scoring stays in backend code.

Frontend presents loading, unavailable, empty, failed, no-viable-direction and
completed outcomes separately. Links preserve source/evidence IDs and only open
HTTP(S) URLs. Missing metrics remain unknown. Task checkboxes/calendar side
effects are not introduced because the backend has no task mutation contract.

Verify repository isolation/404 behavior, offline full workflow through the read
API, stale-run suppression, UI run/poll/error transitions and source links. Run
backend pytest and frontend Vitest, lint and production build.
