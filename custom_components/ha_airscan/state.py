"""Job/batch state shared by the entities of one scanner."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

STATUSES = ["idle", "batch", "running", "done", "queued", "error"]


class ScanTracker:
    """Holds status, page counter and the flatbed batch buffer."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self.signal = f"{DOMAIN}_state_{entry_id}"
        self.status = "idle"
        self.detail = "Bereit"
        self.pages = 0
        self.batch: list[bytes] = []
        self.last: dict = {}  # summary of the last finished scan
        self.finished_at: datetime | None = None
        self.batch_expires_at: datetime | None = None
        self.batch_dpi = 300
        self.timer: CALLBACK_TYPE | None = None

    @callback
    def update(
        self, status: str | None = None, detail: str | None = None, pages: int | None = None
    ) -> None:
        """Change state and notify the entities."""
        if status is not None:
            self.status = status
        if detail is not None:
            self.detail = detail
        if pages is not None:
            self.pages = pages
        async_dispatcher_send(self._hass, self.signal)

    @callback
    def cancel_timer(self) -> None:
        """Stop the forgotten-batch timer."""
        if self.timer:
            self.timer()
            self.timer = None
        self.batch_expires_at = None
