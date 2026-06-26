# Architecture Map

PE-ACC is a Dockerized public-interest graph app:

- `frontend` calls the API.
- `api` reads Neo4j through service and query modules.
- `etl` loads public source data into Neo4j.
- `docs` and registries describe what data is in scope and how public behavior is bounded.

## Domains

| Domain | Path | Responsibility |
|---|---|---|
| API | `api/src/bracc/` | FastAPI app, routers, services, models, middleware, Cypher queries. |
| ETL | `etl/src/bracc_etl/` | Source pipelines, transforms, entity resolution, loader, CLI runner. |
| Frontend | `frontend/src/` | React pages, components, stores, hooks, API client, runtime config. |
| Infra | `docker-compose.yml`, `infra/` | Neo4j, API, frontend containers, healthchecks, deploy/backup helpers. |
| Data | `data/` | Raw, normalized, demo, and fixture-like public data inputs. |
| Governance | `docs/`, `SECURITY.md`, `PRIVACY.md`, `ABUSE_RESPONSE.md` | Public boundary, release, legal, and trust docs. |

## API Shape

- Entry point: `api/src/bracc/main.py`.
- Routers live under `api/src/bracc/routers/`.
- Business logic lives under `api/src/bracc/services/`.
- Models live under `api/src/bracc/models/`.
- Cypher is stored as files under `api/src/bracc/queries/`.
- Public-safe behavior is controlled by env flags such as `PUBLIC_MODE`, `PUBLIC_ALLOW_PERSON`, and `PATTERNS_ENABLED`.

Keep public endpoints conservative. If a route can expose person-adjacent data,
check `docs/release/public_endpoint_matrix.md` and existing `api/tests/unit/test_public_mode.py`.

## ETL Shape

- CLI runner: `etl/src/bracc_etl/runner.py`.
- Pipelines live under `etl/src/bracc_etl/pipelines/`.
- Shared transforms live under `etl/src/bracc_etl/transforms/`.
- Fixtures and pipeline tests live under `etl/tests/`.
- Peruvian priority pipelines use `pe_*` names.

For new Peruvian sources, update `docs/source_registry_pe_v1.csv`, add a fixture,
write a pipeline test, and document input/output expectations.

## Frontend Shape

- App root: `frontend/src/App.tsx`.
- Pages live under `frontend/src/pages/`.
- Reusable UI components live under `frontend/src/components/`.
- API calls live in `frontend/src/api/client.ts`.
- Runtime flags live in `frontend/src/config/runtime.ts`.
- Tests are colocated as `*.test.tsx` or `*.test.ts`.
- Styling uses CSS modules and global tokens.

UI changes should cover loading, error, empty, and public-mode states when relevant.

## Dependency Boundaries

- Frontend must not rely on secrets. Only `VITE_*` public config reaches the client.
- API should keep public filtering in services/routers, not in frontend-only logic.
- ETL should normalize and validate source data before loading graph relationships.
- Docs must stay aligned with source registries and public endpoint behavior.
- Prefer existing helpers and patterns before adding dependencies.

## Local Runtime

- Root `docker-compose.yml` is the normal local stack.
- Ports are bound to `127.0.0.1`: frontend `3000`, API `8000`, Neo4j browser `7474`, Bolt `7687`.
- Healthchecks exist for Neo4j, API, and frontend.
- Demo credentials are documented in `README.md`.
