#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -d .git ]]; then
  echo "Fehler: Updates über dieses Skript setzen eine Installation aus dem Git-Repository voraus." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Fehler: Im Projekt liegen lokale Änderungen. Bitte zuerst sichern oder einchecken." >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "Fehler: .env fehlt." >&2
  exit 1
fi

echo "Suche nach veröffentlichten Versionen …"
git fetch --tags --prune
latest_tag="$(git tag --list 'v[0-9]*' --sort=-v:refname | head -n 1)"
if [[ -z "$latest_tag" ]]; then
  echo "Fehler: Im Repository wurde noch kein versioniertes Release gefunden." >&2
  exit 1
fi
current_version="v$(tr -d '[:space:]' < VERSION)"
if [[ "$current_version" == "$latest_tag" ]]; then
  echo "FamilienPlan $current_version ist bereits aktuell."
  exit 0
fi

echo "Erstelle Sicherheitskopie …"
"$PROJECT_DIR/scripts/backup.sh"

echo "Aktualisiere $current_version auf $latest_tag …"
git checkout --detach "$latest_tag"
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"
npm --prefix "$PROJECT_DIR/frontend" ci
npm --prefix "$PROJECT_DIR/frontend" run build
(cd "$PROJECT_DIR/backend" && ../.venv/bin/alembic upgrade head)

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet familienplan.service; then
  systemctl restart familienplan.service
fi

echo "Update auf FamilienPlan $latest_tag abgeschlossen."
