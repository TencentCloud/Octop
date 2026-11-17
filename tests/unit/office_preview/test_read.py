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


async def test_workspace_without_capped_api_never_downloads() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from octop.infra.office_preview.read import read_workspace_capped

    legacy = AsyncMock(side_effect=AssertionError("unbounded read"))
    with pytest.raises(OctopError) as exc:
        await read_workspace_capped(SimpleNamespace(adownload_bytes=legacy), "file.docx", 8)
    assert exc.value.code is ErrorCode.OFFICE_PREVIEW_UNAVAILABLE
    legacy.assert_not_called()


async def test_workspace_uses_bounded_api() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from octop.infra.office_preview.read import read_workspace_capped

    bounded = AsyncMock(return_value=b"office")
    assert (
        await read_workspace_capped(SimpleNamespace(adownload_bytes_capped=bounded), "file.docx", 8)
        == b"office"
    )
    bounded.assert_awaited_once_with("file.docx", 8)
