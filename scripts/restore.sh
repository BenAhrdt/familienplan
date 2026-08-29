#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then echo "Aufruf: $0 /pfad/zum/backup" >&2; exit 2; fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$(realpath "$1")"
test -f "$TARGET/database.dump"
set -a; source "$PROJECT_DIR/.env"; set +a
PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
(cd "$TARGET" && sha256sum -c SHA256SUMS)
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$PG_URL" "$TARGET/database.dump"
if [[ -f "$TARGET/uploads.tar.gz" ]]; then tar -C "$PROJECT_DIR" -xzf "$TARGET/uploads.tar.gz"; fi
echo "Restore abgeschlossen. Anschließend Migrationen prüfen: cd backend && alembic upgrade head"

