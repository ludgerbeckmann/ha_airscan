"""Tests for the pure-Python parts (no Home Assistant required)."""

import importlib.util
from io import BytesIO
from pathlib import Path
import sys
import types

from PIL import Image

base = Path(__file__).parent.parent / "custom_components" / "airscan"
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
