# Änderungsprotokoll

Alle wesentlichen Änderungen an FamilienPlan werden hier dokumentiert. Die Versionierung folgt dem Schema MAJOR.MINOR.PATCH.

## 0.1.25 – 30. August 2026

### Terminfreigaben und offene Einladungen

- Nicht freigegebene Terminarten werden serverseitig aus Kalenderdaten, Aufenthalten und Geburtstagen entfernt.
- Die Kalenderfilter zeigen einer Person nur die für sie freigeschalteten Terminarten.
- Rubriken für Geburtstage und Abfallkalender benötigen zusätzlich die entsprechende Terminfreigabe.
- Administratoren können die E-Mail-Adresse einer noch nicht registrierten Person ergänzen, ändern oder entfernen.
- Benutzername und Passwort werden weiterhin erst von der eingeladenen Person festgelegt.

## 0.1.24 – 30. August 2026

### Einheitliche Dialoge

- Der Einladungsversand bestätigt die Warteschlange in einem eigenen FamilienPlan-Dialog.
- Das Übernehmen der Ansicht einer anderen Person verwendet einen eigenen Bestätigungsdialog.
- Die Oberfläche enthält keine nativen Browserdialoge über `alert`, `confirm` oder `prompt` mehr.

## 0.1.23 – 30. August 2026

### Synchronisierung und Aktualisierung der Ansichten

- Jede unterstützte externe Kalenderquelle kann in den Admin-Einstellungen einzeln manuell synchronisiert werden.
- Ladezustand, Ergebnis, Fehler und neuer Synchronisationszeitpunkt erscheinen unmittelbar in der Quellenübersicht.
- Erfolgreiche Schreibaktionen lösen appweit eine Aktualisierung abhängiger Daten aus.
- Die geöffnete Kalenderansicht übernimmt Änderungen ohne manuellen Browser-Refresh.

## 0.1.22 – 30. August 2026

### Schreibgeschützte Kalendereinträge

- Ferien öffnen nicht länger versehentlich den Dialog zum Anlegen eines Termins.
- Automatische Geburtstage, Ferien sowie importierte Schul- und Abfalltermine zeigen beim Anklicken einen eigenen Hinweisdialog.
- Der Hinweis erklärt die Herkunft und wo der jeweilige Eintrag geändert werden kann.

## 0.1.21 – 30. August 2026

### Kalenderfilter

- Das Ausblenden von „Aufenthalt“ entfernt nun sowohl geplante als auch täglich vorbelegte Aufenthaltsanzeigen.
- Das Ausblenden von „Geburtstag“ entfernt auch automatisch erzeugte Kinder-, Personen- und private Geburtstage.

## 0.1.20 – 30. August 2026

### Synchronisationsübersicht

- Die Gesamtübersicht aller externen Kalenderquellen befindet sich nun als eigener Admin-Bereich „Externe Kalender“ in den Einstellungen.
- Der Abfallkalender zeigt nur noch den Status seiner eigenen Quelle und die manuell angelegten Abholtermine.

## 0.1.19 – 30. August 2026

### Serienausnahmen und Kalenderanzeige

- Bewusst verschobene Einzeltermine einer Aufenthaltsserie werden als Ausnahmen mit ihrem ursprünglichen Serientermin gespeichert.
- Eine spätere Bearbeitung der gesamten Serie erzeugt am ursprünglichen Datum einer verschobenen Ausnahme keinen neuen Doppeltermin.
- Der sichtbare Zusatz „Privat“ wurde aus Kalenderterminen und Geburtstagen entfernt; die Zugriffsbeschränkung bleibt unverändert wirksam.

## 0.1.18 – 30. August 2026

### Abfallkalender und Kalenderquellen

- Der automatische Abfallkalender gleicht Änderungen und Löschungen vollständig mit der Onlinequelle ab; manuelle Termine bleiben unberührt.
- Importierte Abfuhrtermine erscheinen nicht mehr als lange Terminliste im Verwaltungsbereich.
- Bioabfall, Gelbe Tonne, Restabfall, Altpapier, Schadstoffe und sonstige Abfälle erhalten einzeln einstellbare Farben.
- Tage mit Abfuhrterminen verwenden die persönliche Grundfarbe; der jeweilige Eintrag wird mit der Farbe seiner Abfallart markiert.
- Administratoren sehen den letzten Synchronisationszeitpunkt und Fehler aller Schul-, Abfall- und zukünftigen Kalenderquellen in einer Übersicht.
- Terminarten können im Monatskalender einzeln ein- und ausgeblendet werden; die Auswahl bleibt im Browser gespeichert.
- Die Bezeichnung „Müllabfuhr“ wurde appweit durch „Abfallkalender“ ersetzt.

