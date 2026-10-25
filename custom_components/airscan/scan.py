"""Scan orchestration: scanner -> PDF -> destination."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COLOR_MODE,
    CONF_CORRESPONDENT,
    CONF_DOCUMENT_TYPE,
    CONF_RESOLUTION,
    CONF_TAGS,
    DEFAULT_COLOR_MODE,
    DEFAULT_RESOLUTION,
    EVENT_SCAN_FINISHED,
)
from .escl import EsclError, build_scan_settings
from .paperless import PaperlessError
from .pdf import jpegs_to_pdf

if TYPE_CHECKING:
    from . import AirscanConfigEntry


def parse_ids(value: str | list | None) -> list[str]:
    """Parse '1, 2,3' (or a list) into a list of id strings."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [str(i).strip() for i in items if str(i).strip()]


def _nearest(value: int, available: list[int]) -> int:
    return min(available, key=lambda r: abs(r - value)) if available else value


async def async_scan(
    hass: HomeAssistant,
    entry: AirscanConfigEntry,
    *,
    source: str,
    duplex: bool = False,
    resolution: int | None = None,
    color_mode: str | None = None,
    destination: str = "paperless",
    title: str | None = None,
    tags: str | list | None = None,
    correspondent: str | None = None,
    document_type: str | None = None,
    directory: str | None = None,
) -> dict:
    """Run one scan and deliver the result. Returns a summary."""
    data = entry.runtime_data
    caps = data.capabilities
    opts = entry.options

    if source == "platen":
        duplex = False
        src_caps = caps.platen
    else:
        src_caps = caps.adf_duplex if duplex else caps.adf_simplex
    if src_caps is None:
        raise ServiceValidationError(
            f"Scanner unterstützt diese Quelle nicht ({source}, duplex={duplex})"
        )
    if destination == "paperless" and data.paperless is None:
        raise ServiceValidationError("Paperless ist nicht konfiguriert")

    resolution = _nearest(
        int(resolution or opts.get(CONF_RESOLUTION, DEFAULT_RESOLUTION)),
        src_caps.resolutions,
    )
    color_mode = color_mode or opts.get(CONF_COLOR_MODE, DEFAULT_COLOR_MODE)

    if data.lock.locked():
        raise HomeAssistantError("Es läuft bereits ein Scan")
    async with data.lock:
        settings = build_scan_settings(
            source=source,
            duplex=duplex,
            resolution=resolution,
            color_mode=color_mode,
            width=src_caps.max_width,
            height=src_caps.max_height,
        )
        try:
            pages = await data.client.scan(settings, single_page=source == "platen")
        except EsclError as err:
            raise HomeAssistantError(f"Scan fehlgeschlagen: {err}") from err
        pdf = await hass.async_add_executor_job(jpegs_to_pdf, pages, resolution)

        now = dt_util.now()
        title = title or f"Scan {now:%Y-%m-%d %H:%M}"
        filename = f"scan_{now:%Y%m%d_%H%M%S}.pdf"
        result: dict = {"pages": len(pages), "destination": destination, "title": title}

        if destination == "paperless":
            try:
                result["task_id"] = await data.paperless.upload(
                    pdf,
                    filename,
                    title=title,
                    tags=parse_ids(tags if tags is not None else opts.get(CONF_TAGS)),
                    correspondent=correspondent or opts.get(CONF_CORRESPONDENT),
                    document_type=document_type or opts.get(CONF_DOCUMENT_TYPE),
                )
            except PaperlessError as err:
                raise HomeAssistantError(f"Upload zu Paperless fehlgeschlagen: {err}") from err
        else:
            if not directory:
                raise ServiceValidationError("Für Ziel 'file' ist ein Verzeichnis nötig")
            target = Path(directory) / filename
            if not hass.config.is_allowed_path(str(target)):
                raise ServiceValidationError(
                    f"Pfad nicht erlaubt (allowlist_external_dirs): {directory}"
                )

            def _write() -> None:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(pdf)

            await hass.async_add_executor_job(_write)
            result["path"] = str(target)

    hass.bus.async_fire(EVENT_SCAN_FINISHED, {"entry_id": entry.entry_id, **result})
    await data.coordinator.async_request_refresh()
    return result
