"""Annex-B H.264 helpers for adb screenrecord streams."""

from __future__ import annotations

NAL_SLICE = 1
NAL_IDR = 5
NAL_SPS = 7
NAL_PPS = 8


def nal_type(nal: bytes) -> int:
    if not nal:
        return 0
    return nal[0] & 0x1F


def avc_codec_string(sps: bytes) -> str:
    if len(sps) < 4:
        return "avc1.42C01E"
    return f"avc1.{sps[1]:02X}{sps[2]:02X}{sps[3]:02X}"


def avcc_from_sps_pps(sps: bytes, pps: bytes) -> bytes:
    """Build an AVCDecoderConfigurationRecord (avcC) from SPS/PPS NALs."""
    if len(sps) < 4:
        raise ValueError("SPS too short")
    header = bytes(
        [
            1,
            sps[1],
            sps[2],
            sps[3],
            0xFF,  # lengthSizeMinusOne = 3
            0xE1,  # one SPS
        ]
    )
    return (
        header + len(sps).to_bytes(2, "big") + sps + bytes([1]) + len(pps).to_bytes(2, "big") + pps
    )


def avcc_sample(nals: list[bytes]) -> bytes:
    out = bytearray()
    for nal in nals:
        out += len(nal).to_bytes(4, "big")
        out += nal
    return bytes(out)


def _start_len(buf: bytes | bytearray, idx: int) -> int:
    if buf[idx : idx + 4] == b"\x00\x00\x00\x01":
        return 4
    if buf[idx : idx + 3] == b"\x00\x00\x01":
        return 3
    return 0


def find_start_code(buf: bytes | bytearray, offset: int = 0) -> int:
    i = offset
    end = len(buf) - 2
    while i < end:
        if buf[i] == 0 and buf[i + 1] == 0:
            if i + 3 < len(buf) and buf[i + 2] == 0 and buf[i + 3] == 1:
                return i
            if buf[i + 2] == 1:
                return i
        i += 1
    return -1


class AnnexBSplitter:
    """Incrementally split Annex-B bytes into NAL units (start codes stripped)."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        if data:
            self._buf.extend(data)
        nals: list[bytes] = []
        while True:
            start = find_start_code(self._buf, 0)
            if start < 0:
                if len(self._buf) > 3:
                    del self._buf[:-3]
                return nals
            sc_len = _start_len(self._buf, start)
            nxt = find_start_code(self._buf, start + sc_len)
            if nxt < 0:
                if start > 0:
                    del self._buf[:start]
                return nals
            nal = bytes(self._buf[start + sc_len : nxt])
            if nal:
                nals.append(nal)
            del self._buf[:nxt]
        return nals
