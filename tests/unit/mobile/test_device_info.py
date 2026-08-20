"""Unit tests for adb device-info parsing."""

from __future__ import annotations

from octop.infra.mobile.adb import parse_device_info_payload

SAMPLE = """
model=Pixel 6
market=Pixel 6
manufacturer=Google
release=14
sdk=34
size=Physical size: 1080x2400
density=Physical density: 420
mem_kb=5730304
cores=8
df=114884608 52428800 58232832
fps=fps=60.000004
""".strip()


def test_parse_device_info_payload() -> None:
    info = parse_device_info_payload("emulator-5554", SAMPLE)
    assert info["device"] == "emulator-5554"
    assert info["model"] == "Pixel 6"
    assert info["manufacturer"] == "Google"
    assert info["android_version"] == "14"
    assert info["sdk"] == 34
    assert info["width"] == 1080
    assert info["height"] == 2400
    assert info["density_dpi"] == 420
    assert info["refresh_hz"] == 60.0
    assert info["mem_total_mb"] == 5596
    assert info["cpu_cores"] == 8
    assert info["storage_total_gb"] == round(114884608 / (1024 * 1024), 3)
    assert info["storage_used_gb"] == round(52428800 / (1024 * 1024), 3)
    assert info["storage_avail_gb"] == round(58232832 / (1024 * 1024), 3)


def test_parse_prefers_market_name() -> None:
    text = "model=M2102J20SG\nmarket=Redmi K40\nmanufacturer=Xiaomi\n"
    info = parse_device_info_payload("3b678f5c", text)
    assert info["model"] == "Redmi K40"


def test_parse_handles_empty() -> None:
    info = parse_device_info_payload("x", "")
    assert info["device"] == "x"
    assert info["model"] is None
    assert info["width"] is None
    assert info["cpu_cores"] is None