## 0.1.17 – 30. August 2026

### Aktualisierungen

- Der Ein-Klick-Updater schreibt seine Anforderung zuverlässig in das freigegebene Upload-Verzeichnis, auch wenn in älteren Installationen ein relativer Pfad hinterlegt ist.
- Neuinstallationen speichern den Upload-Pfad direkt als absoluten Installationspfad.
- Eine PostgreSQL-Sperre verhindert, dass parallele Webworker dieselbe Abfallkalender-Quelle gleichzeitig anlegen.

## 0.1.16 – 30. August 2026

### Aktualisierungen

- Administratoren können unter Einstellungen unabhängig vom einstündigen Cache sofort nach neuen Releases suchen.
- Nach dem Start eines Updates zeigt FamilienPlan einen 30-sekündigen Countdown für Backup, Installation und fünf Sekunden Reserve.
- Ein früher erkannter Versionswechsel lädt die Anwendung sofort neu; andernfalls erfolgt das Neuladen nach Ablauf des Countdowns.

## 0.1.15 – 30. August 2026

### Automatische Synchronisierung

- Schulkalender werden beim Anwendungsstart geprüft und anschließend spätestens alle sechs Stunden synchronisiert.
- Ein PostgreSQL-Sperrmechanismus verhindert doppelte Synchronisierung durch mehrere Webworker.
- Fehlgeschlagene oder ungültige Abrufe verändern keine vorhandenen Schultermine.

### Persönliche Kalenderfarben

- Am automatischen Abfallkalender kann eine Standardfarbe für importierte Abfuhrtermine gewählt werden.
- Jeder Benutzer kann Schule, Ferien und freigegebene Rubriken in persönlichen Farben darstellen.
- Farben für Geburtstage und Müllabfuhr werden nur angeboten, wenn die jeweilige Rubrik sichtbar ist.

## 0.1.14 – 30. August 2026

### Schulkalender

- Erfolgreiche Synchronisierungen entfernen automatisch importierte Termine, die nicht mehr in der Schulquelle vorhanden sind.
- Termine anderer Klassen werden bereits beim Import verworfen und aus vorhandenen Datenbeständen bereinigt.
- Die globale Suche verwendet denselben Klassenfilter wie der Kalender.
- Manuell angelegte Schultermine bleiben von Import und Bereinigung unberührt; mögliche manuelle/importierte Dubletten werden gekennzeichnet.

### Mobile Bedienung und Einladungen

- Einladungslinks liefern zuverlässig die Annahmeseite der Anwendung aus.
- Die mobile Kopfzeile enthält eine direkt erreichbare Abmeldefunktion.
- Der Monatskalender zeigt auf kleinen Bildschirmen alle sieben Wochentage ohne horizontales Abschneiden.

## 0.1.13 – 30. August 2026

### Automatischer Abfallkalender

- AWIDO-Abfuhrtermine können anhand von Anbieterkennung, Gemeinde und Ortsteil automatisch übernommen werden; Hohenahr-Ahrdt ist direkt vorkonfiguriert.
- Alternativ lassen sich beliebige iCal- und WebCal-Quellen anbinden.
- FamilienPlan synchronisiert täglich das aktuelle und kommende Jahr, vermeidet doppelte Termine und übernimmt neu veröffentlichte Jahrespläne automatisch.
- Importierte Abholtermine können gezielt für ausgewählte Personen freigegeben werden.

### Oberfläche

- Die Updatebestätigung sowie Updatefehler werden in eigenen FamilienPlan-Dialogen statt in Browser-Pop-ups angezeigt.

## 0.1.12 – 30. August 2026

### Schulkalender

- Ganztägige ICS-Termine werden in der Anwendungszeitzone statt als UTC-Mitternacht importiert.
- Exklusive Enddaten laufen dadurch nicht mehr fälschlich in den Folgetag hinein.
- Die inklusive Datumsanzeige bleibt auch an Sommerzeitwechseln korrekt.

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
