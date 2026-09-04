# Änderungsprotokoll

Alle wesentlichen Änderungen an FamilienPlan werden hier dokumentiert. Die Versionierung folgt dem Schema MAJOR.MINOR.PATCH.

## 0.1.85 – 4. September 2026

### Direkte Terminansicht und klare mobile Markierungen

- Ein Klick auf einen Eintrag unter „Als Nächstes“ öffnet im Kalender unmittelbar dieselbe Detail- oder Bearbeitungsansicht wie ein Klick auf den Kalendereintrag.
- Der separate Link „Zum Kalender“ bleibt für den direkten Wechsel in die reine Kalenderübersicht erhalten.
- Die kleinen Markierungen im mobilen Monatskalender verwenden einheitliche Farbpunkte ohne gequetschte Symbole; die aussagekräftigen Symbole bleiben in der Tagesansicht sichtbar.

## 0.1.84 – 4. September 2026

### Verlässliche Updateanzeige

- Die Updateanzeige lädt nicht mehr irreführend nach 30 Sekunden neu, während die Installation noch läuft.
- Statt eines Countdowns zeigt sie die tatsächlich verstrichene Laufzeit und weist auf mögliche Wartezeiten bei langsamen Paketservern hin.
- FamilienPlan prüft den Versionswechsel bis zu 15 Minuten lang und lädt erst nach dem erfolgreichen Neustart automatisch neu.

## 0.1.83 – 4. September 2026

### Mobile Ansicht und Dialogbedienung

- Kalender und Übersicht bleiben auf Mobilgeräten in der vorgesehenen Größe und können nicht versehentlich per Seitengeste vergrößert werden.
- Beim Betrachten angehängter Dokumente bleibt Zoomen weiterhin möglich.
- Dialoge schließen beim Ziehen einer Textmarkierung über den Rand hinaus nicht mehr; dazu müssen sowohl das Drücken als auch das Loslassen außerhalb des Dialogs erfolgen.
- Anhänge werden in der mobilen Tagesübersicht mit einem klar ausgerichteten, runden Büroklammer-Badge dargestellt.

## 0.1.82 – 3. September 2026

### Einheitliches Kalenderformat der Integrations-API

- Kalenderobjekte verwenden einheitlich `event_type`; das redundante und je nach Objekt unterschiedliche Feld `type` entfällt.
- Schultermine, Schulferien, Geburtstage und Betreuungen werden als `SCHOOL`, `SCHOOL_HOLIDAY`, `BIRTHDAY` beziehungsweise `STAY` gekennzeichnet.
- Standardbetreuungen aus „Wohnt bei“ werden in freien Zeiträumen als erzeugte Betreuungen mit `source: "default"` ausgegeben.
- Auch Kinder- und Aufenthaltsantworten verzichten auf das durch den Endpunkt bereits eindeutig bestimmte `type`-Feld.

## 0.1.81 – 3. September 2026

### Auswählbare Abfallarten

- Jeder Abfallkalender erkennt die vom Anbieter gelieferten Abfallarten und zeigt sie einzeln in seiner Konfiguration an.
- Erkannte Abfallarten können unabhängig voneinander für den Import aktiviert oder deaktiviert werden.
- Große 1.100-Liter-Behälter sind bei der ersten Erkennung standardmäßig deaktiviert; normale Abfallarten bleiben aktiv.
- Bei der nächsten Synchronisierung werden Termine deaktivierter Abfallarten automatisch aus dem Kalender entfernt.

## 0.1.80 – 3. September 2026

### Zuverlässige API-Schlüsselprüfung

- Neu erzeugte API-Schlüssel enthalten eine eindeutige Schlüsselkennung und werden gezielt gegen ihren gespeicherten Hash geprüft.
- Bestehende API-Schlüssel im bisherigen Format bleiben weiterhin gültig.
- Ein automatisierter Test stellt sicher, dass ein Schlüssel unmittelbar nach seiner Erzeugung zur API-Authentifizierung verwendet werden kann.

## 0.1.79 – 3. September 2026

### Mehrere benannte API-Schlüssel pro Person

- Für jede Person lassen sich mehrere API-Schlüssel mit frei wählbaren Namen wie ioBroker oder Home Assistant anlegen.
- Name, Aktivstatus und letzte Verwendung bleiben dauerhaft sichtbar; nur der geheime Schlüsselwert wird weiterhin ausschließlich direkt nach dem Erzeugen angezeigt.
- Schlüssel können einzeln widerrufen werden, ohne die übrigen Integrationen derselben Person zu unterbrechen.
- Alle Schlüssel bleiben dynamisch auf die aktuellen Rechte ihrer zugeordneten Person begrenzt.

## 0.1.78 – 3. September 2026

### Benutzergebundene API-Schlüssel ohne Webhooks

- API-Schlüssel werden direkt bei der jeweiligen Person erzeugt, erneuert oder deaktiviert; ohne aktiven Schlüssel besteht kein API-Zugriff.
- Jeder Schlüssel übernimmt bei jeder Anfrage die aktuellen Kinder-, Terminarten- und Sichtbarkeitsrechte der zugeordneten Person.
- Ein neu erzeugter Schlüssel widerruft automatisch den vorherigen Schlüssel dieser Person.
- Kalenderantworten enthalten zusätzlich den internen `event_type` und die optionale eigene Terminart.
- Webhooks wurden vollständig aus Oberfläche, API, Datenmodell und Hintergrundverarbeitung entfernt. Automatisierungen und zeitliche Vor- beziehungsweise Nachläufe übernimmt künftig der angebundene Client wie ein ioBroker-Adapter.
- Die Migration `0021` entfernt vorhandene Webhook-Konfigurationen und ausstehende Webhook-Zustellungen.

