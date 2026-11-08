# Funktionen im Detail

Zurück zur [Übersicht](../README.md).

## Scannen

- **Quellen:** Flachbett, Dokumenteneinzug (ADF) einseitig und beidseitig (Duplex). Duplex wird per `<scan:Duplex>` angefordert und nur angeboten, wenn der Scanner `AdfDuplexInputCaps` meldet.
- **Mehrseitige Scans** aus dem Einzug werden zu **einem** PDF zusammengefasst. Die JPEG-Bilder des Scanners werden ohne Neukodierung eingebettet, also ohne Qualitätsverlust.
- **Einrichtung:** Zeroconf-Erkennung (`_uscan._tcp` / `_uscans._tcp`) oder manuell; HTTPS mit selbstsigniertem Zertifikat wird akzeptiert. Bei neuer IP aktualisiert die Erkennung die Einrichtung; trotzdem hilft eine DHCP-Reservierung für den Drucker.
- **Immer nur ein Scan gleichzeitig.** Der eSCL-Auftrag wird danach sauber gelöscht. Timeouts: Einzug 900 s, Flachbett 180 s; die Seitenzahl wird live aktualisiert.
- **Aufwärmlogik für den Einzug:** Meldet der Drucker nach dem Standby fälschlich `ScannerAdfEmpty`, wird bis zu 2× ein winziger Flachbett-Scan (100 dpi, 10×10 mm) gemacht, um den Sensor zu aktualisieren. Liefert ein Scan 0 Seiten, gibt es bis zu 3 Versuche mit Pause.
- **Dateiname** `scan-JJJJMMTT-HHMMSS.pdf`.

## Papierformat und Papierlage

- **Papierformat** (Option, Standard A4; A5, Letter, Legal oder volle Scanfläche): Der Scanbereich wird auf das Format begrenzt. Ohne das scannt ein Legal-Einzug (z. B. bei manchen Epson-Geräten) A4-Blätter mit einem weißen Streifen unten.
- **Papierlage im Einzug** (Option: automatisch, links, Mitte, rechts): Liegt das Papier im Einzug an einer Seite an (beim Epson ET-3950 rechts), schneidet die Integration auch die Breite zu und lässt 15 Pixel Spielraum. Bei „automatisch“ wird die Ausrichtung des Scanners verwendet; meldet er keine, bleibt die volle Breite erhalten.

## Flachbett: Stapel

Der Button „Scan Flachbett“ legt die Seite in einen Zwischenspeicher. Beliebig oft wiederholen, dann „Stapel senden“ (ein PDF) oder „Stapel verwerfen“. Wird der Stapel länger als X Minuten (Standard 30) nicht angefasst, feuert das Event `ha_airscan_batch_stale` oder, per Option, der Stapel wird automatisch gesendet. Der Einzug scannt dagegen sofort und lädt direkt hoch. Der Service `ha_airscan.scan` mit `source: platen` sendet weiterhin sofort (für Automationen).

## Leerseitenerkennung

Optional, für Einzug und Flachbett, standardmäßig aus. Schalter und Schwelle in den Optionen, pro Aufruf per `skip_blank` und in der Karte pro Scan überschreibbar.

Jeder Bildpunkt wird mit seiner Umgebung (etwa 8 mm) verglichen; nur echte Strukturen wie Text, Linien und Bilder zählen. Dadurch gelten auch **gleichmäßige Flächen als leer**: weißes Papier, schwach durchscheinende Rückseiten, ein leeres Flachbett mit geschlossenem Deckel samt Schatten oder Verlauf und ein leeres Flachbett bei offenem Deckel (gleichmäßig dunkel oder überbelichtet). Der Rand (4 %) wird ignoriert. Auch eine einzelne Textzeile zählt bei der Standardschwelle als Inhalt.

- **Einzug:** Leere Seiten werden aus dem PDF genommen. Sind alle leer, schlägt der Scan mit einer Meldung fehl.
- **Flachbett:** Eine leere Seite kommt nicht in den Stapel. Die Karte zeigt zehn Minuten lang den Hinweis „Leere Seite erkannt“ (Attribut `notice` am Status-Sensor).

## Ziele

### Paperless-ngx

- **„Fertig“ heißt: Paperless hat das Dokument tatsächlich verarbeitet.** Nach dem Upload fragt die Integration die Paperless-Aufgabe ab (bis 2 Minuten). Lehnt Paperless ab (z. B. Duplikat), wird der Status `error` mit dem Grund aus Paperless. Dauert die Verarbeitung länger, bleibt es `done` mit dem Hinweis „Paperless verarbeitet noch“. Ein Token ohne Zugriff auf die Aufgabenliste funktioniert weiter, dann gilt der Upload als Erfolg.
- **Warteschlange bei Ausfall:** Ist Paperless nicht erreichbar (oder der Token ungültig), geht der Scan **nicht verloren**: Das PDF wird im Ordner `config/ha_airscan_outbox/` gespeichert und automatisch mit wachsenden Abständen (1, 2, 5, 10, 15 min) erneut gesendet, auch nach einem Neustart von Home Assistant. Status `queued` („Wartet auf Paperless“), Sensor *Warteschlange* mit Anzahl und Fehlergrund, Knopf bzw. Service `ha_airscan.retry_queue` zum sofortigen Senden, Event `ha_airscan_queue_delivered`. Meldet Paperless beim erneuten Senden ein Duplikat (der erste Versuch kam doch an), gilt das als zugestellt. Lehnt Paperless ein Dokument endgültig ab, bleibt die Datei zur manuellen Bearbeitung im Ordner liegen und wird nicht weiter versucht.

### Datei

Mit `destination: file` und `directory: /config/scans` wird statt Paperless eine Datei geschrieben (der Pfad muss in `allowlist_external_dirs` stehen, das Medienverzeichnis ist es bereits). Das Schreiben läuft über eine versteckte Temp-Datei mit anschließendem Umbenennen, damit eine Ordnerüberwachung nie halbe PDFs sieht; vorher wird auf mindestens 256 MiB freien Speicher geprüft.

## Grenzen und Diagnose

- Ein Scan oder Stapel darf höchstens 512 MiB groß sein. Der Farbmodus wird gegen die Fähigkeiten der gewählten Quelle geprüft.
- **Diagnose-Download** in Home Assistant (Geräte & Dienste → Integration → ⋮) ohne Token, URL, Host und Scanner-UUID. Hilfreich für einen Fehlerbericht.
- Logs: Logger `custom_components.ha_airscan`.
