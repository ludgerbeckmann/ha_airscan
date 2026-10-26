# AirScan (eSCL) – Home Assistant Integration

Scannt über das Netzwerk (eSCL/AirScan, z. B. Epson-Multifunktionsgeräte) und legt das Ergebnis standardmäßig als PDF in **Paperless-ngx** ab.

- Flachbett, Dokumenteneinzug (ADF) einseitig und beidseitig (Duplex)
- Mehrseitige ADF-Scans werden zu **einem** PDF zusammengefasst (JPEG ohne Neukodierung, A4 nach Scanfläche)
- Zeroconf-Erkennung (`_uscan._tcp` / `_uscans._tcp`) oder manuelle Einrichtung; HTTPS mit selbstsigniertem Zertifikat wird akzeptiert
- **Aufwärmlogik für den Einzug:** Meldet der Drucker nach dem Standby fälschlich `ScannerAdfEmpty`, wird bis zu 2× ein winziger Flachbett-Scan (100 dpi, 10×10 mm) gemacht, um den Sensor zu aktualisieren. Liefert ein Scan 0 Seiten, gibt es bis zu 3 Versuche mit Pause.
- Timeouts: Einzug 900 s, Flachbett 180 s; die Seitenzahl wird live aktualisiert
- Immer nur ein Scan gleichzeitig; der eSCL-Job wird danach sauber gelöscht
- **Flachbett arbeitet immer mit einem Stapel:** Der Button „Scan Flachbett“ legt die Seite in einen Zwischenspeicher. Beliebig oft wiederholen, dann „Stapel senden“ (ein PDF) oder „Stapel verwerfen“. Wird der Stapel länger als X Minuten (Standard 30) nicht angefasst, feuert das Event `ha_airscan_batch_stale` oder – per Option – er wird automatisch gesendet. Der Einzug scannt dagegen sofort und lädt direkt hoch. Der Service `ha_airscan.scan` mit `source: platen` sendet weiterhin sofort (für Automationen).
- Ziel „Datei“ (z. B. Paperless-Consume-Ordner): Schreiben über eine versteckte Temp-Datei mit anschließendem Umbenennen, damit Ordnerüberwachung nie halbe PDFs sieht; vorher Prüfung auf mindestens 256 MiB freien Speicher
- Grenzen: ein Scan oder Stapel darf höchstens 512 MiB groß sein; der Farbmodus wird gegen die Fähigkeiten der gewählten Quelle geprüft
- Diagnose-Download in HA (Geräte & Dienste → Integration → ⋮) ohne Token, URL, Host und Scanner-UUID
- **Leerseitenerkennung (optional, nur Einzug):** Entfernt leere Seiten, vor allem Rückseiten beim Duplex-Scan, vor dem PDF-Bau. Standardmäßig aus; Schalter und Schwelle in den Optionen, pro Aufruf per `skip_blank` überschreibbar. Gemessen wird der Tintenanteil im Seiteninneren (Rand wird ignoriert); schwaches Durchscheinen der Rückseite zählt nicht als Inhalt, eine ganz dunkle Seite nie als leer. Sind alle Seiten leer, schlägt der Scan mit einer Meldung fehl. Das Glas ist ausgenommen.
- Dateiname `scan-YYYYMMDD-HHMMSS.pdf`

## Entitäten

| Entität | Beschreibung |
|---|---|
| Buttons | Scan Flachbett / Einzug (einseitig) / Einzug (beidseitig), Stapel senden / verwerfen |
| Sensor *Status* | `idle` (Bereit), `batch` (Stapel offen), `running` (Läuft), `done` (Fertig), `error` (Fehler); Attribut `detail` mit Klartext |
| Sensor *Seiten* | Seiten des laufenden/letzten Jobs bzw. des offenen Stapels |
| Sensor *Einzug* | `loaded` / `empty` laut Drucker (kann nach Standby veraltet sein) |

Services: `ha_airscan.scan`, `ha_airscan.batch_add`, `ha_airscan.batch_send`, `ha_airscan.batch_discard`. Events: `ha_airscan_scan_finished`, `ha_airscan_batch_stale`.

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

**HACS (empfohlen):** HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/ludgerbeckmann/ha_airscan`, Kategorie *Integration* → herunterladen → Home Assistant neu starten → *Einstellungen → Geräte & Dienste → Integration hinzufügen → „AirScan (eSCL) Scanner“*.

**Manuell:** `custom_components/ha_airscan` nach `config/custom_components/` kopieren und neu starten.

Die Domain lautet `ha_airscan`. Releases entstehen automatisch: Ein Merge nach `main` mit neuer `version` in der `manifest.json` erzeugt Tag `vX.Y.Z` und GitHub-Release (`.github/workflows/release.yml`), HACS zeigt dann das Update.

## Dashboard

Eine fertige Kachel mit Status, Scan-Buttons, Stapelmodus und Einzugsanzeige liegt in [`examples/dashboard.yaml`](examples/dashboard.yaml). Dashboard bearbeiten → Karte hinzufügen → *Manuell* → Inhalt einfügen und `epson_et_3950_series` durch den eigenen Gerätenamen ersetzen. Es werden nur Standard-Karten verwendet.

## Paperless

In Paperless unter *Profil → API-Token* ein Token erzeugen. In den Integrationsoptionen URL, Token und optional Standard-Tags/Korrespondent/Dokumenttyp (numerische IDs) eintragen.

## Service-Beispiel

```yaml
action: ha_airscan.scan
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
