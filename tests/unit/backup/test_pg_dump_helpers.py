from __future__ import annotations

import pytest

from octop.infra.backup import pg_dump
from octop.infra.errors import OctopError


def test_require_tool_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pg_dump.shutil, "which", lambda _name: None)
    with pytest.raises(OctopError, match="pg_dump not found"):
        pg_dump._require_tool("pg_dump")
