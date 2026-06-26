# Agent Playbooks

Use these recipes for common PE-ACC changes. Keep each change small enough to
verify with the matching gate in `docs/agent/quality-gates.md`.

## Frontend Change

1. Read the page/component to edit and a nearby `*.test.tsx`.
2. Check runtime flags in `frontend/src/config/runtime.ts` if public mode matters.
3. Preserve CSS module style and existing component patterns.
4. Cover loading, error, empty, and success states when the flow needs them.
5. Run `make test-frontend`; run `cd frontend && npm run build` for routing, config, or UI-wide changes.

Acceptance criteria:

- User-facing behavior works in the target route.
- Tests cover the changed behavior.
- Text does not imply accusations or legal conclusions.
- No secret or private value is exposed through `VITE_*`.

## Public API Endpoint Change

1. Read the router, service, model, query file, and relevant unit tests.
2. Check `docs/release/public_endpoint_matrix.md` when endpoint visibility changes.
3. Keep public filtering server-side.
4. Add or update tests under `api/tests/unit/`.
5. Run `make test-api`; run `make neutrality` for public text or signal changes.

Acceptance criteria:

- Response contract is explicit through models/tests.
- `PUBLIC_MODE` behavior is tested when relevant.
- Person-adjacent fields remain restricted by default.
- Errors are safe and do not leak internals.

## Peru ETL Pipeline Change

1. Check `docs/source_registry_pe_v1.csv` for source state and naming.
2. Read a nearby `pe_*` pipeline and its tests.
3. Put raw public samples under `data/raw/pe/...` only when they are safe to commit.
4. Normalize outputs under `data/normalized/pe/...` when the workflow needs a committed sample.
5. Add fixtures under `etl/tests/fixtures/` and pipeline tests under `etl/tests/`.
6. Run `make test-etl`.

Acceptance criteria:

- Source has registry entry, URL, load state, cadence, and notes.
- Pipeline handles missing or malformed rows safely.
- Join key, usually RUC, is documented and tested.
- Neo4j relationship semantics are traceable to source fields.

## Source Registry or Docs Change

1. Use `docs/source_registry_pe_v1.csv` for Peru-facing source state.
2. Keep source names, URLs, implementation state, load state, quality status, and notes current.
3. Update README or `docs/agent/*` only when the operating workflow changes.
4. Run `make check-public-claims`.
5. Run `make check-source-urls` when network access is available.

Acceptance criteria:

- Public claims match registry values.
- Source limitations and cutoff dates are visible.
- Links point to existing files or public URLs.

## Public Safety Change

1. Read `docs/public_scope.md`, `docs/release/public_endpoint_matrix.md`, and relevant tests.
2. Prefer conservative defaults.
3. Avoid language like corrupt, criminal, guilty, or severity labels unless legal docs explicitly require it.
4. Run `make neutrality`, `make check-public-claims`, and impacted tests.

Acceptance criteria:

- Public defaults remain safe.
- No new personally sensitive exposure is introduced.
- PR summary includes risk and rollback.

## Manual MVP Verification

Use this after changes that affect the end-to-end demo.

1. `cp .env.example .env` if no local env exists.
2. `make agent-bootstrap-demo`.
3. Open `http://localhost:3000`.
4. Log in with `demo@pe-acc.local` and `peacc-demo-2026`.
5. Search `20100994128`.
6. Open the provider, inspect the graph, hover/click the sanction node and edge.
7. Check `http://localhost:8000/health` and `http://localhost:8000/docs`.
8. Run `make agent-health` and capture any failing service.

Expected result:

- Provider and sanction relationship are visible.
- API health returns ok.
- Frontend, API, and Neo4j containers are healthy or the failure is documented.
