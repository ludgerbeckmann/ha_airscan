"""Delivery queue: keep scans safe while Paperless is unreachable and retry later."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import partial
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import EVENT_QUEUE_DELIVERED
from .outbox_store import OutboxStore, next_delay
from .paperless import PaperlessError
from .scan import wait_for_paperless

if TYPE_CHECKING:
    from . import AirscanConfigEntry, AirscanData

_LOGGER = logging.getLogger(__name__)
STARTUP_DELAY = 30


class Outbox:
    """Persistent queue of PDFs waiting for Paperless, with automatic retries."""

    def __init__(self, hass: HomeAssistant, path: Path, notify: Callable[[], None]) -> None:
        self._hass = hass
        self._store = OutboxStore(path)
        self._notify = notify            # tells the entities that the queue changed
        self._lock = asyncio.Lock()
        self._timer: CALLBACK_TYPE | None = None
        self._failures = 0
        self.items: list[dict] = []
        self.next_retry: datetime | None = None
        self.data: AirscanData | None = None   # set once the entry's runtime data exists

    @property
    def pending(self) -> list[dict]:
        """Items that will be retried."""
        return [i for i in self.items if not i.get("rejected")]

    @property
    def rejected(self) -> list[dict]:
        """Items Paperless refused for good; kept on disk for manual handling."""
        return [i for i in self.items if i.get("rejected")]

    async def async_load(self) -> None:
        """Read the queue from disk (after a restart)."""
        self.items = await self._hass.async_add_executor_job(self._store.load)

    async def async_add(self, pdf: bytes, meta: dict, error: str) -> dict:
        """Store a PDF that could not be uploaded."""
        item = await self._hass.async_add_executor_job(
            self._store.add, pdf, {**meta, "attempts": 1, "last_error": error}
        )
        self.items.append(item)
        self._notify()
        return item

    @callback
    def async_schedule(self, delay: int) -> None:
        """(Re)arm the retry timer."""
        self.async_cancel()
        if not self.pending:
            return
        self.next_retry = dt_util.utcnow() + timedelta(seconds=delay)
        self._timer = async_call_later(self._hass, delay, self._on_timer)
        self._notify()

    @callback
    def async_cancel(self) -> None:
        """Stop the retry timer."""
        if self._timer:
            self._timer()
            self._timer = None
        self.next_retry = None

    async def _on_timer(self, _now) -> None:
        self._timer = None
        self.next_retry = None
        await self.async_deliver()

    def _status(self, detail: str, status: str | None = None) -> None:
        """Update the status sensor, but never overwrite a running scan or an open batch."""
        data = self.data
        if data and data.tracker.status in ("queued", "done", "idle", "error"):
            data.tracker.update(status or "queued", detail)

    async def async_deliver(self) -> dict:
        """Try to upload everything that is waiting. Stops at the first connection problem."""
        data = self.data
        delivered = 0
        if data.paperless is None:
            self._status("Paperless ist nicht konfiguriert – Warteschlange wartet")
            return {"delivered": 0, "remaining": len(self.pending), "rejected": len(self.rejected)}
        async with self._lock:
            self.async_cancel()
            for item in list(self.pending):
                pdf = await self._hass.async_add_executor_job(self._store.read_pdf, item["id"])
                try:
                    info = {
                        "task_id": await data.paperless.upload(
                            pdf, item["filename"], title=item.get("title"), tags=item.get("tags"),
                            correspondent=item.get("correspondent"), document_type=item.get("document_type"),
                        )
                    }
                    await wait_for_paperless(data, info)
                except PaperlessError as err:
                    if err.retryable:
                        self._failures += 1
                        await self._hass.async_add_executor_job(
                            partial(
                                self._store.update, item,
                                attempts=item.get("attempts", 0) + 1, last_error=str(err),
                            )
                        )
                        _LOGGER.warning("Paperless still unreachable (%s), %s scan(s) waiting", err, len(self.pending))
                        break
                    await self._reject(item, str(err))
                    continue
                except HomeAssistantError as err:   # Paperless refused the document while processing
                    if "duplicate" in str(err).lower():
                        info = {}                    # it is already there: counts as delivered
                    else:
                        await self._reject(item, str(err))
                        continue
                self._failures = 0
                delivered += 1
                await self._hass.async_add_executor_job(self._store.remove, item["id"])
                self.items.remove(item)
                self._hass.bus.async_fire(
                    EVENT_QUEUE_DELIVERED,
                    {"title": item.get("title"), "document_id": info.get("document_id")},
                )
            pending = len(self.pending)
            if pending:
                delay = next_delay(self._failures or 1)
                self.async_schedule(delay)
                self._status(f"Paperless nicht erreichbar – {pending} Scan(s) warten, nächster Versuch in {delay // 60} min")
            elif delivered:
                self._status(f"{delivered} Scan(s) aus der Warteschlange an Paperless übertragen", "done")
            self._notify()
        return {"delivered": delivered, "remaining": len(self.pending), "rejected": len(self.rejected)}

    async def _reject(self, item: dict, reason: str) -> None:
        await self._hass.async_add_executor_job(
            partial(self._store.update, item, rejected=True, last_error=reason)
        )
        _LOGGER.error("Paperless refused '%s' for good: %s (file kept in %s)", item.get("title"), reason, self._store.path)
        self._status(f"Paperless lehnt ein Dokument ab: {reason}", "error")


async def async_retry_queue(hass: HomeAssistant, entry: AirscanConfigEntry) -> dict:
    """Service: try to deliver the queue right now."""
    return await entry.runtime_data.outbox.async_deliver()
