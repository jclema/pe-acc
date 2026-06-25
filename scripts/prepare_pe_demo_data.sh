#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_DIR="${ROOT_DIR}/data/demo/pe"
TARGET_DIR="${ROOT_DIR}/data/pe"

mkdir -p \
  "${TARGET_DIR}/sunat_ruc" \
  "${TARGET_DIR}/osce_sanctions" \
  "${TARGET_DIR}/seace_conosce"

cp "${DEMO_DIR}/sunat_ruc/providers.csv" "${TARGET_DIR}/sunat_ruc/providers.csv"
cp "${DEMO_DIR}/osce_sanctions/sanctions.csv" "${TARGET_DIR}/osce_sanctions/sanctions.csv"
cp "${DEMO_DIR}/seace_conosce/processes.csv" "${TARGET_DIR}/seace_conosce/processes.csv"

echo "Demo Peru data copied to ${TARGET_DIR}"
