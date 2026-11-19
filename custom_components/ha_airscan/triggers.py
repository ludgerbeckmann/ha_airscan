"""External buttons (e.g. an IKEA remote via Zigbee2MQTT) that start scans."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .button_map import Debounce, action_for, topic_value, trigger_value
from .const import CONF_BUTTON_ENTITY, CONF_BUTTON_MAP, CONF_BUTTON_TOPIC, CONF_CHORD_WINDOW, EVENT_BUTTON_REJECTED, EVENT_DUPLEX_TOGGLED
from .scan import ScannerBusy, async_cancel_scan, async_batch_add, async_batch_discard, async_batch_send, async_scan

if TYPE_CHECKING:
    from . import AirscanConfigEntry

_LOGGER = logging.getLogger(__name__)

# Two different scan buttons pressed within this time (either order) switch one-/two-sided instead of scanning.
CHORD_WINDOW = 1.0
CHORD_ACTIONS = ("adf", "platen")


class ButtonTriggers:
    """Watches one button entity and runs the scan action mapped to the value it sends."""

    def __init__(self, hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._debounce = Debounce()
        self._pending: tuple[str, object] | None = None   # first press of a possible two-button chord

    @callback
    def async_start(self) -> None:
        """Subscribe (only if a button source and at least one mapping are configured)."""
        mapping = self._entry.options.get(CONF_BUTTON_MAP) or {}
        if not any(mapping.values()):
            return
        if (entity_id := self._entry.options.get(CONF_BUTTON_ENTITY)):
            self._entry.async_on_unload(async_track_state_change_event(self._hass, [entity_id], self._on_change))
        elif (topic := self._entry.options.get(CONF_BUTTON_TOPIC)):
            self._entry.async_create_background_task(self._hass, self._subscribe_mqtt(topic), "ha_airscan_button_mqtt")

    async def _subscribe_mqtt(self, topic: str) -> None:
        """MQTT topic as the source (Zigbee2MQTT publishes `<device>/action` without any entity)."""
        if not await mqtt.async_wait_for_mqtt_client(self._hass):
            _LOGGER.warning("MQTT is not available, the button topic '%s' is not watched", topic)
            return
        self._entry.async_on_unload(await mqtt.async_subscribe(self._hass, topic, self._on_message))

    @callback
    def _on_message(self, msg) -> None:
        _LOGGER.debug("Button MQTT message on %s: %r", getattr(msg, "topic", "?"), msg.payload)
        self._press(topic_value(msg.payload))

    @callback
    def _on_change(self, event: Event) -> None:
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if new is None:
            return
        _LOGGER.debug("Button entity %s: %r -> %r %s", event.data.get("entity_id"), old.state if old else None, new.state, dict(new.attributes))
        self._press(trigger_value(new.domain, old.state if old else None, new.state, dict(new.attributes)))

    def _press(self, value: str | None) -> None:
        action = action_for(value, self._entry.options.get(CONF_BUTTON_MAP) or {})
        if action is None:
            if value:
                _LOGGER.debug("Button value %r is not assigned to an action", value)
            return
        if not self._debounce.accept(value):
            _LOGGER.debug("Button value %r ignored: the same value arrived less than a second ago (radio retransmission)", value)
            return
        _LOGGER.debug("Button value %r -> %s", value, action)
        mapping = self._entry.options.get(CONF_BUTTON_MAP) or {}
        if action in CHORD_ACTIONS and all(mapping.get(a) for a in CHORD_ACTIONS):
            if self._pending and self._pending[0] != action:   # the other scan button just before: a chord
                _LOGGER.info("Buttons %r and %r pressed together: switching one-/two-sided", self._pending[0], action)
                self._pending = None
                self._hass.async_create_task(self._run("toggle_duplex"))
            else:   # hold it back briefly: it may be the first half of a chord
                token = object()
                _LOGGER.debug("Button action %s: waiting %.1f s in case the other scan button follows", action,
                              float(self._entry.options.get(CONF_CHORD_WINDOW, CHORD_WINDOW)))
                self._pending = (action, token)
                self._hass.async_create_task(self._after_window(action, token))
            return
        _LOGGER.info("Button action %s started", action)
        self._hass.async_create_task(self._run(action))

    async def _after_window(self, action: str, token: object) -> None:
        await asyncio.sleep(float(self._entry.options.get(CONF_CHORD_WINDOW, CHORD_WINDOW)))
        if self._pending and self._pending[1] is token:   # nobody pressed the other button: it was a single press
            self._pending = None
            _LOGGER.info("Button action %s started", action)
            await self._run(action)

    async def _run(self, action: str) -> None:
        data = self._entry.runtime_data
        try:
            if action == "adf":
                duplex = data.tracker.duplex_default and data.capabilities.adf_duplex is not None
                await async_scan(self._hass, self._entry, source="adf", duplex=duplex)
            elif action == "platen":
                await async_batch_add(self._hass, self._entry)
            elif action == "batch_send":
                await async_batch_send(self._hass, self._entry)
            elif action == "batch_discard":
                await async_batch_discard(self._hass, self._entry)
            elif action == "cancel":
                await async_cancel_scan(self._hass, self._entry)
            elif action == "toggle_duplex":
                data.tracker.duplex_default = not data.tracker.duplex_default
                data.tracker.update()
                # the remote has no display: let automations and notifications confirm the new mode
                self._hass.bus.async_fire(EVENT_DUPLEX_TOGGLED, {
                    "entry_id": self._entry.entry_id,
                    "duplex": bool(data.tracker.duplex_default and data.capabilities.adf_duplex is not None),
                })
        except ScannerBusy as err:   # still scanning: tell the user, a button has no screen
            _LOGGER.info("Button action %s ignored: %s", action, err)
            self._hass.bus.async_fire(EVENT_BUTTON_REJECTED, {"entry_id": self._entry.entry_id, "action": action, "detail": str(err)})
        except HomeAssistantError as err:   # failed scans also set the status
            _LOGGER.warning("Button action %s did not run: %s", action, err)
