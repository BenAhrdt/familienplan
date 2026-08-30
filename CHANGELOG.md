# Änderungsprotokoll

Alle wesentlichen Änderungen an FamilienPlan werden hier dokumentiert. Die Versionierung folgt dem Schema MAJOR.MINOR.PATCH.

## 0.1.11 – 30. August 2026

### Einladungsversand

- Das Eintragen einer E-Mail-Adresse versendet die Einladung nicht mehr automatisch.
- Beim Erstellen kann der sofortige Versand ausdrücklich ausgewählt werden.
- Offene Einladungen können später gezielt aus den Personeneigenschaften per E-Mail versendet werden.

## 0.1.10 – 30. August 2026

### Ein-Klick-Aktualisierung

- Administratoren können erkannte Updates direkt über die Versionsanzeige installieren.
- Ein fest definierter systemd-Path-Dienst startet Backup und Update als root, ohne `sudo`, freie Befehle oder Parameter.
- Die Oberfläche wartet während des Neustarts und lädt nach dem erfolgreichen Versionswechsel automatisch neu.

## 0.1.9 – 30. August 2026

### E-Mail-Benachrichtigungen

- Schnell aufeinanderfolgende Planungsbenachrichtigungen an dieselbe Person werden nach zwei Minuten Ruhezeit in einer Mail gebündelt, spätestens jedoch nach zehn Minuten versendet.
- PostgreSQL-Zeilensperren verhindern, dass mehrere Hintergrund-Worker dieselbe Outbox-Nachricht doppelt versenden.
- Testmails bleiben sofortig und gehen weiterhin an die E-Mail-Adresse des angemeldeten Administrators.

## 0.1.8 – 30. August 2026

### Personen und Einladungen

- Eingeladene Personen erscheinen sofort mit dem Status „Einladung ausstehend“ und können bereits in Planungen und Berechtigungen ausgewählt werden.
- Administratoren können den offenen Einladungslink in den Personeneigenschaften erneut kopieren oder sicher erneuern.
- Administratoren können die Ansicht bestätigter Nicht-Admin-Personen übernehmen und über einen auffälligen Hinweis zur eigenen Sitzung zurückkehren; beide Vorgänge werden protokolliert.

## 0.1.7 – 30. August 2026

### Oberfläche und Updates

- Mehr Abstand trennt die einzelnen Karten in den Einstellungen deutlicher.
- HTML und Client-Routen werden mit `no-cache` ausgeliefert; versionsbenannte Assets dürfen langfristig und unveränderlich gecacht werden.

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
