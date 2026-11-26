# Security policy

## Supported versions
Only the latest release receives fixes.

## Reporting a vulnerability
Please report a vulnerability privately through GitHub's
[private vulnerability reporting](https://github.com/ludgerbeckmann/ha_airscan/security/advisories/new)
instead of opening a public issue. Include the version, a short description,
and how to reproduce it. Remove private details (addresses, tokens, document
contents) from any logs first.

## Scope
Scan to Paperless is a Home Assistant integration that runs inside your Home
Assistant and talks to two things you configure: a network scanner (eSCL/AirScan,
plain HTTP or HTTPS without authentication, certificates of the scanner are not
verified because they are self-signed) and your Paperless-ngx server (API token).
It has no cloud service and sends no telemetry.

- The Paperless API token and URL are stored in the Home Assistant config entry
  (like any integration); diagnostics downloads redact token, URLs, host and
  webhook ID.
- Scans that could not be delivered wait unencrypted in
  `config/ha_airscan_outbox/` until Paperless is reachable.
- The optional Paperless webhook accepts requests from the local network only;
  its ID in the address acts as the secret, so treat it like a password.
- The dashboard card is served from the integration and talks to Home Assistant
  through its normal frontend connection only.
