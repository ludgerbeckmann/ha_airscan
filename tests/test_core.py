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


def _lid(kind):
    """Synthetic scans of an empty flatbed (pure Pillow, no numpy)."""
    from PIL import ImageChops

    size = (1240, 1754)
    noise = Image.effect_noise(size, 3)                      # gaussian noise around 128
    if kind == "shade":                                      # closed lid with a strong shadow across the page
        base = Image.linear_gradient("L").rotate(90).resize(size).point(lambda v: 255 - v * 105 // 255)
    elif kind == "dark":                                     # lid open, nothing reflects
        base = Image.new("L", size, 25)
    elif kind == "washed":                                   # lid open in daylight
        base = Image.new("L", size, 250)
    else:                                                    # closed lid, slightly grey
        base = Image.new("L", size, 238)
    img = ImageChops.add(base, noise, scale=1, offset=-128)
    b = BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=85)
    return b.getvalue()


def test_blank_detection():
    blank = _load("blank")
    white = _page()
    dust = _page(lambda d, s: [d.ellipse([300 + i * 90, 700, 304 + i * 90, 704], fill=60) for i in range(5)])
    # faint mirrored text of the other side shining through thin paper
    faint = _page(lambda d, s: [d.rectangle([x, y, x + 20, y + 14], fill=228) for y in range(150, 1350, 40) for x in range(120, 1100, 30)])
    shadow_border = _page(lambda d, s: (d.rectangle([0, 0, s[0], 30], fill=90), d.rectangle([0, 0, 25, s[1]], fill=90)))
    full_text = _page(_text(35))
    short_letter = _page(_text(4))           # only a few lines: must NOT be dropped at the default threshold
    one_line = _page(_text(1))
    white_on_black = _page(lambda d, s: [d.rectangle([x, 150 + i * 40, x + 20, 164 + i * 40], fill=235) for i in range(6) for x in range(120, 1100, 30)], base=15)

    assert blank.is_blank(white) and blank.is_blank(dust)
    assert blank.is_blank(faint), "faint show-through must count as blank"
    assert blank.is_blank(shadow_border), "scanner border shadow is ignored"
    assert not blank.is_blank(full_text) and not blank.is_blank(short_letter)
    assert not blank.is_blank(one_line), "even a single line of text is content at the default threshold"

    # an empty flatbed in every way it can look: all blank
    for kind in ("grey", "shade", "dark", "washed"):
        assert blank.is_blank(_lid(kind)), f"empty flatbed ({kind}) must be blank"
    assert blank.is_blank(_page(base=10)), "a uniformly black scan (lid open) is blank"

    # ... while real content is still found on such backgrounds
    from PIL import ImageDraw
    page = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(page)
    for i in range(6):
        for x in range(120, 1120, 30):
            d.rectangle([x, 150 + i * 40, x + 20, 164 + i * 40], fill=20)
    shaded = page.point(lambda v: v)          # text page ...
    grad = Image.linear_gradient("L").rotate(90).resize(page.size).point(lambda v: v * 80 // 255)
    from PIL import ImageChops
    shaded = ImageChops.subtract(shaded, grad)  # ... with a lid shadow across it
    buf = BytesIO()
    shaded.convert("RGB").save(buf, "JPEG", quality=85)
    assert not blank.is_blank(buf.getvalue()), "text on a shaded page is content"
    assert not blank.is_blank(white_on_black), "light text on a dark page is content"

    kept, removed = blank.filter_blank([full_text, white, short_letter, faint, _lid("dark"), full_text])
    assert removed == 3 and kept == [full_text, short_letter, full_text]   # order preserved
    assert blank.filter_blank([white, faint, _lid("shade")]) == ([], 3)


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


# --- delivery queue ---------------------------------------------------------------

import types as _types


def test_outbox_store(tmp_path):
    store_mod = _load("outbox_store")
    store = store_mod.OutboxStore(tmp_path / "q")
    assert store.load() == []
    a = store.add(b"%PDF-a", {"filename": "a.pdf", "title": "A", "tags": ["1"]})
    store.add(b"%PDF-b", {"filename": "b.pdf", "title": "B", "tags": []})
    items = store.load()
    assert [i["title"] for i in items] == ["A", "B"]                      # oldest first
    assert store.read_pdf(a["id"]) == b"%PDF-a"
    store.update(items[0], attempts=3, last_error="boom")
    assert store.load()[0]["attempts"] == 3
    # a JSON without its PDF (crash while removing) and garbage are ignored, not fatal
    (store.path / "x.json").write_text('{"id": "nope"}')
    (store.path / "y.json").write_text("not json")
    assert len(store.load()) == 2
    store.remove(a["id"])
    assert [i["title"] for i in store.load()] == ["B"]
    assert not (store.path / f"{a['id']}.pdf").exists()
    # a new store instance (= after a restart) sees the same queue
    assert [i["title"] for i in store_mod.OutboxStore(tmp_path / "q").load()] == ["B"]
    assert [store_mod.next_delay(n) for n in (0, 1, 2, 3, 4, 5, 6, 50)] == [60, 60, 120, 300, 600, 900, 900, 900]


def test_paperless_errors_are_classified():
    paperless = _load("paperless")
    P = paperless.PaperlessError
    assert P("conn").retryable                                  # no HTTP status: outage / timeout
    assert P("x", 502).retryable and P("x", 503).retryable and P("x", 429).retryable
    assert paperless.PaperlessAuthError("tok", 401).retryable   # token can be fixed in the options
    assert not P("bad request", 400).retryable and not P("too large", 413).retryable
    assert not paperless.PaperlessTaskFailed("duplicate").retryable


def test_delivery_queue(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    paperless = _load("paperless")

    class HAError(Exception):
        pass

    def mod(name, **attrs):
        m = _types.ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)
        return m

    mod("homeassistant"); mod("homeassistant.helpers"); mod("homeassistant.util")
    mod("homeassistant.core", CALLBACK_TYPE=object, HomeAssistant=object, callback=lambda f: f)
    mod("homeassistant.exceptions", HomeAssistantError=HAError)
    mod("homeassistant.helpers.event", async_call_later=lambda hass, delay, action: (hass.timers.append((delay, action)), lambda: None)[1])
    mod("homeassistant.util.dt", utcnow=lambda: datetime.now(timezone.utc))
    waits = []

    async def fake_wait(data, info):
        if waits:
            outcome = waits.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            info.update(outcome)

    monkeypatch.setitem(sys.modules, "airscan_pkg.scan", _types.SimpleNamespace(wait_for_paperless=fake_wait))
    delivery = _load("delivery")

    class Bus:
        def __init__(self):
            self.events = []

        def async_fire(self, name, data):
            self.events.append((name, data))

    class Hass:
        def __init__(self):
            self.bus, self.timers = Bus(), []

        async def async_add_executor_job(self, fn, *args):
            return fn(*args)

    class Tracker:
        status, detail = "queued", ""

        def update(self, status=None, detail=None, pages=None):
            self.status = status or self.status
            self.detail = detail if detail is not None else self.detail

    class FakePaperless:
        def __init__(self):
            self.script, self.sent = [], []

        async def upload(self, pdf, filename, **kw):
            outcome = self.script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            self.sent.append((filename, kw.get("title"), pdf))
            return outcome

    async def go():
        hass, tracker, pl = Hass(), Tracker(), FakePaperless()
        box = delivery.Outbox(hass, tmp_path / "box", lambda: None)
        box.data = SimpleNamespace(paperless=pl, tracker=tracker)
        for n in ("A", "B"):
            await box.async_add(f"%PDF-{n}".encode(), {"filename": f"{n}.pdf", "title": n, "tags": ["1"]}, "down")
        assert len(box.pending) == 2

        # 1) Paperless still down: nothing lost, retry scheduled with growing delay
        for expected in (60, 120, 300):
            pl.script = [paperless.PaperlessError("ConnectError")]
            result = await box.async_deliver()
            assert result == {"delivered": 0, "remaining": 2, "rejected": 0}
            assert hass.timers[-1][0] == expected
            assert tracker.status == "queued" and "nicht erreichbar" in tracker.detail
        assert box.items[0]["attempts"] == 4 and "ConnectError" in box.items[0]["last_error"]

        # 2) wrong token is retryable too (the user can fix it); the scan stays queued
        pl.script = [paperless.PaperlessAuthError("Invalid token", 401)]
        assert (await box.async_deliver())["remaining"] == 2

        # 3) a restart in between: a fresh Outbox finds the same two scans on disk
        box2 = delivery.Outbox(hass, tmp_path / "box", lambda: None)
        await box2.async_load()
        assert [i["title"] for i in box2.pending] == ["A", "B"]
        box2.data = box.data

        # 4) Paperless is back: both delivered, in order, files removed, 'done' status, event fired
        pl.script = ["task-a", "task-b"]
        waits[:] = [{"document_id": 11}, {"document_id": 12}]
        result = await box2.async_deliver()
        assert result == {"delivered": 2, "remaining": 0, "rejected": 0}
        assert [s[1] for s in pl.sent] == ["A", "B"] and pl.sent[0][2] == b"%PDF-A"
        assert tracker.status == "done" and "2 Scan(s)" in tracker.detail
        assert [e[1]["document_id"] for e in hass.bus.events] == [11, 12]
        assert list((tmp_path / "box").glob("*")) == []

        # 5) duplicate = Paperless already has it (first upload succeeded, answer got lost): counts as delivered
        await box2.async_add(b"%PDF-C", {"filename": "C.pdf", "title": "C", "tags": []}, "down")
        pl.script = ["task-c"]
        waits[:] = [HAError("Paperless hat das Dokument abgelehnt: scan.pdf: It is a duplicate of X (#7)")]
        assert (await box2.async_deliver())["delivered"] == 1

        # 6) Paperless refuses for good (HTTP 400, or failed processing): file is kept, other scans continue
        await box2.async_add(b"%PDF-D", {"filename": "D.pdf", "title": "D", "tags": []}, "down")
        await box2.async_add(b"%PDF-E", {"filename": "E.pdf", "title": "E", "tags": []}, "down")
        pl.script = [paperless.PaperlessError("bad", 400), "task-e"]
        waits[:] = [{"document_id": 99}]
        result = await box2.async_deliver()
        assert result == {"delivered": 1, "remaining": 0, "rejected": 1}
        assert len(list((tmp_path / "box").glob("*.pdf"))) == 1               # the refused one stays for manual handling
        assert box2.rejected[0]["title"] == "D" and not box2.pending
        before = len(pl.sent)
        await box2.async_deliver()                                           # refused items are not retried
        assert len(pl.sent) == before

        # 7) Paperless not configured at all: nothing is thrown away
        box2.data = SimpleNamespace(paperless=None, tracker=tracker)
        await box2.async_add(b"%PDF-F", {"filename": "F.pdf", "title": "F", "tags": []}, "down")
        assert (await box2.async_deliver())["remaining"] == 1

    asyncio.run(go())


# --- notifications ----------------------------------------------------------------


def test_notification_texts():
    nm = _load("notify_messages")
    done = nm.scan_message("scan_done", {"pages": 6, "destination": "paperless", "document_id": 123, "blank_removed": 2})
    assert (done["title"], done["message"]) == ("Scan fertig", "6 Seiten → Paperless (Dokument #123), 2 Leerseite(n) entfernt")
    assert nm.scan_message("scan_done", {"pages": 1, "destination": "file"})["message"] == "1 Seite → Datei"
    assert nm.scan_message("scan_done", {"pages": 2, "destination": "paperless", "document_id": 5}, "en")["message"] == "2 pages → Paperless (document #5)"
    err = nm.scan_message("scan_error", {"detail": "Scan fehlgeschlagen: Scanner is busy"})
    assert err["message"] == "Scan fehlgeschlagen: Scanner is busy" and err["time_sensitive"]
    queued = nm.scan_message("queued", {"pages": 3, "queue_error": "ClientConnectorError: no route"})
    assert "Paperless nicht erreichbar" in queued["message"] and "ClientConnectorError" in queued["message"]
    stale = nm.scan_message("batch_stale", {"batch_pages": 3})
    assert stale["actions"] and "3 Seiten" in stale["message"]
    assert nm.scan_message("printer_offline", {})["message"].startswith("Ist der Drucker eingeschaltet")
    rejected = nm.scan_message("button_rejected", {"action": "adf"})
    assert rejected["title"] == "Taster ignoriert" and not rejected["actions"]
    assert nm.scan_message("button_rejected", {}, "en")["title"] == "Button ignored"
    assert nm.action_labels("de") == ("Senden", "Verwerfen")


def test_paperless_webhook_matches_the_old_automation():
    nm = _load("notify_messages")
    # exactly the fields of the existing automation
    doc = nm.normalize_paperless({"typ": "frist", "korrespondent": "Stadtwerke", "titel": "Rechnung 10/2026",
                                  "dokumenttyp": "Rechnung", "belegdatum": "2026-10-20", "url": "http://paperless/documents/7/"})
    msg = nm.paperless_message(doc)
    assert msg == {"title": "Paperless ngx: Frist", "message": "Stadtwerke: Rechnung 10/2026 (Rechnung, 2026-10-20)",
                   "tag": "Paperless-Frist", "url": "http://paperless/documents/7/", "time_sensitive": True, "actions": False}
    new = nm.paperless_message(nm.normalize_paperless({}))                 # all defaults
    assert (new["title"], new["message"], new["tag"], new["time_sensitive"]) == ("Paperless ngx: Neues Dokument", "unbekannt: ohne Titel", "Paperless", False)
    assert nm.paperless_message(nm.normalize_paperless({"titel": "X", "dokumenttyp": "Brief"}))["message"] == "unbekannt: X (Brief)"
    # English field names of a default Paperless workflow work as well
    en = nm.normalize_paperless({"type": "due", "correspondent": "ACME", "title": "Invoice", "document_type": "Bill"})
    assert (en["typ"], en["korrespondent"], en["titel"], en["dokumenttyp"]) == ("frist", "ACME", "Invoice", "Bill")


def test_notifier(monkeypatch):
    from types import SimpleNamespace

    class HAError(Exception):
        pass

    def mod(name, **attrs):
        m = _types.ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)

    class Event:
        def __init__(self, data):
            self.data = data

    mod("homeassistant"); mod("homeassistant.helpers")
    mod("homeassistant.core", Event=Event, HomeAssistant=object, callback=lambda f: f)
    mod("homeassistant.exceptions", HomeAssistantError=HAError)
    scan_calls = []

    async def fake_send(hass, entry):
        scan_calls.append(("send", entry.entry_id))

    async def fake_discard(hass, entry):
        scan_calls.append(("discard", entry.entry_id))

    monkeypatch.setitem(sys.modules, "airscan_pkg.scan", _types.SimpleNamespace(async_batch_send=fake_send, async_batch_discard=fake_discard))
    notifications = _load("notifications")

    class Bus:
        def __init__(self):
            self.listeners = []

        def async_listen(self, event_type, handler):
            self.listeners.append((event_type, handler))
            return lambda: None

    class Services:
        def __init__(self):
            self.calls, self.broken = [], set()

        async def async_call(self, domain, service, data, blocking=False):
            if service in self.broken:
                raise HAError("boom")
            self.calls.append((domain, service, data))

    class Hass:
        def __init__(self):
            self.bus, self.services, self.tasks = Bus(), Services(), []
            self.config = SimpleNamespace(language="de")

        def async_create_task(self, coro):
            self.tasks.append(coro)

    async def go():
        hass = Hass()
        entry = SimpleNamespace(entry_id="E1", options={
            "notify_services": ["mobile_app_iphone", "telegram_me", "persistent_notification", "broken_one"],
            "notify_entities": ["notify.ntfy"],
            "notify_scan_types": ["scan_error", "queued", "batch_stale"],
            "notify_paperless_types": ["frist"],
        }, async_on_unload=lambda fn: None)
        hass.services.broken.add("broken_one")
        n = notifications.Notifier(hass, entry)
        n.async_start()
        assert {t for t, _ in hass.bus.listeners} >= {"ha_airscan_scan_finished", "ha_airscan_scan_failed", "ha_airscan_queue_delivered",
                                                         "ha_airscan_batch_stale", "ha_airscan_printer_offline", "ha_airscan_button_rejected",
                                                         "mobile_app_notification_action"}

        def fire(event_type, data):
            for t, handler in hass.bus.listeners:
                if t == event_type:
                    result = handler(Event(data))
                    if asyncio.iscoroutine(result):
                        hass.tasks.append(result)

        async def settle():
            while hass.tasks:
                await hass.tasks.pop(0)

        # a failed scan reaches every target in the right shape; a broken target does not block the others
        fire("ha_airscan_scan_failed", {"entry_id": "E1", "detail": "Scan fehlgeschlagen: busy"})
        await settle()
        by_service = {c[1]: c for c in hass.services.calls}
        mobile = by_service["mobile_app_iphone"][2]
        assert mobile["title"] == "Scan fehlgeschlagen" and mobile["data"]["push"] == {"interruption-level": "time-sensitive"}
        assert "data" not in by_service["telegram_me"][2], "only the app understands the extra fields"
        assert by_service["create"][0] == "persistent_notification" and by_service["create"][2]["message"].startswith("Scan fehlgeschlagen")
        assert by_service["send_message"][2]["entity_id"] == "notify.ntfy"
        assert "broken_one" not in by_service
        hass.services.calls.clear()

        # types that are not selected, other scanners' events and a missing target stay silent
        fire("ha_airscan_scan_finished", {"entry_id": "E1", "pages": 2, "destination": "paperless"})   # scan_done not selected
        fire("ha_airscan_scan_failed", {"entry_id": "OTHER", "detail": "x"})
        await settle()
        assert hass.services.calls == []
        # queued is the same event with queued=True
        fire("ha_airscan_scan_finished", {"entry_id": "E1", "pages": 2, "queued": True, "queue_error": "down"})
        await settle()
        assert any("Paperless nicht erreichbar" in c[2]["message"] for c in hass.services.calls)
        hass.services.calls.clear()

        # forgotten batch: buttons only for the app, and they work
        fire("ha_airscan_batch_stale", {"entry_id": "E1", "pages": 3})
        await settle()
        actions = {c[1]: c for c in hass.services.calls}["mobile_app_iphone"][2]["data"]["actions"]
        assert [a["action"] for a in actions] == ["HA_AIRSCAN_SEND:E1", "HA_AIRSCAN_DISCARD:E1"]
        fire("mobile_app_notification_action", {"action": "HA_AIRSCAN_SEND:E1"})
        fire("mobile_app_notification_action", {"action": "HA_AIRSCAN_DISCARD:E1"})
        fire("mobile_app_notification_action", {"action": "HA_AIRSCAN_SEND:OTHER"})
        await settle()
        assert scan_calls == [("send", "E1"), ("discard", "E1")]
        hass.services.calls.clear()

        # Paperless webhook: only the selected types, bad input is rejected
        class Req:
            def __init__(self, payload=None, bad=False):
                self._p, self._bad = payload, bad

            async def json(self):
                if self._bad:
                    raise ValueError
                return self._p

        r = await n.async_handle_webhook(hass, "id", Req({"typ": "neu", "titel": "A"}))
        assert r.status == 200 and hass.services.calls == []                    # "neu" is not selected
        r = await n.async_handle_webhook(hass, "id", Req({"typ": "frist", "korrespondent": "Bank", "titel": "Mahnung", "url": "http://p/1"}))
        assert r.status == 200
        mobile = {c[1]: c for c in hass.services.calls}["mobile_app_iphone"][2]
        assert mobile["title"] == "Paperless ngx: Frist" and mobile["data"]["url"] == "http://p/1" and mobile["data"]["clickAction"] == "http://p/1"
        assert (await n.async_handle_webhook(hass, "id", Req(bad=True))).status == 400
        assert (await n.async_handle_webhook(hass, "id", Req(["not", "a", "dict"]))).status == 400

        # no targets at all: silent
        entry.options = {"notify_scan_types": ["scan_error"]}
        hass.services.calls.clear()
        fire("ha_airscan_scan_failed", {"entry_id": "E1", "detail": "x"})
        await settle()
        assert hass.services.calls == []

    asyncio.run(go())


