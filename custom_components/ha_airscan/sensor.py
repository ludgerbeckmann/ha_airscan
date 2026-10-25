"""Status, page counter and feeder sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import AirscanConfigEntry
from .const import DOMAIN
from .state import STATUSES

ADF_STATES = {"scanneradfloaded": "loaded", "scanneradfempty": "empty"}


def _device(entry: AirscanConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title,
        model=entry.runtime_data.capabilities.model,
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add sensors."""
    entities: list[SensorEntity] = [JobStatusSensor(entry), PagesSensor(entry)]
    caps = entry.runtime_data.capabilities
    if caps.adf_simplex or caps.adf_duplex:
        entities.append(FeederSensor(entry))
    async_add_entities(entities)


class _TrackerSensor(SensorEntity):
    """Sensor pushed by the ScanTracker."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: AirscanConfigEntry, key: str) -> None:
        self._tracker = entry.runtime_data.tracker
        self._attr_unique_id = f"{entry.unique_id}_{key}"
        self._attr_device_info = _device(entry)

    async def async_added_to_hass(self) -> None:
        """Subscribe to tracker updates."""
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._tracker.signal, self.async_write_ha_state)
        )


class JobStatusSensor(_TrackerSensor):
    """idle / batch / running / done / error with a detail text."""

    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES

    def __init__(self, entry: AirscanConfigEntry) -> None:
        super().__init__(entry, "status")

    @property
    def native_value(self) -> str:
        """Current job status."""
        return self._tracker.status

    @property
    def extra_state_attributes(self) -> dict[str, str | int]:
        """Detail text and batch size."""
        return {"detail": self._tracker.detail, "batch_pages": len(self._tracker.batch)}


class PagesSensor(_TrackerSensor):
    """Pages of the running/last job, or of the open batch."""

    _attr_translation_key = "pages"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: AirscanConfigEntry) -> None:
        super().__init__(entry, "pages")

    @property
    def native_value(self) -> int:
        """Page count."""
        return self._tracker.pages


class FeederSensor(CoordinatorEntity, SensorEntity):
    """Document feeder: loaded / empty (as reported by the printer)."""

    _attr_has_entity_name = True
    _attr_translation_key = "feeder"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["loaded", "empty"]

    def __init__(self, entry: AirscanConfigEntry) -> None:
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.unique_id}_feeder"
        self._attr_device_info = _device(entry)

    @property
    def native_value(self) -> str | None:
        """Feeder state; may be stale after standby (a scan refreshes it)."""
        return ADF_STATES.get((self.coordinator.data.adf_state or "").lower())

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        """Raw eSCL states."""
        return {
            "scanner_state": self.coordinator.data.state,
            "adf_state": self.coordinator.data.adf_state,
        }
