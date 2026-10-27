"""Scan orchestration: warm-up, retries, PDF, delivery, flatbed batch."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BATCH_AUTO_SEND,
    CONF_BATCH_TIMEOUT,
    CONF_BLANK_DETECTION,
    CONF_BLANK_THRESHOLD,
    CONF_COLOR_MODE,
    CONF_CORRESPONDENT,
    CONF_DOCUMENT_TYPE,
    CONF_PAGE_SIZE,
    CONF_RESOLUTION,
    CONF_TAGS,
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_COLOR_MODE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RESOLUTION,
    EVENT_BATCH_STALE,
    EVENT_SCAN_FINISHED,
)
from .blank import DEFAULT_INK_PERCENT, filter_blank
from .escl import (
    COLOR_MODE_MAP,
    MAX_BATCH_BYTES,
    EsclError,
    EsclNoPagesError,
    SourceCaps,
    build_scan_settings,
    scan_region,
)
from .files import FileOutputError, write_atomic
from .paperless import PaperlessError, PaperlessTaskFailed
from .pdf import jpegs_to_pdf

if TYPE_CHECKING:
    from . import AirscanConfigEntry, AirscanData

_LOGGER = logging.getLogger(__name__)

PAPERLESS_TASK_TIMEOUT = 120
PAPERLESS_TASK_INTERVAL = 2
TIMEOUT_ADF = 900
TIMEOUT_PLATEN = 180
WARMUP_ATTEMPTS = 2
WARMUP_PAUSE = 2
SCAN_ATTEMPTS = 3
RETRY_PAUSE = 5
ADF_LOADED = "ScannerAdfLoaded"
# 10 x 10 mm in 1/300 inch
WARMUP_SIZE = 118


def parse_ids(value: str | list | None) -> list[str]:
    """Parse '1, 2,3' (or a list) into a list of id strings."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    return [str(i).strip() for i in items if str(i).strip()]


def _nearest(value: int, available: list[int]) -> int:
    return min(available, key=lambda r: abs(r - value)) if available else value


def _source_caps(data: AirscanData, source: str, duplex: bool) -> SourceCaps:
    caps = data.capabilities
    if source == "platen":
        src = caps.platen
    else:
        src = caps.adf_duplex if duplex else caps.adf_simplex
    if src is None:
        raise ServiceValidationError(
            f"Scanner unterstützt diese Quelle nicht ({source}, duplex={duplex})"
        )
    return src


def _acquire(data: AirscanData) -> None:
    if data.lock.locked():
        raise HomeAssistantError("Es läuft bereits ein Scan")


async def _prepare_adf(data: AirscanData) -> None:
    """Refresh a stale 'ADF empty' sensor with a tiny flatbed scan."""
    if data.capabilities.platen is None:
        return
    for _ in range(WARMUP_ATTEMPTS):
        try:
            status = await data.client.status()
            if status.adf_state == ADF_LOADED:
                return
        except EsclError:
            pass
        data.tracker.update(detail="Scanner wird aufgewärmt")
        warmup = build_scan_settings(
            source="platen",
            duplex=False,
            resolution=100,
            color_mode="grayscale",
            width=WARMUP_SIZE,
            height=WARMUP_SIZE,
        )
        try:
            await data.client.scan(warmup, single_page=True, timeout=60)
        except EsclError as err:
            _LOGGER.debug("Warm-up scan failed: %s", err)
        await asyncio.sleep(WARMUP_PAUSE)


