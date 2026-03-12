#!/bin/bash
set -euo pipefail

if [ -f /opt/zeroclaw/.zeroclaw-version ]; then
  echo "ZeroClaw image version: $(cat /opt/zeroclaw/.zeroclaw-version)"
fi

exec "$@"
