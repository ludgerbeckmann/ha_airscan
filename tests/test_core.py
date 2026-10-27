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
    x = escl.build_scan_settings(source="adf", duplex=False, resolution=300, color_mode="color", width=1, height=2)
    assert "Feeder" in x and "Duplex" not in x
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


def test_atomic_write(tmp_path):
    files = _load("files")
    target = tmp_path / "in" / "scan.pdf"
    files.write_atomic(target, b"%PDF", min_free=0)
    assert target.read_bytes() == b"%PDF"
    assert [p.name for p in target.parent.iterdir()] == ["scan.pdf"]  # no temp left behind
    try:
        files.write_atomic(target, b"x", min_free=10**18)
    except files.FileOutputError:
        pass
    else:
        raise AssertionError("expected FileOutputError")
    assert target.read_bytes() == b"%PDF"  # existing file untouched


def test_size_limit(monkeypatch):
    async def go():
        monkeypatch.setattr(escl, "MAX_BATCH_BYTES", 10)
        app, _ = _fake_printer(pages_in_adf=3)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            client = escl.EsclClient(sess, srv.host, srv.port, False)
            xml = escl.build_scan_settings(source="adf", duplex=False, resolution=300, color_mode="color", width=1, height=1)
            try:
                await client.scan(xml, single_page=False, timeout=5)
            except escl.EsclError as err:
                assert "zu groß" in str(err)
            else:
                raise AssertionError("expected size error")
    _run(go())


def test_paperless_client():
    paperless = _load("paperless")

    async def go():
        seen = {}

        async def docs(req):
            seen["accept"] = req.headers["Accept"]
            if req.headers.get("Authorization") != "Token good":
                return web.Response(status=401)
            return web.json_response({"results": []})

        async def post(req):
            form = await req.post()
            seen["fields"] = sorted(form.keys())
            seen["tags"] = form.getall("tags")
            return web.Response(text='"task-123"')

        app = web.Application()
        app.router.add_get("/api/documents/", docs)
        app.router.add_post("/api/documents/post_document/", post)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            url = f"http://{srv.host}:{srv.port}"
            ok = paperless.PaperlessClient(sess, url, "good")
            await ok.check()
            assert seen["accept"] == "application/json"  # no pinned API version
            task = await ok.upload(b"%PDF", "scan.pdf", title="t", tags=["1", "2"])
            assert task == "task-123" and seen["tags"] == ["1", "2"]
            assert "document" in seen["fields"] and "title" in seen["fields"]
            try:
                await paperless.PaperlessClient(sess, url, "bad").check()
            except paperless.PaperlessAuthError:
                pass
            else:
                raise AssertionError("expected auth error")
            try:
                await paperless.PaperlessClient(sess, "http://127.0.0.1:1", "x").check()
            except paperless.PaperlessError as err:
                assert "ClientConnectorError" in str(err) or "Connect" in str(err)
            else:
                raise AssertionError("expected connection error")

    _run(go())


def test_post_redirect_is_followed_as_post_and_405_is_explained():
    async def go():
        st = {"methods": []}

        async def redirect(req):
            return web.Response(status=307, headers={"Location": "/eSCL/Jobs2"})

        async def jobs2(req):
            st["methods"].append(req.method)
            return web.Response(status=201, headers={"Location": "/eSCL/ScanJobs/f"})

        async def next_doc(req):
            if not st.get("sent"):
                st["sent"] = True
                return web.Response(body=_jpeg("RGB"), content_type="image/jpeg")
            return web.Response(status=404)

        async def nope(req):
            return web.Response(status=405, headers={"Allow": "GET"}, text="Method Not Allowed")

        app = web.Application()
        app.router.add_post("/eSCL/ScanJobs", redirect)
        app.router.add_post("/eSCL/Jobs2", jobs2)
        app.router.add_get("/eSCL/ScanJobs/{job}/NextDocument", next_doc)
        app.router.add_delete("/eSCL/ScanJobs/{job}", lambda r: web.Response())
        app405 = web.Application()
        app405.router.add_post("/eSCL/ScanJobs", nope)

        xml = escl.build_scan_settings(source="platen", duplex=False, resolution=300, color_mode="color", width=1, height=1)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            client = escl.EsclClient(sess, srv.host, srv.port, False)
            assert len(await client.scan(xml, single_page=True, timeout=5)) == 1
            assert st["methods"] == ["POST"]
        async with TestServer(app405) as srv, aiohttp.ClientSession() as sess:
            client = escl.EsclClient(sess, srv.host, srv.port, False)
            try:
                await client.scan(xml, single_page=True, timeout=5)
            except escl.EsclError as err:
                assert "405" in str(err) and "allowed: GET" in str(err) and "/eSCL/ScanJobs" in str(err)
            else:
                raise AssertionError("expected error")

    _run(go())


