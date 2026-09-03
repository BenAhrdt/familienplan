# Integrationen (REST)

Administratoren verwalten SMTP unter **Einstellungen → Integrationen**. API-Schlüssel werden direkt in **Personen → Person bearbeiten** erzeugt und deaktiviert.

## REST API v1

Authentifizierung: `Authorization: Bearer <API-Schlüssel>`.

Jeder Schlüssel ist genau einer Person zugeordnet und übernimmt bei jeder Anfrage deren aktuelle Kinder-, Terminart- und Sichtbarkeitsrechte. Eine spätere Rechteänderung wirkt daher sofort. Pro Person können mehrere benannte Schlüssel angelegt werden, beispielsweise für ioBroker und Home Assistant. Sie lassen sich unabhängig voneinander widerrufen. Der jeweilige geheime Wert wird nur einmal angezeigt.

- `GET /api/v1/integrations/v1/status`
- `GET /api/v1/integrations/v1/children`
- `GET /api/v1/integrations/v1/events?from_at=...&to_at=...&child_id=...`
- `GET /api/v1/integrations/v1/children/{id}/location?at=...`

Jedes Kalenderobjekt enthält ein `event_type`-Feld, beispielsweise `GENERAL`,
`STAY`, `BIRTHDAY`, `SCHOOL` oder `SCHOOL_HOLIDAY`. Das redundante `type`-Feld
wird nicht ausgegeben. Betreuungen enthalten zusätzlich `responsible_user_id`,
`source` (`stay` oder `default`) und `generated`. Standardbetreuungen aus
„Wohnt bei“ werden für alle Lücken ohne explizite Betreuung als erzeugte
`STAY`-Zeiträume ausgegeben; ihre `id` ist `null`. Zeitangaben sind
ISO-8601-Werte mit Zeitzone.

Automatisierungen, Vor- und Nachlaufzeiten sowie Benachrichtigungen werden vom angebundenen Client wie einem ioBroker-Adapter aus den abgefragten Kalenderdaten berechnet. FamilienPlan versendet keine Webhooks.
