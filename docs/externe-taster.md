# Externe Taster

Zurück zur [Übersicht](../README.md).

Ein Taster oder eine Fernbedienung kann Scans starten, ohne Automation: *Konfigurieren* → Abschnitt *Externe Taster*. Zuerst die Quelle wählen, dann jedem Wert eine Aktion zuordnen:

| Aktion | Wirkung |
|---|---|
| Einzug scannen | scannt den Einzug, beidseitig oder einseitig je nach Schalter „Einzug beidseitig (Taster)“ |
| Flachbett scannen | legt eine Seite in den Stapel |
| Beidseitig umschalten | stellt den Schalter „Einzug beidseitig (Taster)“ um (der Zustand bleibt auch nach einem Neustart erhalten) |
| Stapel senden / verwerfen | wie die Buttons |

**Umschalten ohne eigene Taste:** Sind „Einzug scannen“ und „Flachbett scannen“ belegt, schaltet **kurz nacheinander beide Tasten drücken** (z. B. `open` und `close`, die Reihenfolge ist egal, innerhalb von etwa 0,8 Sekunden) zwischen beidseitig und einseitig um. Dabei wird nicht gescannt. Der Preis dafür: Ein einzelner Druck auf eine dieser beiden Tasten startet den Scan erst nach diesen 0,8 Sekunden, weil abgewartet wird, ob noch die andere folgt. Die Bestätigung kommt wie beim Umschalten über eine eigene Taste (siehe „Rückmeldung beim Umschalten“).

## Quelle: MQTT-Thema oder Entität

Trage nur einen der beiden Wege ein:

- **MQTT-Thema** (empfohlen bei Zigbee2MQTT): `zigbee2mqtt/<Gerätename>/action`, z. B. `zigbee2mqtt/Ikea Fernbedienung/action`. Zigbee2MQTT legt für die „Action“ **standardmäßig keine Entität** an (beide Einstellungen `legacy_action_sensor` und `experimental_event_entities` stehen auf „aus“), es veröffentlicht den Tastendruck nur auf diesem Thema und als MQTT-Gerätetrigger. Das Thema funktioniert deshalb ohne jede Änderung an Zigbee2MQTT. Voraussetzung ist die MQTT-Integration in Home Assistant und die Ausgabe `output: json` (Standard).
- **Entität:** für ZHA, Matter oder Zigbee2MQTT mit eingeschalteten Event-Entitäten (`homeassistant: experimental_event_entities: true` in der Zigbee2MQTT-Konfiguration, danach Neustart). Unterstützt werden `event`- und `sensor`-Entitäten.

## Beispiel: IKEA TRADFRI open/close remote (E1766)

Über Zigbee2MQTT: Thema `zigbee2mqtt/<Gerätename>/action` eintragen (der Gerätename steht in Zigbee2MQTT). Das Gerät meldet laut Zigbee2MQTT die Werte `open`, `close` und `stop`. Sinnvolle Belegung: `open` → *Einzug scannen*, `close` → *Flachbett scannen*. Welche Bedienung `stop` (oder einen anderen Wert) sendet, etwa ein langer Druck, siehst du in Zigbee2MQTT unter *Expose-Funktionen → Action*, während du die Taste drückst. Diesen Wert kannst du auf *Beidseitig umschalten* legen.

## Verhalten

- Beim MQTT-Thema zählt jede Nachricht als Tastendruck; eine leere Nachricht (Zurücksetzen) ist keiner.
- Ein Neustart von Home Assistant oder des Brokers löst keinen Scan aus; derselbe Wert innerhalb einer Sekunde zählt nur einmal.
- Läuft schon ein Scan, wird der Tastendruck ignoriert (die Meldung „Taster ignoriert“ sagt es dir, steht auch im Log).
- **Automatisch zurück auf einseitig:** In den Optionen (Abschnitt *Scan-Standardwerte*) legst du fest, nach wie vielen Minuten ohne Scan der Einzug wieder auf einseitig zurückfällt (0 = nie). Die Zeit läuft ab dem Einschalten von beidseitig und beginnt mit jedem Scan neu. Das Zurückschalten wird wie ein Umschalten gemeldet (Ereignis `ha_airscan_duplex_toggled` mit `reason: timeout`, Text „… (Zeit abgelaufen)“).
- **Rückmeldung beim Umschalten:** Der Taster selbst zeigt nichts an. Jede Umschaltung löst das Ereignis `ha_airscan_duplex_toggled` aus (`duplex`: `true`/`false`), mit dem du eine Ansage, eine Lampe oder Ähnliches steuern kannst. Dazu gibt es die leise Push-Meldung „Einzug umgestellt“ (in den Benachrichtigungen auswählbar). Fehlgeschlagene Scans melden sich wie gewohnt über Status und [Benachrichtigungen](benachrichtigungen.md).
