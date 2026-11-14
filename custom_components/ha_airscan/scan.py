"""Scan orchestration: warm-up, retries, PDF, delivery, flatbed batch."""

from __future__ import annotations

import asyncio
from datetime import timedelta
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
    CONF_ADF_ALIGN,
    CONF_BLANK_DETECTION,
    CONF_BLANK_THRESHOLD,
    CONF_COLOR_MODE,
    CONF_CORRESPONDENT,
    CONF_DOCUMENT_TYPE,
    CONF_PAGE_SIZE,
    CONF_RESOLUTION,
    CONF_TAGS,
    DEFAULT_ADF_ALIGN,
    DEFAULT_BATCH_TIMEOUT,
    DEFAULT_COLOR_MODE,
    DEFAULT_PAGE_SIZE,
    DEFAULT_RESOLUTION,
    EVENT_BATCH_STALE,
    EVENT_SCAN_FAILED,
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
from .outbox_store import next_delay
from .paperless import PaperlessError, PaperlessTaskFailed
from .pdf import jpegs_to_pdf
from .summary import summarize

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


class ScannerBusy(HomeAssistantError):
    """A scan or batch action is still running (the scanner is in use)."""


def _acquire(data: AirscanData) -> None:
    if data.lock.locked():
        raise ScannerBusy("Es läuft bereits ein Scan")


def _begin(data: AirscanData) -> int:
    """Call with the lock held: numbers this scan so that a slower, older one cannot overwrite the status."""
    data.scan_seq += 1
    return data.scan_seq


def _current(data: AirscanData, seq: int | None) -> bool:
    """True if this scan still owns the status display (no newer scan has started)."""
    return seq is None or (seq == data.scan_seq and not data.lock.locked())


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
    adf_align: str = DEFAULT_ADF_ALIGN,
) -> list[bytes]:
    """Scan with warm-up and up to SCAN_ATTEMPTS tries when no page arrives."""
    tracker = data.tracker
    width, height, x_off, y_off = scan_region(
        src_caps, page_size, adf_align if source == "adf" else "auto"
    )
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
        upload = {
            "title": title,
            "tags": parse_ids(tags if tags is not None else opts.get(CONF_TAGS)),
            "correspondent": correspondent or opts.get(CONF_CORRESPONDENT),
            "document_type": document_type or opts.get(CONF_DOCUMENT_TYPE),
        }
        try:
            result["task_id"] = await data.paperless.upload(pdf, filename, **upload)
        except PaperlessError as err:
            if not err.retryable:
                raise HomeAssistantError(f"Upload zu Paperless fehlgeschlagen: {err}") from err
            # Paperless is down or the token needs fixing: keep the scan, retry automatically.
            try:
                await data.outbox.async_add(pdf, {"filename": filename, **upload}, str(err))
            except OSError as disk_err:   # no room to keep it either: now the scan really fails
                raise HomeAssistantError(
                    f"Upload zu Paperless fehlgeschlagen ({err}) und Speichern in der Warteschlange ebenfalls ({disk_err})"
                ) from err
            data.outbox.async_schedule(next_delay(1))
            result["queued"] = True
            result["queue_error"] = str(err)
            return result
    else:
        target = Path(directory) / filename
        try:
            await hass.async_add_executor_job(write_atomic, target, pdf)
        except FileOutputError as err:
            raise HomeAssistantError(str(err)) from err
        result["path"] = str(target)
    return result


async def wait_for_paperless(data: AirscanData, result: dict, seq: int | None = None) -> None:
    """Report 'done' only once Paperless has really ingested the document.

    The upload returns as soon as Paperless queued the file; OCR and duplicate
    checks run afterwards and can still fail. Tokens without access to the task
    list are fine: we then just keep the upload as success.
    """
    if _current(data, seq):
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


async def _complete(hass: HomeAssistant, entry: AirscanConfigEntry, result: dict, seq: int) -> None:
    """After the lock is released: wait until Paperless has ingested the document, then report."""
    data = entry.runtime_data
    try:
        if result.get("task_id"):
            await wait_for_paperless(data, result, seq)
    except HomeAssistantError as err:
        raise _fail(hass, entry, err, seq) from err
    _finish(hass, entry, result, seq)
    await data.coordinator.async_request_refresh()


def _blank_enabled(entry: AirscanConfigEntry, skip_blank: bool | None) -> bool:
    """Blank page removal: the call decides, otherwise the integration option (feeder and flatbed)."""
    return bool(entry.options.get(CONF_BLANK_DETECTION, False) if skip_blank is None else skip_blank)


def _blank_threshold(entry: AirscanConfigEntry) -> float:
    return float(entry.options.get(CONF_BLANK_THRESHOLD, DEFAULT_INK_PERCENT))


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


def _finish(hass: HomeAssistant, entry: AirscanConfigEntry, result: dict, seq: int | None = None) -> None:
    data = entry.runtime_data
    blank = result.get("blank_removed", 0)
    if not _current(data, seq):   # a newer scan is already running: only report the event
        hass.bus.async_fire(EVENT_SCAN_FINISHED, {"entry_id": entry.entry_id, **result})
        return
    data.tracker.finished_at = dt_util.utcnow()
    data.tracker.last = summarize(result, data.tracker.finished_at)
    if result.get("queued"):
        waiting = len(data.outbox.pending)
        data.tracker.update(
            "queued",
            f"{result['pages']} Seite(n) gescannt – Paperless nicht erreichbar, {waiting} Scan(s) warten "
            f"auf automatische Übertragung ({result.get('queue_error', '')})",
            result["pages"],
        )
        hass.bus.async_fire(EVENT_SCAN_FINISHED, {"entry_id": entry.entry_id, **result})
        return
    data.tracker.update(
        "done",
        f"{result['pages']} Seite(n) → {result['destination']}"
        + (f" (Dokument #{result['document_id']})" if result.get("document_id") else "")
        + (" – Paperless verarbeitet noch" if result.get("paperless_pending") else "")
        + (f" ({blank} leer entfernt)" if blank else ""),
        result["pages"],
    )
    hass.bus.async_fire(EVENT_SCAN_FINISHED, {"entry_id": entry.entry_id, **result})


