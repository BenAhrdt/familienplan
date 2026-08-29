#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PID=""
FRONTEND_PID=""

stop_services() {
  trap - INT TERM EXIT
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}

trap stop_services INT TERM EXIT

if [[ ! -x "$PROJECT_DIR/.venv/bin/uvicorn" ]]; then
  echo "Python-Umgebung fehlt. Bitte zuerst die Installation aus der README ausführen."
  exit 1
fi

if [[ ! -d "$PROJECT_DIR/frontend/node_modules" ]]; then
  echo "Frontend-Abhängigkeiten fehlen. Installiere sie einmalig mit: cd frontend && npm install"
  exit 1
fi

echo "Prüfe Datenbankmigrationen …"
(cd "$PROJECT_DIR/backend" && ../.venv/bin/alembic upgrade head)

echo "Starte Backend auf http://127.0.0.1:8000 …"
(cd "$PROJECT_DIR/backend" && ../.venv/bin/uvicorn app.main:app --reload) &
BACKEND_PID=$!

echo "Starte Frontend auf http://localhost:5173 …"
(cd "$PROJECT_DIR/frontend" && npm run dev) &
FRONTEND_PID=$!

echo "FamilienPlan läuft. Mit Strg+C werden beide Prozesse beendet."

wait -n "$BACKEND_PID" "$FRONTEND_PID"
