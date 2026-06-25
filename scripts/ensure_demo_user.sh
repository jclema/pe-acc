#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

DEMO_USER_EMAIL="${DEMO_USER_EMAIL:-demo@pe-acc.local}"
DEMO_USER_PASSWORD="${DEMO_USER_PASSWORD:-peacc-demo-2026}"
NEO4J_USER="${NEO4J_USER:-neo4j}"

if [[ -z "${NEO4J_PASSWORD:-}" && -f "${ROOT_DIR}/.env" ]]; then
  NEO4J_PASSWORD="$(grep -E '^NEO4J_PASSWORD=' "${ROOT_DIR}/.env" | tail -n 1 | cut -d '=' -f2- || true)"
  export NEO4J_PASSWORD
fi

if [[ -z "${NEO4J_PASSWORD:-}" ]]; then
  NEO4J_PASSWORD="changeme"
  export NEO4J_PASSWORD
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required to provision the demo user." >&2
  exit 1
fi

echo "Ensuring demo user exists: ${DEMO_USER_EMAIL}"

PASSWORD_HASH="$(
  docker compose -f "${COMPOSE_FILE}" exec -T api uv run python -c \
    "from bracc.services.auth_service import hash_password; print(hash_password('${DEMO_USER_PASSWORD}'))"
)"

docker exec -i bracc-neo4j cypher-shell -u "${NEO4J_USER}" -p "${NEO4J_PASSWORD}" <<EOF
MERGE (u:User {email: '${DEMO_USER_EMAIL}'})
ON CREATE SET
  u.id = randomUUID(),
  u.created_at = datetime()
SET
  u.password_hash = '${PASSWORD_HASH}'
RETURN u.id AS id, u.email AS email, toString(u.created_at) AS created_at;
EOF

echo "Demo user ready."
echo "- Email: ${DEMO_USER_EMAIL}"
echo "- Password: ${DEMO_USER_PASSWORD}"