## 0.1.77 – 3. September 2026

### Sofort aktualisierte Suchergebnisse

- Nach Änderungen an Terminen oder Betreuungsnotizen wird eine geöffnete Trefferliste unmittelbar verworfen und neu geladen.
- Suchanfragen umgehen den Browser-Cache, damit alte Titel nicht bis zum nächsten Seitenaufruf sichtbar bleiben.
- Eine bereits eingegebene Suche zeigt dadurch ohne manuellen Refresh den aktuellen Datenstand.

## 0.1.76 – 3. September 2026

### Aussagekräftige Feriennamen und erneut nutzbare Suche

- Ferien werden im Kalender mit ihrem konkreten Namen wie Sommerferien oder Winterferien angezeigt.
- Bei einem oder zwei betroffenen Kindern erscheinen deren Namen; bei drei oder mehr Kindern wird die Anzahl und bei allen Schulkindern „Alle Kinder“ angezeigt.
- Der Detaildialog nennt unabhängig von der kompakten Beschriftung stets alle betroffenen Kinder.
- Nach dem Öffnen eines Suchtreffers kann die globale Suche durch Klick oder weitere Eingabe sofort erneut verwendet werden, ohne sie zuvor über das X zurücksetzen zu müssen.

## 0.1.75 – 3. September 2026

### Dauerhaft sichtbares Schließen-X

- Auf dem Desktop schwebt das Schließen-X über der äußeren oberen rechten Dialogecke.
- Die Position berücksichtigt automatisch unterschiedlich breite und hohe Dialoge.
- Auf Mobilgeräten bleibt die Schaltfläche beim Scrollen fest im sichtbaren Bereich und innerhalb der Safe Area.
- Größenänderungen und ein Wechsel der Geräteausrichtung positionieren die Schaltfläche automatisch neu.

## 0.1.74 – 3. September 2026

### Schwebende Schließen-Schaltfläche

- Dialoge erhalten oben rechts eine gut sichtbare, runde Schließen-Schaltfläche.
- Das Schließen-X bleibt beim Scrollen langer Formulare an seiner Position.
- Auf Mobilgeräten wird die Schaltfläche fest innerhalb der Safe Area angezeigt.
- Kontrast, Schatten und sichtbarer Tastaturfokus verbessern Erkennbarkeit und Bedienbarkeit.

## 0.1.73 – 3. September 2026

### Eigener mobiler PDF-Viewer

- PDFs werden unabhängig vom eingebauten Browser-Viewer mit vollständig eingepasster Seite dargestellt.
- Schaltflächen zum Verkleinern, Vergrößern und erneuten Einpassen ermöglichen eine kontrollierte Ansicht.
- Mehrseitige PDFs erhalten eine Seitennavigation.
- Zurück, Download und Teilen bleiben während der Dokumentansicht erreichbar.
- Der PDF-Renderer wird erst beim Öffnen eines Dokuments geladen und verwendet eine Version ohne bekannte Sicherheitslücken.

## 0.1.72 – 3. September 2026

### Eingepasste und zoombare Dokumentansicht

- PDFs öffnen standardmäßig mit vollständig eingepasster erster Seite.
- Die bisherige globale Zoom-Sperre für Mobilgeräte wurde entfernt, sodass Dokumente per Zwei-Finger-Geste vergrößert werden können.
- Die im Home-Bildschirm-Modus problematische Aktion „Separat öffnen“ wurde entfernt.
- Zurück, Download und Teilen bleiben direkt oberhalb des Dokuments erreichbar.

## 0.1.71 – 3. September 2026

### Mobile Dokumentansicht, Download und Teilen

- Anhänge öffnen in einer eigenen Vollbildansicht mit dauerhaft sichtbarer Zurück-Schaltfläche.
- Die Zurück-Geste beziehungsweise Zurück-Taste des Mobilgeräts schließt die Dokumentansicht ebenfalls.
- Dokumente lassen sich direkt herunterladen oder über den nativen Teilen-Dialog von Android und iOS als Datei weitergeben.
- Zusätzlich können Anhänge weiterhin separat im Browser geöffnet werden.

## 0.1.70 – 3. September 2026

### Zurück-Navigation nach dem Öffnen von Anhängen

- Dokumente öffnen auf mobilen Geräten nicht mehr in einer separaten App-/PWA-Browseransicht.
- Die normale Zurück-Funktion führt nach der Dokumentansicht wieder zuverlässig zu FamilienPlan.

## 0.1.69 – 3. September 2026

### Dokumente an Kalendereinträgen

- An bestehenden Terminen lassen sich PDF-, Bild-, Text-, Word- und OpenDocument-Dateien per Dateiauswahl oder Drag-and-drop anhängen.
- Anhänge können geschützt im Browser geöffnet und von berechtigten Personen wieder gelöscht werden; pro Datei gilt eine Größenbegrenzung von 15 MB.
- Die Funktion steht auch für importierte Termine aus Schul- und anderen externen Kalendern zur Verfügung.
- Eine Büroklammer kennzeichnet Termine mit Dokumenten in Familienübersicht, Monatskalender, mobiler Tagesansicht und Serienübersicht.
- Eine neue Datenbankmigration speichert Metadaten und Berechtigungsbezug der Anhänge, während die Dateien im konfigurierten Upload-Verzeichnis abgelegt werden.

