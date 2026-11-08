# Externe Taster

Zurück zur [Übersicht](../README.md).

Ein Taster oder eine Fernbedienung kann Scans starten, ohne Automation: *Konfigurieren* → *Externe Taster*. Zuerst die Quelle wählen, danach jedem Wert eine Aktion zuordnen:

| Aktion | Wirkung |
|---|---|
| Einzug scannen | scannt den Einzug, beidseitig oder einseitig je nach Schalter „Einzug beidseitig (Taster)“ |
| Flachbett scannen | legt eine Seite in den Stapel |
| Beidseitig umschalten | stellt den Schalter „Einzug beidseitig (Taster)“ um (der Zustand bleibt auch nach einem Neustart erhalten) |
| Stapel senden / verwerfen | wie die Buttons |

## Quelle: MQTT-Thema oder Entität

Trage nur einen der beiden Wege ein:

- **MQTT-Thema** (empfohlen bei Zigbee2MQTT): `zigbee2mqtt/<Gerätename>/action`, z. B. `zigbee2mqtt/Ikea Fernbedienung/action`. Zigbee2MQTT legt für die „Action“ **standardmäßig keine Entität** an (beide Einstellungen `legacy_action_sensor` und `experimental_event_entities` stehen auf „aus“), es veröffentlicht den Tastendruck nur auf diesem Thema und als MQTT-Gerätetrigger. Das Thema funktioniert deshalb ohne jede Änderung an Zigbee2MQTT. Voraussetzung ist die MQTT-Integration in Home Assistant und die Ausgabe `output: json` (Standard).
- **Entität:** für ZHA, Matter oder Zigbee2MQTT mit eingeschalteten Event-Entitäten (`homeassistant: experimental_event_entities: true` in der Zigbee2MQTT-Konfiguration, danach Neustart). Unterstützt werden `event`- und `sensor`-Entitäten.

## Beispiel: IKEA TRADFRI open/close remote (E1766)

Über Zigbee2MQTT: Thema `zigbee2mqtt/<Gerätename>/action` eintragen (der Gerätename steht in Zigbee2MQTT). Das Gerät meldet laut Zigbee2MQTT die Werte `open`, `close` und `stop`. Sinnvolle Belegung: `open` → *Einzug scannen*, `close` → *Flachbett scannen*. Welche Bedienung `stop` (oder einen anderen Wert) sendet, etwa ein langer Druck, siehst du in Zigbee2MQTT unter *Expose-Funktionen → Action*, während du die Taste drückst. Diesen Wert kannst du auf *Beidseitig umschalten* legen.

## Verhalten

- Beim MQTT-Thema zählt jede Nachricht als Tastendruck; eine leere Nachricht (Zurücksetzen) ist keiner.
- Ein Neustart von Home Assistant oder des Brokers löst keinen Scan aus; derselbe Wert innerhalb einer Sekunde zählt nur einmal.
- Läuft schon ein Scan, wird der Tastendruck ignoriert (steht im Log). Fehlgeschlagene Scans melden sich wie gewohnt über Status und [Benachrichtigungen](benachrichtigungen.md).
