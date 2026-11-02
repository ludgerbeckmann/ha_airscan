"""Job/batch state shared by the entities of one scanner."""

from __future__ import annotations

from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN

STATUSES = ["idle", "batch", "running", "done", "queued", "error"]
# The printer counts as offline after this many failed status polls in a row (30 s apart),
# so a single slow answer does not raise an alarm.
OFFLINE_AFTER_FAILURES = 2


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
        self.notice = ""                    # e.g. "blank_skipped": something worth a hint, but no error
        self.notice_at: datetime | None = None
        self.duplex_default = False          # feeder scans from external buttons: two-sided?
        self.printer_failures = 0           # consecutive failed status polls
        self.printer_state: str | None = None   # eSCL state: Idle, Processing, Stopped, ...
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
    def set_notice(self, notice: str, now: datetime | None = None) -> None:
        """Remember a hint (shown for a few minutes) or clear it with an empty string."""
        self.notice = notice
        self.notice_at = now if notice else None

    @property
    def printer_online(self) -> bool:
        """False once the printer did not answer several status polls in a row."""
        return self.printer_failures < OFFLINE_AFTER_FAILURES

    @callback
    def cancel_timer(self) -> None:
        """Stop the forgotten-batch timer."""
        if self.timer:
            self.timer()
            self.timer = None
        self.batch_expires_at = None
