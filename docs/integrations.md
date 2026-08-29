# Integrationen (REST und Webhooks)

Administratoren verwalten API-Schlüssel, Webhooks und SMTP unter **Einstellungen → Integrationen**.

## REST API v1

Authentifizierung: `Authorization: Bearer <API-Schlüssel>`.

- `GET /api/v1/integrations/v1/status`
- `GET /api/v1/integrations/v1/children`
- `GET /api/v1/integrations/v1/events?from_at=...&to_at=...&child_id=...`
- `GET /api/v1/integrations/v1/children/{id}/location?at=...`

Jedes Kalenderobjekt enthält ein stabiles `type`-Feld: `stay`, `appointment`,
`birthday`, `school_holiday` oder `school_event`. Der aktuelle Aufenthaltsstatus
verwendet `location_state`. Zeitangaben sind ISO-8601-Werte mit Zeitzone.

## Webhooks

Der Server sendet JSON per POST. Relevante Ereignisse sind unter anderem
`notification.created`, `stay.started`, `stay.ended`, `appointment.started`,
`school_event.started` und `school_holiday.started`.

Die Signatur steht in `X-FamilienPlan-Signature` als `sha256=<hex>` und ist ein
HMAC-SHA256 über den unveränderten Request-Body. Fehlgeschlagene Zustellungen
werden mit wachsendem Abstand bis zu achtmal versucht.

Private Termine werden nicht als zeitgesteuerte Webhooks versendet. In der REST-
API sind sie nur mit dem expliziten Recht `read:private` sichtbar.
