# Referenz: Entitäten, Dienste, Ereignisse

Zurück zur [Übersicht](../README.md).

## Entitäten

| Entität | Beschreibung |
|---|---|
| Buttons | Scan Flachbett / Einzug (einseitig) / Einzug (beidseitig), Stapel senden / verwerfen, Warteschlange jetzt senden, Testnachricht senden (Konfiguration) |
| Sensor *Status* | `idle` (Bereit), `batch` (Stapel offen), `running` (Läuft), `done` (Fertig), `queued` (Wartet auf Paperless), `error` (Fehler) |
| Sensor *Letzter Scan* | Zeitpunkt, an dem der letzte Scan abgeschlossen wurde (bleibt nach einem Neustart erhalten) |
| Sensor *Warteschlange* | Anzahl der Scans, die auf Paperless warten (Attribute: Fehlergrund, nächster Versuch) |
| Sensor *Seiten* | Seiten des laufenden/letzten Jobs bzw. des offenen Stapels |
| Sensor *Einzug* | `loaded`, `empty`, `processing` (während des Scans), `jam`, `cover_open`, `error` laut Drucker (`loaded`/`empty` kann nach Standby veraltet sein) |
| Schalter *Einzug beidseitig (Taster)* | Ob Einzug-Scans von [externen Tastern](externe-taster.md) beidseitig sind |

Attribute des Status-Sensors: `detail` (Klartext), `pages`, `batch_pages`, `batch_expires_at`, `batch_auto_send`, `notice` / `notice_at`, `duplex_default`, `printer_online`, `printer_state`, `paperless_url`, `settings` (Standardwerte der Integration) sowie zum letzten Scan `source` (`platen`/`adf`/`adf_duplex`), `destination`, `document_id`, `blank_removed`, `finished_at`.

## Dienste

| Dienst | Zweck |
|---|---|
| `ha_airscan.scan` | Scan starten: `source` (`platen`/`adf`), `duplex`, `resolution`, `color_mode`, `page_size`, `skip_blank`, `destination` (`paperless`/`file`), `title`, `tags`, `correspondent`, `document_type`, `directory` |
| `ha_airscan.batch_add` | Eine Flachbett-Seite in den Stapel scannen |
| `ha_airscan.batch_send` | Stapel als ein PDF senden |
| `ha_airscan.batch_discard` | Stapel verwerfen |
| `ha_airscan.retry_queue` | Wartende Scans sofort an Paperless senden |
| `ha_airscan.send_test` | Testnachricht an die Benachrichtigungsziele |

Bei mehreren Scannern zusätzlich `config_entry`. Beispiel:

```yaml
action: ha_airscan.scan
data:
  source: adf
  duplex: true
  resolution: 300
  title: Post vom {{ now().strftime('%d.%m.') }}
  tags: "3,7"
```

## Ereignisse

| Ereignis | Wann |
|---|---|
| `ha_airscan_scan_finished` | Ein Scan ist abgeschlossen (auch wenn er in die Warteschlange ging: `queued: true`) |
| `ha_airscan_scan_failed` | Ein Scan ist fehlgeschlagen (`detail`) |
| `ha_airscan_batch_stale` | Ein Stapel wurde vergessen |
| `ha_airscan_queue_delivered` | Ein wartender Scan wurde an Paperless zugestellt |
| `ha_airscan_printer_offline` | Der Drucker antwortet nicht mehr |

## Beispiel: Automation bei Fehler

```yaml
triggers:
  - trigger: state
    entity_id: sensor.epson_et_3950_series_status   # dein Status-Sensor
    to: error
actions:
  - action: notify.notify
    data:
      message: "Scan fehlgeschlagen: {{ state_attr('sensor.epson_et_3950_series_status', 'detail') }}"
```

Einfacher geht es mit den eingebauten [Benachrichtigungen](benachrichtigungen.md).
