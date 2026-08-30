# Änderungsprotokoll

Alle wesentlichen Änderungen an FamilienPlan werden hier dokumentiert. Die Versionierung folgt dem Schema MAJOR.MINOR.PATCH.

## 0.1.6 – 30. August 2026

### Dienststart

- Die virtuelle Python-Umgebung wird am endgültigen Produktionspfad neu erstellt, statt mit ungültigen absoluten Pfaden kopiert zu werden.
- Der Installer prüft nach dem Neustart, ob `familienplan.service` tatsächlich aktiv ist, und zeigt bei Fehlern Status und Protokoll an.

## 0.1.5 – 30. August 2026

### Installation

- Der irreführende Entwicklungsstandard `http://localhost:5173` wurde aus der Produktionsinstallation entfernt.
- Die öffentliche Adresse wird nun als vollständige HTTP(S)-URL abgefragt und validiert.

## 0.1.4 – 30. August 2026

### Reverse Proxy

- FamilienPlan liefert Produktionsfrontend und API gemeinsam über Port 8000 aus.
- Der systemd-Dienst ist im LXC-Netz direkt für Zoraxy erreichbar; ein zusätzlicher nginx entfällt.
- Dokumentation und Abschlussmeldung nennen das korrekte Zoraxy-Ziel.

## 0.1.3 – 30. August 2026

### Produktionsbetrieb

- Der Installer richtet die Anwendung unter `/opt/familienplan` ein und erstellt einen gehärteten, automatisch startenden systemd-Dienst.
- nginx wird installiert, für die gewählte Subdomain konfiguriert und beim Systemstart aktiviert.
- Abschlussmeldung und Dokumentation erklären DNS-Ziel, Reverse-Proxy-Port und HTTPS-Verantwortung.

## 0.1.2 – 30. August 2026

### Installation

- Überflüssige SMTP-Abfragen aus dem Installer entfernt; die Mailkonfiguration erfolgt später in der Weboberfläche.
- Der Installer fragt bei einer neuen Einrichtung nur noch die öffentliche Basisadresse ab.

## 0.1.1 – 30. August 2026

### Installation

- Geführte Ein-Befehl-Installation für Debian und Ubuntu.
- Automatische Installation und Einrichtung von PostgreSQL sowie Node.js 22 LTS bei Bedarf.
- Sichere automatische Erzeugung von Datenbankpasswort und `SECRET_KEY`.
- Interaktive Erstellung der geschützten `.env` einschließlich optionaler SMTP-Konfiguration.
- Korrigierter Testaufruf in der Dokumentation.

## 0.1.0 – 29. August 2026

### Erste öffentliche Version

- Gemeinsamer Familienkalender mit Terminen, Serien und individuellen Sichtbarkeiten.
- Terminarten Aufenthalt, Allgemein, Geburtstag, Müllabfuhr, Putzfrau, Schule und Sonstiges.
- Automatisch erzeugte Geburtstage für Kinder, Benutzer und weitere Personen.
- Aufenthaltsplanung mit wiederkehrenden Terminen und Zuordnung zu Bezugspersonen.
- Schulkalender-Import mit Filterung nach der beim Kind hinterlegten Klasse.
- Eigene Rubriken für Geburtstage und Müllabfuhr mit administrierbaren Benutzerfreigaben.
- Ferien und Feiertage sowie eine gemeinsame Ferienplanung.
- Benutzer-, Rollen-, Kinder- und Terminartberechtigungen.
- Individuelle Farben für Benutzer sowie globale Farben für Ferien, Geburtstage und Schule.
- REST-API-Schlüssel, signierte Webhooks und E-Mail-Konfiguration.
- PostgreSQL-Datenbank, Alembic-Migrationen, Argon2id-Passwort-Hashes und serverseitige Sitzungen.
- Backup-, Restore-, Installations- und Update-Skripte für den selbst gehosteten Betrieb.
