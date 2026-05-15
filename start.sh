#!/usr/bin/env bash
# start.sh — Start the Vantyx local server
# Usage: bash start.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
  echo "[Vantyx] Loaded credentials from .env"
else
  echo "[Vantyx] WARNING: .env not found — copy .env.example to .env and fill in your credentials"
fi

echo ""
echo "=============================================="
echo "  Vantyx Local Server"
echo "  Website:   http://localhost:${LOI_PORT:-8080}/"
echo "  LOI Form:  http://localhost:${LOI_PORT:-8080}/loi"
echo "  Dashboard: http://localhost:${LOI_PORT:-8080}/dashboard"
echo "=============================================="
echo ""

exec python server.py
