# API dependency security refresh

Validated on 2026-10-01 against main `98a06b9` using Python 3.12.
Targeted lock updates address the 11 packages in the frozen runtime audit:
anyio 4.14.2, click 8.3.3, cryptography 50.0.2, idna 3.15, Pillow 12.3.0,
pydantic-settings 2.14.2, PyJWT 2.15.1, python-dotenv 1.2.2,
python-multipart 0.0.31, Starlette 1.3.1 and WeasyPrint 70.0.
FastAPI 0.142.2 supports patched Starlette and adds opentelemetry-api 1.45.0;
development updates include Pygments 2.20.0, pytest 9.0.3, requests 2.33.0 and urllib3 2.8.0.

The [PyJWT advisory](https://github.com/advisories/GHSA-gvp8-978c-rx2q)
lists no patched version and an affected range ending at 2.13.0.
The [2.15.1 source](https://github.com/jpadilla/pyjwt/blob/2.15.1/jwt/api_jwt.py)
copies caller options. A regression test checks that unverified inspection
cannot disable expiry validation on subsequent reuse.

The [WeasyPrint advisory](https://github.com/advisories/GHSA-jhhc-3hcp-qhm5)
lists no patched version and an affected range ending at 68.1.
The [70.0 source](https://github.com/Kozea/WeasyPrint/blob/v70.0/weasyprint/css/__init__.py)
parses and escapes background URLs. Local smoke checks rendered a real PDF and
confirmed that a background attribute cannot inject a red text declaration.

Frozen runtime and development requirements pass strict pip-audit with no findings
or ignores. Full API compatibility tests, lint and types pass
when the separate API quality fix is included. Standalone main still has its
known test failures. Database integration was not run.
Rollback: revert and `uv sync --frozen --extra dev`.
