"""Map the value an external button sends to a scan action (pure logic)."""

from __future__ import annotations

import json
import time
from typing import Any

# What a button can do. The value is what the user maps to it (e.g. "open" of an IKEA remote).
BUTTON_ACTIONS = ["adf", "platen", "toggle_duplex", "batch_send", "batch_discard"]
IGNORED_STATES = ("unknown", "unavailable", "")
DEBOUNCE_SECONDS = 1.0


def trigger_value(domain: str, old_state: str | None, new_state: str, attributes: dict[str, Any]) -> str | None:
    """The button value of a state change, or None if the change is not a button press.

    - `event` entities (Zigbee2MQTT 2.x, ZHA, Matter ...): every press changes the state (a time stamp);
      the pressed button is the attribute `event_type`.
    - `sensor` entities (older Zigbee2MQTT "action" sensors): the state is the value. A change from
      unknown/unavailable is ignored, so a restart of Home Assistant or the broker does not scan.
    """
    if new_state in IGNORED_STATES or new_state is None:
        return None
    if domain == "event":
        if old_state in ("unavailable", None):      # entity just appeared / came back
            return None
        value = attributes.get("event_type")
        return str(value) if value else None
    if old_state in ("unavailable", "unknown", None):
        return None
    return str(new_state)


def topic_value(payload: Any) -> str | None:
    """The button value in an MQTT message.

    Zigbee2MQTT publishes the pressed button as plain text on `<base>/<device>/action`; the JSON
    on `<base>/<device>` carries it in the field "action". Empty values (resets) are no press.
    """
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    text = str(payload or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return None
        text = str(data.get("action") or "").strip() if isinstance(data, dict) else ""
    return text or None


def valid_topic(topic: str) -> bool:
    """A concrete MQTT topic, no wildcards (a wildcard would catch other devices as well)."""
    return bool(topic.strip()) and not any(ch in topic for ch in "#+") and not topic.startswith("/")


def action_for(value: str | None, mapping: dict[str, str]) -> str | None:
    """The action a value is mapped to (case-insensitive), or None."""
    if not value:
        return None
    wanted = value.strip().lower()
    for action in BUTTON_ACTIONS:
        configured = str(mapping.get(action) or "").strip().lower()
        if configured and configured == wanted:
            return action
    return None


def duplicate_values(mapping: dict[str, str]) -> list[str]:
    """Values that are mapped to more than one action (not allowed)."""
    seen: dict[str, int] = {}
    for action in BUTTON_ACTIONS:
        configured = str(mapping.get(action) or "").strip().lower()
        if configured:
            seen[configured] = seen.get(configured, 0) + 1
    return [v for v, n in seen.items() if n > 1]


def values_of(attributes: dict[str, Any]) -> list[str]:
    """Known values of a button entity (`event_types` of event entities, `options` of enum sensors)."""
    raw = attributes.get("event_types") or attributes.get("options") or []
    return sorted({str(v) for v in raw if v not in (None, "")})


class Debounce:
    """Ignore the same value arriving again within a short time (radio retransmissions)."""

    def __init__(self, seconds: float = DEBOUNCE_SECONDS) -> None:
        self._seconds = seconds
        self._last: tuple[str, float] | None = None

    def accept(self, value: str, now: float | None = None) -> bool:
        """True if this press counts."""
        now = time.monotonic() if now is None else now
        if self._last and self._last[0] == value and now - self._last[1] < self._seconds:
            return False
        self._last = (value, now)
        return True
