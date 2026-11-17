from __future__ import annotations

import struct
import zipfile
from io import BytesIO

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.archive import expanded_size


def archive_bytes(payload: bytes) -> bytes:
    out = BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", payload)
    return out.getvalue()


def test_actual_expansion_limit() -> None:
    data = archive_bytes(b"x" * 100000)
    assert expanded_size(data, 100000) == 100000
    with pytest.raises(OctopError) as exc:
        expanded_size(data, 1000)
    assert exc.value.code is ErrorCode.OFFICE_PREVIEW_TOO_LARGE


def test_forged_directory_sizes_do_not_bypass_expansion_cap() -> None:
    data = bytearray(archive_bytes(b"x" * 100000))
    directory = data.index(b"PK\x01\x02")
    struct.pack_into("<I", data, directory + 24, 1)
    struct.pack_into("<I", data, 22, 1)
    with pytest.raises(OctopError):
        expanded_size(bytes(data), 1000)


def test_crc_is_verified() -> None:
    data = bytearray(archive_bytes(b"hello"))
    directory = data.index(b"PK\x01\x02")
    struct.pack_into("<I", data, directory + 16, 0)
    with pytest.raises(zipfile.BadZipFile):
        expanded_size(bytes(data), 1000)
