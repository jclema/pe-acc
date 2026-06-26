# Agent Knowledge Index

This directory is the Codex-facing system of record for working in PE-ACC.
`AGENTS.md` stays short; these files hold the deeper operating context.

## Core Docs

| Need | Read |
|---|---|
| Repo purpose and MVP state | `README.md` |
| Domain and package map | `docs/agent/architecture.md` |
| How to make common changes | `docs/agent/playbooks.md` |
| Which checks to run | `docs/agent/quality-gates.md` |
| PR review criteria | `docs/agent/review-checklist.md` |
| Local reproducibility | `docs/reproducibility.md` |
| Public boundary | `docs/public_scope.md` |
| Public endpoint behavior | `docs/release/public_endpoint_matrix.md` |
| Peruvian source registry | `docs/source_registry_pe_v1.csv` |

## Operating Principle

Prefer progressive disclosure. Start with `AGENTS.md`, then load only the doc
that matches the task. Do not paste or carry the whole repo context into a task
when a focused section is enough.

## Current Agent Harness

- `Makefile` exposes stable commands for setup, development, checks, and bootstrap.
- `docker-compose.yml` starts the local API, frontend, Neo4j, and optional ETL service.
- `scripts/ci/python_quality.sh` and `scripts/ci/frontend_quality.sh` mirror CI checks.
- `.github/workflows/ci.yml` runs API, ETL, frontend, neutrality, and optional integration jobs.
- `.github/pull_request_template.md` captures release metadata, validation, public safety, risk, and rollback.

## Known Harness Gaps

- Some inherited BR-ACC docs and scripts still exist for upstream context.
- Integration tests require a running Neo4j or CI service container.
- Browser-level UI verification is manual today; use the MVP manual path in `playbooks.md`.
- Observability is basic local logs and healthchecks, not a full local traces/metrics stack.
