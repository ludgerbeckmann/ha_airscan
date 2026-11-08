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
from homeassistant.data_entry_flow import section
from homeassistant.components import webhook
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    COLOR_MODES,
    CONF_ADF_ALIGN,
    CONF_BATCH_AUTO_SEND,
    CONF_BUTTON_ENTITY,
    CONF_BUTTON_MAP,
    CONF_BUTTON_TOPIC,
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_PAPERLESS_TYPES,
    CONF_NOTIFY_SCAN_TYPES,
    CONF_NOTIFY_SERVICES,
    CONF_NOTIFY_TARGETS,
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
from .button_map import BUTTON_ACTIONS, duplicate_values, valid_topic, values_of
from .escl import EsclClient, EsclError
from .notify_messages import PAPERLESS_TYPES, SCAN_TYPES
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


def _notify_targets(hass: HomeAssistant, d: dict[str, Any]) -> list[dict[str, str]]:
    """notify services and notify entities in one list (entity ids contain a dot)."""
    services = hass.services.async_services_for_domain("notify")
    names = sorted(s for s in services if s not in ("send_message", PERSISTENT_NOTIFICATION))
    chosen_services = [c for c in d.get(CONF_NOTIFY_SERVICES, []) if c != PERSISTENT_NOTIFICATION]
    names += [c for c in chosen_services if c not in names]
    options = [{"value": PERSISTENT_NOTIFICATION, "label": "Benachrichtigung in Home Assistant"}]
    options += [{"value": n, "label": n} for n in names]
    entity_ids = set(hass.states.async_entity_ids("notify")) | set(d.get(CONF_NOTIFY_ENTITIES, []))
    for entity_id in sorted(entity_ids):
        state = hass.states.get(entity_id)
        label = state.name if state else entity_id
        options.append({"value": entity_id, "label": f"{label} ({entity_id})"})
    return options


def _targets_value(d: dict[str, Any]) -> list[str]:
    return list(d.get(CONF_NOTIFY_SERVICES, [])) + list(d.get(CONF_NOTIFY_ENTITIES, []))


def _split_targets(hass: HomeAssistant, values: list[str]) -> tuple[list[str], list[str]]:
    """Back into (services, entities); 'notify.x' is an entity if it exists, else a service name."""
    services: list[str] = []
    entities: list[str] = []
    for value in values:
        value = str(value).strip()
        if not value:
            continue
        if "." in value and hass.states.get(value) is not None:
            entities.append(value)
        else:
            services.append(value.removeprefix("notify."))
    return services, entities


def _notify_schema(hass: HomeAssistant, d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_NOTIFY_TARGETS, default=_targets_value(d)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_notify_targets(hass, d),
                    multiple=True, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN,
                )
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
        }
    )


def _webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    try:
        return webhook.async_generate_url(hass, webhook_id, prefer_external=False)
    except Exception:  # noqa: BLE001 - no internal/external URL configured
        return f"/api/webhook/{webhook_id}"


SECTION_PAPERLESS = "paperless"
SECTION_SCAN = "scan"
SECTION_NOTIFY = "notifications"
SECTION_BUTTONS = "buttons"

_PAPERLESS_KEYS = {
    CONF_PAPERLESS_URL, CONF_PAPERLESS_TOKEN, CONF_PAPERLESS_VERIFY_SSL,
    CONF_TAGS, CONF_CORRESPONDENT, CONF_DOCUMENT_TYPE,
}


def _pick(schema: vol.Schema, keys: set[str], *, invert: bool = False) -> vol.Schema:
    """Sub-schema with only (or without) the given keys."""
    return vol.Schema(
        {k: v for k, v in schema.schema.items() if (str(k) in keys) != invert}
    )


def _buttons_schema(d: dict[str, Any], known: list[str]) -> vol.Schema:
    shown = d.get(CONF_BUTTON_MAP) or {}
    fields: dict[Any, Any] = {
        vol.Optional(
            CONF_BUTTON_ENTITY, description={"suggested_value": d.get(CONF_BUTTON_ENTITY)}
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain=["event", "sensor"])),
        vol.Optional(
            CONF_BUTTON_TOPIC, description={"suggested_value": d.get(CONF_BUTTON_TOPIC)}
        ): str,
    }
    for action in BUTTON_ACTIONS:
        fields[vol.Optional(action, description={"suggested_value": shown.get(action, "")})] = (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=known, custom_value=True, mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        )
    return vol.Schema(fields)


