"""Config flow for AirScan."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    COLOR_MODES,
    CONF_BATCH_AUTO_SEND,
    CONF_BATCH_TIMEOUT,
    CONF_COLOR_MODE,
    CONF_CORRESPONDENT,
    CONF_DOCUMENT_TYPE,
    CONF_PAPERLESS_TOKEN,
    CONF_PAPERLESS_URL,
    CONF_RESOLUTION,
    CONF_ROOT,
    CONF_TAGS,
    CONF_TLS,
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_COLOR_MODE,
    DEFAULT_PORT,
    DEFAULT_RESOLUTION,
    DEFAULT_ROOT,
    DOMAIN,
)
from .escl import EsclClient, EsclError
from .paperless import PaperlessAuthError, PaperlessClient, PaperlessError


def _options_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_PAPERLESS_URL, default=d.get(CONF_PAPERLESS_URL, "")): str,
            vol.Optional(CONF_PAPERLESS_TOKEN, default=d.get(CONF_PAPERLESS_TOKEN, "")): str,
            vol.Optional(CONF_TAGS, default=d.get(CONF_TAGS, "")): str,
            vol.Optional(CONF_CORRESPONDENT, default=d.get(CONF_CORRESPONDENT, "")): str,
            vol.Optional(CONF_DOCUMENT_TYPE, default=d.get(CONF_DOCUMENT_TYPE, "")): str,
            vol.Optional(
                CONF_RESOLUTION, default=d.get(CONF_RESOLUTION, DEFAULT_RESOLUTION)
            ): vol.All(vol.Coerce(int), vol.Range(min=75, max=1200)),
            vol.Optional(
                CONF_COLOR_MODE, default=d.get(CONF_COLOR_MODE, DEFAULT_COLOR_MODE)
            ): vol.In(COLOR_MODES),
            vol.Optional(
                CONF_BATCH_TIMEOUT, default=d.get(CONF_BATCH_TIMEOUT, DEFAULT_BATCH_TIMEOUT)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
            vol.Optional(
                CONF_BATCH_AUTO_SEND, default=d.get(CONF_BATCH_AUTO_SEND, False)
            ): bool,
        }
    )


async def _validate_paperless(hass: HomeAssistant, user_input: dict[str, Any]) -> str | None:
    """Return an error key or None."""
    url = user_input.get(CONF_PAPERLESS_URL, "").strip()
    token = user_input.get(CONF_PAPERLESS_TOKEN, "").strip()
    if not url and not token:
        return None
    if not url or not token:
        return "paperless_incomplete"
    try:
        await PaperlessClient(async_get_clientsession(hass), url, token).check()
    except PaperlessAuthError:
        return "invalid_auth"
    except PaperlessError:
        return "cannot_connect"
    return None


class AirscanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._title = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Options flow."""
        return AirscanOptionsFlow()

    async def _probe(self) -> str | None:
        """Query the scanner, set unique id. Returns error key or None."""
        client = EsclClient(
            async_get_clientsession(self.hass, verify_ssl=False),
            self._data[CONF_HOST],
            self._data[CONF_PORT],
            self._data[CONF_TLS],
            self._data[CONF_ROOT],
        )
        try:
            caps = await client.capabilities()
        except EsclError:
            return "cannot_connect"
        await self.async_set_unique_id(caps.uuid or self._data[CONF_HOST])
        self._abort_if_unique_id_configured(updates=self._data)
        self._title = self._title or caps.model or self._data[CONF_HOST]
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manual setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {
                CONF_HOST: user_input[CONF_HOST].strip(),
                CONF_PORT: user_input[CONF_PORT],
                CONF_TLS: user_input[CONF_TLS],
                CONF_ROOT: DEFAULT_ROOT,
            }
            self._title = user_input.get(CONF_NAME, "")
            if not (error := await self._probe()):
                return await self.async_step_paperless()
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_TLS, default=False): bool,
                    vol.Optional(CONF_NAME, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """Discovered via _uscan(s)._tcp."""
        props = discovery_info.properties
        self._data = {
            CONF_HOST: str(discovery_info.ip_address),
            CONF_PORT: discovery_info.port or DEFAULT_PORT,
            CONF_TLS: discovery_info.type.startswith("_uscans"),
            CONF_ROOT: props.get("rs") or DEFAULT_ROOT,
        }
        self._title = props.get("ty") or discovery_info.name.split(".")[0]
        if uuid := props.get("UUID"):
            await self.async_set_unique_id(uuid)
            self._abort_if_unique_id_configured(updates=self._data)
        if error := await self._probe():
            return self.async_abort(reason=error)
        self.context["title_placeholders"] = {"name": self._title}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm a discovered scanner."""
        if user_input is not None:
            return await self.async_step_paperless()
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": self._title}
        )

    async def async_step_paperless(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Paperless and scan defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await _validate_paperless(self.hass, user_input)):
                return self.async_create_entry(
                    title=self._title, data=self._data, options=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="paperless",
            data_schema=_options_schema(user_input or {}),
            errors=errors,
        )


class AirscanOptionsFlow(OptionsFlow):
    """Edit Paperless and scan defaults."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (error := await _validate_paperless(self.hass, user_input)):
                return self.async_create_entry(data=user_input)
            errors["base"] = error
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or dict(self.config_entry.options)),
            errors=errors,
        )