## 0.1.68 – 2. September 2026

### Automatische Symbole anhand des Termintitels

- Termine ohne festes Standardsymbol erhalten anhand häufiger Begriffe ein passendes Motiv, etwa Ticket, Theatermasken, Musiknote, Filmklappe, Arzt-, Sport-, Einkaufs-, Reise- oder Werkstattsymbol.
- Anime-, Manga- und Cosplay-Termine werden mit einer eigenen stilisierten Figur gekennzeichnet; diese Erkennung hat Vorrang vor allgemeineren Begriffen wie „Festival“.
- Die zentrale Erkennung gilt einheitlich in der Familienübersicht, im Monatskalender und in der mobilen Tagesansicht.

## 0.1.67 – 2. September 2026

### Wischmopp für Reinigungstermine

- Termine der Art „Putzfrau“ erhalten ein Wischmopp-Symbol.
- Das Symbol erscheint einheitlich in der Familienübersicht sowie in der Desktop- und mobilen Kalenderansicht.

## 0.1.66 – 2. September 2026

### Einheitliche Symbole in Übersicht und Kalender

- Die Familienübersicht zeigt für Geburtstage und Abfalltermine nun dieselben Torten- und Mülltonnensymbole wie der Kalender.
- Betreuungszeiten und kindbezogene Termine übernehmen ihre Personen- und Kindermarkierungen ebenfalls in die Übersicht.
- Schultermine erhalten in der Übersicht sowie in der Desktop- und mobilen Kalenderansicht ein Buchsymbol.

## 0.1.65 – 2. September 2026

### Lange Namen im mobilen Menü

- Lange Menübezeichnungen wie „Planung zusammenstellen“ brechen innerhalb ihres Buttons sauber auf mehrere Zeilen um.
- Die Beschriftung kann nicht mehr über den Rand der Menüschaltfläche hinausragen.

## 0.1.64 – 2. September 2026

### Sichtbare untere Tagesdetails

- Die untere Tagesdetailkarte verwendet keine mit der mobilen Navigation kollidierende CSS-Klasse mehr.
- Sie erscheint dadurch zuverlässig zwischen Monatskalender und Terminartenfilter.

## 0.1.63 – 2. September 2026

### Tagesdetails ober- und unterhalb des Kalenders

- Die mobile Tagesdetailkarte wird synchron oberhalb und unterhalb des Monatskalenders angezeigt.
- Dadurch bleiben die ausgewählten Einträge sowohl in den oberen als auch in den unteren Kalenderwochen direkt erreichbar.

## 0.1.62 – 2. September 2026

### Keine doppelten Ferien und Feiertage

- Schulkalendereinträge werden ausgeblendet, wenn Name und Datum bereits durch die offiziellen Ferien- oder Feiertagsdaten abgedeckt sind.
- Die Bereinigung gilt in „Ferien & Feiertage“ und im normalen Monatskalender.
- Eigenständige Schultermine wie erste Schultage, Brückentage und bewegliche Ferientage bleiben erhalten.

## 0.1.61 – 2. September 2026

### Tagesdetails unter dem Monatskalender

- Die mobile Tagesdetailkarte erscheint nun direkt unterhalb des Monatskalenders statt davor.
- Filter und periodische Einträge folgen anschließend, sodass Termine der unteren Kalenderwochen ohne Zurückscrollen erreichbar sind.

## 0.1.60 – 2. September 2026

### Korrigierte mobile Kalenderkennzeichnung

- Der Abstand zur feststehenden Suche wird nun in der tatsächlich zuletzt wirksamen Layoutregel gesetzt, sodass Rubrik und Überschrift vollständig sichtbar bleiben.
- Normale Terminmarkierungen bleiben durch feste Abmessungen zuverlässig kreisrund.
- Personen-Kreis und Kinderstern einer Betreuung stehen mit erkennbarem Abstand nebeneinander.
- Die Tagesdetailkarte zeigt dieselben Mülltonnen-, Torten-, Betreuungs- und Farbkreissymbole wie das Monatsraster.

## 0.1.59 – 2. September 2026

### Aussagekräftige Kalendersymbole

- Abfalltermine zeigen eine Mülltonne in der konfigurierten Abfallfarbe – mobil und im Desktopkalender.
- Geburtstage werden im mobilen Raster mit der Geburtstagstorte gekennzeichnet.
- Betreuungen zeigen den farbigen Anfangsbuchstaben der betreuenden Person zusammen mit dem Stern des Kindes.
- Alle übrigen Termine erscheinen mobil als echte runde Farbmarkierung statt als Oval.
- Seitenüberschriften erhalten auf Mobilgeräten nochmals deutlich mehr Abstand zur feststehenden Suche.

## 0.1.58 – 2. September 2026

### Mobiles Monatsraster mit Tagesdetails

