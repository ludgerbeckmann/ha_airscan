"""Minimal async client for the eSCL (AirScan) protocol."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import aiohttp
from aiohttp import ClientTimeout

NS_PWG = "http://www.pwg.org/schemas/2010/12/sm"
NS_SCAN = "http://schemas.hp.com/imaging/escl/2011/05/03"

COLOR_MODE_MAP = {"color": "RGB24", "grayscale": "Grayscale8"}

# Fallback scan area (A4 at 1/300 inch) when the scanner does not report one.
DEFAULT_WIDTH = 2480
DEFAULT_HEIGHT = 3508

PAGE_TIMEOUT = 180
BUSY_RETRY_DELAY = 1.0


class EsclError(Exception):
    """Scanner reported an error or could not be reached."""


@dataclass
class SourceCaps:
    """Capabilities of one input source."""

    max_width: int = DEFAULT_WIDTH
    max_height: int = DEFAULT_HEIGHT
    resolutions: list[int] = field(default_factory=list)
    color_modes: list[str] = field(default_factory=list)


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
    return Capabilities(
        model=root.findtext("MakeAndModel"),
        uuid=root.findtext("UUID"),
        platen=_parse_source(root.find(".//PlatenInputCaps")),
        adf_simplex=_parse_source(root.find(".//AdfSimplexInputCaps")),
        adf_duplex=_parse_source(root.find(".//AdfDuplexInputCaps")),
    )


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
        "<pwg:XOffset>0</pwg:XOffset><pwg:YOffset>0</pwg:YOffset>"
        "</pwg:ScanRegion></pwg:ScanRegions>"
        "<pwg:DocumentFormat>image/jpeg</pwg:DocumentFormat>"
        f"<pwg:InputSource>{input_source}</pwg:InputSource>"
        f"<scan:ColorMode>{COLOR_MODE_MAP[color_mode]}</scan:ColorMode>"
        f"<scan:XResolution>{resolution}</scan:XResolution>"
        f"<scan:YResolution>{resolution}</scan:YResolution>"
        + (f"<scan:Duplex>{'true' if duplex else 'false'}</scan:Duplex>" if source == "adf" else "")
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

    async def scan(self, settings_xml: str, *, single_page: bool) -> list[bytes]:
        """Run a scan job and return all pages as JPEG data."""
        try:
            resp = await self._session.post(
                f"{self._base}/ScanJobs",
                data=settings_xml.encode(),
                headers={"Content-Type": "text/xml"},
                timeout=ClientTimeout(total=30),
            )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EsclError(f"Cannot reach scanner: {err}") from err
        async with resp:
            if resp.status == 409:
                raise EsclError("Scanner refused the job (ADF empty or cover open?)")
            if resp.status == 503:
                raise EsclError("Scanner is busy")
            if resp.status != 201 or not (location := resp.headers.get("Location")):
                raise EsclError(f"Scan job rejected (HTTP {resp.status})")
        # Some devices answer with an absolute URL using a wrong scheme/host.
        job_url = f"{self._origin}{urlparse(location).path}".rstrip("/")

        pages: list[bytes] = []
        try:
            deadline = asyncio.get_running_loop().time() + PAGE_TIMEOUT
            while True:
                try:
                    page_resp = await self._session.get(
                        f"{job_url}/NextDocument",
                        timeout=ClientTimeout(total=PAGE_TIMEOUT),
                    )
                except (aiohttp.ClientError, TimeoutError) as err:
                    raise EsclError(f"Scan interrupted: {err}") from err
                async with page_resp:
                    if page_resp.status == 200:
                        pages.append(await page_resp.read())
                        deadline = asyncio.get_running_loop().time() + PAGE_TIMEOUT
                        if single_page:
                            break
                    elif page_resp.status == 404:
                        break
                    elif page_resp.status == 503:
                        if asyncio.get_running_loop().time() > deadline:
                            raise EsclError("Timeout waiting for the scanner")
                        await asyncio.sleep(BUSY_RETRY_DELAY)
                    else:
                        raise EsclError(f"NextDocument returned HTTP {page_resp.status}")
        finally:
            try:
                await self._session.delete(job_url, timeout=ClientTimeout(total=10))
            except (aiohttp.ClientError, TimeoutError):
                pass

        if not pages:
            raise EsclError("Scanner returned no pages (ADF empty?)")
        return pages
