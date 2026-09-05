Passe den ioBroker-Adapter an FamilienPlan 0.1.100 an und setze die Änderungen samt Tests und Dokumentation um.

Die Integrations-API liefert unter GET /api/v1/integrations/v1/calendar (Alias /events) für automatisch erzeugte Geburtstage zusätzliche Felder:
- event_type: "BIRTHDAY"
- source: "birthday", "child" oder "person"
- first_name, last_name, display_name, full_name
- birth_date: tatsächliches Geburtsdatum als "YYYY-MM-DD"
- title: weiterhin der gewählte Anzeigename
- starts_at, ends_at: jährliches Vorkommen, all_day: true
- age: Alter an diesem Geburtstag

Beispiel: title und display_name sind "Tom", first_name ist "Tom", last_name ist "Grywnow", full_name ist "Tom Grywnow", birth_date ist "2011-09-11".

Aufgaben:
1. Übernimm die neuen Felder in die Geburtstagsdaten und Datenpunkte. Verwende für den vollständigen Namen (z. B. das bisherige Feld name) bevorzugt full_name; fallback: Vor- und Nachname, display_name, title. Bewahre den vom Server gelieferten title/Anzeigenamen separat.
2. Zeige Geburtstage aller drei Quellen sowohl in der Kalenderverarbeitung als auch in den Geburtstags-Datenpunkten an.
3. IDs unterstützen Zahlen und Strings: separat erfasste Geburtstage behalten numerische IDs; Kindergeburtstage haben "child:<ID>", Personengeburtstage "person:<ID>". Dazu kommen child_id bzw. user_id. Identifiziere einzelne jährliche Vorkommen zusätzlich über starts_at.
4. /api/v1/integrations/v1/children liefert seit 0.1.99 birth_date als "YYYY-MM-DD" oder null. Beibehalten. Erzeuge keine doppelten Kalendergeburtstage aus diesen Stammdaten, wenn der Server den Geburtstag bereits liefert.
5. Verwende birth_date für das tatsächliche Geburtsdatum. Schätze niemals das Geburtsjahr aus starts_at. Bewahre Datumswerte ohne Zeitzonenverschiebung; berücksichtige Zeitzonen bei starts_at/ends_at und daysUntil.
6. Bleibe kompatibel zu älteren Servern und alten, noch nicht umgewandelten gewöhnlichen Kalenderterminen vom Typ BIRTHDAY: source, Namensfelder, birth_date und age können fehlen. Fehlende Geburtsdaten/Alter bleiben unbekannt. Keine erfundenen Werte.
7. Jährliche Wiederholung und die Behandlung des 29. Februar (28. Februar in Nicht-Schaltjahren) erfolgen serverseitig. Ergänze Tests für alle Quellen, alte Antworten, null-Werte, String-IDs und die Vermeidung doppelter Einträge.

Offene Anfragen:
FamilienPlan zeigt offene Betreuungs-, Änderungs-, Löschungs- und Gruppenanfragen jetzt intern im Kalender mit Uhrsymbol. Diese Vorschauen werden NICHT über die Integrations-API ausgegeben. Auch die Aufenthaltsabfrage berücksichtigt ausschließlich bestätigte Betreuungen. Der Adapter braucht dafür weder neue Abrufe noch Datenpunkte und soll keine internen Anfragen-Endpunkte verwenden.

Berechtigungen bleiben unverändert: read:birthdays und passende Personen-/Kinder-/Terminartrechte, für private Geburtstage zusätzlich read:private. /children benötigt read:children.

Dokumentation:
https://github.com/BenAhrdt/familienplan/blob/v0.1.100/docs/integrations.md