- Auf Mobilgeräten bleibt das vertraute Monatsraster erhalten; Einträge werden darin als kompakte Farbpunkte dargestellt.
- Ein Tipp auf einen Tag markiert ihn und zeigt Termine, Betreuungen, Geburtstage und Ferien darunter vollständig lesbar an.
- Erst ein Tipp auf den konkreten Eintrag öffnet dessen Details oder Bearbeitung.

## 0.1.57 – 2. September 2026

### Mobile Monatsagenda

- Der Monatskalender erscheint auf kleinen Bildschirmen als übersichtliche Agenda mit Datum und vollständigen Einträgen statt als zu enges Sieben-Spalten-Raster.
- Tage ohne Einträge und die angrenzenden Monatstage werden in der mobilen Agenda ausgeblendet.
- Der Abstand zwischen feststehender Suche und Seitenüberschrift wurde weiter vergrößert.

## 0.1.56 – 2. September 2026

### Verbesserte mobile Kalenderansicht

- Seitenüberschriften beginnen auf Mobilgeräten zuverlässig unterhalb des feststehenden Suchfeldes.
- Termine im Monatskalender werden auf kleinen Bildschirmen mehrzeilig dargestellt und sind dadurch direkt besser lesbar.

## 0.1.55 – 1. September 2026

### Anonymisierte Übergabeanfragen

- Antragsteller sehen eine nicht freigegebene aktuelle Betreuungsperson auch innerhalb ihrer offenen Übergabeanfrage nur als „Andere Betreuungsperson“.
- Der tatsächliche Empfänger der Anfrage sieht weiterhin die beteiligten Namen, die er für seine Entscheidung benötigt.

## 0.1.54 – 1. September 2026

### Vertrauliche Betreuungsdaten

- Betreuungen nicht freigegebener Personen werden bereits von der API aus Kalender-, Dashboard-, Serien- und Konfliktdaten entfernt.
- Konfliktkarten verraten dadurch weder Namen noch Zeiträume von Personen, die für das angemeldete Konto nicht sichtbar sind.
- Direkt beteiligte Empfänger einer konkreten Betreuungsanfrage erhalten weiterhin ausschließlich die für diese Entscheidung erforderlichen Namen.

## 0.1.53 – 1. September 2026

### Einheitliche Dialogebenen

- Hauptdialoge, nachgelagerte Bestätigungen und Auswahl-Popups besitzen appweit klar getrennte Darstellungsebenen.
- Verschachtelte Popups bleiben dadurch zuverlässig sichtbar und werden nicht von ihrem Ausgangsdialog überdeckt.
- Escape schließt nur noch die oberste sichtbare Ebene, statt Auswahl- und Hauptdialog gleichzeitig zu schließen.
- Auch der Löschdialog für Geburtstage lässt sich einheitlich über Escape und einen Hintergrundklick schließen.

## 0.1.52 – 1. September 2026

### Sichtbare Auswahl-Popups

- Ausgelagerte Auswahl-Popups liegen nun zuverlässig über dem geöffneten Hauptdialog und verschwinden nicht mehr optisch dahinter.

## 0.1.51 – 1. September 2026

### Betreuungsanfragen zwischen beteiligten Personen

- Bei einer Übergabe bestätigen sich bisherige und zukünftige Betreuungsperson gegenseitig; die Standardbezugsperson bleibt dabei außen vor.
- Die Standardbezugsperson wird nur als Ersatz angefragt, wenn jemand eine eigene neue Betreuung oder die Löschung der eigenen Betreuung vorschlägt.
- Eine neue Einzelbetreuung, die eine vorhandene Betreuung überschneidet, wird als Übergabe behandelt und erzeugt keinen parallelen Eintrag.
- Empfänger sehen die für ihre Entscheidung benötigten Personennamen und können die Anfrage auch ohne allgemeine Sichtbarkeit der anderen Person bestätigen.

## 0.1.50 – 1. September 2026

### Auswahl-Popups in langen Dialogen

- Auswahl-Popups werden nun unabhängig vom scrollbaren Hauptdialog dargestellt.
- Dadurch bleiben sie vollständig sichtbar, mittig im Browserfenster und werden nicht mehr an den abgerundeten Dialogkanten abgeschnitten.

## 0.1.49 – 1. September 2026

### Eigene Terminarten im Personenformular

- Administratoren sehen im Personenformular nun auch die eigenen Terminarten.
- Sichtbarkeit und Anlegen/Bearbeiten können dort getrennt für die ausgewählte Person vergeben werden.
- Personen- und Terminartenrubrik bearbeiten dieselben zentralen Rechte und bleiben dadurch automatisch synchron.
- Bearbeitungsrechte schließen Leserechte automatisch ein; Löschen bleibt Erstellern und Administratoren vorbehalten.

### Bereinigte Dialoge und verlässliche Terminarten

- „Terminarten“ ist als eigene, nur für Administratoren sichtbare Hauptrubrik erreichbar.
- Lange Dialoge besitzen sauber beschnittene, vollständig abgerundete Ecken – einschließlich des Scrollbereichs.
- Aktionsleisten verdecken keine Formularfelder mehr und Termin- sowie Betreuungsdialoge bieten einen Abbrechen-Button.
- Das störende mitscrollende Schließen-Symbol wurde entfernt; Hintergrundklick und Escape schließen Dialoge weiterhin.
- Nach dem Speichern eigener Terminarten prüft FamilienPlan durch einen cachefreien Kontrollabruf, ob sie im Terminformular verfügbar sind.

