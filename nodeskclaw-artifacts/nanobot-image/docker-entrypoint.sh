#!/bin/bash
set -euo pipefail

CONFIG_TEMPLATE="/opt/nanobot/nanobot.yaml.template"
CONFIG_FILE="/opt/nanobot/nanobot.yaml"

if [ -f "${CONFIG_TEMPLATE}" ] && [ ! -f "${CONFIG_FILE}" ]; then
  envsubst < "${CONFIG_TEMPLATE}" > "${CONFIG_FILE}"
fi

if [ -f /opt/nanobot/.nanobot-version ]; then
  echo "Nanobot image version: $(cat /opt/nanobot/.nanobot-version)"
fi

exec "$@"
