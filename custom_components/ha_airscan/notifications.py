"""Send notifications for scan events and Paperless webhooks to the chosen targets."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import TYPE_CHECKING, Any

from aiohttp import web

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_PAPERLESS_TYPES,
    CONF_NOTIFY_SCAN_TYPES,
    CONF_NOTIFY_SERVICES,
    DEFAULT_NOTIFY_PAPERLESS_TYPES,
    DEFAULT_NOTIFY_SCAN_TYPES,
    EVENT_BATCH_STALE,
    EVENT_PRINTER_OFFLINE,
    EVENT_QUEUE_DELIVERED,
    EVENT_SCAN_FAILED,
    EVENT_SCAN_FINISHED,
    PERSISTENT_NOTIFICATION,
)
from .notify_messages import action_labels, normalize_paperless, paperless_message, scan_message
from .scan import async_batch_discard, async_batch_send

if TYPE_CHECKING:
    from . import AirscanConfigEntry

_LOGGER = logging.getLogger(__name__)
ACTION_SEND = "HA_AIRSCAN_SEND"
ACTION_DISCARD = "HA_AIRSCAN_DISCARD"


class Notifier:
    """Listens to the events of one scanner and notifies the configured targets."""

    def __init__(self, hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    @property
    def _options(self):
        return self._entry.options

    @property
    def has_targets(self) -> bool:
        """At least one target is configured."""
        return bool(self._options.get(CONF_NOTIFY_SERVICES) or self._options.get(CONF_NOTIFY_ENTITIES))

    @callback
    def async_start(self) -> None:
        """Subscribe to our events; unsubscribes when the entry unloads."""
        bus = self._hass.bus
        for event_type, kind_of in (
            (EVENT_SCAN_FINISHED, lambda d: "queued" if d.get("queued") else "scan_done"),
            (EVENT_SCAN_FAILED, lambda d: "scan_error"),
            (EVENT_QUEUE_DELIVERED, lambda d: "queue_delivered"),
            (EVENT_BATCH_STALE, lambda d: "batch_stale"),
            (EVENT_PRINTER_OFFLINE, lambda d: "printer_offline"),
        ):
            self._entry.async_on_unload(bus.async_listen(event_type, self._make_handler(kind_of)))
        self._entry.async_on_unload(bus.async_listen("mobile_app_notification_action", self._on_action))

    def _make_handler(self, kind_of):
        @callback
        def _handler(event: Event) -> None:
            if event.data.get("entry_id") != self._entry.entry_id or not self.has_targets:
                return
            kind = kind_of(event.data)
            if kind not in self._options.get(CONF_NOTIFY_SCAN_TYPES, DEFAULT_NOTIFY_SCAN_TYPES):
                return
            message = scan_message(kind, dict(event.data), self._hass.config.language)
            self._hass.async_create_task(self.async_send(message))

        return _handler

    async def _on_action(self, event: Event) -> None:
        """Buttons of the 'forgotten batch' notification."""
        action = str(event.data.get("action", ""))
        name, _, entry_id = action.partition(":")
        if entry_id != self._entry.entry_id:
            return
        try:
            if name == ACTION_SEND:
                await async_batch_send(self._hass, self._entry)
            elif name == ACTION_DISCARD:
                await async_batch_discard(self._hass, self._entry)
        except HomeAssistantError as err:   # the status sensor and the log already carry the reason
            _LOGGER.warning("Notification action %s failed: %s", name, err)

    async def async_handle_webhook(self, hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        """Paperless-ngx workflow webhook: new document / due date."""
        try:
            payload: Any = await request.json()
        except ValueError:
            return web.Response(status=400, text="JSON expected")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="JSON object expected")
        doc = normalize_paperless(payload)
        if doc["typ"] in self._options.get(CONF_NOTIFY_PAPERLESS_TYPES, DEFAULT_NOTIFY_PAPERLESS_TYPES) and self.has_targets:
            await self.async_send(paperless_message(doc, hass.config.language))
        return web.Response(status=200)

    async def async_send(self, msg: dict) -> None:
        """Send one message to every configured target."""
        await async_send_message(self._hass, self._options, self._entry.entry_id, msg)


def _mobile_data(hass: HomeAssistant, entry_id: str, msg: dict) -> dict:
    """Extra fields understood by the Home Assistant app (iOS and Android)."""
    extra: dict[str, Any] = {"tag": msg["tag"]}
    if msg.get("url"):
        extra["url"] = msg["url"]            # iOS
        extra["clickAction"] = msg["url"]    # Android
    if msg.get("time_sensitive"):
        extra["push"] = {"interruption-level": "time-sensitive"}
    if msg.get("actions"):
        send, discard = action_labels(hass.config.language)
        extra["actions"] = [
            {"action": f"{ACTION_SEND}:{entry_id}", "title": send},
            {"action": f"{ACTION_DISCARD}:{entry_id}", "title": discard, "destructive": True},
        ]
    return extra


async def async_send_message(hass: HomeAssistant, options: Mapping[str, Any], entry_id: str, msg: dict) -> int:
    """Send to every target; one broken target never blocks the others. Returns the number of failures."""
    calls: list[tuple[str, str, dict]] = []
    for service in options.get(CONF_NOTIFY_SERVICES, []):
        if service == PERSISTENT_NOTIFICATION:
            calls.append(("persistent_notification", "create",
                          {"title": msg["title"], "message": msg["message"], "notification_id": msg["tag"]}))
            continue
        data: dict[str, Any] = {"title": msg["title"], "message": msg["message"]}
        if service.startswith("mobile_app_"):   # other services do not know these fields
            data["data"] = _mobile_data(hass, entry_id, msg)
        calls.append(("notify", service, data))
    for entity_id in options.get(CONF_NOTIFY_ENTITIES, []):
        calls.append(("notify", "send_message",
                      {"entity_id": entity_id, "title": msg["title"], "message": msg["message"]}))
    failures = 0
    for domain, service, data in calls:
        try:
            await hass.services.async_call(domain, service, data, blocking=True)
        except HomeAssistantError as err:
            failures += 1
            _LOGGER.warning("Notification via %s.%s failed: %s", domain, service, err)
    return failures


async def async_send_test(hass: HomeAssistant, options: Mapping[str, Any], entry_id: str) -> int:
    """Test message for the options dialog."""
    text = ("Testnachricht", "Die Benachrichtigungen von Scan to Paperless funktionieren.") \
        if str(hass.config.language).startswith("de") else ("Test message", "Notifications from Scan to Paperless are working.")
    return await async_send_message(hass, options, entry_id, {"title": text[0], "message": text[1], "tag": "ha_airscan_test"})
