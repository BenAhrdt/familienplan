# FamilienPlan

FamilienPlan ist eine selbst gehostete, deutschsprachige Webanwendung für gemeinsame Familienorganisation. Der erste Meilenstein enthält ein PostgreSQL-basiertes FastAPI-Fundament, Alembic-Migrationen, sichere Ersteinrichtung und Anmeldung, Einladungen, Rollen, Kinderberechtigungen, Aufenthalte samt Konfliktprüfung sowie eine responsive React-Oberfläche.

Aktuelle Version: **0.1.9** · [Änderungsprotokoll](CHANGELOG.md) · [MIT-Lizenz](LICENSE)

## Geführte Ein-Befehl-Installation

Der Installer unterstützt Debian und Ubuntu. Er installiert die benötigten Systempakete einschließlich PostgreSQL, richtet Datenbank und Datenbankbenutzer ein, erzeugt sichere Zufallswerte für Datenbankpasswort und `SECRET_KEY`, fragt die öffentliche Basisadresse ab, baut die Anwendung und richtet einen automatisch startenden `familienplan.service` ein. Benötigt werden lediglich `root`-Rechte oder ein Benutzer mit funktionierendem `sudo`.

```bash
git clone https://github.com/BenAhrdt/familienplan.git
cd familienplan
./scripts/install.sh
```

Bei einer HTTPS-Adresse setzt der Installer automatisch den Produktivmodus und sichere Sitzungscookies. Einstellungen wie SMTP werden später in der Weboberfläche vorgenommen. Eine vorhandene vollständige `.env` kann bei einem erneuten Aufruf beibehalten werden. Liefert das Betriebssystem eine zu alte Node.js-Version, richtet der Installer das signierte NodeSource-Repository für Node.js 22 LTS ein.

### DNS, Zoraxy und HTTPS

Lege für die eingegebene Subdomain einen DNS-Record an: `A` zeigt auf die öffentliche IPv4-Adresse von Zoraxy, `AAAA` nur bei tatsächlich erreichbarer IPv6-Adresse. In Zoraxy wird ein Proxy-Eintrag für die öffentliche Subdomain angelegt. Als Upstream beziehungsweise Proxy-Ziel dient `http://IP-DES-FAMILIENPLAN-LXC:8000`. HTTPS/TLS wird in Zoraxy für diese Subdomain aktiviert. FamilienPlan liefert Frontend und API gemeinsam über Port 8000 aus; ein zusätzlicher nginx im LXC ist nicht erforderlich.

Der Anwendungsdienst startet nach einem Neustart automatisch. Status und Protokoll lassen sich so prüfen:

```bash
systemctl status familienplan
journalctl -u familienplan -n 100 --no-pager
```

## Aktualisieren

Updates werden ausschließlich aus versionierten GitHub-Releases installiert. Das Skript bricht bei lokalen Änderungen ab, erstellt zuerst ein vollständiges Backup, aktualisiert Abhängigkeiten und Frontend, führt anschließend Alembic-Migrationen aus und startet einen aktiven `familienplan.service` neu.

```bash
cd familienplan
./scripts/update.sh
```

Vor einem produktiven Update sollte das erzeugte Backup zusätzlich auf ein getrenntes, verschlüsseltes Medium kopiert werden. Release-Hinweise und mögliche besondere Migrationsschritte stehen im [Änderungsprotokoll](CHANGELOG.md).

Damit die Anwendung verfügbare Updates in den Einstellungen anzeigen kann, muss nach Erstellung des öffentlichen Repositorys Folgendes in `.env` stehen:

```env
GITHUB_REPOSITORY=BenAhrdt/familienplan
```

Die Prüfung erfolgt höchstens einmal pro Stunde gegen das neueste veröffentlichte GitHub-Release. Es werden keine Updates automatisch installiert.

## Architektur und Sicherheitsentscheidungen

