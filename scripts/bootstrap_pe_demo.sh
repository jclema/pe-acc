#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"
NEO4J_USER="${NEO4J_USER:-neo4j}"

if [[ -z "${NEO4J_PASSWORD:-}" && -f "${ROOT_DIR}/.env" ]]; then
  NEO4J_PASSWORD="$(grep -E '^NEO4J_PASSWORD=' "${ROOT_DIR}/.env" | tail -n 1 | cut -d '=' -f2- || true)"
  export NEO4J_PASSWORD
fi

if [[ -z "${NEO4J_PASSWORD:-}" ]]; then
  NEO4J_PASSWORD="changeme"
  export NEO4J_PASSWORD
  echo "NEO4J_PASSWORD was not set; using fallback 'changeme'." >&2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to run the Peru MVP bootstrap." >&2
  exit 1
fi

echo "Starting Docker stack for Peru MVP demo..."
docker compose -f "${COMPOSE_FILE}" --profile etl up -d --build

echo "Waiting for Neo4j health..."
for _ in $(seq 1 60); do
  if docker exec bracc-neo4j cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" "RETURN 1" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! docker exec bracc-neo4j cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" "RETURN 1" >/dev/null 2>&1; then
  echo "Neo4j health check failed." >&2
  exit 1
fi

echo "Waiting for API health endpoint..."
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
  echo "API health check failed at http://localhost:8000/health" >&2
  exit 1
fi

echo "Preparing Peru demo CSV inputs..."
bash "${ROOT_DIR}/scripts/prepare_pe_demo_data.sh"

run_pipeline() {
  local source="$1"
  echo "- Running ETL source: ${source}"
  docker compose -f "${COMPOSE_FILE}" --profile etl run --rm etl \
    uv run bracc-etl run \
    --source "${source}" \
    --neo4j-uri "bolt://neo4j:7687" \
    --neo4j-user "${NEO4J_USER}" \
    --neo4j-password "${NEO4J_PASSWORD}" \
    --neo4j-database "${NEO4J_DATABASE}" \
    --data-dir ../data
}

run_pipeline "pe_sunat_ruc"
run_pipeline "pe_osce_sanctions"
run_pipeline "pe_seace_conosce"

node_count="$(docker exec bracc-neo4j cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" "MATCH (n) RETURN count(n) AS c" --format plain 2>/dev/null | tail -n 1 | tr -d '[:space:]')"

echo "Peru MVP bootstrap complete."
echo "- API: http://localhost:8000/health"
echo "- API Docs: http://localhost:8000/docs"
echo "- Frontend: http://localhost:3000"
echo "- Neo4j Browser: http://localhost:7474"
echo "- Current graph node count: ${node_count:-unknown}"
