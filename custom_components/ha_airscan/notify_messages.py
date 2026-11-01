"""Texts of the notifications (pure logic, no Home Assistant needed)."""

from __future__ import annotations

from typing import Any

SCAN_TYPES = ["scan_done", "scan_error", "queued", "queue_delivered", "batch_stale", "printer_offline"]
PAPERLESS_TYPES = ["neu", "frist"]

_TEXT = {
    "de": {
        "scan_done": ("Scan fertig", "{pages} → {dest}{doc}{blank}"),
        "scan_error": ("Scan fehlgeschlagen", "{detail}"),
        "queued": ("Scan wartet auf Paperless", "{pages} gescannt, Paperless nicht erreichbar. Wird automatisch erneut gesendet ({reason})."),
        "queue_delivered": ("Warteschlange zugestellt", "{title} ist jetzt in Paperless{doc}."),
        "batch_stale": ("Stapel vergessen", "{pages} warten auf dem Flachbett-Stapel: senden oder verwerfen?"),
        "printer_offline": ("Drucker nicht erreichbar", "{detail}"),
        "pages_one": "{n} Seite", "pages_many": "{n} Seiten", "doc": " (Dokument #{id})", "blank": ", {n} Leerseite(n) entfernt",
        "send": "Senden", "discard": "Verwerfen",
        "pl_new": "Paperless ngx: Neues Dokument", "pl_due": "Paperless ngx: Frist",
        "unknown": "unbekannt", "untitled": "ohne Titel", "file": "Datei",
        "offline_detail": "Ist der Drucker eingeschaltet und im Netzwerk?",
    },
    "en": {
        "scan_done": ("Scan finished", "{pages} → {dest}{doc}{blank}"),
        "scan_error": ("Scan failed", "{detail}"),
        "queued": ("Scan waiting for Paperless", "{pages} scanned, Paperless not reachable. Will be sent again automatically ({reason})."),
        "queue_delivered": ("Queue delivered", "{title} is now in Paperless{doc}."),
        "batch_stale": ("Batch forgotten", "{pages} waiting in the flatbed batch: send or discard?"),
        "printer_offline": ("Printer not reachable", "{detail}"),
        "pages_one": "{n} page", "pages_many": "{n} pages", "doc": " (document #{id})", "blank": ", {n} blank page(s) removed",
        "send": "Send", "discard": "Discard",
        "pl_new": "Paperless ngx: New document", "pl_due": "Paperless ngx: Due date",
        "unknown": "unknown", "untitled": "untitled", "file": "file",
        "offline_detail": "Is the printer switched on and on the network?",
    },
}


def _t(lang: str) -> dict:
    return _TEXT["de" if str(lang).lower().startswith("de") else "en"]


def _pages(t: dict, n: Any) -> str:
    n = int(n or 0)
    return t["pages_one" if n == 1 else "pages_many"].format(n=n)


def scan_message(kind: str, data: dict, lang: str = "de") -> dict | None:
    """Build a notification for one of our events; None if the event is not worth a message.

    kind: scan_done | scan_error | queued | queue_delivered | batch_stale | printer_offline
    """
    t = _t(lang)
    title, template = t[kind]
    doc = t["doc"].format(id=data["document_id"]) if data.get("document_id") else ""
    blank = t["blank"].format(n=data["blank_removed"]) if data.get("blank_removed") else ""
    values = {
        "pages": _pages(t, data.get("pages", data.get("batch_pages", 0))),
        "dest": "Paperless" if data.get("destination") == "paperless" else t["file"],
        "doc": doc,
        "blank": blank,
        "detail": str(data.get("detail") or ""),
        "title": data.get("title") or "",
        "reason": str(data.get("queue_error") or "")[:80],
    }
    if kind == "printer_offline" and not values["detail"]:
        values["detail"] = t["offline_detail"]
    return {
        "title": title,
        "message": template.format(**values),
        "tag": f"ha_airscan_{kind}",
        "url": "",
        "time_sensitive": kind in ("scan_error", "batch_stale"),
        "actions": kind == "batch_stale",
    }


def normalize_paperless(payload: dict) -> dict:
    """Map the (German or English) webhook fields of a Paperless workflow to one shape."""
    def pick(*keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    typ = pick("typ", "type").lower()
    return {
        "typ": "frist" if typ in ("frist", "deadline", "due", "due_date") else "neu",
        "korrespondent": pick("korrespondent", "correspondent"),
        "titel": pick("titel", "title"),
        "dokumenttyp": pick("dokumenttyp", "document_type"),
        "belegdatum": pick("belegdatum", "created", "date"),
        "url": pick("url"),
    }


def paperless_message(doc: dict, lang: str = "de") -> dict:
    """Notification for a Paperless webhook (same wording as the former automation)."""
    t = _t(lang)
    due = doc["typ"] == "frist"
    extra = ""
    if doc["dokumenttyp"]:
        extra = f" ({doc['dokumenttyp']}" + (f", {doc['belegdatum']}" if doc["belegdatum"] else "") + ")"
    return {
        "title": t["pl_due" if due else "pl_new"],
        "message": f"{doc['korrespondent'] or t['unknown']}: {doc['titel'] or t['untitled']}{extra}",
        "tag": "Paperless-Frist" if due else "Paperless",
        "url": doc["url"],
        "time_sensitive": due,
        "actions": False,
    }


def action_labels(lang: str = "de") -> tuple[str, str]:
    """Texts of the two buttons of the 'forgotten batch' notification."""
    t = _t(lang)
    return t["send"], t["discard"]