# --- external buttons --------------------------------------------------------------


def test_button_values():
    bm = _load("button_map")
    # event entities (Zigbee2MQTT 2.x, ZHA): the pressed button is the attribute "event_type"
    assert bm.trigger_value("event", "2026-11-02T08:00:00", "2026-11-02T08:00:05", {"event_type": "open"}) == "open"
    assert bm.trigger_value("event", "unavailable", "2026-11-02T08:00:05", {"event_type": "open"}) is None   # came back, no press
    assert bm.trigger_value("event", "2026-11-02T08:00:00", "2026-11-02T08:00:05", {}) is None
    # enum sensors (older Zigbee2MQTT): the state is the value; the "" in between is the reset
    assert bm.trigger_value("sensor", "", "open", {}) == "open"
    assert bm.trigger_value("sensor", "close", "open", {}) == "open"
    assert bm.trigger_value("sensor", "open", "", {}) is None
    assert bm.trigger_value("sensor", "unavailable", "open", {}) is None          # restart of HA or the broker must not scan
    assert bm.trigger_value("sensor", None, "open", {}) is None
    assert bm.trigger_value("sensor", "open", "unknown", {}) is None

    mapping = {"adf": "open", "platen": " Close ", "toggle_duplex": "stop", "batch_send": "", "batch_discard": ""}
    assert [bm.action_for(v, mapping) for v in ("open", "OPEN", "close", "stop", "other", "", None)] == ["adf", "adf", "platen", "toggle_duplex", None, None, None]
    assert bm.duplicate_values({"adf": "open", "platen": "Open"}) == ["open"] and bm.duplicate_values(mapping) == []
    assert bm.values_of({"event_types": ["stop", "open", "close"]}) == ["close", "open", "stop"]
    assert bm.values_of({"options": ["open", "", None, "close"]}) == ["close", "open"] and bm.values_of({}) == []

    # MQTT: Zigbee2MQTT publishes the value as plain text on <device>/action, the JSON on <device> has it in "action"
    assert [bm.topic_value(p) for p in ("open", b"close", " stop \n", "", None, '{"action": "open", "linkquality": 18}', '{"action": ""}', '{"battery": 90}', "{kaputt", "[1]")] == \
        ["open", "close", "stop", None, None, "open", None, None, None, "[1]"]
    assert bm.valid_topic("zigbee2mqtt/Ikea Fernbedienung/action") and not bm.valid_topic("zigbee2mqtt/#") and not bm.valid_topic("zigbee2mqtt/+/action") \
        and not bm.valid_topic("") and not bm.valid_topic("  ") and not bm.valid_topic("/zigbee2mqtt/x/action")

    d = bm.Debounce(1.0)
    assert d.accept("open", 10.0) and not d.accept("open", 10.4) and d.accept("close", 10.5) and d.accept("open", 12.0)


