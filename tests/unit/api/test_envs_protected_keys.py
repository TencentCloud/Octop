"""Unit tests for the ``/api/envs`` protected-key guard.

``_is_protected_env_key`` already keeps HOME / USER / SHELL / PWD and every
``OCTOP_*`` key out of the MCP stdio overlay, but the Admin "Global environment
variables" write path had no such guard: any key that satisfied ``_KEY_RE`` was
persisted to ``~/.octop/env`` *and* pushed into the running Octop process via
``apply_env_file_replace``. Rewriting ``OCTOP_AUTH_DIR`` or ``HOME`` that way
re-points every agent subprocess at attacker-chosen directories.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.api.routers import envs
from octop.infra.errors import OctopError


def _server(root: Path) -> SimpleNamespace:
    return SimpleNamespace(paths=SimpleNamespace(root=root))


async def _put(root: Path, body: dict[str, str]) -> list[dict[str, str]]:
    return await envs.batch_save_envs(body, None, _server(root))


async def test_put_rejects_process_identity_keys(tmp_path: Path) -> None:
    for key in ("HOME", "USER", "USERNAME", "LOGNAME", "SHELL", "PWD"):
        with pytest.raises(OctopError):
            await _put(tmp_path, {key: "/tmp/evil"})


async def test_put_rejects_octop_reserved_prefix(tmp_path: Path) -> None:
    for key in ("OCTOP_AUTH_DIR", "OCTOP_SKILLS_DIR", "OCTOP_HOME", "OCTOP_AGENT_ID"):
        with pytest.raises(OctopError):
            await _put(tmp_path, {key: "/tmp/evil"})


async def test_rejected_key_is_not_persisted_or_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "real-home"))
    monkeypatch.delenv("OCTOP_AUTH_DIR", raising=False)

    with pytest.raises(OctopError):
        await _put(tmp_path, {"OCTOP_AUTH_DIR": "/tmp/evil", "FOO": "bar"})

    # The batch is rejected as a whole, so the sibling key must not land either.
    assert not (tmp_path / "env").exists()
    assert "OCTOP_AUTH_DIR" not in os.environ
    assert "FOO" not in os.environ
    assert os.environ["HOME"] == str(tmp_path / "real-home")


async def test_delete_rejects_process_identity_keys(tmp_path: Path) -> None:
    with pytest.raises(OctopError):
        await envs.delete_env("HOME", None, _server(tmp_path))


async def test_captcha_secrets_remain_writable(tmp_path: Path) -> None:
    # The captcha pair is the one reserved name this endpoint owns end to end:
    # redacted on read, sentinel-restored on write. Guarding OCTOP_* must not
    # lock admins out of rotating them.
    rows = await _put(tmp_path, {"OCTOP_CAPTCHA_SECRET": "live-secret", "FOO": "bar"})
    assert "live-secret" in (tmp_path / "env").read_text(encoding="utf-8")
    by_key = {row["key"]: row["value"] for row in rows}
    assert by_key["OCTOP_CAPTCHA_SECRET"] == "********"


async def test_ordinary_keys_still_round_trip(tmp_path: Path) -> None:
    rows = await _put(tmp_path, {"FOO": "bar", "TAVILY_API_KEY": "tvly-1"})
    assert {row["key"] for row in rows} == {"FOO", "TAVILY_API_KEY"}
    assert "FOO=bar" in (tmp_path / "env").read_text(encoding="utf-8")

    remaining = await envs.delete_env("FOO", None, _server(tmp_path))
    assert {row["key"] for row in remaining} == {"TAVILY_API_KEY"}