async def _run_scan(
    data: AirscanData,
    *,
    source: str,
    duplex: bool,
    resolution: int,
    color_mode: str,
    src_caps: SourceCaps,
    page_size: str = DEFAULT_PAGE_SIZE,
) -> list[bytes]:
    """Scan with warm-up and up to SCAN_ATTEMPTS tries when no page arrives."""
    tracker = data.tracker
    width, height, x_off, y_off = scan_region(src_caps, page_size)
    settings = build_scan_settings(
        source=source,
        duplex=duplex,
        resolution=resolution,
        color_mode=color_mode,
        width=width,
        height=height,
        x_offset=x_off,
        y_offset=y_off,
    )

    def _on_page(n: int) -> None:
        tracker.update(detail=f"Seite {n} gescannt", pages=n)

    for attempt in range(1, SCAN_ATTEMPTS + 1):
        if source == "adf":
            await _prepare_adf(data)
        tracker.update(detail="Scannt…" if attempt == 1 else f"Scannt… (Versuch {attempt})")
        try:
            return await data.client.scan(
                settings,
                single_page=source == "platen",
                timeout=TIMEOUT_ADF if source == "adf" else TIMEOUT_PLATEN,
                on_page=_on_page,
            )
        except EsclNoPagesError as err:
            _LOGGER.warning("Scan attempt %s/%s: %s", attempt, SCAN_ATTEMPTS, err)
            if attempt == SCAN_ATTEMPTS:
                raise
            tracker.update(detail=f"Keine Seiten, neuer Versuch {attempt + 1}/{SCAN_ATTEMPTS}")
            await asyncio.sleep(RETRY_PAUSE)
    raise AssertionError  # pragma: no cover


async def _deliver(
    hass: HomeAssistant,
    entry: AirscanConfigEntry,
    pages: list[bytes],
    dpi: int,
    *,
    destination: str,
    title: str | None,
    tags: str | list | None,
    correspondent: str | None,
    document_type: str | None,
    directory: str | None,
) -> dict:
    """Build the PDF and store it."""
    data = entry.runtime_data
    opts = entry.options
    pdf = await hass.async_add_executor_job(jpegs_to_pdf, pages, dpi)
    now = dt_util.now()
    title = title or f"Scan {now:%Y-%m-%d %H:%M}"
    filename = f"scan-{now:%Y%m%d-%H%M%S}.pdf"
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
        await _wait_for_paperless(data, result)
    else:
        target = Path(directory) / filename
        try:
            await hass.async_add_executor_job(write_atomic, target, pdf)
        except FileOutputError as err:
            raise HomeAssistantError(str(err)) from err
        result["path"] = str(target)
    return result


async def _wait_for_paperless(data: AirscanData, result: dict) -> None:
    """Report 'done' only once Paperless has really ingested the document.

    The upload returns as soon as Paperless queued the file; OCR and duplicate
    checks run afterwards and can still fail. Tokens without access to the task
    list are fine: we then just keep the upload as success.
    """
    data.tracker.update(detail="Paperless verarbeitet das Dokument…")
    deadline = asyncio.get_running_loop().time() + PAPERLESS_TASK_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        try:
            task = await data.paperless.task_status(result["task_id"])
        except PaperlessTaskFailed as err:
            raise HomeAssistantError(f"Paperless hat das Dokument abgelehnt: {err}") from err
        except PaperlessError as err:
            _LOGGER.debug("Paperless task status unavailable: %s", err)
            return
        if task is None:
            return
        if task.get("related_document"):
            result["document_id"] = task["related_document"]
        if task.get("finished"):
            return
        await asyncio.sleep(PAPERLESS_TASK_INTERVAL)
    result["paperless_pending"] = True  # still being processed; not an error


def _check_destination(hass: HomeAssistant, data: AirscanData, destination: str, directory: str | None) -> None:
    if destination == "paperless":
        if data.paperless is None:
            raise ServiceValidationError("Paperless ist nicht konfiguriert")
    elif not directory:
        raise ServiceValidationError("Für Ziel 'file' ist ein Verzeichnis nötig")
    elif not hass.config.is_allowed_path(str(Path(directory) / "x.pdf")):
        raise ServiceValidationError(f"Pfad nicht erlaubt (allowlist_external_dirs): {directory}")


