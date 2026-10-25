"""Scan buttons."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AirscanConfigEntry
from .const import DOMAIN
from .scan import async_scan


@dataclass(frozen=True, kw_only=True)
class ScanButtonDescription(ButtonEntityDescription):
    """Describes one scan mode."""

    source: str
    duplex: bool = False


BUTTONS = (
    ScanButtonDescription(key="platen", translation_key="scan_platen", source="platen"),
    ScanButtonDescription(key="adf_simplex", translation_key="scan_adf_simplex", source="adf"),
    ScanButtonDescription(
        key="adf_duplex", translation_key="scan_adf_duplex", source="adf", duplex=True
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add buttons for the sources the scanner supports."""
    caps = entry.runtime_data.capabilities
    supported = {
        "platen": caps.platen,
        "adf_simplex": caps.adf_simplex,
        "adf_duplex": caps.adf_duplex,
    }
    async_add_entities(
        ScanButton(entry, d) for d in BUTTONS if supported[d.key] is not None
    )


class ScanButton(ButtonEntity):
    """Starts a scan with the entry's default settings."""

    _attr_has_entity_name = True
    entity_description: ScanButtonDescription

    def __init__(self, entry: AirscanConfigEntry, description: ScanButtonDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            manufacturer="eSCL",
            model=entry.runtime_data.capabilities.model,
        )

    async def async_press(self) -> None:
        """Scan."""
        d = self.entity_description
        await async_scan(
            self.hass,
            self._entry,
            source=d.source,
            duplex=d.duplex,
            destination="paperless",
        )