def _fail(hass: HomeAssistant, entry: AirscanConfigEntry, err: Exception, seq: int | None = None) -> HomeAssistantError:
    data = entry.runtime_data
    msg = f"Scan fehlgeschlagen: {err}" if isinstance(err, EsclError) else str(err)
    if _current(data, seq):
        data.tracker.update("error", msg)
    _LOGGER.error(msg)
    hass.bus.async_fire(EVENT_SCAN_FAILED, {"entry_id": entry.entry_id, "detail": msg})
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

    Blank page removal (feeder and flatbed) follows the integration option unless
    `skip_blank` is given.
    """
    data = entry.runtime_data
    duplex = duplex and source == "adf"
    src_caps = _source_caps(data, source, duplex)
    _check_destination(hass, data, destination, directory)
    dpi, color = _resolve(entry, resolution, color_mode, src_caps)

    _acquire(data)
    async with data.lock:
        seq = _begin(data)
        data.tracker.set_notice("")
        data.tracker.update("running", "Scan startet", 0)
        try:
            pages = await _run_scan(
                data, source=source, duplex=duplex, resolution=dpi, color_mode=color,
                src_caps=src_caps,
                page_size=page_size or entry.options.get(CONF_PAGE_SIZE, DEFAULT_PAGE_SIZE),
                adf_align=entry.options.get(CONF_ADF_ALIGN, DEFAULT_ADF_ALIGN),
            )
            removed = 0
            if _blank_enabled(entry, skip_blank):
                data.tracker.update(detail="Prüfe auf Leerseiten…")
                pages, removed = await hass.async_add_executor_job(filter_blank, pages, _blank_threshold(entry))
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
            result["source"] = "adf_duplex" if duplex else source
        except (EsclError, HomeAssistantError) as err:
            raise _fail(hass, entry, err) from err
    # the scanner is free again; waiting for Paperless must not block the next scan
    await _complete(hass, entry, result, seq)
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
        data.tracker.batch_expires_at = None
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
    data.tracker.batch_expires_at = dt_util.utcnow() + timedelta(minutes=minutes)
    data.tracker.update()  # publish the new expiry time


async def async_batch_add(
    hass: HomeAssistant,
    entry: AirscanConfigEntry,
    *,
    resolution: int | None = None,
    color_mode: str | None = None,
    page_size: str | None = None,
    skip_blank: bool | None = None,
) -> dict:
    """Scan one flatbed page into the batch buffer (a blank page is not added)."""
    data = entry.runtime_data
    src_caps = _source_caps(data, "platen", False)
    dpi, color = _resolve(entry, resolution, color_mode, src_caps)
    if data.tracker.batch:
        dpi = data.tracker.batch_dpi  # one PDF, one resolution

    _acquire(data)
    async with data.lock:
        _begin(data)
        data.tracker.cancel_timer()
        data.tracker.set_notice("")
        data.tracker.update("running", "Scan startet")
        try:
            pages = await _run_scan(
                data, source="platen", duplex=False, resolution=dpi, color_mode=color,
                src_caps=src_caps,
                page_size=page_size or entry.options.get(CONF_PAGE_SIZE, DEFAULT_PAGE_SIZE),
            )
        except EsclError as err:
            error = _fail(hass, entry, err)
            _arm_stale_timer(hass, entry)
            raise error from err
        if _blank_enabled(entry, skip_blank):
            data.tracker.update(detail="Prüfe auf Leerseiten…")
            pages, removed = await hass.async_add_executor_job(filter_blank, pages, _blank_threshold(entry))
            if not pages:   # empty flatbed: nothing to add, but tell the user
                data.tracker.set_notice("blank_skipped", dt_util.utcnow())
                _batch_idle(data)
                _arm_stale_timer(hass, entry)
                return {"batch_pages": len(data.tracker.batch), "blank_skipped": removed}
        if sum(map(len, data.tracker.batch)) + sum(map(len, pages)) > MAX_BATCH_BYTES:
            error = _fail(hass, entry, HomeAssistantError("Stapel zu groß (Limit 512 MiB) – bitte senden"))
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
        seq = _begin(data)
        data.tracker.cancel_timer()
        data.tracker.set_notice("")
        data.tracker.update("running", "Erzeuge PDF und speichere…")
        sent = list(data.tracker.batch)
        try:
            result = await _deliver(
                hass, entry, sent, data.tracker.batch_dpi,
                destination=destination, title=title, tags=tags,
                correspondent=correspondent, document_type=document_type, directory=directory,
            )
        except HomeAssistantError as err:
            error = _fail(hass, entry, err)
            _arm_stale_timer(hass, entry)  # batch is kept for another try
            raise error from err
        data.tracker.batch.clear()
    result["source"] = "platen"
    try:
        await _complete(hass, entry, result, seq)
    except HomeAssistantError:
        if not data.tracker.batch:   # Paperless refused it: keep the pages for another try
            data.tracker.batch.extend(sent)
            _arm_stale_timer(hass, entry)
        raise
    return result


async def async_batch_discard(hass: HomeAssistant, entry: AirscanConfigEntry) -> None:
    """Empty the batch buffer."""
    data = entry.runtime_data
    data.tracker.cancel_timer()
    data.tracker.set_notice("")
    data.tracker.batch.clear()
    _batch_idle(data, "Stapel verworfen")
