# Stundenpläne

Unter **Kinder → beim jeweiligen Kind → Stundenplan** den Wochenplan erfassen. Einzelne Stunden lassen sich in den nächsten freien Zeitraum desselben Tages duplizieren. Ganze Tage können auf einen anderen Wochentag kopiert werden; vorhandene Stunden bleiben erhalten, Überschneidungen werden abgewiesen. Jede Stunde hat eine frei wählbare Farbe. Änderungen werden erst mit „Stundenplan speichern“ gespeichert und erzeugen keine Kalendertermine.

Leserechte folgen den Kinderfreigaben; Bearbeiten benötigt EDIT für das Kind oder Administratorrechte. Die Übersicht zeigt die Lehrkraft beim laufenden Unterricht und eine aufklappbare Woche; sie aktualisiert sich alle 15 Sekunden sowie beim Wiederöffnen des Browsertabs.

Der Bild-/PDF-Upload wurde entfernt, da die lokale Erkennung fotografierte Stundenpläne nicht zuverlässig zuordnet. OCR-Pakete sind nicht mehr erforderlich.

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

`weeklySchedule` enthält alle Wochenstunden (im Beispiel ausgelassen). `plan` liefert zusätzlich `timezone`, `valid_from`, `valid_until`, `days_off` und `lessons`. Jede Stunde enthält `color` als Hex-Farbe (`#RRGGBB`, Standard für bestehende Stunden: `#3979b8`). Wochentage: Montag=0 bis Sonntag=6. Uhrzeiten: `HH:MM` in der Zeitzone des Plans.

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

Die Browseroberfläche nutzt mit Sitzung/CSRF `GET` und `PUT /api/v1/children/{id}/timetable`. Bearer-Clients verwenden ausschließlich den Integration-Endpunkt.

Ferien, Feiertage und Vertretungen werden nicht automatisch übernommen. Unterrichtsfreie Tage können im Plan hinterlegt werden. Der Plan beschreibt die reguläre Woche, keine Live-Auskunft der Schule.
