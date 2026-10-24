"""API tests for the secret-file submit endpoint (POST .../chat/secret-file/submit)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from octop.api.app import _install_exception_handlers
from octop.api.deps import current_user, get_server
from octop.api.routers.chat.models import SecretFileSubmitBody
from octop.api.routers.chat.routes import router, submit_secret_file
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.hitl.coordinator import HitlChannelCoordinator

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only private writes")

SECRET = "synthetic-api-token-abcdef"  # synthetic; never a real credential


class _FakeBackend:
    sandbox_fs = False


class _FakeWorkspace:
    def __init__(self, root: Path) -> None:
        self.workspace_dir = root
        self.system_files_path = ".octop"
        self.backend = _FakeBackend()

    def system_rel(self, path: str) -> str:
        return f"{self.system_files_path}/{path}"

    def resolve_path(self, fragment: str) -> str:
        return str((Path(self.workspace_dir) / fragment).resolve())

    async def als(self, path: str):
        directory = Path(self.workspace_dir) / path

        class _Result:
            entries = [1] if directory.is_dir() and any(directory.iterdir()) else []

        return _Result()

    async def aexists(self, path: str) -> bool:
        return (Path(self.workspace_dir) / path).exists()


class _Request:
    headers: dict[str, str] = {}

    async def is_disconnected(self) -> bool:
        return False


def _row(agent_id: str = "AGT1", user_id: int = 7, *, is_shared: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        agent_id=agent_id,
        user_id=user_id,
        is_shared=is_shared,
        enabled=True,
        last_state="running",
    )


def _server(
    *,
    row: SimpleNamespace,
    workspace: _FakeWorkspace,
    hitl: HitlChannelCoordinator,
    captured: dict[str, Any],
) -> SimpleNamespace:
    registry = MagicMock()
    registry.get_row.return_value = row
    registry.get_agent.return_value = SimpleNamespace(workspace=workspace)
    registry.workspace_for_agent.return_value = workspace

    async def _resume(*, agent_id, thread_id, user_id, decisions):
        captured["decisions"] = decisions
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    processor = MagicMock()
    processor.hitl_coordinator = hitl
    processor.iter_hitl_resume_chunks = _resume
    return SimpleNamespace(
        app_runtime=SimpleNamespace(
            agent_registry=registry,
            gateway=SimpleNamespace(processor=processor),
        ),
        services=SimpleNamespace(
            sharing_repo=SimpleNamespace(can_access=lambda *_a: False),
        ),
    )


def _register_secret_pending(
    hitl: HitlChannelCoordinator,
    *,
    agent_id: str = "AGT1",
    user_id: int = 7,
    thread_id: str = "thr-1",
    path: str = "hr.token",
) -> str:
    record = hitl.store.register(
        thread_id=thread_id,
        agent_id=agent_id,
        user_id=user_id,
        session_key=f"{agent_id}:dashboard:{user_id}:dm",
        channel_type="dashboard",
        action_requests=[
            {
                "name": "request_secret_file",
                "args": {"path": path, "prompt": "HR 系统 Token"},
            }
        ],
        review_configs=None,
    )
    return record.pending_id


async def _collect_sse(response) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    async for frame in response.body_iterator:
        for line in str(frame).split("\n"):
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    return frames


@pytest.mark.asyncio
@posix_only
async def test_submit_writes_file_and_resumes(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    workspace = _FakeWorkspace(tmp_path)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=workspace, hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)

    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
        _Request(),
        user=user,
        server=server,
    )
    frames = await _collect_sse(response)

    target = tmp_path / ".octop" / "auth" / "hr.token"
    assert target.read_text() == SECRET
    assert hitl.store.get(pending_id).status == "filled"  # type: ignore[union-attr]
    # resume decision carries the path but never the secret
    message = captured["decisions"][0]["message"]
    assert "hr.token" in message and "filled" in message
    assert SECRET not in message
    assert SECRET not in json.dumps(frames, ensure_ascii=False)


@pytest.mark.asyncio
async def test_cancel_writes_nothing(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)

    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, action="cancel", content=""),
        _Request(),
        user=user,
        server=server,
    )
    await _collect_sse(response)

    assert not (tmp_path / ".octop" / "auth").exists()
    assert hitl.store.get(pending_id).status == "cancelled"  # type: ignore[union-attr]
    assert "cancelled" in captured["decisions"][0]["message"]


@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("decision_type", ["respond", "approve", "reject"])
def test_generic_resume_refuses_secret_pending_over_http(
    tmp_path: Path, mixed: bool, decision_type: str
) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    record = hitl.store.get(pending_id)
    assert record is not None
    if mixed:
        record.action_requests.insert(0, {"name": "execute", "args": {"command": "pwd"}})
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    app = FastAPI()
    _install_exception_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7, is_admin=False)
    app.dependency_overrides[get_server] = lambda: server

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/AGT1/chat/hitl/resume",
            json={
                "thread_id": "thr-1",
                "decisions": [
                    {"type": decision_type, "message": SECRET} for _ in record.action_requests
                ],
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == ErrorCode.SECRET_REQUEST_INVALID
        assert SECRET not in response.text
        assert record.status == "pending"
        assert captured == {}
        server.app_runtime.agent_registry.workspace_for_agent.assert_not_called()

        response = client.post(
            "/api/agents/AGT1/chat/secret-file/submit",
            json={"thread_id": "thr-1", "pending_id": pending_id, "action": "cancel"},
        )
        assert response.status_code == 200
        assert record.status == "cancelled"
        assert SECRET not in response.text
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
@posix_only
async def test_replay_after_filled_is_rejected(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)
    body = SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET)

    await _collect_sse(await submit_secret_file("AGT1", body, _Request(), user=user, server=server))
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file("AGT1", body, _Request(), user=user, server=server)
    assert excinfo.value.code == ErrorCode.SECRET_REQUEST_INVALID
    # the file still holds the first write
    assert (tmp_path / ".octop" / "auth" / "hr.token").read_text() == SECRET


@pytest.mark.asyncio
async def test_other_user_cannot_submit(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl, user_id=7)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    stranger = SimpleNamespace(id=8, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=stranger,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pending_agent_id", "pending_user_id", "thread_id"),
    [("AGT1", 7, "thr-other"), ("AGT2", 7, "thr-1"), ("AGT1", 8, "thr-1")],
)
async def test_wrong_pending_scope_is_rejected(
    tmp_path: Path, pending_agent_id: str, pending_user_id: int, thread_id: str
) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl, agent_id=pending_agent_id, user_id=pending_user_id)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id=thread_id, pending_id=pending_id, content=SECRET),
            _Request(),
            user=user,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.SECRET_REQUEST_INVALID
    assert hitl.store.get(pending_id).status == "pending"  # type: ignore[union-attr]
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("extra_action", ["request_secret_file", "execute"])
async def test_multiple_actions_refuse_submit_but_allow_cancel(
    tmp_path: Path, extra_action: str
) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    record = hitl.store.get(pending_id)
    assert record is not None
    record.action_requests.append({"name": extra_action, "args": {"path": "other.token"}})
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=user,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.SECRET_REQUEST_INVALID
    assert record.status == "pending"
    assert not (tmp_path / ".octop").exists()
    assert captured == {}

    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, action="cancel"),
        _Request(),
        user=user,
        server=server,
    )
    await _collect_sse(response)
    assert record.status == "cancelled"
    assert len(captured["decisions"]) == 2
    assert all("cancelled" in decision["message"] for decision in captured["decisions"])
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
@posix_only
async def test_submit_resume_annotates_followup_secret_card(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    workspace = _FakeWorkspace(tmp_path)
    server = _server(row=_row(), workspace=workspace, hitl=hitl, captured={})

    async def _resume(**_kwargs):
        yield {
            "type": "hitl_required",
            "request": {
                "action_requests": [{"name": "request_secret_file", "args": {"path": "hr.token"}}]
            },
        }

    server.app_runtime.gateway.processor.iter_hitl_resume_chunks = _resume
    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
        _Request(),
        user=SimpleNamespace(id=7, is_admin=False),
        server=server,
    )
    frames = await _collect_sse(response)
    followup = next(frame["request"] for frame in frames if frame["type"] == "hitl_required")
    metadata = followup["action_requests"][0]["args"]["_secret_card"]
    assert metadata == {
        "path": str((tmp_path / ".octop" / "auth" / "hr.token").resolve()),
        "exists": True,
    }
    stored = hitl.store.get(followup["pending_id"])
    assert stored is not None and stored.status == "pending"
    assert stored.action_requests[0]["args"]["_secret_card"] == metadata
    assert SECRET not in json.dumps(frames)


@pytest.mark.asyncio
@posix_only
async def test_resume_failure_keeps_filled_and_rejects_rewrite(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)

    async def _resume(**kwargs):
        captured["decisions"] = kwargs["decisions"]
        raise RuntimeError("resume failed")
        yield {}  # pragma: no cover

    server.app_runtime.gateway.processor.iter_hitl_resume_chunks = _resume
    user = SimpleNamespace(id=7, is_admin=False)
    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
        _Request(),
        user=user,
        server=server,
    )
    target = tmp_path / ".octop" / "auth" / "hr.token"
    assert target.read_text() == SECRET
    frames = await _collect_sse(response)
    assert any(frame["type"] == "error" for frame in frames)
    assert SECRET not in json.dumps(frames)
    assert SECRET not in json.dumps(captured)
    assert hitl.store.get(pending_id).status == "filled"  # type: ignore[union-attr]
    assert hitl.store.resolve_pending_for_thread("thr-1", agent_id="AGT1", user_id=7) is None

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET + "-new"),
            _Request(),
            user=user,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.SECRET_REQUEST_INVALID
    assert target.read_text() == SECRET


@pytest.mark.asyncio
@posix_only
async def test_write_failure_keeps_old_file_and_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    target = tmp_path / ".octop" / "auth" / "hr.token"
    target.parent.mkdir(parents=True)
    target.write_text("old-synthetic-token")

    def _fail_replace(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("octop.infra.agents.secret_file.private_write.os.replace", _fail_replace)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=SimpleNamespace(id=7, is_admin=False),
            server=server,
        )
    assert excinfo.value.code == ErrorCode.SECRET_WRITE_FAILED
    assert SECRET not in excinfo.value.message
    assert hitl.store.get(pending_id).status == "pending"  # type: ignore[union-attr]
    assert target.read_text() == "old-synthetic-token"
    assert list(target.parent.iterdir()) == [target]
    assert captured == {}


@pytest.mark.asyncio
async def test_shared_expert_is_refused(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    captured: dict[str, Any] = {}
    server = _server(
        row=_row(is_shared=1),
        workspace=_FakeWorkspace(tmp_path),
        hitl=hitl,
        captured=captured,
    )
    user = SimpleNamespace(id=7, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=user,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [False, True])
async def test_non_owner_is_refused(tmp_path: Path, is_admin: bool) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl, user_id=7)
    captured: dict[str, Any] = {}
    server = _server(
        row=_row(user_id=9),
        workspace=_FakeWorkspace(tmp_path),
        hitl=hitl,
        captured=captured,
    )
    owner_elsewhere = SimpleNamespace(id=7, is_admin=is_admin)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=owner_elsewhere,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.FORBIDDEN
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
async def test_invalid_path_reopens_pending_for_retry(tmp_path: Path) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl, path="../etc/evil")
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured=captured)
    user = SimpleNamespace(id=7, is_admin=False)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=user,
            server=server,
        )
    assert excinfo.value.code == ErrorCode.SECRET_PATH_INVALID
    assert hitl.store.get(pending_id).status == "pending"  # type: ignore[union-attr]
    assert not (tmp_path / ".octop").exists()


@pytest.mark.asyncio
async def test_stopped_agent_error_reopens_pending(tmp_path: Path) -> None:
    """Workspace acquisition failure must not strand the request in filling."""
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    workspace = _FakeWorkspace(tmp_path)
    captured: dict[str, Any] = {}
    server = _server(row=_row(), workspace=workspace, hitl=hitl, captured=captured)
    # agent stopped: live handle gone and no rebuild-window fallback
    row = server.app_runtime.agent_registry.get_row("AGT1")
    row.last_state = "stopped"
    server.app_runtime.agent_registry.get_agent.side_effect = OctopError(
        ErrorCode.AGENT_NOT_RUNNING, "agent 'AGT1' not running"
    )
    user = SimpleNamespace(id=7, is_admin=False)
    body = SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_file("AGT1", body, _Request(), user=user, server=server)
    assert excinfo.value.code == ErrorCode.AGENT_NOT_RUNNING
    assert hitl.store.get(pending_id).status == "pending"  # type: ignore[union-attr]
    assert not (tmp_path / ".octop").exists()

    # cancel still allowed after the failed submit
    server.app_runtime.agent_registry.get_agent.side_effect = None
    response = await submit_secret_file(
        "AGT1",
        SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, action="cancel"),
        _Request(),
        user=user,
        server=server,
    )
    await _collect_sse(response)
    assert hitl.store.get(pending_id).status == "cancelled"  # type: ignore[union-attr]


def test_submit_body_requires_content_for_submit() -> None:
    with pytest.raises(ValueError):
        SecretFileSubmitBody(thread_id="t", pending_id="p", action="submit", content="  ")
    body = SecretFileSubmitBody(thread_id="t", pending_id="p", action="cancel")
    assert body.content == ""


@pytest.mark.asyncio
async def test_unexpected_write_error_never_logs_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    hitl = HitlChannelCoordinator()
    pending_id = _register_secret_pending(hitl)
    server = _server(row=_row(), workspace=_FakeWorkspace(tmp_path), hitl=hitl, captured={})
    monkeypatch.setattr(
        "octop.api.routers.chat.routes.submit_secret_content",
        AsyncMock(side_effect=RuntimeError(SECRET)),
    )
    with pytest.raises(OctopError) as error:
        await submit_secret_file(
            "AGT1",
            SecretFileSubmitBody(thread_id="thr-1", pending_id=pending_id, content=SECRET),
            _Request(),
            user=SimpleNamespace(id=7, is_admin=False),
            server=server,
        )
    assert error.value.code == ErrorCode.SECRET_WRITE_FAILED
    assert SECRET not in error.value.message
    assert SECRET not in caplog.text
    assert "secret-file write failed" in caplog.text
    assert hitl.store.get(pending_id).status == "pending"  # type: ignore[union-attr]
