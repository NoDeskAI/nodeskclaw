#!/usr/bin/env bash
set -euo pipefail

GITEA_URL="${GITEA_URL:-http://localhost:3001}"
GITEA_ADMIN_USER="${GITEA_ADMIN_USER:-genehub}"
GITEA_ADMIN_PASSWORD="${GENEHUB_ADMIN_TOKEN:-admin-dev-token}"
GITEA_ADMIN_EMAIL="${GITEA_ADMIN_EMAIL:-admin@genehub.local}"

ORGS=("${GITEA_ORG:-genes}" "genomes" "templates")
ORG_LABELS=("GeneHub Genes:Gene repository storage" "GeneHub Genomes:Genome repository storage" "GeneHub Templates:Agent template repository storage")

wait_for_gitea() {
  echo "Waiting for Gitea at ${GITEA_URL}..."
  for i in $(seq 1 60); do
    if curl -fsS "${GITEA_URL}/api/v1/version" >/dev/null 2>&1; then
      echo "Gitea is ready."
      return 0
    fi
    sleep 2
  done
  echo "ERROR: Gitea did not become ready in time."
  exit 1
}

create_admin() {
  echo "Creating admin user '${GITEA_ADMIN_USER}'..."
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    "${GITEA_URL}/api/v1/admin/users" \
    -H "Content-Type: application/json" \
    -d "{
      \"email\": \"${GITEA_ADMIN_EMAIL}\",
      \"full_name\": \"GeneHub Admin\",
      \"login_name\": \"${GITEA_ADMIN_USER}\",
      \"must_change_password\": false,
      \"password\": \"${GITEA_ADMIN_PASSWORD}\",
      \"send_notify\": false,
      \"username\": \"${GITEA_ADMIN_USER}\",
      \"visibility\": \"public\"
    }")

  if [ "$status" = "201" ]; then
    echo "Admin user created."
  elif [ "$status" = "422" ]; then
    echo "Admin user already exists, skipping."
  else
    echo "WARNING: Unexpected status $status when creating admin user."
  fi
}

create_org() {
  local org_name="$1"
  local full_name="$2"
  local description="$3"

  echo "Creating organization '${org_name}'..."
  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    -u "${GITEA_ADMIN_USER}:${GITEA_ADMIN_PASSWORD}" \
    "${GITEA_URL}/api/v1/orgs" \
    -H "Content-Type: application/json" \
    -d "{
      \"username\": \"${org_name}\",
      \"full_name\": \"${full_name}\",
      \"description\": \"${description}\",
      \"visibility\": \"public\"
    }")

  if [ "$status" = "201" ]; then
    echo "Organization '${org_name}' created."
  elif [ "$status" = "422" ]; then
    echo "Organization '${org_name}' already exists, skipping."
  else
    echo "WARNING: Unexpected status $status when creating organization '${org_name}'."
  fi
}

wait_for_gitea
create_admin

for i in "${!ORGS[@]}"; do
  IFS=':' read -r full_name description <<< "${ORG_LABELS[$i]}"
  create_org "${ORGS[$i]}" "$full_name" "$description"
done

echo "Gitea initialization complete."
