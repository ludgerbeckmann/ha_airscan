"""Diagnostics for bug reports."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import AirscanConfigEntry
from .const import CONF_PAPERLESS_TOKEN, CONF_PAPERLESS_URL

TO_REDACT = {CONF_HOST, CONF_PAPERLESS_TOKEN, CONF_PAPERLESS_URL, "uuid"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AirscanConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics (no token, URL, host or scanner UUID)."""
    data = entry.runtime_data
    status = data.coordinator.data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "capabilities": async_redact_data(asdict(data.capabilities), TO_REDACT),
        "scanner_status": asdict(status) if status else None,
        "queue": {
            "pending": len(data.outbox.pending),
            "rejected": len(data.outbox.rejected),
            "attempts": [i.get("attempts") for i in data.outbox.items],
            "errors": [i.get("last_error") for i in data.outbox.items],
        },
        "job": {
            "status": data.tracker.status,
            "detail": data.tracker.detail,
            "pages": data.tracker.pages,
            "batch_pages": len(data.tracker.batch),
        },
    }
