"""Unit tests for Ollama local service enablement defaults."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from octop.api.routers import ollama_models
from octop.infra.utils.ollama_manager import SETTINGS_KEY_MODELS_DIR


def _server(values: dict[str, str | None]) -> SimpleNamespace:
    store = dict(values)
    repo = MagicMock()
    repo.get.side_effect = lambda key: store.get(key)

    def _set(key: str, value: str) -> None:
        store[key] = value

    repo.set.side_effect = _set
    return SimpleNamespace(services=SimpleNamespace(settings_repo=repo))


def test_ollama_service_defaults_to_disabled_when_unset() -> None:
    server = SimpleNamespace(services=SimpleNamespace(settings_repo=MagicMock()))
    server.services.settings_repo.get.return_value = None
    assert ollama_models._ollama_service_enabled(server) is False


def test_ollama_service_respects_stored_true() -> None:
    server = SimpleNamespace(services=SimpleNamespace(settings_repo=MagicMock()))
    server.services.settings_repo.get.return_value = "true"
    assert ollama_models._ollama_service_enabled(server) is True


def test_ollama_models_dir_empty_when_unset() -> None:
    server = _server({})
    assert ollama_models._ollama_models_dir(server) == ""


def test_ollama_models_dir_reads_setting() -> None:
    server = _server({SETTINGS_KEY_MODELS_DIR: " /data/models "})
    assert ollama_models._ollama_models_dir(server) == "/data/models"


@pytest.mark.asyncio
async def test_list_uses_models_dir_when_service_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    from octop.infra.utils import ollama_manager as om

    monkeypatch.setattr(om, "_original_ollama_models", om._UNSET)
    monkeypatch.setattr(om, "_applied_models_dir", None)
    dest = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    dest.mkdir(parents=True)
    (dest / "7b").write_text("{}", encoding="utf-8")
    server = _server(
        {
            ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "false",
            SETTINGS_KEY_MODELS_DIR: str(tmp_path),
        }
    )
    result = await ollama_models.list_ollama_models(server=server, _=None)
    assert [m.name for m in result] == ["qwen2.5:7b"]
    assert result[0].size == 0


@pytest.mark.asyncio
async def test_list_uses_running_daemon_when_service_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.utils import ollama_manager as om
    from octop.infra.utils.ollama_manager import OllamaModelInfo

    monkeypatch.setattr(om, "is_ollama_reachable", lambda: True)
    listed = MagicMock(return_value=[OllamaModelInfo(name="llama3.2:latest", size=2_000_000_000)])
    monkeypatch.setattr(om.OllamaModelManager, "list_models", listed)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "false"})
    result = await ollama_models.list_ollama_models(server=server, _=None)
    assert [m.name for m in result] == ["llama3.2:latest"]
    listed.assert_called_once_with(start_if_needed=False)


@pytest.mark.asyncio
async def test_list_does_not_start_daemon_when_service_off_and_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from octop.infra.utils import ollama_manager as om

    monkeypatch.setattr(om, "is_ollama_reachable", lambda: False)
    listed = MagicMock()
    monkeypatch.setattr(om.OllamaModelManager, "list_models", listed)
    server = _server({})
    with pytest.raises(HTTPException) as exc_info:
        await ollama_models.list_ollama_models(server=server, _=None)
    assert exc_info.value.status_code == 503
    listed.assert_not_called()


@pytest.mark.asyncio
async def test_put_service_rejects_relative_models_dir() -> None:
    server = _server({})
    body = ollama_models.OllamaServiceBody(models_dir="relative/models")
    with pytest.raises(HTTPException) as exc_info:
        await ollama_models.put_ollama_service(body=body, server=server, _=None)
    assert exc_info.value.status_code == 400


def _patch_ollama_lifecycle(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    from octop.infra.utils import ollama_manager as om

    monkeypatch.setattr(om, "_original_ollama_models", om._UNSET)
    monkeypatch.setattr(om, "_applied_models_dir", None)
    stop = MagicMock(return_value=True)
    start = MagicMock()
    monkeypatch.setattr("octop.infra.utils.ollama_manager.stop_ollama_service", stop)
    monkeypatch.setattr("octop.infra.utils.ollama_manager.start_ollama_service", start)
    monkeypatch.setattr("octop.infra.utils.ollama_manager.is_ollama_reachable", lambda: False)
    return stop, start


@pytest.mark.asyncio
async def test_put_models_dir_without_enabled_does_not_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop, start = _patch_ollama_lifecycle(monkeypatch)
    server = _server({})
    body = ollama_models.OllamaServiceBody(models_dir=str(tmp_path))
    status = await ollama_models.put_ollama_service(body=body, server=server, _=None)
    server.services.settings_repo.set.assert_any_call(SETTINGS_KEY_MODELS_DIR, str(tmp_path))
    assert status.models_dir == str(tmp_path)
    assert status.enabled is False
    stop.assert_not_called()
    start.assert_not_called()


@pytest.mark.asyncio
async def test_put_models_dir_restarts_when_service_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stop, start = _patch_ollama_lifecycle(monkeypatch)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "true"})
    body = ollama_models.OllamaServiceBody(models_dir=str(tmp_path))
    status = await ollama_models.put_ollama_service(body=body, server=server, _=None)
    assert status.enabled is True
    stop.assert_called_once()
    start.assert_called_once()


@pytest.mark.asyncio
async def test_put_enabled_false_still_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    stop, start = _patch_ollama_lifecycle(monkeypatch)
    server = _server({ollama_models._SETTINGS_KEY_OLLAMA_SERVICE: "true"})
    body = ollama_models.OllamaServiceBody(enabled=False)
    status = await ollama_models.put_ollama_service(body=body, server=server, _=None)
    assert status.enabled is False
    stop.assert_called_once()
    start.assert_not_called()
