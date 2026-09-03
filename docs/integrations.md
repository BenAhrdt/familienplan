# Integrationen (REST)

Administratoren verwalten SMTP unter **Einstellungen → Integrationen**. API-Schlüssel werden direkt in **Personen → Person bearbeiten** erzeugt und deaktiviert.

## REST API v1

Authentifizierung: `Authorization: Bearer <API-Schlüssel>`.

Jeder Schlüssel ist genau einer Person zugeordnet und übernimmt bei jeder Anfrage deren aktuelle Kinder-, Terminart- und Sichtbarkeitsrechte. Eine spätere Rechteänderung wirkt daher sofort. Pro Person können mehrere benannte Schlüssel angelegt werden, beispielsweise für ioBroker und Home Assistant. Sie lassen sich unabhängig voneinander widerrufen. Der jeweilige geheime Wert wird nur einmal angezeigt.

- `GET /api/v1/integrations/v1/status`
- `GET /api/v1/integrations/v1/children`
- `GET /api/v1/integrations/v1/events?from_at=...&to_at=...&child_id=...`
- `GET /api/v1/integrations/v1/children/{id}/location?at=...`

Jedes Kalenderobjekt enthält ein stabiles `type`-Feld: `stay`, `appointment`,
`birthday`, `school_holiday` oder `school_event`. Der aktuelle Aufenthaltsstatus
verwendet `location_state`. Zeitangaben sind ISO-8601-Werte mit Zeitzone.

Automatisierungen, Vor- und Nachlaufzeiten sowie Benachrichtigungen werden vom angebundenen Client wie einem ioBroker-Adapter aus den abgefragten Kalenderdaten berechnet. FamilienPlan versendet keine Webhooks.
