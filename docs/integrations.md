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

### Namen und Geburtsdatum

Automatisch erzeugte `BIRTHDAY`-Einträge aller drei Quellen liefern zusätzlich
`first_name`, `last_name`, `display_name`, `full_name` und `birth_date`.
`title` bleibt der Anzeigename. `full_name` kombiniert Vor- und Nachnamen und
fällt bei fehlenden Namensbestandteilen auf den Anzeigenamen zurück.
`birth_date` enthält das tatsächliche Geburtsdatum im Format `YYYY-MM-DD`,
während `starts_at` den jeweiligen jährlichen Geburtstag bezeichnet.

Beispiel (weitere Kalenderfelder ausgelassen):

```json
{
  "event_type": "BIRTHDAY",
  "source": "birthday",
  "id": 3,
  "title": "Tom",
  "display_name": "Tom",
  "first_name": "Tom",
  "last_name": "Grywnow",
  "full_name": "Tom Grywnow",
  "birth_date": "2011-09-11",
  "all_day": true,
  "age": 15
}
```

Bestehende, noch nicht umgewandelte gewöhnliche Kalendertermine mit
`event_type: "BIRTHDAY"` können weiterhin ohne diese Zusatzfelder vorkommen.
Sie enthalten kein verlässlich ableitbares Geburtsjahr. Clients müssen fehlende
Felder tolerieren und dürfen das Geburtsjahr nicht aus `starts_at` schätzen.

Neue Geburtstage werden in der Weboberfläche über ein gemeinsames Formular im
Kalender und im Geburtstagsmenü angelegt und jährlich wiederholt. Bestehende
Kalendertermine lassen sich nach Eingabe des echten Geburtsdatums umwandeln;
dabei wird auch eine bestehende Terminserie durch einen Geburtstag ersetzt.
Für schreibende Clients mit Sitzung gilt: neue Geburtstage über `/birthdays`
anlegen. `POST /calendar` akzeptiert keine neuen gewöhnlichen `BIRTHDAY`-Termine.
Die Integrations-API bleibt lesend.

### Offene Anfragen

Die Weboberfläche zeigt offene Betreuungs-, Änderungs-, Löschungs- und
Gruppenanfragen für Antragsteller und Empfänger als vorläufige Einträge mit
Uhrsymbol. Bestätigte Betreuungen bleiben bis zur Entscheidung unverändert.
Diese Vorschauen sind ausschließlich über die interne, sitzungsgebundene
Anfragenverwaltung verfügbar und werden **nicht** über die Integrations-API
oder die Aufenthaltsabfrage ausgegeben. Im Adapter sind hierfür weder ein neuer
Abruf noch neue Datenpunkte erforderlich.
