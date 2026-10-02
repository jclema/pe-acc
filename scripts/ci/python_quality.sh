#!/usr/bin/env bash
set -u

fail=0

echo "[python-quality] installing dependencies"
uv sync --frozen --extra dev || exit 1

echo "[python-quality] lint"
uv run --frozen ruff check src/ tests/ || fail=1

echo "[python-quality] type-check"
uv run --frozen mypy src/ || fail=1

echo "[python-quality] tests"
uv run --frozen pytest -q || fail=1

if [ "$fail" -ne 0 ]; then
  echo "[python-quality] one or more checks failed"
fi

exit "$fail"
