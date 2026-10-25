# AirScan (eSCL) – Home Assistant Integration

Scannt über das Netzwerk (eSCL/AirScan, z. B. Epson-Multifunktionsgeräte) und legt das Ergebnis standardmäßig als PDF in **Paperless-ngx** ab.

- Flachbett, Dokumenteneinzug (ADF) einseitig und beidseitig (Duplex)
- Mehrseitige ADF-Scans werden zu **einem** PDF zusammengefasst (JPEG ohne Neukodierung, A4 nach Scanfläche)
- Zeroconf-Erkennung (`_uscan._tcp` / `_uscans._tcp`) oder manuelle Einrichtung; HTTPS mit selbstsigniertem Zertifikat wird akzeptiert
- **Aufwärmlogik für den Einzug:** Meldet der Drucker nach dem Standby fälschlich `ScannerAdfEmpty`, wird bis zu 2× ein winziger Flachbett-Scan (100 dpi, 10×10 mm) gemacht, um den Sensor zu aktualisieren. Liefert ein Scan 0 Seiten, gibt es bis zu 3 Versuche mit Pause.
- Timeouts: Einzug 900 s, Flachbett 180 s; die Seitenzahl wird live aktualisiert
- Immer nur ein Scan gleichzeitig; der eSCL-Job wird danach sauber gelöscht
- **Stapelmodus am Flachbett:** „Seite hinzufügen“ sammelt Seiten im Speicher, „Senden“ baut ein PDF, „Verwerfen“ leert den Speicher. Wird der Stapel länger als X Minuten (Standard 30) nicht angefasst, feuert das Event `airscan_batch_stale` oder – per Option – der Stapel wird automatisch gesendet.
- Dateiname `scan-YYYYMMDD-HHMMSS.pdf`

## Entitäten

| Entität | Beschreibung |
|---|---|
| Buttons | Scan Flachbett / Einzug (einseitig) / Einzug (beidseitig), Stapel: hinzufügen / senden / verwerfen |
| Sensor *Status* | `idle` (Bereit), `batch` (Stapel offen), `running` (Läuft), `done` (Fertig), `error` (Fehler); Attribut `detail` mit Klartext |
| Sensor *Seiten* | Seiten des laufenden/letzten Jobs bzw. des offenen Stapels |
| Sensor *Einzug* | `loaded` / `empty` laut Drucker (kann nach Standby veraltet sein) |

Services: `airscan.scan`, `airscan.batch_add`, `airscan.batch_send`, `airscan.batch_discard`. Events: `airscan_scan_finished`, `airscan_batch_stale`.

Fehler-Benachrichtigung per Automation auf den Statussensor:

```yaml
triggers:
  - trigger: state
    entity_id: sensor.epson_status
    to: error
actions:
  - action: notify.notify
    data:
      message: "Scan fehlgeschlagen: {{ state_attr('sensor.epson_status', 'detail') }}"
```

## Installation

Per HACS als benutzerdefiniertes Repository oder `custom_components/airscan` nach `config/custom_components/` kopieren, HA neu starten, Integration „AirScan“ hinzufügen.

## Paperless

In Paperless unter *Profil → API-Token* ein Token erzeugen. In den Integrationsoptionen URL, Token und optional Standard-Tags/Korrespondent/Dokumenttyp (numerische IDs) eintragen.

## Service-Beispiel

```yaml
action: airscan.scan
data:
  source: adf
  duplex: true
  resolution: 300
  title: Post vom {{ now().strftime('%d.%m.') }}
  tags: "3,7"
```

Mit `destination: file` und `directory: /config/scans` wird stattdessen eine Datei geschrieben (Pfad muss in `allowlist_external_dirs` stehen).

## Hinweise

- Duplex wird per `<scan:Duplex>` angefordert und nur angeboten, wenn der Scanner `AdfDuplexInputCaps` meldet.
- Tipp: Dem Drucker eine DHCP-Reservierung geben; bei neuer IP aktualisiert die Zeroconf-Erkennung die Einrichtung.
- Nicht mit echter Hardware getestet (nur gegen einen simulierten eSCL-Server); bei Problemen bitte Modell und `http://<ip>/eSCL/ScannerCapabilities` in einem Issue anhängen.
