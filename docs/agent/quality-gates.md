# Quality Gates

Run the smallest gate that proves the change. Report what passed and what was
skipped.

## Fast Gates

| Change | Command |
|---|---|
| API only | `make test-api` |
| ETL only | `make test-etl` |
| Frontend only | `make test-frontend` |
| Public wording or signal | `make neutrality` |
| Source registry/docs claim | `make check-public-claims` |
| Stack health | `make agent-health` |

## Agent Gates

| Gate | Command | Use When |
|---|---|---|
| Fast agent gate | `make agent-check-fast` | Before handing back most code changes. |
| Full agent gate | `make agent-check-full` | Before PRs or broad cross-stack changes. |
| Demo bootstrap | `make agent-bootstrap-demo` | Before claiming MVP demo works end-to-end. |

## Standard Gates

- `make lint`: ruff for API/ETL and eslint for frontend.
- `make type-check`: mypy for API/ETL and TypeScript for frontend.
- `make test`: API, ETL, and frontend tests.
- `make check`: lint, type-check, and tests.
- `make neutrality`: banned public-safety wording scan.

## Heavy or Conditional Gates

- `make test-integration`: requires Neo4j.
- `make bootstrap-all`: long-running ingestion path.
- `make check-source-urls`: requires network and can fail because public portals are down or rate-limited.
- `make bootstrap-all-noninteractive`: destructive to local graph by design; use only when reset is intended.

## Full Gate Definition

`make agent-check-full` should cover:

- `make check`
- `make neutrality`
- `make check-public-claims`
- `make check-source-urls`
- `cd frontend && npm run build`

If network is unavailable, run the rest and report that `check-source-urls` was skipped.

## Failure Handling

- Read the first actionable error, not the whole log.
- Fix root cause, not symptoms.
- Re-run the smallest failing gate.
- If a gate is flaky or externally blocked, document command, failure, and likely blocker.
