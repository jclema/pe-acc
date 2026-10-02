# ETL dependency security refresh

Validated on 2026-10-01 against main `98a06b9` using Python 3.12.
Targeted updates: anyio 4.14.2, click 8.3.3, idna 3.15,
pydantic-settings 2.14.2, pypdf 6.19.0, pytest 9.0.3,
python-dotenv 1.2.2, requests 2.33.0 and urllib3 2.8.0.
Direct dependency minima and both development declarations remain consistent.

Strict pip-audit of frozen default and development exports reports no findings
without ignores. With the separate ETL quality fix included, all 1018 tests,
Ruff and mypy pass; database integration and optional BigQuery/resolution
environments were not exercised. No pipeline, dataset or schema changed.

Rollback: revert this commit and run `uv sync --frozen --extra dev`.