def _resolve(entry: AirscanConfigEntry, resolution: int | None, color_mode: str | None, src: SourceCaps) -> tuple[int, str]:
    dpi = _nearest(int(resolution or entry.options.get(CONF_RESOLUTION, DEFAULT_RESOLUTION)), src.resolutions)
    color = color_mode or entry.options.get(CONF_COLOR_MODE, DEFAULT_COLOR_MODE)
    if src.color_modes and COLOR_MODE_MAP[color] not in src.color_modes:
        raise ServiceValidationError(
            f"Farbmodus '{color}' wird von dieser Quelle nicht unterstützt "
            f"(verfügbar: {', '.join(src.color_modes)})"
        )
    return dpi, color


def _finish(hass: HomeAssistant, entry: AirscanConfigEntry, result: dict) -> None:
    data = entry.runtime_data
    blank = result.get("blank_removed", 0)
    data.tracker.update(
        "done",
        f"{result['pages']} Seite(n) → {result['destination']}"
        + (f" (Dokument #{result['document_id']})" if result.get("document_id") else "")
        + (" – Paperless verarbeitet noch" if result.get("paperless_pending") else "")
        + (f" ({blank} leer entfernt)" if blank else ""),
        result["pages"],
    )
    hass.bus.async_fire(EVENT_SCAN_FINISHED, {"entry_id": entry.entry_id, **result})


def _fail(data: AirscanData, err: Exception) -> HomeAssistantError:
    msg = f"Scan fehlgeschlagen: {err}" if isinstance(err, EsclError) else str(err)
    data.tracker.update("error", msg)
    _LOGGER.error(msg)
    return err if isinstance(err, HomeAssistantError) else HomeAssistantError(msg)


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
    skip_blank: bool | None = None,
    page_size: str | None = None,
) -> dict:
    """Scan (flatbed = one page, ADF = whole stack) and deliver the PDF.

    Blank page removal only applies to the feeder; it follows the integration
    option unless `skip_blank` is given.
    """
    data = entry.runtime_data
    duplex = duplex and source == "adf"
    src_caps = _source_caps(data, source, duplex)
    _check_destination(hass, data, destination, directory)
    dpi, color = _resolve(entry, resolution, color_mode, src_caps)

    _acquire(data)
    async with data.lock:
        data.tracker.update("running", "Scan startet", 0)
        try:
            pages = await _run_scan(
                data, source=source, duplex=duplex, resolution=dpi, color_mode=color,
                src_caps=src_caps,
                page_size=page_size or entry.options.get(CONF_PAGE_SIZE, DEFAULT_PAGE_SIZE),
            )
            removed = 0
            if source == "adf" and (
                entry.options.get(CONF_BLANK_DETECTION, False)
                if skip_blank is None
                else skip_blank
            ):
                data.tracker.update(detail="Prüfe auf Leerseiten…")
                pages, removed = await hass.async_add_executor_job(
                    filter_blank, pages, float(entry.options.get(CONF_BLANK_THRESHOLD, DEFAULT_INK_PERCENT))
                )
                if not pages:
                    raise HomeAssistantError(
                        "Alle Seiten wurden als leer erkannt – Papier richtig eingelegt?"
                    )
            data.tracker.update(detail="Erzeuge PDF und speichere…")
            result = await _deliver(
                hass, entry, pages, dpi, destination=destination, title=title, tags=tags,
                correspondent=correspondent, document_type=document_type, directory=directory,
            )
            result["blank_removed"] = removed
        except (EsclError, HomeAssistantError) as err:
            raise _fail(data, err) from err
    _finish(hass, entry, result)
    await data.coordinator.async_request_refresh()
    return result


# --- flatbed batch -------------------------------------------------------


def _batch_idle(data: AirscanData, detail: str | None = None) -> None:
    n = len(data.tracker.batch)
    if n:
        data.tracker.update("batch", detail or f"Stapel: {n} Seite(n) – senden oder verwerfen", n)
    else:
        data.tracker.update("idle", detail or "Bereit", 0)


