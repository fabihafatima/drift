#!/usr/bin/env bash
# Starts the Drift API (:8000) and web app (:3000). Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d api/.venv ]; then
  python3 -m venv api/.venv
  api/.venv/bin/pip install -q -r api/requirements.txt
fi
[ -d web/node_modules ] || (cd web && npm install)

trap 'kill 0' EXIT
(cd api && .venv/bin/uvicorn drift.main:app --port 8000) &
(cd web && npm run dev) &
wait
