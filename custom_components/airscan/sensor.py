"""Scanner status sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AirscanConfigEntry
from .const import DOMAIN

STATES = ["idle", "processing", "testing", "stopped", "down"]


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the status sensor."""
    async_add_entities([ScannerStatusSensor(entry)])


class ScannerStatusSensor(CoordinatorEntity, SensorEntity):
    """eSCL scanner state."""

    _attr_has_entity_name = True
    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATES

    def __init__(self, entry: AirscanConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.unique_id}_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            model=entry.runtime_data.capabilities.model,
        )

    @property
    def native_value(self) -> str | None:
        """Current state."""
        state = self.coordinator.data.state.lower()
        return state if state in STATES else None

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """ADF state (e.g. ScannerAdfLoaded / ScannerAdfEmpty)."""
        return {"adf_state": self.coordinator.data.adf_state}