def _arm_stale_timer(hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
    data = entry.runtime_data
    data.tracker.cancel_timer()
    minutes = entry.options.get(CONF_BATCH_TIMEOUT, DEFAULT_BATCH_TIMEOUT)
    if not minutes or not data.tracker.batch:
        return

    async def _expired(_now) -> None:
        data.tracker.timer = None
        if not data.tracker.batch:
            return
        if entry.options.get(CONF_BATCH_AUTO_SEND):
            try:
                await async_batch_send(hass, entry)
            except HomeAssistantError:
                pass  # state already set to error
            return
        data.tracker.update(detail="Stapel vergessen – bitte senden oder verwerfen")
        hass.bus.async_fire(
            EVENT_BATCH_STALE,
            {"entry_id": entry.entry_id, "pages": len(data.tracker.batch)},
        )

    data.tracker.timer = async_call_later(hass, minutes * 60, _expired)


async def async_batch_add(
    hass: HomeAssistant,
    entry: AirscanConfigEntry,
    *,
    resolution: int | None = None,
    color_mode: str | None = None,
    page_size: str | None = None,
) -> dict:
    """Scan one flatbed page into the batch buffer."""
    data = entry.runtime_data
    src_caps = _source_caps(data, "platen", False)
    dpi, color = _resolve(entry, resolution, color_mode, src_caps)
    if data.tracker.batch:
        dpi = data.tracker.batch_dpi  # one PDF, one resolution

    _acquire(data)
    async with data.lock:
        data.tracker.cancel_timer()
        data.tracker.update("running", "Scan startet")
        try:
            pages = await _run_scan(
                data, source="platen", duplex=False, resolution=dpi, color_mode=color,
                src_caps=src_caps,
                page_size=page_size or entry.options.get(CONF_PAGE_SIZE, DEFAULT_PAGE_SIZE),
            )
        except EsclError as err:
            error = _fail(data, err)
            _arm_stale_timer(hass, entry)
            raise error from err
        if sum(map(len, data.tracker.batch)) + sum(map(len, pages)) > MAX_BATCH_BYTES:
            error = _fail(data, HomeAssistantError("Stapel zu groß (Limit 512 MiB) – bitte senden"))
            _arm_stale_timer(hass, entry)
            raise error
        data.tracker.batch.extend(pages)
        data.tracker.batch_dpi = dpi
        _batch_idle(data)
        _arm_stale_timer(hass, entry)
    return {"batch_pages": len(data.tracker.batch)}


async def async_batch_send(
    hass: HomeAssistant,
    entry: AirscanConfigEntry,
    *,
    destination: str = "paperless",
    title: str | None = None,
    tags: str | list | None = None,
    correspondent: str | None = None,
    document_type: str | None = None,
    directory: str | None = None,
) -> dict:
    """Build one PDF from the batch buffer and deliver it."""
    data = entry.runtime_data
    if not data.tracker.batch:
        raise ServiceValidationError("Der Stapel ist leer")
    _check_destination(hass, data, destination, directory)

    _acquire(data)
    async with data.lock:
        data.tracker.cancel_timer()
        data.tracker.update("running", "Erzeuge PDF und speichere…")
        try:
            result = await _deliver(
                hass, entry, list(data.tracker.batch), data.tracker.batch_dpi,
                destination=destination, title=title, tags=tags,
                correspondent=correspondent, document_type=document_type, directory=directory,
            )
        except HomeAssistantError as err:
            error = _fail(data, err)
            _arm_stale_timer(hass, entry)  # batch is kept for another try
            raise error from err
        data.tracker.batch.clear()
    _finish(hass, entry, result)
    return result


async def async_batch_discard(hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
    """Empty the batch buffer."""
    data = entry.runtime_data
    data.tracker.cancel_timer()
    data.tracker.batch.clear()
    _batch_idle(data, "Stapel verworfen")
