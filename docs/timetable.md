# Stundenpläne

Unter **Personen → Stundenpläne der Kinder** einen Wochenplan manuell erfassen oder ein Bild/PDF hochladen. Der Upload analysiert die Datei lokal und zeigt einen Vorschlag. Erst „Vorschlag zur Bearbeitung übernehmen“ füllt das Formular; erst „Stundenplan speichern“ speichert es. Das Original wird nur temporär zur Analyse verarbeitet, nicht dauerhaft gespeichert. Änderungen am Plan erzeugen keine Kalendertermine.

Leserechte folgen den Kinderfreigaben; Bearbeiten und Hochladen benötigen EDIT für das Kind oder Administratorrechte. Die Übersicht zeigt den aktuellen planmäßigen Status und eine aufklappbare Woche; sie aktualisiert sich alle 15 Sekunden sowie beim Wiederöffnen des Browsertabs.

## API

`GET /api/v1/integrations/v1/children/{child_id}/timetable`

Authentifizierung: `Authorization: Bearer <API-Schlüssel>`. Erforderlicher Scope: `read:children`. Kinderbeschränkungen des Schlüssels und aktuelle Freigaben des Benutzers gelten gemeinsam.

Optional: `?on=2026-09-08` wählt das Datum für `dailySchedule`. `status`, `currentLesson` und `nextLesson` beziehen sich immer auf den aktuellen Zeitpunkt (`evaluatedAt`, `statusDate`), nicht auf das abgefragte Datum. `nextLesson` enthält die nächste Stunde am aktuellen Tag, bei Unterrichtsschluss `null`.

```json
{
  "childId": 1,
  "childName": "Rika",
  "status": "break",
  "statusText": "Pause",
  "evaluatedAt": "2026-09-07T08:47:00+02:00",
  "statusDate": "2026-09-07",
  "date": "2026-09-07",
  "timezone": "Europe/Berlin",
  "currentLesson": null,
  "nextLesson": {"weekday": 0, "start": "08:50", "end": "09:35", "subject": "Deutsch", "room": "102", "teacher": ""},
  "dailySchedule": [
    {"weekday": 0, "start": "08:00", "end": "08:45", "subject": "Mathematik", "room": "204", "teacher": ""},
    {"weekday": 0, "start": "08:50", "end": "09:35", "subject": "Deutsch", "room": "102", "teacher": ""}
  ],
  "weeklySchedule": [],
  "configured": true,
  "basis": "planned"
}
```

`weeklySchedule` enthält alle Wochenstunden (im Beispiel ausgelassen). `plan` liefert zusätzlich `timezone`, `valid_from`, `valid_until`, `days_off` und `lessons`. Wochentage: Montag=0 bis Sonntag=6. Uhrzeiten: `HH:MM` in der Zeitzone des Plans.

| Status | Bedeutung |
| --- | --- |
| `lesson` | Unterricht läuft; Beginn inklusive, Ende exklusive |
| `break` | Lücke zwischen zwei Stunden des heutigen Tages |
| `before_school` | Vor der ersten heutigen Stunde |
| `finished` | Ab Ende der letzten heutigen Stunde |
| `no_school` | Keine Stunden für diesen Wochentag oder expliziter freier Tag |
| `not_configured` | Noch nie ein Stundenplan gespeichert |
| `outside_validity` | Plan gilt am aktuellen Datum noch nicht oder nicht mehr |

Ein bewusst leer gespeicherter Wochenplan bedeutet `no_school`. Gültigkeitsgrenzen gelten einschließlich. Überschneidungen, ungültige Zeiten und leere Fächer werden beim Speichern abgewiesen.

Die Browseroberfläche nutzt mit Sitzung/CSRF `GET` und `PUT /api/v1/children/{id}/timetable` sowie `POST /api/v1/children/{id}/timetable/analyze` (Multipart-Feld `file`). Bearer-Clients verwenden ausschließlich den Integration-Endpunkt.

## Lokale Dateierkennung

Serverpakete auf Debian/Ubuntu:

```sh
sudo apt-get install tesseract-ocr tesseract-ocr-deu tesseract-ocr-eng poppler-utils
```

Der Installer installiert diese Pakete für neue Installationen. Auf bestehenden Installationen vor der Nutzung der Erkennung nachinstallieren. Ohne diese Pakete sind manuelle Bearbeitung und API weiterhin verfügbar; beim Analyseversuch erscheint ein konkreter Hinweis.

Akzeptiert werden PNG, JPEG, WebP und unverschlüsselte PDFs (höchstens 10 MB, PDF höchstens 3 Seiten). Die Erkennung unterstützt Tabellen mit Wochentagen als Spalten und expliziten Von-/Bis-Uhrzeiten links. OCR ist ungenau: alle Ergebnisse müssen geprüft werden. Reine Stundennummern ohne Zeiten, ungewöhnliche Layouts und mehrwöchige/A-/B-Pläne werden nicht automatisch zuverlässig zugeordnet. Ohne erkennbares Layout bleibt die Vorschlagsliste leer; Vorlage und erkannter Text helfen beim manuellen Eintragen. Raum/Lehrkraft können im erkannten Fachtext stehen und sind dann manuell zuzuordnen.

Ferien, Feiertage und Vertretungen werden nicht automatisch übernommen. Unterrichtsfreie Tage können im Plan hinterlegt werden. Der Plan beschreibt die reguläre Woche, keine Live-Auskunft der Schule.
