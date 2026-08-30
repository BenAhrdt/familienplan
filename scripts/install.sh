#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
DB_NAME="familienplan"
DB_USER="familienplan"
INSTALL_DIR="/opt/familienplan"

fail() { echo "Fehler: $*" >&2; exit 1; }

run_as_root() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then "$@"
  elif command -v sudo >/dev/null 2>&1; then sudo "$@"
  else fail "Für die Installation werden root-Rechte oder sudo benötigt."
  fi
}

run_as_postgres() {
  if [[ ${EUID:-$(id -u)} -eq 0 ]]; then runuser -u postgres -- "$@"
  else sudo -u postgres "$@"
  fi
}

ask_public_origin() {
  local answer
  while true; do
    read -r -p "Öffentliche Adresse (z. B. https://familienplan.example.de): " answer
    answer="${answer%/}"
    if [[ "$answer" =~ ^https?://[^/]+$ ]]; then
      printf '%s' "$answer"
      return
    fi
    echo "Bitte eine vollständige Adresse mit http:// oder https:// ohne Pfad eingeben." >&2
  done
}

env_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}

write_env() {
  local temporary_file
  temporary_file="$(mktemp "$PROJECT_DIR/.env.XXXXXX")"
  chmod 600 "$temporary_file"
  {
    printf 'DATABASE_URL=postgresql+psycopg://%s:%s@127.0.0.1:5432/%s\n' "$DB_USER" "$4" "$DB_NAME"
    printf 'SECRET_KEY=%s\n' "$5"
    printf 'APP_ENV=%s\n' "$2"
    printf 'APP_ORIGIN=%s\n' "$1"
    printf 'SESSION_COOKIE_SECURE=%s\n' "$3"
    printf 'SESSION_HOURS=12\nREMEMBER_SESSION_DAYS=30\nINVITATION_HOURS=72\n'
    printf 'SMTP_HOST=\nSMTP_PORT=587\nSMTP_USERNAME=\nSMTP_PASSWORD=\n'
    printf 'SMTP_FROM=FamilienPlan <familienplan@example.de>\nSMTP_STARTTLS=true\n'
    printf 'UPLOAD_DIR=./uploads\nGITHUB_REPOSITORY=BenAhrdt/familienplan\n'
  } > "$temporary_file"
  mv "$temporary_file" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

echo "FamilienPlan – geführte Installation"
echo

[[ -r /etc/os-release ]] || fail "Die automatische Systemeinrichtung unterstützt derzeit Debian und Ubuntu."
. /etc/os-release
case "${ID:-}" in
  debian|ubuntu) ;;
  *) fail "Unterstützt werden Debian und Ubuntu (erkannt: ${ID:-unbekannt})." ;;
esac

echo "Installiere benötigte Systempakete …"
run_as_root apt-get update
run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl gnupg openssl postgresql postgresql-client python3 python3-venv python3-pip

node_major=0
if command -v node >/dev/null 2>&1; then
  node_major="$(node --version | sed 's/^v//' | cut -d. -f1)"
fi
if [[ ! "$node_major" =~ ^[0-9]+$ ]] || (( node_major < 20 )); then
  echo "Installiere aktuelle Node.js-LTS-Version …"
  nodesource_key="$(mktemp)"
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key -o "$nodesource_key"
  run_as_root mkdir -p /usr/share/keyrings
  run_as_root gpg --dearmor --yes -o /usr/share/keyrings/nodesource.gpg "$nodesource_key"
  rm -f "$nodesource_key"
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main' | \
    run_as_root tee /etc/apt/sources.list.d/nodesource.list >/dev/null
  run_as_root apt-get update
  run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y nodejs
fi
node_major="$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1)"

for required_command in python3 node npm pg_isready openssl; do
  command -v "$required_command" >/dev/null 2>&1 || fail "'$required_command' wurde nicht gefunden."
done
(( node_major >= 20 )) || fail "Benötigt wird Node.js 20 oder neuer; installiert ist $(node --version)."

echo "Starte PostgreSQL …"
run_as_root systemctl enable --now postgresql
pg_isready -q || fail "PostgreSQL ist nicht erreichbar."

reuse_config=false
configure_database=true
if [[ -f "$ENV_FILE" ]] && ! grep -q 'CHANGE_ME' "$ENV_FILE"; then
  read -r -p "Vorhandene .env weiterverwenden? [J/n]: " reuse_answer
  case "${reuse_answer:-j}" in j|J|ja|JA|Ja|y|Y|yes|YES) reuse_config=true ;; esac
fi

