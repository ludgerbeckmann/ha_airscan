"""Switch: should feeder scans started from external buttons be two-sided?"""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import AirscanConfigEntry
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Only for scanners that can scan both sides."""
    if entry.runtime_data.capabilities.adf_duplex is not None:
        async_add_entities([DuplexSwitch(entry)])


class DuplexSwitch(RestoreEntity, SwitchEntity):
    """On = a feeder scan started by an external button is two-sided."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "duplex_default"

    def __init__(self, entry: AirscanConfigEntry) -> None:
        self._tracker = entry.runtime_data.tracker
        self._attr_unique_id = f"{entry.unique_id}_duplex_default"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            model=entry.runtime_data.capabilities.model,
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last setting and follow changes (an external button can toggle it)."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None:
            self._tracker.duplex_default = last.state == "on"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._tracker.signal, self.async_write_ha_state)
        )

    @property
    def is_on(self) -> bool:
        """Two-sided by default."""
        return self._tracker.duplex_default

    async def async_turn_on(self, **kwargs) -> None:
        """Two-sided."""
        self._tracker.duplex_default = True
        self._tracker.update()

    async def async_turn_off(self, **kwargs) -> None:
        """One-sided."""
        self._tracker.duplex_default = False
        self._tracker.update()