## 0.1.48 – 1. September 2026

### Eigene Terminarten und zentrale Freigaben

- Die neue, ausschließlich für Administratoren zugängliche Rubrik „Terminarten“ bündelt die Freigaben der festen Standardtypen.
- Eigene Terminarten können mit Namen, Farbe sowie getrennten Sicht- und Bearbeitungsrechten angelegt werden.
- Einfache und wiederkehrende Termine unterstützen die eigenen Terminarten.
- Sichtbarkeitsrechte gelten auch für Suche und Serienansicht; Löschen bleibt Erstellern und Administratoren vorbehalten.
- Verwendete Terminarten sind vor versehentlichem Löschen geschützt, während Umbenennungen bestehende Termine mitführen.

### Einheitliche Auswahl-Popups und Dialoge

- Mehrfachauswahlen für Personen, Kinder, Terminarten und weitere Freigaben öffnen ein einheitliches kompaktes Popup.
- Personen werden darin mit ihrer Farbe und Initiale übersichtlich dargestellt.
- Dialoge besitzen auf allen Bildschirmgrößen vier abgerundete Ecken und besser ausgerichtete, dauerhaft erreichbare Aktionsbuttons.
- Das Schließen-Symbol bleibt beim Scrollen sichtbar; zusätzlich schließen ein Klick außerhalb oder die Escape-Taste den obersten Dialog.
- Einfache Ja/Nein-Einstellungen bleiben bewusst direkt bedienbare Checkboxen.

## 0.1.47 – 1. September 2026

### Persönliche Kalenderanzeige pro Benutzerkonto

- Die automatisch aus „Wohnt bei“ abgeleitete Standardbetreuung ist nun standardmäßig ausgeblendet.
- Die Anzeige lässt sich weiterhin unabhängig von ausdrücklich angelegten Betreuungsterminen einschalten.
- Die Auswahl wird serverseitig pro Benutzerkonto gespeichert und gilt damit über Browser und Geräte hinweg.
- Andere Benutzerkonten – auch im selben Browser – übernehmen diese persönliche Einstellung nicht.

## 0.1.46 – 1. September 2026

### Standardbetreuung gezielt ausblenden

- Im Kalenderfilter lässt sich die automatisch aus „Wohnt bei“ abgeleitete Standardbetreuung separat ausblenden.
- Ausdrücklich angelegte Betreuungstermine bleiben dabei weiterhin sichtbar.
- Die persönliche Auswahl wird wie die übrigen Terminart-Filter dauerhaft im Browser gespeichert.

## 0.1.45 – 1. September 2026

### Abfallkalender persönlich ausblenden

- Jeder sichtbare Abfallkalender kann über „Für mich ausblenden“ aus dem persönlichen Kalender entfernt werden.
- Das Ausblenden verändert weder die Synchronisierung noch die Freigaben und Ansichten anderer Personen.
- Ausgeblendete Kalender bleiben in der Verwaltung erkennbar und können jederzeit wieder eingeblendet werden.
- Bereits importierte Termine werden unmittelbar anhand ihrer Kalenderquelle ausgefiltert.

## 0.1.44 – 1. September 2026

### Mehrere Abfallkalender mit sicheren Freigaben

- Administratoren können mehrere automatische Abfallkalender mit eigenem Namen, Anbieter, Farben und Synchronisationsstatus anlegen.
- Jeder Abfallkalender lässt sich gezielt für einzelne Personen freigeben.
- Freigegebene Personen dürfen den Kalender und seine Termine sehen, aber weder seine Einstellungen verändern noch ihn löschen.
- Nur Eigentümer und Administratoren dürfen einen Abfallkalender verwalten oder löschen.
- Beim Löschen werden ausschließlich die importierten Termine des ausgewählten Kalenders entfernt.
- Der bisherige einzelne Abfallkalender wird automatisch und ohne Datenverlust übernommen.
- Die Hintergrundsynchronisierung verarbeitet alle aktivierten Abfallkalender getrennt.

## 0.1.43 – 31. August 2026

### Sichtbare Personen

- Die bisherige Freigabe für Personenfarben heißt nun „Sichtbare Personen“ und steuert die gesamte verfügbare Personenliste.
- Bei der Auswahl „Das Kind ist bei“ erscheinen nur die eigene und ausdrücklich freigegebene Personen; Administratoren sehen weiterhin alle Personen.
- Auch Gruppenplanungen und Betreuungsanfragen akzeptieren serverseitig keine Zuordnung zu einer nicht freigegebenen Person.
- Die Personen-API gibt nicht administrativen Benutzern keine nicht freigegebenen Personen mehr preis.

### Getrennte Rubrik- und Kalenderfreigaben

- Die Kinder-Rubrik ist ausschließlich für Administratoren sichtbar; freigegebene Kinder bleiben in Kalender und Planung nutzbar.
- Die Rubrikenfreigabe erlaubt unabhängig vom Hauptkalender das Öffnen und Pflegen von Geburtstagen beziehungsweise Abfallkalendern.
- Die persönlichen Terminarten steuern getrennt davon, ob Geburtstage und Abfalltermine im Hauptkalender erscheinen.
- Die konkrete Auswahl „Sichtbar für“ an Geburtstagen und am Abfallkalender wird zusätzlich berücksichtigt.

