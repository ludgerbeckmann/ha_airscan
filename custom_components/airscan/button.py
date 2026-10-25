"""Scan and batch buttons."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import AirscanConfigEntry
from .const import DOMAIN
from .scan import async_batch_add, async_batch_discard, async_batch_send, async_scan


@dataclass(frozen=True, kw_only=True)
class AirscanButtonDescription(ButtonEntityDescription):
    """One button: which capability it needs and what it runs."""

    needs: str  # attribute of Capabilities
    action: Callable[[HomeAssistant, AirscanConfigEntry], Awaitable]


BUTTONS = (
    AirscanButtonDescription(
        key="platen", translation_key="scan_platen", needs="platen",
        action=lambda h, e: async_scan(h, e, source="platen"),
    ),
    AirscanButtonDescription(
        key="adf_simplex", translation_key="scan_adf_simplex", needs="adf_simplex",
        action=lambda h, e: async_scan(h, e, source="adf"),
    ),
    AirscanButtonDescription(
        key="adf_duplex", translation_key="scan_adf_duplex", needs="adf_duplex",
        action=lambda h, e: async_scan(h, e, source="adf", duplex=True),
    ),
    AirscanButtonDescription(
        key="batch_add", translation_key="batch_add", needs="platen",
        action=lambda h, e: async_batch_add(h, e),
    ),
    AirscanButtonDescription(
        key="batch_send", translation_key="batch_send", needs="platen",
        action=lambda h, e: async_batch_send(h, e),
    ),
    AirscanButtonDescription(
        key="batch_discard", translation_key="batch_discard", needs="platen",
        action=lambda h, e: async_batch_discard(h, e),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the buttons the scanner supports."""
    caps = entry.runtime_data.capabilities
    async_add_entities(
        AirscanButton(entry, d) for d in BUTTONS if getattr(caps, d.needs) is not None
    )


class AirscanButton(ButtonEntity):
    """Runs a scan or batch action with the entry defaults."""

    _attr_has_entity_name = True
    entity_description: AirscanButtonDescription

    def __init__(self, entry: AirscanConfigEntry, description: AirscanButtonDescription) -> None:
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id)},
            name=entry.title,
            model=entry.runtime_data.capabilities.model,
        )

    async def async_press(self) -> None:
        """Run the action."""
        await self.entity_description.action(self.hass, self._entry)
