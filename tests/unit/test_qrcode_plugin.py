"""The bundled qrcode plugin must report oversized content, not raise."""

from __future__ import annotations

import importlib.util
import json

import pytest

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root


def _load_qrcode():
    path = default_bundled_plugins_root() / "qrcode" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_qrcode", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(raw: str) -> dict[str, object]:
    return json.loads(raw)


@pytest.mark.asyncio
async def test_short_content_still_returns_an_image() -> None:
    data = _payload(await _load_qrcode().make_qrcode("https://example.com"))["data"]
    assert str(data["image_data_url"]).startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_cjk_beyond_segno_capacity_reports_too_long() -> None:
    """1500 CJK chars clear the 2048-char guard but exceed segno's error-M capacity."""
    mod = _load_qrcode()
    data = _payload(await mod.make_qrcode("中" * 1500))["data"]
    assert data.get("error") == "too long"
    assert "image_data_url" not in data