### Aufgeräumte Übersicht

- Abfall- und Putzfrauentermine zeigen in „Als Nächstes“ keine unpassende Zuordnung zu „Ganze Familie“ mehr.
- Geburtstage verzichten dort auf die redundante Zusatzzeile „Geburtstag“ beziehungsweise „Privater Geburtstag“.

## 0.1.42 – 31. August 2026

### Terminfarben folgen den Freigaben

- Die Farbschnellwahl zeigt Typfarben nur noch für freigeschaltete Terminarten.
- Ohne Freigabe für den Abfallkalender wird dessen Farbe nicht mehr angeboten.
- Auch die Farben für Betreuung, Allgemein, Putzfrau, Privat und Sonstiges stehen passend zu den jeweiligen Berechtigungen bereit.
- Personenfarben bleiben unabhängig davon über die administrativen Personenfreigaben gesteuert.

## 0.1.41 – 31. August 2026

### Freigaben für Personenfarben

- Administratoren können pro Person festlegen, welche Personenfarben ihr im Terminformular angeboten werden.
- Freigegebene Personen erscheinen als beschriftete Farbschnellwahl neben den persönlichen Kalenderfarben.
- Administratoren sehen automatisch alle bestehenden und künftig hinzugefügten Personenfarben.
- Die Freigabeauswahl ist ausschließlich in der Administration veränderbar und wird serverseitig geprüft.

## 0.1.40 – 31. August 2026

### Ganztägige Termine und Farbschnellwahl

- Neue Termine sind standardmäßig ganztägig und laufen sauber von 00:00 Uhr bis 00:00 Uhr des Folgetags.
- Die Option „Ganztägig“ kann im Terminformular sichtbar ein- oder ausgeschaltet werden.
- Zusätzlich zur freien Farbpalette stehen die eigene Personenfarbe und die persönlichen Kalenderfarben als beschriftete Schnellwahl bereit.
- Farben anderer Personen werden in der Schnellwahl nicht offengelegt.

## 0.1.39 – 31. August 2026

### Verständliche Zeiten mehrtägiger Termine

- Der erste Tag eines mehrtägigen Termins zeigt beispielsweise „ab 06:00“ statt „06:00–24:00“.
- Vollständig vom Termin abgedeckte Zwischentage werden verständlich als „ganztägig“ bezeichnet.
- Der letzte Tag zeigt beispielsweise „bis 04:00“ statt „00:00–04:00“.
- Eintägige Termine behalten ihre präzise Zeitspanne wie „10:00–11:00“.

## 0.1.38 – 31. August 2026

### Orientierung am Kalenderende

- Unterhalb des Monatsrasters erscheint eine zweite Wochentagszeile von Montag bis Sonntag.
- Die untere Beschriftung verwendet exakt dieselbe Sieben-Spalten-Ausrichtung wie Kalender und obere Wochentagszeile.
- Auch in der kompakten mobilen Monatsansicht bleiben Abstände und Schriftgrößen konsistent.

## 0.1.37 – 31. August 2026

### Aussagekräftige Termineinträge

- Manuelle Termine zeigen im Monatskalender neben dem Titel auch ihre Notiz und die sichtbare Uhrzeit.
- Mehrtägige Termine begrenzen die angezeigte Uhrzeit passend auf den jeweiligen Kalendertag; ganztägige Termine bleiben ohne unnötige Zeitangabe.
- Lange Notizen werden in kleinen Tageszellen platzsparend gekürzt.
- Umfangreiche Beschreibungen importierter Termine werden nicht ungefiltert in der Monatsansicht ausgegeben.
- Neue manuelle Termine übernehmen standardmäßig die persönliche Farbe ihres Erstellers, bleiben aber individuell anpassbar.

## 0.1.36 – 31. August 2026

### Persistente Terminänderungen und mobile Suche

- Änderungen an einzelnen manuellen Terminen werden vor dem erneuten Laden zuverlässig committed.
- Neu ausgewählte Kinder, Datum, Uhrzeit, Terminart, Notiz und Farbe bleiben nach dem Speichern und erneuten Öffnen erhalten.
- Ein Datenbank-Regressionstest prüft ausdrücklich die nachträgliche Kinderzuordnung eines zuvor allgemeinen Termins.
- Die mobile Suchleiste wird nicht länger von einer später geladenen Desktop-Regel überschrieben.
- Suche, Breite und Position unterhalb des mobilen Headers funktionieren nun im Hoch- und Querformat bis 900 Pixel.

## 0.1.35 – 31. August 2026

### Terminbearbeitung und einzelne Betreuungsausnahmen

- Das Verschieben eines einzelnen Vorkommnisses einer Betreuungsserie ersetzt nun den vollständigen Termin, ohne einen fälschlichen Minuten-Rest anzulegen.
- Die Serienregel und alle übrigen Vorkommnisse bleiben bei „Nur diesen Termin“ unverändert erhalten.
- Unberührte Teile eines mehrtägigen Betreuungszeitraums werden nur noch bei der ausdrücklichen Auswahl „Nur diesen Kalendertag (Rest des Zeitraums erhalten)“ gespeichert.
- Berechtigte Editoren können gemeinsame manuell angelegte Termine vollständig bearbeiten, auch wenn sie nicht deren ursprüngliche Ersteller sind.
- Private Termine bleiben ausschließlich durch ihren Ersteller bearbeitbar; importierte Schul- und Abfalltermine sowie reine Leser bleiben schreibgeschützt.

