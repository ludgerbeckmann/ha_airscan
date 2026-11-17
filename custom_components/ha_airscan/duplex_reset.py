"""Switch back to one-sided feeder scans after a while (option)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later

from .const import CONF_DUPLEX_RESET, EVENT_DUPLEX_TOGGLED

if TYPE_CHECKING:
    from . import AirscanConfigEntry


class DuplexReset:
    """Two-sided is meant to be the exception: after N idle minutes it goes back to one-sided.

    The timer starts when two-sided is switched on (button, switch or the app) and starts
    over with every scan activity, so a pile of documents is never interrupted halfway.
    """

    def __init__(self, hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._cancel: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        """Follow the tracker; everything is cleaned up when the entry unloads."""
        tracker = self._entry.runtime_data.tracker
        self._entry.async_on_unload(async_dispatcher_connect(self._hass, tracker.signal, self._on_state))
        self._entry.async_on_unload(self._stop)
        self._on_state()

    @callback
    def _stop(self) -> None:
        if self._cancel:
            self._cancel()
            self._cancel = None

    @callback
    def _on_state(self) -> None:
        tracker = self._entry.runtime_data.tracker
        minutes = int(self._entry.options.get(CONF_DUPLEX_RESET, 0) or 0)
        if minutes <= 0 or not tracker.duplex_default:
            self._stop()
            return
        if self._cancel and tracker.status != "running":
            return   # already counting down; only scanning restarts the time
        self._stop()
        self._cancel = async_call_later(self._hass, minutes * 60, self._expired)

    async def _expired(self, _now) -> None:
        self._cancel = None
        tracker = self._entry.runtime_data.tracker
        if not tracker.duplex_default:
            return
        tracker.duplex_default = False
        tracker.update()
        self._hass.bus.async_fire(
            EVENT_DUPLEX_TOGGLED, {"entry_id": self._entry.entry_id, "duplex": False, "reason": "timeout"}
        )
