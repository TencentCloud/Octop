from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.office_preview.read import read_path_capped, read_stream_capped


def test_read_path_capped_stats_then_rejects(tmp_path: Path) -> None:
    target = tmp_path / "huge.docx"
    target.write_bytes(b"x" * 32)
    with pytest.raises(OctopError) as raised:
        read_path_capped(target, max_bytes=8)
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_TOO_LARGE


def test_read_stream_capped_enforces_hard_limit() -> None:
    with pytest.raises(OctopError) as raised:
        read_stream_capped(BytesIO(b"x" * 32), max_bytes=8)
    assert raised.value.code is ErrorCode.OFFICE_PREVIEW_TOO_LARGE
