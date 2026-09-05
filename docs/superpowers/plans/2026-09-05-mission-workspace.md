# Mission Workspace Implementation Plan

**Goal:** Make the existing research-to-action workflow usable from the dashboard.
**Architecture:** A read-only aggregate API over existing repositories, a typed
browser client, a detail route with bounded polling, and result presentation.
**Tech Stack:** FastAPI/Pydantic/SQLAlchemy, Next.js 16/React 19/TypeScript, Vitest.
**Spec:** `docs/superpowers/specs/2026-09-05-mission-workspace-design.md`

## Tasks

- [ ] Add failing backend API tests for empty/missing missions, saved provenance,
  full mock workflow and stale results. Implement `MissionWorkspace` schema and
  `MissionWorkspaceService.get(mission_id)` using repositories; expose
  `GET /missions/{mission_id}/workspace` without changing existing responses.
- [ ] Add typed browser request helper and contract types. Test HTTP errors,
  timeouts and abort cleanup. Add `MissionDetail` with run POST, status refresh,
  completion-aware polling, loading and retry; protect against stale requests.
- [ ] Render saved sources/evidence, opportunities, decision, candidate claims,
  PoC tasks, success metrics and event history with provenance links. Add detail
  route and dashboard links; replace fake overview metrics with mission counts.
- [ ] Add UI regression tests for execution, failure, polling cleanup and output
  navigation. Keep existing mission creation and race-condition tests passing.
- [ ] Run full backend tests, frontend tests/lint/build and inspect the rendered
  detail/dashboard. Document API and UI behavior; update Phase 13 only if done.

Verification commands (repository-local tools):

```powershell
.venv/Scripts/python.exe -m pytest backend/tests
cd frontend
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

No production research calls or calendar side effects are needed for testing.