def test_button_triggers(monkeypatch):
    from types import SimpleNamespace

    class HAError(Exception):
        pass

    class Busy(HAError):
        pass

    def mod(name, **attrs):
        m = _types.ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)

    watched = {}

    def track(hass, entity_ids, action):
        watched["ids"], watched["action"] = entity_ids, action
        return lambda: None

    subs = []

    async def mqtt_wait(hass):
        return True

    async def mqtt_subscribe(hass, topic, callback):
        subs.append((topic, callback))
        return lambda: None

    mqtt_mod = _types.ModuleType("homeassistant.components.mqtt")
    mqtt_mod.async_wait_for_mqtt_client, mqtt_mod.async_subscribe = mqtt_wait, mqtt_subscribe
    components = _types.ModuleType("homeassistant.components")
    components.mqtt = mqtt_mod
    monkeypatch.setitem(sys.modules, "homeassistant.components", components)
    monkeypatch.setitem(sys.modules, "homeassistant.components.mqtt", mqtt_mod)
    mod("homeassistant"); mod("homeassistant.helpers")
    mod("homeassistant.core", Event=object, HomeAssistant=object, callback=lambda f: f)
    mod("homeassistant.exceptions", HomeAssistantError=HAError)
    mod("homeassistant.helpers.event", async_track_state_change_event=track)
    calls = []
    fail = {"scan": False}

    async def scan(hass, entry, **kw):
        calls.append(("scan", kw))
        if fail["scan"]:
            raise Busy("Es läuft bereits ein Scan")

    async def add(hass, entry, **kw):
        calls.append(("batch_add", kw))

    async def send(hass, entry, **kw):
        calls.append(("batch_send", kw))

    async def discard(hass, entry, **kw):
        calls.append(("batch_discard", kw))

    monkeypatch.setitem(sys.modules, "airscan_pkg.scan", _types.SimpleNamespace(
        ScannerBusy=Busy, async_scan=scan, async_batch_add=add, async_batch_send=send, async_batch_discard=discard))
    triggers = _load("triggers")

    class Tracker:
        duplex_default = False
        updates = 0

        def update(self, *a, **k):
            self.updates += 1

    fired = []

    class Hass:
        def __init__(self):
            self.tasks = []
            self.bus = SimpleNamespace(async_fire=lambda event, data: fired.append((event, data)))

        def async_create_task(self, coro):
            self.tasks.append(coro)

    async def go():
        tracker = Tracker()
        entry = SimpleNamespace(
            entry_id="E1",
            options={"button_entity": "event.remote_action",
                     "button_map": {"adf": "open", "platen": "close", "toggle_duplex": "stop", "batch_send": "", "batch_discard": ""}},
            runtime_data=SimpleNamespace(tracker=tracker, capabilities=SimpleNamespace(adf_duplex=object())),
            async_on_unload=lambda fn: None,
        )
        hass = Hass()
        t = triggers.ButtonTriggers(hass, entry)
        t.async_start()
        assert watched["ids"] == ["event.remote_action"]

        clock = [100.0]
        monkeypatch.setattr(sys.modules["airscan_pkg.button_map"].time, "monotonic", lambda: clock[0])

        async def press(value, old="2026-11-02T08:00:00", advance=2.0):
            clock[0] += advance
            new = SimpleNamespace(domain="event", state=f"t{clock[0]}", attributes={"event_type": value})
            watched["action"](SimpleNamespace(data={"old_state": SimpleNamespace(state=old), "new_state": new}))
            while hass.tasks:
                await hass.tasks.pop(0)

        await press("open")                       # feeder, one-sided
        await press("close")                      # flatbed -> batch
        await press("stop")                       # long press: switch to two-sided
        assert tracker.duplex_default is True and tracker.updates == 1
        await press("open")                       # feeder, now two-sided
        await press("stop")                       # and back
        await press("open")
        await press("nothing-mapped")
        assert calls == [("scan", {"source": "adf", "duplex": False}), ("batch_add", {}),
                         ("scan", {"source": "adf", "duplex": True}), ("scan", {"source": "adf", "duplex": False})]

        calls.clear()
        await press("open", advance=2.0)
        await press("open", advance=0.3)          # radio retransmission within a second: ignored
        assert len(calls) == 1

        fail["scan"] = True                       # a scan that cannot start must not crash the listener
        calls.clear()
        await press("open", advance=3.0)
        assert len(calls) == 1
        # ...and a press that is turned away because the scanner is busy is reported (a button has no screen)
        assert fired == [("ha_airscan_button_rejected", {"entry_id": "E1", "action": "adf", "detail": "Es läuft bereits ein Scan"})]

        # a scanner without duplex never asks for it, even if the switch state says so
        tracker.duplex_default = True
        entry.runtime_data.capabilities.adf_duplex = None
        fail["scan"] = False
        calls.clear()
        await press("open", advance=3.0)
        assert calls == [("scan", {"source": "adf", "duplex": False})]

        # MQTT topic as the source (Zigbee2MQTT without any entity)
        tracker.duplex_default = False
        entry.runtime_data.capabilities.adf_duplex = object()
        entry.options = {"button_topic": "zigbee2mqtt/Ikea Fernbedienung/action",
                         "button_map": {"adf": "open", "platen": "close", "toggle_duplex": "stop", "batch_send": "", "batch_discard": ""}}
        entry.async_create_background_task = lambda hass_, coro, name: hass.tasks.append(coro)
        watched.clear()
        calls.clear()
        triggers.ButtonTriggers(hass, entry).async_start()
        assert watched == {}                      # no entity watched
        while hass.tasks:
            await hass.tasks.pop(0)
        assert [s[0] for s in subs] == ["zigbee2mqtt/Ikea Fernbedienung/action"]
        send_msg = subs[0][1]

        async def message(payload, advance=2.0):
            clock[0] += advance
            send_msg(SimpleNamespace(payload=payload))
            while hass.tasks:
                await hass.tasks.pop(0)

        await message("open")
        await message("close")
        await message(b"stop")                    # toggles two-sided
        await message("")                         # reset message of the broker: no press
        await message('{"action": "open", "linkquality": 18}')
        await message("open", advance=0.2)        # retransmission within a second: ignored
        await message("something-else")
        assert tracker.duplex_default is True
        assert calls == [("scan", {"source": "adf", "duplex": False}), ("batch_add", {}), ("scan", {"source": "adf", "duplex": True})]

        # nothing configured: nothing subscribed
        watched.clear()
        subs.clear()
        entry.options = {}
        triggers.ButtonTriggers(hass, entry).async_start()
        assert watched == {}

    asyncio.run(go())
