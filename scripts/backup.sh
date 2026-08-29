#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ ! -f "$PROJECT_DIR/.env" ]]; then echo "Fehler: .env fehlt" >&2; exit 1; fi
DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' "$PROJECT_DIR/.env" | tail -n 1)"
: "${DATABASE_URL:?DATABASE_URL fehlt}"
BACKUP_ROOT="${BACKUP_DIR:-$PROJECT_DIR/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TARGET="$BACKUP_ROOT/familienplan-$STAMP"
mkdir -p "$TARGET"
PG_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_dump --format=custom --no-owner --no-acl --file="$TARGET/database.dump" "$PG_URL"
install -m 600 "$PROJECT_DIR/.env" "$TARGET/app.env"
if [[ -d "$PROJECT_DIR/uploads" ]]; then tar -C "$PROJECT_DIR" -czf "$TARGET/uploads.tar.gz" uploads; fi
sha256sum "$TARGET"/* > "$TARGET/SHA256SUMS"
echo "Backup erstellt: $TARGET"
