"""Config flow for AirScan."""

from __future__ import annotations

import logging
import re
import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.components import webhook
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    COLOR_MODES,
    CONF_ADF_ALIGN,
    CONF_BATCH_AUTO_SEND,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_PAPERLESS_TYPES,
    CONF_NOTIFY_SCAN_TYPES,
    CONF_NOTIFY_SERVICES,
    CONF_PAPERLESS_WEBHOOK,
    CONF_PAPERLESS_WEBHOOK_ID,
    DEFAULT_NOTIFY_PAPERLESS_TYPES,
    DEFAULT_NOTIFY_SCAN_TYPES,
    PERSISTENT_NOTIFICATION,
    CONF_BATCH_TIMEOUT,
    CONF_BLANK_DETECTION,
    CONF_BLANK_THRESHOLD,
    CONF_COLOR_MODE,
    CONF_CORRESPONDENT,
    CONF_DOCUMENT_TYPE,
    CONF_PAPERLESS_TOKEN,
    CONF_PAPERLESS_URL,
    CONF_PAPERLESS_VERIFY_SSL,
    CONF_RESOLUTION,
    CONF_PAGE_SIZE,
    CONF_ROOT,
    CONF_TAGS,
    CONF_TLS,
    DEFAULT_ADF_ALIGN,
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_COLOR_MODE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_PORT,
    ADF_ALIGN_OPTIONS,
    PAGE_SIZE_OPTIONS,
    DEFAULT_RESOLUTION,
    DEFAULT_ROOT,
    DOMAIN,
)
from .blank import DEFAULT_INK_PERCENT
from .escl import EsclClient, EsclError
from .notify_messages import PAPERLESS_TYPES, SCAN_TYPES
from .notifications import async_send_test
from .paperless import PaperlessAuthError, PaperlessClient, PaperlessError

_LOGGER = logging.getLogger(__name__)


def _options_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_PAPERLESS_URL, default=d.get(CONF_PAPERLESS_URL, "")): str,
            vol.Optional(CONF_PAPERLESS_TOKEN, default=d.get(CONF_PAPERLESS_TOKEN, "")): str,
            vol.Optional(
                CONF_PAPERLESS_VERIFY_SSL, default=d.get(CONF_PAPERLESS_VERIFY_SSL, True)
            ): bool,
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
                CONF_PAGE_SIZE, default=d.get(CONF_PAGE_SIZE, DEFAULT_PAGE_SIZE)
            ): vol.In(PAGE_SIZE_OPTIONS),
            vol.Optional(
                CONF_ADF_ALIGN, default=d.get(CONF_ADF_ALIGN, DEFAULT_ADF_ALIGN)
            ): vol.In(ADF_ALIGN_OPTIONS),
            vol.Optional(
                CONF_BATCH_TIMEOUT, default=d.get(CONF_BATCH_TIMEOUT, DEFAULT_BATCH_TIMEOUT)
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=1440)),
            vol.Optional(
                CONF_BATCH_AUTO_SEND, default=d.get(CONF_BATCH_AUTO_SEND, False)
            ): bool,
            vol.Optional(
                CONF_BLANK_DETECTION, default=d.get(CONF_BLANK_DETECTION, False)
            ): bool,
            vol.Optional(
                CONF_BLANK_THRESHOLD, default=d.get(CONF_BLANK_THRESHOLD, DEFAULT_INK_PERCENT)
            ): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=5)),
        }
    )