## 0.1.34 – 31. August 2026

### Mehrtägige externe Termine

- Mehrtägige Schultermine bleiben an jedem tatsächlich betroffenen Kalendertag sichtbar.
- Der Detaildialog zeigt bei ganztägigen Terminen den vollständigen Zeitraum einschließlich des letzten Tages, beispielsweise „19.09.2026 – 21.09.2026 · ganztägig“.
- Eintägige ganztägige Termine behalten ihre kompakte Datumsanzeige.
- Importierte Schul- und Abfalltermine bleiben als Daten der externen Quelle schreibgeschützt; manuell angelegte Termine lassen sich weiterhin vollständig bearbeiten.
- Drag-and-drop wurde bewusst nicht ergänzt, damit die bestehenden Bearbeitungs- und Synchronisationswege zunächst zuverlässig bleiben.

## 0.1.33 – 31. August 2026

### Mobile Suche, Dialoge und Terminmarkierungen

- Die mobile Suche füllt im Hoch- und Querformat die verfügbare Breite mittig aus und verwendet eine kompaktere Höhe.
- Der Inhaltsabstand berücksichtigt die kompakte Suchleiste, sodass sie nicht mehr vom festen App-Header verdeckt wird.
- Dialoge und ihre Schließen-Schaltflächen liegen auf Mobilgeräten zuverlässig oberhalb von Header, Suche und unterer Navigation.
- Eine widersprüchliche Dashboard-Regel, durch die die Suche verschoben wurde oder im Querformat verschwand, wurde entfernt.
- Der Kinderstern erscheint nun bei jeder Terminart mit Kind-Zuordnung; der Personen-Kreis bleibt eindeutig Betreuungszeiten vorbehalten.
- Reines Schwarz (`#000000`) ist wieder eine gültige globale und persönliche Kalenderfarbe und wird nicht mehr durch eine Standardfarbe ersetzt.

## 0.1.32 – 31. August 2026

### Kinderfarben, zuverlässige Einstellungen und Schulkalender

- Kinder erhalten im Bearbeitungsdialog eine eigene Farbe, die auch im Kinderprofil verwendet wird.
- Betreuungszeiten zeigen rechts oben einen echten farbigen Stern mit weißer Kinderinitiale; die betreuende Person bleibt links als runder Farbchip sichtbar.
- Persönliche Kalenderfarben, globale Darstellungswerte und Rubrikenfreigaben werden atomar gespeichert und anschließend aus der Datenbank verifiziert.
- Das Logbuch enthält bei persönlichen Kalenderfarben die tatsächlich gespeicherten Werte.
- Die Schulkalender-Synchronisierung erkennt auch überlappende Dubletten aus derselben Quelle mit unterschiedlichen externen Kennungen und bevorzugt den präziseren kürzeren Eintrag.
- Manuelle Schultermine sowie gleichnamige Termine an getrennten Tagen bleiben bei der Bereinigung erhalten.

## 0.1.31 – 31. August 2026

### Private Termine, Betreuung und Kalenderpflege

- Die neue Terminart „Privat“ ist für jede Person verfügbar und kann nur vom Ersteller bearbeitet oder gelöscht werden; ausgewählte Personen können gezielt Leserechte erhalten.
- Private Termine werden in Kalender, Suche, Terminserien und Integrationszugriffen konsequent nach ihrer Sichtbarkeit gefiltert.
- Betreuungslabels zeigen die betreuende Person als runden Farbchip und das Kind als Stern in seiner Kinderfarbe; weiße Initialen sorgen für eine schnelle Zuordnung.
- Abfallkalender, Geburtstage und Putzfrau benötigen keine Kinderauswahl und speichern auch über die API keine Kind-Zuordnung.
- Die Schulkalender-Synchronisierung entfernt eindeutig erkennbare Altimporte aus früheren Importpfaden, ohne manuell angelegte Schultermine anzutasten.
- Das Formular zum Ändern des eigenen Passworts ist in den Profileinstellungen wieder vollständig gestaltet und übersichtlich angeordnet.

## 0.1.30 – 30. August 2026

### Kalender, Rechte und Kontosicherheit

- „Aufenthalt“ heißt in der Oberfläche verständlicher „Betreuung“ beziehungsweise „Betreuungszeit“; Formulare erklären mit „Das Kind ist bei“ eindeutig den Zweck.
- Normale Termine verwenden standardmäßig „Kein Kind“, während Betreuungszeiten weiterhin zwingend einem Kind zugeordnet werden.
- Benutzer mit reinen Leserechten sehen keine Schaltflächen oder Eingabemasken zum Anlegen, Bearbeiten und Löschen; vorhandene Einträge öffnen eine reine Detailansicht.
- Die Sichtbarkeit normaler Termine richtet sich einheitlich nach Rubrik- und Kinderfreigaben statt nach einer zusätzlichen Personenauswahl.
- Bereits gewählte Ferien und Feiertage sind im Planungsentwurf gesperrt und können nicht doppelt übernommen werden; Planungsaktionen wurden aus der Ferienübersicht entfernt.
- Persönliche Kalenderfarben besitzen nur noch eine eindeutige Quelle. Die globale Darstellung verwaltet ausschließlich die Akzentfarbe und überschreibt keine persönlichen Kalenderfarben mehr.
- Eigene Passwörter lassen sich in den Einstellungen ändern. „Passwort vergessen“ verwendet einen eine Stunde gültigen Einmal-Link, beendet alte Sitzungen und protokolliert niemals Passwörter, Hashes oder Reset-Token.
- Die globale Suche bleibt auf Desktop und Mobilgeräten fest sichtbar; aufklappbare Kalenderbereiche wurden einheitlich gestaltet.
- Die manuelle Schulkalender-Synchronisierung funktioniert wieder. Ganztägige Schul- und Abfalltermine werden über lokale Datumsgrenzen ohne UTC-Tagesverschiebung ausgewertet.

