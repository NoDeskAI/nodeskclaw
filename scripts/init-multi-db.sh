#!/usr/bin/env bash
set -e

if [ -n "$GENEHUB_DB" ] && [ "$GENEHUB_DB" != "$POSTGRES_DB" ]; then
  host_arg=""
  if [ -n "${PGHOST:-}" ]; then
    host_arg="--host=$PGHOST"
  fi
  psql -v ON_ERROR_STOP=1 $host_arg --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE $GENEHUB_DB OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$GENEHUB_DB')\gexec
EOSQL
  echo "Database '$GENEHUB_DB' ensured."
fi