- Backend: Python 3.13, FastAPI, SQLAlchemy 2, Psycopg 3
- Frontend: React, TypeScript und Vite; statischer Produktions-Build
- ausschließlich PostgreSQL in Entwicklung und Produktion; eine SQLite-URL wird beim Start abgelehnt
- reproduzierbares Schema über Alembic, kein `create_all()` beim App-Start
- Argon2id-Passwort-Hashes; Sitzungs-, Einladungs- und API-Tokens werden nur gehasht gespeichert
- serverseitige, widerrufbare Sessions in HttpOnly-/SameSite-Cookies; Secure-Cookie in Produktion
- CSRF-Prüfung für zustandsändernde Cookie-Anfragen
- rollenbasierte und zusätzlich kindbezogene Rechteprüfung im Backend
- Initial-Admin durch PostgreSQL-Tabellensperre gegen parallele Registrierung geschützt
- Audit-Log ohne Secrets; PostgreSQL-Constraints und serverseitige Konfliktprüfung
- keine Tracker, externen Fonts oder Cloud-Pflicht

Das relationale Modell umfasst Benutzer, Sessions, Einladungen, Kinder und deren Berechtigungen, Kalenderquellen/-termine, Aufenthalte und Serien, Ferienperioden/-pläne/-segmente, Änderungsanfragen und Zustimmungen, Benachrichtigungen, API-Tokens, Audit-Logs sowie Systemeinstellungen. Kalenderquellen werden passend zu den tatsächlich gewählten Einrichtungen angelegt; produktive Abrufadapter und die vollständigen Planungsworkflows sind noch auszubauen.

## PostgreSQL manuell einrichten

Dieser Abschnitt ist nur für eine bewusst manuelle Installation oder für Systeme außerhalb von Debian und Ubuntu erforderlich. Ersetze das Passwort durch die Ausgabe von `openssl rand -hex 24`:

```bash
apt update
apt install -y postgresql postgresql-client python3-venv
systemctl enable --now postgresql
sudo -u postgres psql <<'SQL'
CREATE ROLE familienplan LOGIN PASSWORD 'HIER_SICHERES_PASSWORT_EINSETZEN' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE DATABASE familienplan OWNER familienplan ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE familienplan FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE familienplan TO familienplan;
SQL
pg_isready
```

Der App-Benutzer besitzt die Datenbank, aber keine Cluster-Superuser-, Rollen- oder Datenbank-Erstellrechte. Das Eigentum ist nötig, damit Alembic das Anwendungsschema verwalten kann.

## Manuelle Installation und Entwicklung

```bash
cp .env.example .env
openssl rand -hex 32
# SECRET_KEY und das zuvor erzeugte DB-Passwort ausschließlich in .env eintragen
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/uvicorn app.main:app --reload
```

Danach lassen sich Backend und Frontend gemeinsam aus dem Projektordner starten:

```bash
./start.sh
# alternativ: npm run dev oder npm start
```

Das Startskript führt ausstehende Datenbankmigrationen aus, startet beide Entwicklungsserver und beendet beide wieder mit `Strg+C`. Für die einmalige Installation der Frontend-Abhängigkeiten weiterhin `cd frontend && npm install` verwenden.

Die Oberfläche läuft unter `http://localhost:5173`. Beim ersten Aufruf erscheint ausschließlich der geschützte Setup-Assistent. Nach Anlage des ersten Admins wird dieser Endpunkt dauerhaft geschlossen. Die API liegt unter `/api/v1/`, die lokale API-Dokumentation unter `http://127.0.0.1:8000/api/docs`.

`DATABASE_URL` hat dieses Format:

```env
DATABASE_URL=postgresql+psycopg://familienplan:URL_ENCODED_PASSWORD@127.0.0.1:5432/familienplan
```

Sonderzeichen im Passwort müssen URL-kodiert werden. `.env` ist durch `.gitignore` ausgeschlossen und muss Modus `0600` besitzen: `chmod 600 .env`.

## Migrationen und Initialisierung

```bash
cd backend
../.venv/bin/alembic current
../.venv/bin/alembic upgrade head
../.venv/bin/alembic revision --autogenerate -m "kurze beschreibung"
../.venv/bin/alembic downgrade -1
```

Jede Modelländerung benötigt eine geprüfte Migration. In Produktion wird `alembic upgrade head` vor dem Dienstneustart ausgeführt. Tabellen werden nie implizit beim App-Start erzeugt.

## Datenbank-Health-Check

`GET /api/v1/health` führt `SELECT 1` gegen PostgreSQL aus. Erfolgreich antwortet er mit HTTP 200 und `{"status":"ok","database":"postgresql","connected":true}`; bei einem Verbindungsfehler mit HTTP 503. Für Monitoring:

```bash
./scripts/healthcheck.sh
```

## Tests

```bash
cd backend
../.venv/bin/python -m pytest -q
cd ../frontend
npm run build
```

