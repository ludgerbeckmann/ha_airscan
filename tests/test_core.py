"""Tests for the pure-Python parts (no Home Assistant required)."""

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import types

from PIL import Image

base = Path(__file__).parent.parent / "custom_components" / "ha_airscan"
pkg = types.ModuleType("airscan_pkg")
pkg.__path__ = [str(base)]
sys.modules["airscan_pkg"] = pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"airscan_pkg.{name}", base / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


escl, pdf = _load("escl"), _load("pdf")

CAPS = """<?xml version="1.0"?>
<scan:ScannerCapabilities xmlns:scan="http://schemas.hp.com/imaging/escl/2011/05/03" xmlns:pwg="http://www.pwg.org/schemas/2010/12/sm">
<pwg:MakeAndModel>EPSON XP-7100</pwg:MakeAndModel><pwg:UUID>abc</pwg:UUID>
<scan:Platen><scan:PlatenInputCaps><scan:MaxWidth>2552</scan:MaxWidth><scan:MaxHeight>3507</scan:MaxHeight>
<scan:SettingProfiles><scan:SettingProfile><scan:ColorModes><scan:ColorMode>RGB24</scan:ColorMode></scan:ColorModes>
<scan:SupportedResolutions><scan:DiscreteResolutions><scan:DiscreteResolution><scan:XResolution>300</scan:XResolution><scan:YResolution>300</scan:YResolution></scan:DiscreteResolution></scan:DiscreteResolutions></scan:SupportedResolutions>
</scan:SettingProfile></scan:SettingProfiles></scan:PlatenInputCaps></scan:Platen>
<scan:Adf><scan:AdfSimplexInputCaps><scan:MaxWidth>2480</scan:MaxWidth></scan:AdfSimplexInputCaps>
<scan:AdfDuplexInputCaps><scan:MaxWidth>2480</scan:MaxWidth></scan:AdfDuplexInputCaps></scan:Adf>
</scan:ScannerCapabilities>"""


def test_capabilities():
    caps = escl.parse_capabilities(CAPS)
    assert caps.model == "EPSON XP-7100" and caps.uuid == "abc"
    assert caps.platen.max_width == 2552 and caps.platen.resolutions == [300]
    assert caps.adf_simplex and caps.adf_duplex


def test_status():
    xml = '<scan:ScannerStatus xmlns:pwg="p" xmlns:scan="s"><pwg:State>Idle</pwg:State><scan:AdfState>ScannerAdfLoaded</scan:AdfState></scan:ScannerStatus>'
    s = escl.parse_status(xml)
    assert (s.state, s.adf_state) == ("Idle", "ScannerAdfLoaded")


def test_settings_duplex():
    x = escl.build_scan_settings(source="adf", duplex=True, resolution=300, color_mode="color", width=1, height=2)
    assert "Feeder" in x and "<scan:Duplex>true" in x and "RGB24" in x
    x = escl.build_scan_settings(source="platen", duplex=False, resolution=300, color_mode="grayscale", width=1, height=2)
    assert "Platen" in x and "Duplex" not in x and "Grayscale8" in x


def _jpeg(mode):
    b = BytesIO()
    Image.new(mode, (30, 40), 128 if mode == "L" else (1, 2, 3)).save(b, "JPEG")
    return b.getvalue()


def test_pdf():
    data = pdf.jpegs_to_pdf([_jpeg("RGB"), _jpeg("L")], 300)
    assert data.startswith(b"%PDF") and data.rstrip().endswith(b"%%EOF")
    assert data.count(b"/Type /Page ") == 2 and b"DeviceGray" in data
    assert _jpeg("RGB") in data  # embedded losslessly


# --- fake eSCL scanner ------------------------------------------------------

import asyncio

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer


def _fake_printer(pages_in_adf=3, stale_adf=False):
    """Mimics the ET-3950 quirks: duplex flag, 404 after last page, stale ADF state."""
    st = {"adf": pages_in_adf, "stale": stale_adf, "jobs": {}, "deleted": [], "settings": []}

    async def post_job(req):
        body = (await req.read()).decode()
        st["settings"].append(body)
        if "Feeder" in body:
            if st["stale"]:
                return web.Response(status=201, headers={"Location": "/eSCL/ScanJobs/empty"})
            st["jobs"]["1"] = st["adf"]
            return web.Response(status=201, headers={"Location": "http://wrong-host/eSCL/ScanJobs/1"})
        st["stale"] = False  # a flatbed scan refreshes the sensor
        st["jobs"]["f"] = 1
        return web.Response(status=201, headers={"Location": "/eSCL/ScanJobs/f"})

    async def next_doc(req):
        job = req.match_info["job"]
        if st["jobs"].get(job, 0) > 0:
            st["jobs"][job] -= 1
            return web.Response(body=_jpeg("RGB"), content_type="image/jpeg")
        return web.Response(status=404)

    async def delete(req):
        st["deleted"].append(req.match_info["job"])
        return web.Response(status=200)

    app = web.Application()
    app.router.add_post("/eSCL/ScanJobs", post_job)
    app.router.add_get("/eSCL/ScanJobs/{job}/NextDocument", next_doc)
    app.router.add_delete("/eSCL/ScanJobs/{job}", delete)
    return app, st


def _run(coro):
    return asyncio.run(coro)


def test_adf_duplex_collects_all_pages():
    async def go():
        app, st = _fake_printer(pages_in_adf=4)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            client = escl.EsclClient(sess, srv.host, srv.port, False)
            seen = []
            xml = escl.build_scan_settings(source="adf", duplex=True, resolution=300, color_mode="color", width=2480, height=3508)
            pages = await client.scan(xml, single_page=False, timeout=5, on_page=seen.append)
            assert len(pages) == 4 and seen == [1, 2, 3, 4]
            assert "<scan:Duplex>true" in st["settings"][0]
            assert st["deleted"] == ["1"]  # absolute Location with wrong host handled
    _run(go())


def test_platen_single_page_and_no_pages_error():
    async def go():
        app, st = _fake_printer(pages_in_adf=0)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            client = escl.EsclClient(sess, srv.host, srv.port, False)
            plat = escl.build_scan_settings(source="platen", duplex=False, resolution=300, color_mode="color", width=100, height=100)
            assert len(await client.scan(plat, single_page=True, timeout=5)) == 1
            adf = escl.build_scan_settings(source="adf", duplex=False, resolution=300, color_mode="color", width=100, height=100)
            try:
                await client.scan(adf, single_page=False, timeout=5)
            except escl.EsclNoPagesError:
                pass
            else:
                raise AssertionError("expected EsclNoPagesError")
    _run(go())
