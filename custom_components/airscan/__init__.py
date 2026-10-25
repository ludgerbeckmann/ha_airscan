"""AirScan (eSCL) scanner integration with Paperless-ngx upload."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    COLOR_MODES,
    CONF_PAPERLESS_TOKEN,
    CONF_PAPERLESS_URL,
    CONF_ROOT,
    CONF_TLS,
    DEFAULT_ROOT,
    DESTINATIONS,
    DOMAIN,
    SERVICE_SCAN,
    SOURCES,
)
from .escl import Capabilities, EsclClient, EsclError, Status
from .paperless import PaperlessClient
from .scan import async_scan

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BUTTON, Platform.SENSOR]


@dataclass
class AirscanData:
    """Runtime data of one config entry."""

    client: EsclClient
    capabilities: Capabilities
    paperless: PaperlessClient | None
    coordinator: DataUpdateCoordinator[Status]
    lock: asyncio.Lock


type AirscanConfigEntry = ConfigEntry[AirscanData]

SCAN_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry"): cv.string,
        vol.Optional("source", default="platen"): vol.In(SOURCES),
        vol.Optional("duplex", default=False): cv.boolean,
        vol.Optional("resolution"): vol.Coerce(int),
        vol.Optional("color_mode"): vol.In(COLOR_MODES),
        vol.Optional("destination", default="paperless"): vol.In(DESTINATIONS),
        vol.Optional("title"): cv.string,
        vol.Optional("tags"): vol.Any(cv.string, [cv.string]),
        vol.Optional("correspondent"): cv.string,
        vol.Optional("document_type"): cv.string,
        vol.Optional("directory"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: AirscanConfigEntry) -> bool:
    """Set up a scanner."""
    session = async_get_clientsession(hass, verify_ssl=False)  # printers use self-signed certs
    client = EsclClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TLS],
        entry.data.get(CONF_ROOT, DEFAULT_ROOT),
    )
    try:
        capabilities = await client.capabilities()
    except EsclError as err:
        raise ConfigEntryNotReady(str(err)) from err

    async def _update() -> Status:
        try:
            return await client.status()
        except EsclError as err:
            raise UpdateFailed(str(err)) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=entry,
        name=DOMAIN,
        update_method=_update,
        update_interval=timedelta(seconds=30),
    )
    await coordinator.async_config_entry_first_refresh()

    paperless = None
    if entry.options.get(CONF_PAPERLESS_URL) and entry.options.get(CONF_PAPERLESS_TOKEN):
        paperless = PaperlessClient(
            async_get_clientsession(hass),
            entry.options[CONF_PAPERLESS_URL],
            entry.options[CONF_PAPERLESS_TOKEN],
        )

    entry.runtime_data = AirscanData(client, capabilities, paperless, coordinator, asyncio.Lock())
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_SCAN):

        async def _handle_scan(call: ServiceCall) -> dict:
            params = dict(call.data)
            entries = hass.config_entries.async_entries(DOMAIN)
            if (entry_id := params.pop("config_entry", None)) is not None:
                entries = [e for e in entries if e.entry_id == entry_id]
            entries = [e for e in entries if hasattr(e, "runtime_data")]
            if len(entries) != 1:
                raise ServiceValidationError(
                    "Scanner nicht eindeutig – bitte 'config_entry' angeben"
                )
            return await async_scan(hass, entries[0], **params)

        hass.services.async_register(
            DOMAIN,
            SERVICE_SCAN,
            _handle_scan,
            schema=SCAN_SCHEMA,
            supports_response=SupportsResponse.OPTIONAL,
        )
    return True


async def _reload(hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: AirscanConfigEntry) -> bool:
    """Unload a scanner."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not any(
        e.entry_id != entry.entry_id and e.state.value == "loaded"
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        hass.services.async_remove(DOMAIN, SERVICE_SCAN)
    return unloaded