## 0.1.29 – 30. August 2026

### Navigation, Kalender und Logbuch

- Die Einstellungen zeigen als echte Registeransicht nur noch den jeweils ausgewählten Bereich.
- Aktualisierungen, Integrationen, globale Darstellung und das neue Logbuch besitzen eigene Einstellungsbereiche.
- Die globale Suche bleibt beim Scrollen sichtbar, ohne mobile Seiteninhalte zu überdecken.
- Die Monatsnavigation ist oberhalb und unterhalb des Kalenders einheitlich aufgebaut; „Termin anlegen“ liegt rechts im Navigationsbereich.
- Aufklappbare Kalenderbereiche verwenden eine gestaltete Plus-/Minus-Schaltfläche, aktive Flächen und eine dezente Öffnungsanimation.
- Terminarten erscheinen als farbige Auswahlchips passend zu ihrer Darstellung im Kalender.
- Das neue Admin-Logbuch zeigt Anmeldungen, Änderungen, Einladungen, Planungen, Kalenderaktionen, Synchronisationen und Systemupdates.
- Logbucheinträge lassen sich nach Person und Aktivität filtern und enthalten Zeitpunkt, Zielobjekt, IP-Adresse sowie aufklappbare Änderungsdetails.
- Neue Audit-Einträge bewahren den damaligen Anzeigenamen; Passwörter, Sitzungswerte und geheime Schlüssel werden nicht protokolliert.

## 0.1.28 – 30. August 2026

### Personenverwaltung

- Abstände, Gruppen und Aktionsflächen im Dialog zum Bearbeiten einer Person wurden auf Desktop und Mobilgeräten vereinheitlicht.
- Einladungslink und Kopieraktion ordnen sich auf kleinen Bildschirmen untereinander an.
- Administratoren können Personen über einen eigenen Bestätigungsdialog dauerhaft löschen.
- Das eigene Administratorkonto ist vor dem Löschen geschützt.
- Personen mit verknüpften Planungs- oder Kalenderdaten werden nicht unkontrolliert entfernt; FamilienPlan weist stattdessen auf die bestehenden Zuordnungen hin.
- Beim Löschen werden Sitzungen, Einladungen, Berechtigungen und Rubrikenfreigaben der Person sicher bereinigt.

## 0.1.27 – 30. August 2026

### Einstellungen, Kalender und API

- Die Einstellungsseite nutzt auf großen Bildschirmen eine kompakte zweispaltige Gliederung, Sprungmarken und breite Bereiche für externe Kalender und Integrationen.
- Rubrikenfreigabe und Abfallkalender verwenden denselben Berechtigungsstand; ein älterer Einrichtungsstand kann Freigaben nicht länger zurücksetzen.
- Ausstehende Personen ohne E-Mail-Adresse werden korrekt geladen und lassen nicht mehr die gesamte Personenliste leer erscheinen.
- Die Integrations-API bietet mit `/api/v1/integrations/v1/calendar` einen zentralen, berechtigungsgefilterten Kalenderabruf einschließlich bestätigter Aufenthalte; `/events` bleibt kompatibel.
- Importierte Kalendertermine zeigen beim Anklicken Datum, Uhrzeit und vorhandene Beschreibung zusätzlich zum Schreibschutzhinweis.
- Unterhalb des Monatskalenders stehen eine gespiegelte Monatsnavigation und ein weiterer Knopf zum Anlegen eines Termins bereit.
- Mobile Dialoge bleiben mit eingeblendeter Tastatur scrollbar; die Suchleiste überdeckt auf kleinen Bildschirmen keine Seiteninhalte mehr.
- Die Suche berücksichtigt nun dieselben Terminarten und persönlichen Sichtbarkeiten wie der Kalender.

## 0.1.26 – 30. August 2026

### Mobile App-Ansicht

- Die doppelte Benachrichtigungsglocke wurde entfernt und die mobile Kopfzeile neu ausgerichtet.
- Der Abmeldeknopf besitzt eine kompakte, klar erkennbare Darstellung.
- Die untere Navigation zeigt Übersicht, Kalender und ein aufklappendes Menü für alle weiteren Bereiche.
- Das mobile Menü nutzt den verfügbaren Bildschirm übersichtlich in zwei beziehungsweise drei Spalten.
- Im Kalender steht die Monatsansicht vor Terminfiltern und periodischen Einträgen.
- Terminfilter und periodische Einträge sind platzsparend einklappbar.
- Hoch- und Querformat bis 900 Pixel verhindern horizontales Seitenverschieben.
- Die mobile Browseransicht ist auf App-Größe fixiert und lässt kein versehentliches Zoomen zu.

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
