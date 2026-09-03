# Contributing

Thank you for contributing to R&D Intelligence Agent. Human contributors and
coding agents follow the same scoped, testable workflow.

## Before starting

1. Read `README.md`, `AGENTS.md`, and `docs/ROADMAP.md`.
2. Pick or create a GitHub issue with clear acceptance criteria.
3. Confirm that no other contributor owns the same files or contract change.
4. Create a branch from `main`:

```bash
git switch -c feat/short-description
```

Use `fix/`, `docs/`, or `chore/` where appropriate.

## Change guidelines

- Keep each pull request focused on one issue or roadmap phase.
- Include tests with behavior changes.
- Do not mix broad refactors with new features unless required.
- Never commit secrets or generated local state.
- Use conventional commit prefixes such as `feat:`, `fix:`, `test:`, `docs:`,
  and `chore:`.
- Record intentional API/schema changes in the PR description.

## Required verification

```bash
cd backend && ../.venv/bin/python -m pytest
cd frontend && npm run lint && npm run build
```

If a command does not apply, explain why in the pull request.

## Pull requests

- Link the issue with `Closes #...` when appropriate.
- Complete the PR template, including tests and remaining limitations.
- Request review before merge; do not push directly to `main` after repository
  branch protection is enabled.
- Prefer squash merge so each scoped issue has one clear commit on `main`.