async def _validate_paperless(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[str | None, str]:
    """Return (error key or None, human readable detail)."""
    url = user_input.get(CONF_PAPERLESS_URL, "").strip()
    token = user_input.get(CONF_PAPERLESS_TOKEN, "").strip()
    if not url and not token:
        return None, ""
    if not url or not token:
        return "paperless_incomplete", ""
    session = async_get_clientsession(
        hass, verify_ssl=user_input.get(CONF_PAPERLESS_VERIFY_SSL, True)
    )
    try:
        await PaperlessClient(session, url, token).check()
    except PaperlessAuthError as err:
        return "invalid_auth", str(err)
    except PaperlessError as err:
        _LOGGER.warning("Paperless check against %s failed: %s", url, err)
        return "cannot_connect", str(err)
    return None, ""


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
            error, detail = await _validate_paperless(self.hass, user_input)
            if not error:
                return self.async_create_entry(
                    title=self._title, data=self._data, options=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="paperless",
            data_schema=_options_schema(user_input or {}),
            errors=errors,
            description_placeholders={"error_detail": detail if errors else ""},
        )


def _notify_services(hass: HomeAssistant, current: list[str]) -> list[dict[str, str]]:
    """notify.* services that exist right now (plus what is already selected)."""
    services = hass.services.async_services_for_domain("notify")
    names = sorted(s for s in services if s not in ("send_message", PERSISTENT_NOTIFICATION))
    names += [c for c in current if c not in names and c != PERSISTENT_NOTIFICATION]
    return [{"value": PERSISTENT_NOTIFICATION, "label": "Benachrichtigung in Home Assistant"}] + [
        {"value": n, "label": n} for n in names
    ]


def _notify_schema(hass: HomeAssistant, d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_NOTIFY_SERVICES, default=d.get(CONF_NOTIFY_SERVICES, [])): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_notify_services(hass, d.get(CONF_NOTIFY_SERVICES, [])),
                    multiple=True, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_NOTIFY_ENTITIES, default=d.get(CONF_NOTIFY_ENTITIES, [])): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="notify", multiple=True)
            ),
            vol.Optional(
                CONF_NOTIFY_SCAN_TYPES, default=d.get(CONF_NOTIFY_SCAN_TYPES, DEFAULT_NOTIFY_SCAN_TYPES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SCAN_TYPES, multiple=True, translation_key="notify_scan_types",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_PAPERLESS_WEBHOOK, default=d.get(CONF_PAPERLESS_WEBHOOK, False)): bool,
            vol.Optional(
                CONF_PAPERLESS_WEBHOOK_ID,
                default=d.get(CONF_PAPERLESS_WEBHOOK_ID) or f"paperless_{secrets.token_hex(8)}",
            ): str,
            vol.Optional(
                CONF_NOTIFY_PAPERLESS_TYPES, default=d.get(CONF_NOTIFY_PAPERLESS_TYPES, DEFAULT_NOTIFY_PAPERLESS_TYPES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=PAPERLESS_TYPES, multiple=True, translation_key="notify_paperless_types",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional("send_test", default=False): bool,
        }
    )


def _webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    try:
        return webhook.async_generate_url(hass, webhook_id, prefer_external=False)
    except Exception:  # noqa: BLE001 - no internal/external URL configured
        return f"/api/webhook/{webhook_id}"


class AirscanOptionsFlow(OptionsFlow):
    """Options: scan/Paperless settings and notifications."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Menu."""
        return self.async_show_menu(step_id="init", menu_options=["settings", "notifications"])

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Paperless and scan defaults (merged into the other options)."""
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            error, detail = await _validate_paperless(self.hass, user_input)
            if not error:
                return self.async_create_entry(data={**self.config_entry.options, **user_input})
            errors["base"] = error
        return self.async_show_form(
            step_id="settings",
            data_schema=_options_schema(user_input or dict(self.config_entry.options)),
            errors=errors,
            description_placeholders={"error_detail": detail if errors else ""},
        )

    async def async_step_notifications(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Where to send which message."""
        errors: dict[str, str] = {}
        current = user_input or dict(self.config_entry.options)
        if user_input is not None:
            webhook_id = str(user_input.get(CONF_PAPERLESS_WEBHOOK_ID, "")).strip()
            if user_input.get(CONF_PAPERLESS_WEBHOOK) and not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", webhook_id):
                errors[CONF_PAPERLESS_WEBHOOK_ID] = "invalid_webhook_id"
            else:
                options = {**self.config_entry.options, **{k: v for k, v in user_input.items() if k != "send_test"}}
                options[CONF_PAPERLESS_WEBHOOK_ID] = webhook_id
                if user_input.get("send_test"):
                    failures = await async_send_test(self.hass, options, self.config_entry.entry_id)
                    if failures:
                        errors["base"] = "test_failed"
                if not errors:
                    return self.async_create_entry(data=options)
        schema = _notify_schema(self.hass, current)
        webhook_id = current.get(CONF_PAPERLESS_WEBHOOK_ID) or next(
            (k.default() for k in schema.schema if k == CONF_PAPERLESS_WEBHOOK_ID), ""
        )
        return self.async_show_form(
            step_id="notifications",
            data_schema=schema,
            errors=errors,
            description_placeholders={"webhook_url": _webhook_url(self.hass, webhook_id)},
        )