Die vorhandenen Tests sichern PostgreSQL-only-Konfiguration, Argon2id und Token-Hashing ab. API-Integrationstests für Setup, Login, Einladungen, Rechte, Konflikte, Zustimmung, Ferienplanung und Import-Deduplizierung sind im nächsten Ausbauschritt gegen eine eigene PostgreSQL-Testdatenbank zu ergänzen; SQLite darf auch dort nicht verwendet werden.

## E-Mail und Kalenderimporte

SMTP wird ausschließlich über die `SMTP_*`-Variablen in `.env` konfiguriert. Solange kein SMTP-Worker implementiert ist, zeigt die Admin-API den Einladungslink genau bei der Erstellung an; in der Datenbank liegt nur sein SHA-256-Hash. Produktiv sollte die Ausgabe durch einen Hintergrundjob mit Retry-/Fehlerprotokoll ersetzt werden.

Bei der Anlage und Bearbeitung eines Kindes können Schule und Betreuung anhand von Name und Ort gesucht werden. FamilienPlan übernimmt die öffentlich bekannte Homepage und erkennt dort verlinkte Kalenderseiten beziehungsweise ICS-Quellen. Strukturierte ICS-/JSON-/WordPress-Endpunkte sind vor HTML-Scraping zu bevorzugen. Der eigentliche Scheduler und die Importadapter gehören noch zu den bekannten Einschränkungen dieses Fundaments.

## Produktionsbetrieb

1. Projekt nach `/opt/familienplan` kopieren und eigenen Systembenutzer `familienplan` verwenden.
2. Python-Umgebung installieren, Migrationen ausführen und `frontend` mit `npm ci && npm run build` bauen.
3. `.env` als `familienplan:familienplan`, Modus `0600`, ablegen; in Produktion `APP_ENV=production`, korrekte HTTPS-Origin und `SESSION_COOKIE_SECURE=true` setzen.
4. [deploy/familienplan.service](deploy/familienplan.service) nach `/etc/systemd/system/` übernehmen.
5. `systemctl daemon-reload && systemctl enable --now familienplan`; Zoraxy auf `http://IP-DES-LXC:8000` weiterleiten lassen und dort TLS aktivieren.

Der Anwendungsprozess lauscht für Zoraxy auf Port 8000 im LXC-Netz. Dieser Port sollte per Firewall nur aus dem vertrauenswürdigen internen Netz erreichbar sein. Schreibzugriff erhält der gehärtete Dienst ausschließlich auf `uploads`; öffentlich erfolgt der Zugriff ausschließlich per HTTPS über Zoraxy.

## Backup und Restore

Ein Backup umfasst PostgreSQL per `pg_dump`, die lokale Konfiguration und Uploads. Zielmedium verschlüsseln, restriktiv berechtigen, räumlich getrennt aufbewahren und Aufbewahrungsfristen definieren. `.env` enthält Secrets und darf weder öffentlich noch in Git oder unverschlüsselt in externen Speicher gelangen.

```bash
chmod +x scripts/*.sh
BACKUP_DIR=/sicheres/verschluesseltes/ziel ./scripts/backup.sh
./scripts/restore.sh /sicheres/verschluesseltes/ziel/familienplan-YYYYMMDDTHHMMSSZ
```

Das Skript erzeugt einen Custom-Format-Dump, eine geschützte Konfigurationskopie, ein Upload-Archiv und Prüfsummen. Ein Restore überschreibt Daten und sollte zuerst in einer separaten Restore-Datenbank geprobt werden. Backup und Restore regelmäßig automatisiert testen.

## REST-API

Die Weboberfläche verwendet dieselbe API unter `/api/v1/`. Vorhanden sind Health, Setup, Login/Logout/Session, Admin-Benutzerliste, Einladungen, Kinder, Kindberechtigungen, Aufenthalte und `GET /children/{id}/location/today`. Externe Clients erhalten später widerrufbare, gehashte API-Tokens mit Scopes; das Schema ist bereits vorhanden.

## Bekannte Einschränkungen

Die erste Version ist für selbst gehostete Installationen gedacht. Vor einem Einsatz mit vielen Familien oder öffentlich erreichbaren Registrierungen sollten insbesondere vollständige PostgreSQL-Integrationstests, automatisierte Wiederherstellungstests, Rate-Limits und ein externer Sicherheitsreview ergänzt werden.
