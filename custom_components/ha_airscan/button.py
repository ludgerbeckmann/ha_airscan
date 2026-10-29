"""Scan and batch buttons."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers import entity_registry as er

from . import AirscanConfigEntry
from .const import DOMAIN
from .delivery import async_retry_queue
from .scan import async_batch_add, async_batch_discard, async_batch_send, async_scan


@dataclass(frozen=True, kw_only=True)
class AirscanButtonDescription(ButtonEntityDescription):
    """One button: which capability it needs and what it runs."""

    needs: str | None  # attribute of Capabilities, None = always available
    action: Callable[[HomeAssistant, AirscanConfigEntry], Awaitable]


BUTTONS = (
    AirscanButtonDescription(
        key="platen", translation_key="scan_platen", needs="platen",
        action=lambda h, e: async_batch_add(h, e),
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
        key="batch_send", translation_key="batch_send", needs="platen",
        action=lambda h, e: async_batch_send(h, e),
    ),
    AirscanButtonDescription(
        key="batch_discard", translation_key="batch_discard", needs="platen",
        action=lambda h, e: async_batch_discard(h, e),
    ),
    AirscanButtonDescription(
        key="retry_queue", translation_key="retry_queue", needs=None,
        action=lambda h, e: async_retry_queue(h, e),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: AirscanConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the buttons the scanner supports."""
    caps = entry.runtime_data.capabilities
    # "Seite hinzufügen" was merged into "Scan Flachbett"; drop the obsolete entity.
    registry = er.async_get(hass)
    if old := registry.async_get_entity_id("button", DOMAIN, f"{entry.unique_id}_batch_add"):
        registry.async_remove(old)
    async_add_entities(
        AirscanButton(entry, d) for d in BUTTONS if d.needs is None or getattr(caps, d.needs) is not None
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