# --- blank page detection ---------------------------------------------------

from PIL import ImageDraw


def _page(draw_fn=None, base=255, size=(1240, 1754)):
    img = Image.new("L", size, base)
    if draw_fn:
        draw_fn(ImageDraw.Draw(img), size)
    b = BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=85)
    return b.getvalue()


def _text(lines):
    def draw(d, size):
        for i in range(lines):
            y = 150 + i * 40
            for x in range(120, size[0] - 120, 30):  # word-like blocks
                d.rectangle([x, y, x + 20, y + 14], fill=20)
    return draw


def test_blank_detection():
    blank = _load("blank")
    white = _page()
    dust = _page(lambda d, s: [d.ellipse([300 + i * 90, 700, 304 + i * 90, 704], fill=60) for i in range(5)])
    showthrough = _page(_text(30), base=255)
    # faint mirrored text of the other side shining through thin paper
    faint = _page(lambda d, s: [d.rectangle([x, y, x + 20, y + 14], fill=228) for y in range(150, 1350, 40) for x in range(120, 1100, 30)])
    shadow_border = _page(lambda d, s: (d.rectangle([0, 0, s[0], 30], fill=90), d.rectangle([0, 0, 25, s[1]], fill=90)))
    full_text = _page(_text(35))
    short_letter = _page(_text(4))  # only a few lines: must NOT be dropped at the default threshold
    black = _page(base=10)

    assert blank.is_blank(white) and blank.is_blank(dust)
    assert blank.is_blank(faint), "faint show-through must count as blank"
    assert blank.is_blank(shadow_border), "scanner border shadow is ignored"
    assert not blank.is_blank(full_text)
    assert not blank.is_blank(short_letter)
    assert not blank.is_blank(black), "a dark page is content, not blank"
    assert showthrough  # sanity: generator works

    kept, removed = blank.filter_blank([full_text, white, short_letter, faint, full_text])
    assert removed == 2 and kept == [full_text, short_letter, full_text]  # order preserved
    assert blank.filter_blank([white, faint]) == ([], 2)


# --- page size / feeder states / paperless task ---------------------------------


def test_scan_region_cuts_legal_feeder_to_a4():
    legal_feeder = escl.SourceCaps(max_width=2550, max_height=4200)  # real ET-3950 simplex feeder
    # Alignment unknown: keep the full width (a wrongly guessed side would clip the sheet),
    # cut the height to A4 plus a little slack.
    assert escl.scan_region(legal_feeder, "a4") == (2550, 3528, 0, 0)
    assert escl.scan_region(legal_feeder, "legal") == (2550, 4200, 0, 0)  # 4200 + slack is capped
    assert escl.scan_region(legal_feeder, "max") == (2550, 4200, 0, 0)
    # The user says the sheet lies on the right (measured on the real scans):
    # same crop as the working Paperless fix script: x 55..2550, A4 height + slack.
    assert escl.scan_region(legal_feeder, "a4", "right") == (2495, 3528, 55, 0)
    assert escl.scan_region(legal_feeder, "a4", "left") == (2495, 3528, 0, 0)
    assert escl.scan_region(legal_feeder, "a4", "center") == (2495, 3528, 27, 0)
    # Alignment reported by the scanner is used for "auto", an explicit choice wins.
    reported = escl.SourceCaps(max_width=2550, max_height=4200, x_align="Right", y_align="Top")
    assert escl.scan_region(reported, "a4") == (2495, 3528, 55, 0)
    assert escl.scan_region(reported, "a4", "left") == (2495, 3528, 0, 0)
    # The duplex feeder reports A4 height already; never larger than the device can do.
    duplex = escl.SourceCaps(max_width=2550, max_height=3510)
    assert escl.scan_region(duplex, "a4", "right") == (2495, 3510, 55, 0)
    small = escl.SourceCaps(max_width=2400, max_height=3000, x_align="Right")
    assert escl.scan_region(small, "a4") == (2400, 3000, 0, 0)
    x = escl.build_scan_settings(source="adf", duplex=False, resolution=300, color_mode="color",
                                 width=2495, height=3528, x_offset=55, y_offset=0)
    assert "<pwg:XOffset>55</pwg:XOffset>" in x and "<pwg:Height>3528</pwg:Height>" in x