def _options_form(hass: HomeAssistant, d: dict[str, Any], known: list[str]) -> vol.Schema:
    """One form, four collapsible sections."""
    flat = _options_schema(d)
    return vol.Schema(
        {
            vol.Required(SECTION_PAPERLESS): section(
                _pick(flat, _PAPERLESS_KEYS), {"collapsed": False}
            ),
            vol.Required(SECTION_SCAN): section(
                _pick(flat, _PAPERLESS_KEYS, invert=True), {"collapsed": True}
            ),
            vol.Required(SECTION_NOTIFY): section(_notify_schema(hass, d), {"collapsed": True}),
            vol.Required(SECTION_BUTTONS): section(_buttons_schema(d, known), {"collapsed": True}),
        }
    )


def _flatten(user_input: dict[str, Any]) -> dict[str, Any]:
    """Sections back to flat options (button settings under their option keys)."""
    flat: dict[str, Any] = {}
    for name in (SECTION_PAPERLESS, SECTION_SCAN, SECTION_NOTIFY):
        flat.update(user_input.get(name) or {})
    buttons = user_input.get(SECTION_BUTTONS) or {}
    flat[CONF_BUTTON_ENTITY] = buttons.get(CONF_BUTTON_ENTITY) or ""
    flat[CONF_BUTTON_TOPIC] = str(buttons.get(CONF_BUTTON_TOPIC) or "").strip()
    flat[CONF_BUTTON_MAP] = {a: str(buttons.get(a) or "").strip() for a in BUTTON_ACTIONS}
    return flat


class AirscanOptionsFlow(OptionsFlow):
    """Options: everything on one page, grouped in sections."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Paperless, scan defaults, notifications and external buttons."""
        saved = dict(self.config_entry.options)
        current = saved
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            flat = _flatten(user_input)
            services, entities = _split_targets(self.hass, flat.pop(CONF_NOTIFY_TARGETS, []))
            flat[CONF_NOTIFY_SERVICES], flat[CONF_NOTIFY_ENTITIES] = services, entities
            current = {**saved, **flat}
            entity, topic, mapping = flat[CONF_BUTTON_ENTITY], flat[CONF_BUTTON_TOPIC], flat[CONF_BUTTON_MAP]
            webhook_id = str(flat.get(CONF_PAPERLESS_WEBHOOK_ID, "")).strip()
            error, detail = await _validate_paperless(self.hass, flat)
            if error:
                errors["base"] = error
            elif flat.get(CONF_PAPERLESS_WEBHOOK) and not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", webhook_id):
                errors["base"] = "invalid_webhook_id"
            elif entity and topic:
                errors["base"] = "button_source_both"
            elif topic and not valid_topic(topic):
                errors["base"] = "invalid_topic"
            elif (entity or topic) and duplicate_values(mapping):
                errors["base"] = "duplicate_button_value"
            elif (entity or topic) and not any(mapping.values()):
                errors["base"] = "no_button_mapping"
            else:
                options = {**saved, **flat}
                options[CONF_PAPERLESS_WEBHOOK_ID] = webhook_id
                for key in (CONF_BUTTON_ENTITY, CONF_BUTTON_TOPIC, CONF_BUTTON_MAP):
                    options.pop(key, None)
                if entity or topic:
                    options[CONF_BUTTON_ENTITY if entity else CONF_BUTTON_TOPIC] = entity or topic
                    options[CONF_BUTTON_MAP] = mapping
                return self.async_create_entry(data=options)
        webhook_id = current.get(CONF_PAPERLESS_WEBHOOK_ID) or f"paperless_{secrets.token_hex(8)}"
        current = {**current, CONF_PAPERLESS_WEBHOOK_ID: webhook_id}
        source = current.get(CONF_BUTTON_ENTITY)
        state = self.hass.states.get(source) if source else None
        known = values_of(dict(state.attributes)) if state else []
        return self.async_show_form(
            step_id="init",
            data_schema=_options_form(self.hass, current, known),
            errors=errors,
            description_placeholders={
                "error_detail": detail if errors else "",
                "webhook_url": _webhook_url(self.hass, webhook_id),
                "known": ", ".join(known) or "–",
            },
        )
