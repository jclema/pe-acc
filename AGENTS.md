# PE-ACC Agent Map

PE-ACC is a public-interest integrity graph for Peru. It adapts BR-ACC ideas to
Peruvian public data: SUNAT providers, OSCE sanctions, SEACE/CONOSCE procurement,
and later MEF budget context.

This file is an index for Codex, not the full manual. Load deeper docs only when
the task needs them.

## Start Here

- Product overview: `README.md`
- Agent knowledge index: `docs/agent/index.md`
- Architecture map: `docs/agent/architecture.md`
- Task playbooks: `docs/agent/playbooks.md`
- Quality gates: `docs/agent/quality-gates.md`
- Review checklist: `docs/agent/review-checklist.md`
- Public scope: `docs/public_scope.md`
- Source registry: `docs/source_registry_pe_v1.csv`
- Reproducibility: `docs/reproducibility.md`

## Repo Map

- `api/`: FastAPI app, routers, services, models, Cypher query files.
- `etl/`: data ingestion framework, source pipelines, transforms, fixtures.
- `frontend/`: React 19, Vite, TypeScript, CSS modules.
- `infra/`: Docker infrastructure, Neo4j bootstrap, backup/deploy scripts.
- `scripts/`: local automation, quality checks, bootstrap orchestration.
- `docs/`: public docs, source registries, release/compliance material.
- `data/`: raw, normalized, and demo data. Treat real data carefully.

## Default Commands

- Setup env: `make setup-env`
- Start local stack: `make dev`
- Stop local stack: `make stop`
- Fast agent check: `make agent-check-fast`
- Full agent check: `make agent-check-full`
- Demo bootstrap: `make agent-bootstrap-demo`
- Stack health: `make agent-health`
- All standard checks: `make check`

## Scope-Based Checks

- API change: `make test-api`, then `make lint` and `make type-check` if shared behavior changed.
- ETL change: `make test-etl`, plus source-specific fixture tests.
- Frontend change: `make test-frontend`, and `cd frontend && npm run build` for UI or routing changes.
- Public safety change: `make neutrality` and `make check-public-claims`.
- Source registry change: `make check-source-urls` when network access is available.
- Before PR: run the smallest relevant gate, then explain anything skipped.

## Safety Boundaries

- Do not commit `.env`, credentials, downloaded private data, or production dumps.
- Never put secrets in `VITE_*`; frontend env is public.
- Public output must not accuse, rank corruption, or imply legal guilt.
- Keep `PUBLIC_MODE` behavior conservative unless the user explicitly asks to change it.
- Do not expose person-adjacent data in public flows without checking public boundary docs.
- Ask before changing database schema, auth behavior, public endpoint exposure, or release policy.

## Product Rules

- Prioritize visible Peru MVP value: search, traceability, source coverage, operations.
- Prefer data provenance and source links over interpretive scoring.
- Keep imported upstream BR-ACC code only when it serves PE-ACC.
- For new Peruvian data, register the source and document cutoff, license, limitations, and load state.
- For new ETL, include a fixture and a pipeline test before broadening the dataset.

## Working Style

- Read relevant source, tests, and one nearby pattern before editing.
- Keep changes small and vertical.
- Preserve existing architecture unless there is a clear reason to change it.
- Add docs when commands, workflows, public behavior, or data contracts change.
- When requirements conflict, surface the conflict instead of guessing.
- After editing, run the minimum relevant check and report exactly what passed or could not run.

## PR Expectations

- Explain user impact, risk, validation, and rollback.
- Include tests for behavior changes.
- Review public safety and privacy when endpoints, graph output, or data fields change.
- Use `docs/agent/review-checklist.md` before opening or updating a PR.
