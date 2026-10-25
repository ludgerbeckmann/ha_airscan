# AirScan (eSCL) – Home Assistant Integration

Scannt über das Netzwerk (eSCL/AirScan, z. B. Epson-Multifunktionsgeräte) und legt das Ergebnis standardmäßig als PDF in **Paperless-ngx** ab.

- Flachbett, Dokumenteneinzug (ADF) einseitig und beidseitig (Duplex)
- Mehrseitige ADF-Scans werden zu **einem** PDF zusammengefasst (JPEG ohne Neukodierung)
- Zeroconf-Erkennung (`_uscan._tcp` / `_uscans._tcp`) oder manuelle Einrichtung
- Entitäten: je Quelle ein Button, Status-Sensor
- Service `airscan.scan` mit Antwort (`pages`, `task_id`) und Event `airscan_scan_finished`

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
- Nicht mit echter Hardware getestet; bei Problemen bitte Modell und `http://<ip>/eSCL/ScannerCapabilities` in einem Issue anhängen.