if [[ "$reuse_config" == true ]]; then
  database_url="$(env_value DATABASE_URL)"
  if [[ "$database_url" =~ ^postgresql(\+psycopg)?://familienplan:([^@]+)@127\.0\.0\.1:5432/familienplan$ ]]; then
    db_password="${BASH_REMATCH[2]}"
  else
    fail "Die vorhandene DATABASE_URL nutzt nicht die lokal verwaltete Standarddatenbank."
  fi
  echo "Bestehende Konfiguration wird beibehalten."
  configure_database=false
else
  app_origin="$(ask_public_origin)"
  if [[ "$app_origin" == https://* ]]; then
    app_env="production"; cookie_secure="true"
  else
    app_env="development"; cookie_secure="false"
  fi

  db_password="$(openssl rand -hex 24)"
  secret_key="$(openssl rand -hex 32)"
  write_env "$app_origin" "$app_env" "$cookie_secure" "$db_password" "$secret_key"
  echo "Konfiguration wurde geschützt unter $ENV_FILE gespeichert."
fi

if [[ "$configure_database" == true ]]; then
  echo "Richte PostgreSQL-Datenbank ein …"
  if run_as_postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -qx 1; then
    printf '%s\n' "ALTER ROLE $DB_USER WITH LOGIN PASSWORD :'db_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;" | run_as_postgres psql --set=db_password="$db_password"
  else
    printf '%s\n' "CREATE ROLE $DB_USER LOGIN PASSWORD :'db_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;" | run_as_postgres psql --set=db_password="$db_password"
  fi
  if ! run_as_postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -qx 1; then
    run_as_postgres createdb --owner="$DB_USER" --encoding=UTF8 --template=template0 "$DB_NAME"
  fi
  run_as_postgres psql -c "REVOKE ALL ON DATABASE $DB_NAME FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE $DB_NAME TO $DB_USER;"
fi

echo "Installiere Anwendungsabhängigkeiten …"
[[ -d "$PROJECT_DIR/.venv" ]] || python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
"$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/backend/requirements.txt"
npm --prefix "$PROJECT_DIR/frontend" ci
npm --prefix "$PROJECT_DIR/frontend" run build

echo "Führe Datenbankmigrationen aus …"
(cd "$PROJECT_DIR/backend" && ../.venv/bin/alembic upgrade head)

echo "Richte Produktionsdienst ein …"
if ! id -u familienplan >/dev/null 2>&1; then
  run_as_root useradd --system --home-dir "$INSTALL_DIR" --shell /usr/sbin/nologin familienplan
fi
if [[ "$PROJECT_DIR" != "$INSTALL_DIR" ]]; then
  run_as_root mkdir -p "$INSTALL_DIR"
  run_as_root cp -a "$PROJECT_DIR/." "$INSTALL_DIR/"
  echo "Erzeuge verschiebbare Python-Umgebung am Produktionspfad …"
  run_as_root python3 -m venv --clear "$INSTALL_DIR/.venv"
  run_as_root "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
  run_as_root "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
fi
run_as_root chown -R root:root "$INSTALL_DIR"
run_as_root chown -R familienplan:familienplan "$INSTALL_DIR/uploads"
run_as_root chown root:familienplan "$INSTALL_DIR/.env"
run_as_root chmod 640 "$INSTALL_DIR/.env"

service_file="$(mktemp)"
cat > "$service_file" <<EOF
[Unit]
Description=FamilienPlan Webanwendung
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=familienplan
Group=familienplan
WorkingDirectory=$INSTALL_DIR/backend
EnvironmentFile=$INSTALL_DIR/.env
Environment=UPLOAD_DIR=$INSTALL_DIR/uploads
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/uploads
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
run_as_root install -m 644 "$service_file" /etc/systemd/system/familienplan.service
rm -f "$service_file"

update_service_file="$(mktemp)"
cat > "$update_service_file" <<EOF
[Unit]
Description=FamilienPlan sicher aktualisieren
After=network-online.target postgresql.service

[Service]
Type=oneshot
User=root
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/usr/bin/rm -f $INSTALL_DIR/uploads/.update-requested
ExecStart=$INSTALL_DIR/scripts/update.sh
TimeoutStartSec=infinity
EOF
run_as_root install -m 644 "$update_service_file" /etc/systemd/system/familienplan-update.service
rm -f "$update_service_file"

update_path_file="$(mktemp)"
cat > "$update_path_file" <<EOF
[Unit]
Description=FamilienPlan Updateanforderung überwachen

[Path]
PathExists=$INSTALL_DIR/uploads/.update-requested
Unit=familienplan-update.service

[Install]
WantedBy=multi-user.target
EOF
run_as_root install -m 644 "$update_path_file" /etc/systemd/system/familienplan-update.path
rm -f "$update_path_file"

# Entfernt ausschließlich die kurzzeitig von Version 0.1.3 angelegte lokale nginx-Site.
if [[ -e /etc/nginx/sites-enabled/familienplan || -e /etc/nginx/sites-available/familienplan ]]; then
  run_as_root rm -f /etc/nginx/sites-enabled/familienplan /etc/nginx/sites-available/familienplan
  if command -v nginx >/dev/null 2>&1 && run_as_root nginx -t; then
    run_as_root systemctl reload nginx
  fi
fi

run_as_root systemctl daemon-reload
run_as_root systemctl enable --now familienplan-update.path
run_as_root systemctl enable --now familienplan
run_as_root systemctl restart familienplan
sleep 2
if ! run_as_root systemctl is-active --quiet familienplan; then
  echo "Fehler: familienplan.service konnte nicht gestartet werden." >&2
  run_as_root systemctl status familienplan --no-pager --full >&2 || true
  run_as_root journalctl -u familienplan -n 50 --no-pager >&2 || true
  exit 1
fi

echo
echo "FamilienPlan wurde erfolgreich installiert."
echo "Dienststatus: systemctl status familienplan"
echo "Aufrufen: $(env_value APP_ORIGIN)"
echo "Zoraxy-Ziel: http://<IP-DIESES-LXC>:8000"
echo "DNS: Die öffentliche Subdomain muss auf die öffentliche IP von Zoraxy zeigen."
