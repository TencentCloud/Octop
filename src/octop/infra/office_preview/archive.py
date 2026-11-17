"""Validate actual OOXML expansion without trusting ZIP size declarations."""

from __future__ import annotations

import binascii
import struct
import zipfile
import zlib
from io import BytesIO

from octop.infra.office_preview.read import too_large_error


def expanded_size(data: bytes, limit: int) -> int:
    """Inflate bounded chunks, checking actual size, CRC and stream termination."""
    end_record = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end_record < 0 or end_record + 22 > len(data):
        raise zipfile.BadZipFile("missing end record")
    entries_count = struct.unpack_from("<H", data, end_record + 10)[0]
    central_bytes = struct.unpack_from("<I", data, end_record + 12)[0]
    if entries_count > 10000 or central_bytes > 8 * 1024 * 1024:
        raise too_large_error()
    total = 0
    with zipfile.ZipFile(BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 10000:
            raise too_large_error()
        for info in entries:
            if info.flag_bits & 1 or info.compress_type not in {0, 8}:
                raise zipfile.BadZipFile("unsupported ZIP member")
            offset = info.header_offset
            if data[offset : offset + 4] != b"PK\x03\x04":
                raise zipfile.BadZipFile("invalid local header")
            method = struct.unpack_from("<H", data, offset + 8)[0]
            name_size, extra_size = struct.unpack_from("<HH", data, offset + 26)
            if method != info.compress_type:
                raise zipfile.BadZipFile("inconsistent ZIP method")
            start = offset + 30 + name_size + extra_size
            end = start + info.compress_size
            if end > len(data) or end > int(archive.start_dir):
                raise zipfile.BadZipFile("invalid ZIP extent")
            decoder = zlib.decompressobj(-15) if method == 8 else None
            count = 0
            crc = 0
            pos = start
            pending = b""
            while pos < end or pending:
                if not pending:
                    pending = data[pos : min(pos + 65536, end)]
                    pos += len(pending)
                if decoder is None:
                    chunk, pending = pending, b""
                else:
                    chunk = decoder.decompress(pending, min(65536, limit - total + 1))
                    pending = decoder.unconsumed_tail
                    if decoder.unused_data:
                        raise zipfile.BadZipFile("trailing compressed data")
                total += len(chunk)
                count += len(chunk)
                if total > limit:
                    raise too_large_error()
                crc = binascii.crc32(chunk, crc)
            if decoder is not None and not decoder.eof:
                raise zipfile.BadZipFile("truncated compressed stream")
            if count != info.file_size or crc != info.CRC:
                raise zipfile.BadZipFile("inconsistent ZIP size or CRC")
    return total
