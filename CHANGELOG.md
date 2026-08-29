# Änderungsprotokoll

Alle wesentlichen Änderungen an FamilienPlan werden hier dokumentiert. Die Versionierung folgt dem Schema MAJOR.MINOR.PATCH.

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
