#!/usr/bin/env bash
# start_loi.sh — launch the Vantyx LOI email handler
# Usage: bash start_loi.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
  echo "[LOI] Loaded credentials from $ENV_FILE"
else
  echo "[LOI] WARNING: $ENV_FILE not found — using existing environment variables"
fi

echo "[LOI] Starting handler on port ${LOI_PORT:-8080} …"
cd "$SCRIPT_DIR"
exec python loi_handler.py
