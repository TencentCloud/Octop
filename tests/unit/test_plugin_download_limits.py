"""Downloads have explicit per-read and total budgets."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest

from octop.infra.agents.plugins import installation


def test_download_limits_bytes(tmp_path: Path) -> None:
    with (
        patch.object(installation, "MAX_ARCHIVE_BYTES", 3),
        patch.object(
            installation.urllib.request, "urlopen", return_value=io.BytesIO(b"1234")
        ) as opened,
        pytest.raises(ValueError, match="exceeds"),
    ):
        installation.download("https://example.test/plugin.zip", tmp_path / "plugin.zip")
    assert opened.call_args.kwargs["timeout"] == installation.DOWNLOAD_TIMEOUT


def test_download_total_budget(tmp_path: Path) -> None:
    with (
        patch.object(installation.time, "monotonic", side_effect=[0, 121]),
        patch.object(installation.urllib.request, "urlopen", return_value=io.BytesIO(b"1234")),
        pytest.raises(TimeoutError, match="budget"),
    ):
        installation.download("https://example.test/plugin.zip", tmp_path / "plugin.zip")
