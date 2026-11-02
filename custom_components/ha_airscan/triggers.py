"""External buttons (e.g. an IKEA remote via Zigbee2MQTT) that start scans."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components import mqtt
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from .button_map import Debounce, action_for, topic_value, trigger_value
from .const import CONF_BUTTON_ENTITY, CONF_BUTTON_MAP, CONF_BUTTON_TOPIC
from .scan import async_batch_add, async_batch_discard, async_batch_send, async_scan

if TYPE_CHECKING:
    from . import AirscanConfigEntry

_LOGGER = logging.getLogger(__name__)


class ButtonTriggers:
    """Watches one button entity and runs the scan action mapped to the value it sends."""

    def __init__(self, hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._debounce = Debounce()

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
        self._press(topic_value(msg.payload))

    @callback
    def _on_change(self, event: Event) -> None:
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if new is None:
            return
        self._press(trigger_value(new.domain, old.state if old else None, new.state, dict(new.attributes)))

    def _press(self, value: str | None) -> None:
        action = action_for(value, self._entry.options.get(CONF_BUTTON_MAP) or {})
        if action is None or not self._debounce.accept(value):
            return
        _LOGGER.debug("Button value %r -> %s", value, action)
        self._hass.async_create_task(self._run(action))

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
            elif action == "toggle_duplex":
                data.tracker.duplex_default = not data.tracker.duplex_default
                data.tracker.update()
        except HomeAssistantError as err:   # e.g. a scan is already running; failed scans also set the status
            _LOGGER.warning("Button action %s did not run: %s", action, err)
