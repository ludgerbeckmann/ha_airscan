"""Minimal async client for the eSCL (AirScan) protocol."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp import ClientTimeout

NS_PWG = "http://www.pwg.org/schemas/2010/12/sm"
NS_SCAN = "http://schemas.hp.com/imaging/escl/2011/05/03"

_LOGGER = logging.getLogger(__name__)

COLOR_MODE_MAP = {"color": "RGB24", "grayscale": "Grayscale8"}

# Fallback scan area (A4 at 1/300 inch) when the scanner does not report one.
DEFAULT_WIDTH = 2480
DEFAULT_HEIGHT = 3508

PAGE_TIMEOUT = 180
MAX_BATCH_BYTES = 512 * 1024 * 1024
BUSY_RETRY_DELAY = 1.0


class EsclError(Exception):
    """Scanner reported an error or could not be reached."""


class EsclNoPagesError(EsclError):
    """Job ended without any page (ADF empty or stale sensor); worth retrying."""


@dataclass
class SourceCaps:
    """Capabilities of one input source."""

    max_width: int = DEFAULT_WIDTH
    max_height: int = DEFAULT_HEIGHT
    resolutions: list[int] = field(default_factory=list)
    color_modes: list[str] = field(default_factory=list)
    # Where the sheet lies inside the scan area (feeder only): Left/Center/Right, Top/Center/Bottom
    x_align: str | None = None
    y_align: str | None = None


@dataclass
class Capabilities:
    """Scanner capabilities."""

    model: str | None = None
    uuid: str | None = None
    platen: SourceCaps | None = None
    adf_simplex: SourceCaps | None = None
    adf_duplex: SourceCaps | None = None


@dataclass
class Status:
    """Scanner status."""

    state: str
    adf_state: str | None = None


def _strip_namespaces(root: ET.Element) -> ET.Element:
    for el in root.iter():
        el.tag = el.tag.rsplit("}", 1)[-1]
    return root


def _parse_source(el: ET.Element | None) -> SourceCaps | None:
    if el is None:
        return None
    caps = SourceCaps()
    if (w := el.findtext("MaxWidth")) and w.isdigit():
        caps.max_width = int(w)
    if (h := el.findtext("MaxHeight")) and h.isdigit():
        caps.max_height = int(h)
    caps.color_modes = [c.text for c in el.iter("ColorMode") if c.text]
    caps.resolutions = sorted(
        {int(r.text) for r in el.iter("XResolution") if r.text and r.text.isdigit()}
    )
    return caps


def parse_capabilities(xml: str | bytes) -> Capabilities:
    """Parse a ScannerCapabilities document."""
    try:
        root = _strip_namespaces(ET.fromstring(xml))
    except ET.ParseError as err:
        raise EsclError("Invalid ScannerCapabilities response") from err
    caps = Capabilities(
        model=root.findtext("MakeAndModel"),
        uuid=root.findtext("UUID"),
        platen=_parse_source(root.find(".//PlatenInputCaps")),
        adf_simplex=_parse_source(root.find(".//AdfSimplexInputCaps")),
        adf_duplex=_parse_source(root.find(".//AdfDuplexInputCaps")),
    )
    if (adf := root.find(".//Adf")) is not None:
        for src in (caps.adf_simplex, caps.adf_duplex):
            if src:
                src.x_align = (adf.findtext("XImagePosition") or "").strip() or None
                src.y_align = (adf.findtext("YImagePosition") or "").strip() or None
    return caps


# Paper sizes in 1/300 inch (width, height). "max" = whole scan area.
PAGE_SIZES: dict[str, tuple[int, int] | None] = {
    "a4": (2480, 3508),
    "a5": (1748, 2480),
    "letter": (2550, 3300),
    "legal": (2550, 4200),
    "max": None,
}


# Slack added around the paper so a slightly skewed or oversized sheet keeps its edges.
WIDTH_MARGIN = 15
HEIGHT_MARGIN = 20


def scan_region(
    src: SourceCaps, page_size: str, align: str = "auto"
) -> tuple[int, int, int, int]:
    """Return (width, height, x_offset, y_offset) for the requested paper size.

    Scanning the whole area of a Legal-sized feeder gives A4 pages with a white
    strip at the bottom, so the region is cut to the paper size plus a small
    margin. The width is only narrowed when we know where the sheet lies: either
    the user said so (`align` = left/center/right) or the scanner reports it.
    Otherwise the full width is kept, since a wrongly guessed side would clip
    the sheet. The sheet is assumed at the top.
    """
    size = PAGE_SIZES.get(page_size)
    if size is None:  # "max": whole scan area, no cutting
        return src.max_width, src.max_height, 0, 0
    height = min(size[1] + HEIGHT_MARGIN, src.max_height)
    y_off = {"Center": (src.max_height - height) // 2, "Bottom": src.max_height - height}.get(
        src.y_align or "", 0
    )
    x_align = {"left": "Left", "center": "Center", "right": "Right"}.get(align, src.x_align)
    if x_align in ("Left", "Center", "Right"):
        width = min(size[0] + WIDTH_MARGIN, src.max_width)
        x_off = {
            "Left": 0,
            "Center": (src.max_width - width) // 2,
            "Right": src.max_width - width,
        }[x_align]
    else:
        width, x_off = src.max_width, 0
    return width, height, x_off, y_off


ADF_STATE_KEYS = {
    "scanneradfloaded": "loaded",
    "scanneradfempty": "empty",
    "scanneradfprocessing": "processing",
    "scanneradfjam": "jam",
    "scanneradfhatchopen": "cover_open",
    "scanneradfmispick": "error",
    "scanneradfmultipickdetected": "error",
    "scanneradfinputtrayfailed": "error",
    "scanneradfinputtrayoverloaded": "error",
    "scanneradfduplexpagetooshort": "error",
    "scanneradfduplexpagetoolong": "error",
}
ADF_STATE_OPTIONS = ["loaded", "empty", "processing", "jam", "cover_open", "error"]


def adf_state_key(raw: str | None) -> str | None:
    """Map an eSCL AdfState to a sensor option (None if the scanner has no feeder)."""
    if not raw:
        return None
    return ADF_STATE_KEYS.get(raw.lower(), "error")


def parse_status(xml: str | bytes) -> Status:
    """Parse a ScannerStatus document."""
    try:
        root = _strip_namespaces(ET.fromstring(xml))
    except ET.ParseError as err:
        raise EsclError("Invalid ScannerStatus response") from err
    return Status(
        state=(root.findtext("State") or "Unknown"),
        adf_state=root.findtext("AdfState"),
    )


def build_scan_settings(
    *,
    source: str,
    duplex: bool,
    resolution: int,
    color_mode: str,
    width: int,
    height: int,
    x_offset: int = 0,
    y_offset: int = 0,
) -> str:
    """Build the ScanSettings XML (element order follows the eSCL schema)."""
    input_source = "Platen" if source == "platen" else "Feeder"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<scan:ScanSettings xmlns:pwg="{NS_PWG}" xmlns:scan="{NS_SCAN}">'
        "<pwg:Version>2.0</pwg:Version>"
        "<pwg:ScanRegions><pwg:ScanRegion>"
        "<pwg:ContentRegionUnits>escl:ThreeHundredthsOfInches</pwg:ContentRegionUnits>"
        f"<pwg:Height>{height}</pwg:Height><pwg:Width>{width}</pwg:Width>"
        f"<pwg:XOffset>{x_offset}</pwg:XOffset><pwg:YOffset>{y_offset}</pwg:YOffset>"
        "</pwg:ScanRegion></pwg:ScanRegions>"
        "<pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>"
        f"<pwg:InputSource>{input_source}</pwg:InputSource>"
        f"<scan:ColorMode>{COLOR_MODE_MAP[color_mode]}</scan:ColorMode>"
        f"<scan:XResolution>{resolution}</scan:XResolution>"
        f"<scan:YResolution>{resolution}</scan:YResolution>"
        # Only ask for duplex when wanted; some devices dislike an explicit "false".
        + ("<scan:Duplex>true</scan:Duplex>" if source == "adf" and duplex else "")
        + "</scan:ScanSettings>"
    )


class EsclClient:
    """Talk to one eSCL scanner."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        tls: bool,
        root: str = "eSCL",
    ) -> None:
        self._session = session
        self._origin = f"{'https' if tls else 'http'}://{host}:{port}"
        self._base = f"{self._origin}/{root.strip('/')}"

    async def _get(self, url: str, timeout: int = 15) -> aiohttp.ClientResponse:
        try:
            return await self._session.get(url, timeout=ClientTimeout(total=timeout))
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EsclError(f"Cannot reach scanner: {err}") from err

    async def capabilities(self) -> Capabilities:
        """Fetch the scanner capabilities."""
        async with await self._get(f"{self._base}/ScannerCapabilities") as resp:
            if resp.status != 200:
                raise EsclError(f"ScannerCapabilities returned HTTP {resp.status}")
            return parse_capabilities(await resp.read())

    async def status(self) -> Status:
        """Fetch the scanner status."""
        async with await self._get(f"{self._base}/ScannerStatus") as resp:
            if resp.status != 200:
                raise EsclError(f"ScannerStatus returned HTTP {resp.status}")
            return parse_status(await resp.read())

    async def scan(
        self,
        settings_xml: str,
        *,
        single_page: bool,
        timeout: int = PAGE_TIMEOUT,
        on_page: Callable[[int], None] | None = None,
    ) -> list[bytes]:
        """Run a scan job and return all pages as JPEG data.

        `timeout` bounds each wait for the next page. `on_page` is called with
        the running page count.
        """
        loop = asyncio.get_running_loop()
        url = f"{self._base}/ScanJobs"
        location = None
        for _ in range(3):  # POST must not be silently turned into a GET by a redirect
            try:
                resp = await self._session.post(
                    url,
                    data=settings_xml.encode(),
                    headers={"Content-Type": "text/xml"},
                    timeout=ClientTimeout(total=30),
                    allow_redirects=False,
                )
            except (aiohttp.ClientError, TimeoutError) as err:
                raise EsclError(f"Cannot reach scanner: {err}") from err
            async with resp:
                if resp.status in (301, 302, 303, 307, 308) and resp.headers.get("Location"):
                    url = urljoin(url, resp.headers["Location"])
                    _LOGGER.debug("ScanJobs redirected to %s", url)
                    continue
                if resp.status == 409:
                    raise EsclNoPagesError("Scanner refused the job (ADF empty or cover open?)")
                if resp.status == 503:
                    raise EsclError("Scanner is busy")
                if resp.status != 201 or not (location := resp.headers.get("Location")):
                    body = (await resp.text(errors="replace"))[:200].strip()
                    allow = resp.headers.get("Allow")
                    _LOGGER.warning(
                        "Scan job rejected: POST %s -> HTTP %s, Allow=%s, body=%r, settings=%s",
                        url, resp.status, allow, body, settings_xml,
                    )
                    raise EsclError(
                        f"Scan job rejected (HTTP {resp.status}) by POST {url}"
                        + (f", allowed: {allow}" if allow else "")
                        + (f", reply: {body}" if body else "")
                    )
                break
        else:
            raise EsclError("Too many redirects while creating the scan job")
        # Some devices answer with an absolute URL using a wrong scheme/host.
        job_origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        job_url = f"{job_origin}{urlparse(location).path}".rstrip("/")

        pages: list[bytes] = []
        try:
            deadline = loop.time() + timeout
            while True:
                try:
                    page_resp = await self._session.get(
                        f"{job_url}/NextDocument", timeout=ClientTimeout(total=timeout)
                    )
                except (aiohttp.ClientError, TimeoutError) as err:
                    raise EsclError(f"Scan interrupted: {err}") from err
                async with page_resp:
                    if page_resp.status == 200:
                        pages.append(await page_resp.read())
                        if sum(map(len, pages)) > MAX_BATCH_BYTES:
                            raise EsclError(
                                "Scan zu groß (Limit 512 MiB) – kleinere Auflösung oder weniger Seiten"
                            )
                        deadline = loop.time() + timeout
                        if on_page:
                            on_page(len(pages))
                        if single_page:
                            break
                    elif page_resp.status in (404, 409, 410):
                        break  # no more pages / feeder ran out
                    elif page_resp.status == 503:
                        if loop.time() > deadline:
                            raise EsclError("Timeout waiting for the scanner")
                        await asyncio.sleep(BUSY_RETRY_DELAY)
                    else:
                        raise EsclError(f"NextDocument returned HTTP {page_resp.status}")
        finally:
            # 404 here (job already completed) is harmless.
            try:
                await self._session.delete(job_url, timeout=ClientTimeout(total=10))
            except (aiohttp.ClientError, TimeoutError):
                pass

        if not pages:
            raise EsclNoPagesError("Scanner returned no pages (ADF empty?)")
        return pages
