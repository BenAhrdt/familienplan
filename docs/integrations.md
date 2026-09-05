# Integrationen (REST)

Administratoren verwalten SMTP unter **Einstellungen → Integrationen**. API-Schlüssel werden direkt in **Personen → Person bearbeiten** erzeugt und deaktiviert.

## REST API v1

Authentifizierung: `Authorization: Bearer <API-Schlüssel>`.

Jeder Schlüssel ist genau einer Person zugeordnet und übernimmt bei jeder Anfrage deren aktuelle Kinder-, Terminart- und Sichtbarkeitsrechte. Eine spätere Rechteänderung wirkt daher sofort. Pro Person können mehrere benannte Schlüssel angelegt werden, beispielsweise für ioBroker und Home Assistant. Sie lassen sich unabhängig voneinander widerrufen. Der jeweilige geheime Wert wird nur einmal angezeigt.

- `GET /api/v1/integrations/v1/status`
- `GET /api/v1/integrations/v1/children`
- `GET /api/v1/integrations/v1/calendar?from_at=...&to_at=...&child_id=...`
- `GET /api/v1/integrations/v1/children/{id}/location?at=...`

Jedes Kalenderobjekt enthält ein `event_type`-Feld, beispielsweise `GENERAL`,
`STAY`, `BIRTHDAY`, `SCHOOL` oder `SCHOOL_HOLIDAY`. Das redundante `type`-Feld
wird nicht ausgegeben. Betreuungen enthalten zusätzlich `responsible_user_id`,
`source` (`stay` oder `default`) und `generated`. Standardbetreuungen aus
„Wohnt bei“ werden für alle Lücken ohne explizite Betreuung als erzeugte
`STAY`-Zeiträume ausgegeben; ihre `id` ist `null`. Zeitangaben sind
ISO-8601-Werte mit Zeitzone.

Automatisierungen, Vor- und Nachlaufzeiten sowie Benachrichtigungen werden vom angebundenen Client wie einem ioBroker-Adapter aus den abgefragten Kalenderdaten berechnet. FamilienPlan versendet keine Webhooks.

## Titel und Notizen

Betreuungen und reguläre Kalendertermine liefern `title` und `description`.
Bei Betreuungen enthält `description` die Notizen (oder `null`). `title`
enthält den eigenen Titel; ohne Titel wird „Emma bei Papa“ aus den Namen
des Kindes und der Betreuungsperson gebildet. Bestehende Notizen bleiben erhalten
und werden nicht mehr als Titel ausgegeben. Clients, die bisher die Notiz aus
`title` gelesen haben, müssen dafür künftig `description` verwenden.

Erzeugte Standardbetreuungen haben beispielsweise `title: "(Standard) Emma bei Papa"`
und `description: null`. Der bisherige Pfad `/events` bleibt als Alias verfügbar.

## Geburtstage

`/children` liefert mit `read:children` zusätzlich das Feld `birth_date` je
freigegebenem Kind: das Geburtsdatum als `YYYY-MM-DD` oder `null`, wenn keines
hinterlegt ist.

Mit `read:birthdays` liefert `/calendar` (ebenso `/events`) sowohl separat erfasste
Geburtstage als auch die Geburtsdaten aktiver, freigegebener Kinder und sichtbarer
aktiver Personen. Alle erscheinen als ganztägige Kalendereinträge mit
`event_type: "BIRTHDAY"`, `all_day: true` und `age` (Alter am Geburtstag).
Die Terminart muss für die Person freigeschaltet sein; private Geburtstage
benötigen zusätzlich `read:private` und die entsprechende Sichtbarkeit.

`source` unterscheidet `birthday`, `child` und `person`. Separat erfasste
Geburtstage behalten ihre numerische `id`; erzeugte Einträge verwenden
`child:<ID>` beziehungsweise `person:<ID>`, damit sich die IDs nicht überschneiden.
Zusätzlich enthalten sie `child_id` beziehungsweise `user_id`.
Ein `child_id`-Filter schränkt Kindergeburtstage ein; sichtbare Personen und
separat erfasste Geburtstage bleiben wie sonstige kinderunabhängige Termine enthalten.
Am 29. Februar Geborene erscheinen in Nicht-Schaltjahren am 28. Februar.
