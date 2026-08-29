#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

need_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Fehler: '$1' fehlt. Bitte zuerst $2 installieren." >&2
    exit 1
  fi
}

need_command python3 "Python 3 mit venv"
need_command npm "Node.js und npm"
need_command pg_isready "den PostgreSQL-Client"
need_command openssl "OpenSSL"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  install -m 600 "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
  secret_key="$(openssl rand -hex 32)"
  sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$secret_key|" "$PROJECT_DIR/.env"
  echo "Konfiguration wurde unter $PROJECT_DIR/.env angelegt."
  echo "Trage dort DATABASE_URL und APP_ORIGIN ein und starte das Skript erneut."
  exit 2
fi

chmod 600 "$PROJECT_DIR/.env"
if grep -q '^DATABASE_URL=.*CHANGE_ME' "$PROJECT_DIR/.env"; then
  echo "Fehler: Bitte zuerst DATABASE_URL in $PROJECT_DIR/.env konfigurieren." >&2
  exit 2
fi
if grep -q '^SECRET_KEY=.*CHANGE_ME' "$PROJECT_DIR/.env"; then
  echo "Fehler: Bitte zuerst einen sicheren SECRET_KEY in $PROJECT_DIR/.env konfigurieren." >&2
  exit 2
fi

if [[ ! -d "$PROJECT_DIR/.venv" ]]; then
  python3 -m venv "$PROJECT_DIR/.venv"
fi
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"
npm --prefix "$PROJECT_DIR/frontend" ci
npm --prefix "$PROJECT_DIR/frontend" run build
(cd "$PROJECT_DIR/backend" && ../.venv/bin/alembic upgrade head)

echo
echo "FamilienPlan wurde erfolgreich installiert."
echo "Entwicklung: $PROJECT_DIR/start.sh"
echo "Produktion:  Hinweise zu nginx und systemd in der README beachten."
