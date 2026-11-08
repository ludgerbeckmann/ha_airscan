# Benachrichtigungen

Zurück zur [Übersicht](../README.md).

Einstellungen → Geräte & Dienste → Scan to Paperless → *Konfigurieren* → *Benachrichtigungen*. Ohne ein Ziel wird nichts gesendet.

## Ziele

Beliebig viele Benachrichtigungsdienste (z. B. `mobile_app_mein_iphone`, Telegram), „Benachrichtigung in Home Assistant“ (Seitenleiste) und Benachrichtigungs-Entitäten (`notify.*`). Ein Ziel, das einmal nicht antwortet, hält die anderen nicht auf. Mit **„Testnachricht senden“** prüfst du die Ziele sofort.

Nur die Home-Assistant-App bekommt die Zusatzfelder (Link, Priorität „zeitkritisch“, Knöpfe); andere Dienste bekommen nur Titel und Text.

## Scan-Meldungen

Einzeln wählbar: Scan fertig, Scan fehlgeschlagen, Scan wartet auf Paperless, Warteschlange zugestellt, Stapel vergessen, Drucker nicht erreichbar. Vorbelegt sind Fehler, Warteschlange, vergessener Stapel und Drucker offline.

Die Meldung „Stapel vergessen“ hat in der Home-Assistant-App die Knöpfe **Senden** und **Verwerfen**, die direkt den Stapel verarbeiten.

## Paperless-Meldungen per Webhook

Neue Dokumente und Fristen aus Paperless-ngx lassen sich ebenfalls melden: Option einschalten, die angezeigte Adresse in Paperless-ngx bei einem Workflow als Aktion „Webhook“ eintragen (POST, JSON). Erkannt werden die Felder `typ` (`neu` oder `frist`), `korrespondent`, `titel`, `dokumenttyp`, `belegdatum` und `url`; auch die englischen Namen (`type`, `correspondent`, `title`, `document_type`) funktionieren. Wählbar ist, ob neue Dokumente, Fristen oder beides gemeldet werden. Der Webhook ist nur aus dem lokalen Netz erreichbar. Fristen kommen als „zeitkritisch“ an.

**Eine bestehende Automation ablösen:** Hast du die Meldungen bisher mit einer Automation auf einen Webhook gebaut, trage dieselbe **Webhook-ID** (den hinteren Teil der Adresse `…/api/webhook/<ID>`) in den Optionen ein, nachdem du die Automation **ausgeschaltet** hast. Dann musst du in Paperless nichts ändern. Titel und Text lauten „Paperless ngx: Neues Dokument“ bzw. „Paperless ngx: Frist“.