def test_capabilities_alignment_is_parsed():
    xml = CAPS.replace("<scan:Adf>", "<scan:Adf><scan:XImagePosition>Center</scan:XImagePosition><scan:YImagePosition>Top</scan:YImagePosition>")
    caps = escl.parse_capabilities(xml)
    assert (caps.adf_simplex.x_align, caps.adf_simplex.y_align) == ("Center", "Top")
    assert caps.platen.x_align is None


def test_feeder_states_do_not_become_unknown():
    assert escl.adf_state_key("ScannerAdfLoaded") == "loaded"
    assert escl.adf_state_key("ScannerAdfEmpty") == "empty"
    assert escl.adf_state_key("ScannerAdfProcessing") == "processing"  # appears during a scan
    assert escl.adf_state_key("ScannerAdfJam") == "jam"
    assert escl.adf_state_key("SomethingNew") == "error"  # unknown vendor value is still a valid option
    assert escl.adf_state_key(None) is None
    assert {escl.adf_state_key(k) for k in ("ScannerAdfProcessing", "ScannerAdfJam", "ScannerAdfHatchOpen", "x")} <= set(escl.ADF_STATE_OPTIONS)


def test_paperless_task_status():
    paperless = _load("paperless")

    async def go():
        tasks = {"t-ok": {"status": "SUCCESS", "related_document": 123},
                 "t-run": {"status": "STARTED", "related_document": None},
                 "t-dup": {"status": "FAILURE", "result": "scan.pdf: Not consuming scan.pdf: It is a duplicate of Foo (#7)"}}

        async def handler(req):
            tid = req.query["task_id"]
            if tid == "forbidden":
                return web.Response(status=403)
            return web.json_response([{"task_id": tid, **tasks[tid]}] if tid in tasks else [])

        app = web.Application()
        app.router.add_get("/api/tasks/", handler)
        async with TestServer(app) as srv, aiohttp.ClientSession() as sess:
            c = paperless.PaperlessClient(sess, f"http://{srv.host}:{srv.port}", "t")
            assert await c.task_status("t-ok") == {"finished": True, "related_document": 123}
            assert (await c.task_status("t-run"))["finished"] is False
            assert (await c.task_status("unknown"))["finished"] is False  # not registered yet
            assert await c.task_status("forbidden") is None  # token without task access: do not block
            try:
                await c.task_status("t-dup")
            except paperless.PaperlessTaskFailed as err:
                assert "duplicate" in str(err)
            else:
                raise AssertionError("expected PaperlessTaskFailed")

    _run(go())


def test_last_scan_summary():
    from datetime import datetime, timezone
    summary = _load("summary")
    when = datetime(2026, 10, 27, 20, 0, 13, tzinfo=timezone.utc)
    out = summary.summarize(
        {"pages": 6, "source": "adf_duplex", "destination": "paperless", "document_id": 123, "blank_removed": 2, "task_id": "x"},
        when,
    )
    assert out == {"source": "adf_duplex", "destination": "paperless", "document_id": 123,
                   "blank_removed": 2, "finished_at": "2026-10-27T20:00:13+00:00"}
    out = summary.summarize({"pages": 1, "source": "platen", "destination": "file"}, when)
    assert out["document_id"] is None and out["blank_removed"] == 0
