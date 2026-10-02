#!/usr/bin/env bash
set -u

fail=0

echo "[frontend-quality] installing dependencies"
npm ci || exit 1

echo "[frontend-quality] lint"
npx --no-install eslint src/ || fail=1

echo "[frontend-quality] type-check"
npx --no-install tsc --noEmit || fail=1

echo "[frontend-quality] tests"
npm test -- --run || fail=1

echo "[frontend-quality] build"
npm run build || fail=1

if [ "$fail" -ne 0 ]; then
  echo "[frontend-quality] one or more checks failed"
fi

exit "$fail"
