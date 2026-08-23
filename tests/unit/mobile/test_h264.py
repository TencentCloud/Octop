"""Unit tests for mobile capture / H.264 helpers."""

from __future__ import annotations

from octop.infra.mobile.adb import extract_png, extract_raw_rgba, screenrecord_h264_args
from octop.infra.mobile.h264 import (
    NAL_IDR,
    NAL_PPS,
    NAL_SPS,
    AnnexBSplitter,
    avc_codec_string,
    avcc_from_sps_pps,
    avcc_sample,
    nal_type,
)


def test_extract_png_strips_screencap_warning() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    blob = b"[Warning] Multiple displays were found\n" + png
    assert extract_png(blob) == png
    assert extract_png(png) == png
    assert extract_png(b"[Warning] only") is None


def test_extract_raw_rgba_skips_warning_prefix() -> None:
    width, height = 32, 16
    header = (
        width.to_bytes(4, "little")
        + height.to_bytes(4, "little")
        + (1).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
    )
    body = bytes([i % 256 for i in range(width * height * 4)])
    blob = b"[Warning] Multiple displays\n" + header + body
    got = extract_raw_rgba(blob)
    assert got == (width, height, body)


def test_annexb_splitter_handles_prefix_and_mixed_start_codes() -> None:
    sps = bytes([0x67, 0x42, 0xC0, 0x32, 0x0A])
    pps = bytes([0x68, 0xCE, 0x01, 0xA8])
    idr = bytes([0x65, 0x88, 0x80])
    blob = (
        b"[Warning] ignore me"
        + b"\x00\x00\x00\x01"
        + sps
        + b"\x00\x00\x01"
        + pps
        + b"\x00\x00\x00\x01"
        + idr
        + b"\x00\x00\x00\x01"
    )
    splitter = AnnexBSplitter()
    nals = splitter.feed(blob[:20]) + splitter.feed(blob[20:])
    assert nals == [sps, pps, idr]
    assert nal_type(sps) == NAL_SPS
    assert nal_type(pps) == NAL_PPS
    assert nal_type(idr) == NAL_IDR


def test_avcc_and_codec_string() -> None:
    sps = bytes([0x67, 0x42, 0xC0, 0x32, 0x0A])
    pps = bytes([0x68, 0xCE, 0x01, 0xA8])
    assert avc_codec_string(sps) == "avc1.42C032"
    avcc = avcc_from_sps_pps(sps, pps)
    assert avcc[0] == 1
    assert avcc[1:4] == sps[1:4]
    idr = bytes([0x65, 0x00])
    sample = avcc_sample([idr])
    assert sample[:4] == (2).to_bytes(4, "big")
    assert sample[4:] == idr


def test_screenrecord_args_include_display_id() -> None:
    cmd = screenrecord_h264_args(
        "emulator-5554", adb="/usr/bin/adb", display_id="42", bit_rate=1000
    )
    assert cmd[:4] == ["/usr/bin/adb", "-s", "emulator-5554", "exec-out"]
    assert "--output-format=h264" in cmd
    assert "--time-limit=0" in cmd
    assert "--size" in cmd
    assert "720x1600" in cmd
    assert "--display-id" in cmd
    assert "42" in cmd
    assert cmd[-1] == "-"
