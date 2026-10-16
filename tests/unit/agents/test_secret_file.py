"""Unit tests for the secret-file card core (paths, private write, tool)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from octop.infra.agents.secret_file import (
    build_secret_file_tools,
    describe_secret_request,
    maybe_annotate_secret_payload,
    normalize_secret_name,
    resolve_auth_fragment,
    submit_secret_content,
)
from octop.infra.agents.secret_file.private_write import write_secret_private
from octop.infra.errors import ErrorCode, OctopError

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only permission semantics")

SECRET = "synthetic-test-token-0123456789"  # synthetic; never a real credential


class _FakeBackend:
    def __init__(self, *, sandbox_fs: bool = False) -> None:
        self.sandbox_fs = sandbox_fs
        self.commands: list[str] = []
        self.exit_code = 0

    def execute(self, command: str, *, timeout: int | None = None):
        self.commands.append(command)

        class _Result:
            exit_code = self.exit_code
            output = ""

        return _Result()


class _FakeWorkspace:
    """Minimal BackendWorkspace stand-in backed by a host temp dir."""

    def __init__(self, root: Path, prefix: str = ".octop", *, backend: _FakeBackend | None = None):
        self.workspace_dir = root
        self.system_files_path = prefix
        self.backend = backend or _FakeBackend()
        self.uploads: dict[str, bytes] = {}

    def system_rel(self, path: str) -> str:
        return f"{self.system_files_path}/{path}" if self.system_files_path else path

    def resolve_path(self, fragment: str) -> str:
        return str((Path(self.workspace_dir) / fragment).resolve())

    async def als(self, path: str):
        directory = Path(self.workspace_dir) / path

        class _Result:
            entries = [1] if directory.is_dir() and any(directory.iterdir()) else []

        return _Result()

    async def aexists(self, path: str) -> bool:
        return (Path(self.workspace_dir) / path).exists()

    async def aupload_bytes(self, path: str, data: bytes) -> None:
        self.uploads[path] = data


# ---------------------------------------------------------------------------
# normalize_secret_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hr.token", "hr.token"),
        ("auth/hr.token", "hr.token"),
        (".octop/auth/hr.token", "hr.token"),
        (".octop-auth/hr.token", "hr.token"),
        ("./hr.token", "hr.token"),
        ("feishu/app.token", "feishu/app.token"),
        (" auth/nested/dir/token.txt ", "nested/dir/token.txt"),
    ],
)
def test_normalize_secret_name_accepts_relative(raw: str, expected: str) -> None:
    assert normalize_secret_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "/etc/passwd",
        "~/.ssh/id_rsa",
        "../outside",
        "a/../b",
        "..",
        ".",
        "",
        "   ",
        "C:/secrets/x",
        "C:\\secrets\\x",
        "//share/x",
        "a//b",
        ".octop/auth/",
        "auth/",
        None,
        123,
    ],
)
def test_normalize_secret_name_rejects(raw) -> None:
    with pytest.raises(OctopError) as excinfo:
        normalize_secret_name(raw)
    assert excinfo.value.code == ErrorCode.SECRET_PATH_INVALID


# ---------------------------------------------------------------------------
# auth fragment layouts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_fragment_new_layout(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    assert await resolve_auth_fragment(ws) == ".octop/auth"


@pytest.mark.asyncio
async def test_auth_fragment_legacy_with_files(tmp_path: Path) -> None:
    legacy = tmp_path / ".octop-auth"
    legacy.mkdir()
    (legacy / "old.token").write_text("old")
    ws = _FakeWorkspace(tmp_path)
    assert await resolve_auth_fragment(ws) == ".octop-auth"


@pytest.mark.asyncio
async def test_auth_fragment_legacy_empty_prefers_canonical(tmp_path: Path) -> None:
    (tmp_path / ".octop-auth").mkdir()
    ws = _FakeWorkspace(tmp_path)
    assert await resolve_auth_fragment(ws) == ".octop/auth"


@pytest.mark.asyncio
async def test_auth_fragment_no_prefix_is_legacy(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path, prefix="")
    assert await resolve_auth_fragment(ws) == ".octop-auth"


# ---------------------------------------------------------------------------
# local private write
# ---------------------------------------------------------------------------


@posix_only
@pytest.mark.asyncio
async def test_submit_writes_into_canonical_auth_dir(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    display = await submit_secret_content(ws, raw_path="hr.token", content=SECRET)
    target = tmp_path / ".octop" / "auth" / "hr.token"
    assert target.read_text() == SECRET
    assert display == str(target.resolve())


@posix_only
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.asyncio
async def test_real_workspace_writes_to_platform_auth_directory(tmp_path: Path, legacy: bool):
    from octop_harness.backends import resolve_backend
    from octop_harness.backends.workspace import BackendWorkspace

    if legacy:
        old = tmp_path / ".octop-auth" / "old.token"
        old.parent.mkdir()
        old.write_text("existing", encoding="utf-8")
    backend = resolve_backend(
        {"type": "filesystem", "root_dir": str(tmp_path), "virtual_mode": False},
        workspace_dir=tmp_path,
        system_files_path=".octop",
    )
    workspace = BackendWorkspace(backend, tmp_path, system_files_path=".octop")
    target = tmp_path / (".octop-auth" if legacy else ".octop/auth") / "hr.token"
    assert await submit_secret_content(workspace, raw_path="hr.token", content=SECRET) == str(
        target
    )
    assert target.read_text(encoding="utf-8") == SECRET
    assert await describe_secret_request(workspace, {"path": "hr.token"}) == {
        "path": str(target),
        "exists": True,
    }
    assert not (tmp_path / "auth").exists()
    if legacy:
        assert old.read_text(encoding="utf-8") == "existing"


@posix_only
@pytest.mark.asyncio
async def test_submit_permissions_are_private(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    await submit_secret_content(ws, raw_path="hr.token", content=SECRET)
    target = tmp_path / ".octop" / "auth" / "hr.token"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert target.stat().st_uid == os.geteuid()


@posix_only
@pytest.mark.asyncio
async def test_submit_replaces_existing_file(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    await submit_secret_content(ws, raw_path="hr.token", content=SECRET)
    await submit_secret_content(ws, raw_path="hr.token", content=SECRET + "-v2")
    assert (tmp_path / ".octop" / "auth" / "hr.token").read_text() == SECRET + "-v2"


@posix_only
@pytest.mark.asyncio
async def test_submit_supports_legacy_auth_dir(tmp_path: Path) -> None:
    legacy = tmp_path / ".octop-auth"
    legacy.mkdir()
    (legacy / "old.token").write_text("old")
    ws = _FakeWorkspace(tmp_path)
    await submit_secret_content(ws, raw_path="new.token", content=SECRET)
    assert (legacy / "new.token").read_text() == SECRET


@posix_only
@pytest.mark.asyncio
async def test_submit_rejects_symlink_target(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    auth = tmp_path / ".octop" / "auth"
    auth.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("keep-me")
    (auth / "link").symlink_to(outside)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(ws, raw_path="link", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_PATH_INVALID
    assert outside.read_text() == "keep-me"


@posix_only
@pytest.mark.asyncio
async def test_submit_rejects_symlinked_auth_parent(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    (tmp_path / ".octop").symlink_to(tmp_path.parent)
    with pytest.raises(OctopError):
        await submit_secret_content(ws, raw_path="z.token", content=SECRET)


@posix_only
@pytest.mark.parametrize("operation", ["replace", "fchmod"])
@pytest.mark.asyncio
async def test_failed_write_preserves_existing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    ws = _FakeWorkspace(tmp_path)
    await submit_secret_content(ws, raw_path="hr.token", content=SECRET)

    def _boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, operation, _boom)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(ws, raw_path="hr.token", content=SECRET + "-new")
    assert excinfo.value.code == ErrorCode.SECRET_WRITE_FAILED
    # original file untouched, temp file cleaned up
    assert (tmp_path / ".octop" / "auth" / "hr.token").read_text() == SECRET
    leftovers = [p.name for p in (tmp_path / ".octop" / "auth").iterdir()]
    assert leftovers == ["hr.token"]
    # error message must not contain the secret
    assert SECRET not in excinfo.value.message


@posix_only
@pytest.mark.parametrize("linked_fragment", [".octop", ".octop/auth"])
@pytest.mark.asyncio
async def test_auth_ancestor_symlink_inside_workspace_is_refused(
    tmp_path: Path, linked_fragment: str
) -> None:
    redirected = tmp_path / "redirected"
    redirected.mkdir(mode=0o755)
    original_mode = stat.S_IMODE(redirected.stat().st_mode)
    link = tmp_path / linked_fragment
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(redirected, target_is_directory=True)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(_FakeWorkspace(tmp_path), raw_path="token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_PATH_INVALID
    assert list(redirected.iterdir()) == []
    assert stat.S_IMODE(redirected.stat().st_mode) == original_mode


@posix_only
@pytest.mark.asyncio
async def test_nested_auth_directories_are_all_private(tmp_path: Path) -> None:
    await submit_secret_content(
        _FakeWorkspace(tmp_path), raw_path="cli-home/.config/example/token", content=SECRET
    )
    auth = tmp_path / ".octop" / "auth"
    for suffix in ("", "cli-home", "cli-home/.config", "cli-home/.config/example"):
        assert stat.S_IMODE((auth / suffix).stat().st_mode) == 0o700


@pytest.mark.asyncio
async def test_non_posix_backend_is_refused_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from octop.infra.agents.secret_file import private_write

    monkeypatch.setattr(private_write, "_POSIX", False)
    workspace = _FakeWorkspace(tmp_path)
    assert not private_write.secret_backend_supported(workspace.backend)
    assert await describe_secret_request(workspace, {"path": "token"}) == {
        "invalid": True,
        "unsupported": True,
    }
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(workspace, raw_path="token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_BACKEND_UNSUPPORTED
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_submit_rejects_empty_and_huge_content(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(ws, raw_path="hr.token", content="   ")
    assert excinfo.value.code == ErrorCode.SECRET_REQUEST_INVALID
    with pytest.raises(OctopError):
        await submit_secret_content(ws, raw_path="hr.token", content="x" * (70 * 1024))


# ---------------------------------------------------------------------------
# sandbox + unsupported backends
# ---------------------------------------------------------------------------


class _SyntheticSandboxBackend(_FakeBackend):
    """Sandbox stand-in: protocol upload lands on a host dir like docker's
    tar-based _put_file (0644), execute runs a real local shell."""

    def __init__(self, root: Path) -> None:
        super().__init__(sandbox_fs=True)
        self._root = root

    def _map_path(self, virtual: str) -> str:
        return str(self._root / virtual.lstrip("/"))


class _SyntheticSandboxWorkspace(_FakeWorkspace):
    def __init__(self, root: Path, backend: _SyntheticSandboxBackend) -> None:
        super().__init__(root, backend=backend)

    async def aupload_bytes(self, path: str, data: bytes) -> None:
        # docker _put_file semantics: tar entry with default 0644 mode.
        target = Path(self.backend._map_path("/" + path))  # type: ignore[attr-defined]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        os.chmod(target, 0o644)


@posix_only
@pytest.mark.asyncio
async def test_sandbox_auth_symlink_cannot_escape(tmp_path: Path) -> None:
    """auth dir symlinked outside the workspace: no write may follow it."""
    ws_root = tmp_path / "ws"
    ws_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (ws_root / ".octop").symlink_to(outside)
    backend = _SyntheticSandboxBackend(ws_root)
    ws = _SyntheticSandboxWorkspace(ws_root, backend)

    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(ws, raw_path="hr.token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_BACKEND_UNSUPPORTED
    # nothing landed outside, nothing uploaded, no command ran
    assert not (outside / "auth" / "hr.token").exists()
    assert list(outside.rglob("*.tmp-*")) == []
    assert backend.commands == []
    assert SECRET.encode() not in [p.read_bytes() for p in ws_root.rglob("*") if p.is_file()]


@pytest.mark.asyncio
async def test_sandbox_backend_is_refused_without_partial_writes(tmp_path: Path) -> None:
    """Sandbox protocol uploads are 0644 tar entries with no mode control, so
    the backend is refused outright — no temp secret may be left behind."""
    backend = _SyntheticSandboxBackend(tmp_path)
    backend.exit_code = 1
    ws = _SyntheticSandboxWorkspace(tmp_path, backend)
    with pytest.raises(OctopError) as excinfo:
        await submit_secret_content(ws, raw_path="hr.token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_BACKEND_UNSUPPORTED
    leftovers = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert leftovers == []
    assert backend.commands == []


@pytest.mark.asyncio
async def test_sandbox_without_execute_is_refused(tmp_path: Path) -> None:
    backend = _FakeBackend(sandbox_fs=True)
    ws = _FakeWorkspace(tmp_path, backend=backend)
    with pytest.raises(OctopError) as excinfo:
        await write_secret_private(ws, fragment=".octop/auth/x.token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_BACKEND_UNSUPPORTED


@pytest.mark.asyncio
async def test_cloud_backend_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from octop.infra.agents.secret_file import private_write

    monkeypatch.setattr(private_write, "is_cloud_storage_backend", lambda _b: True)
    ws = _FakeWorkspace(tmp_path)
    with pytest.raises(OctopError) as excinfo:
        await write_secret_private(ws, fragment=".octop/auth/x.token", content=SECRET)
    assert excinfo.value.code == ErrorCode.SECRET_BACKEND_UNSUPPORTED


# ---------------------------------------------------------------------------
# tool schema
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# card metadata annotation
# ---------------------------------------------------------------------------


@posix_only
@pytest.mark.asyncio
async def test_describe_reports_normalized_path_and_existence(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    existing = tmp_path / ".octop" / "auth" / "old.token"
    existing.parent.mkdir(parents=True)
    existing.write_text("old")

    info = await describe_secret_request(ws, {"path": "auth/old.token"})
    assert info == {"path": str(existing.resolve()), "exists": True}

    missing = await describe_secret_request(ws, {"path": "new.token"})
    assert missing["exists"] is False
    assert missing["path"].endswith(".octop/auth/new.token")


@posix_only
@pytest.mark.asyncio
async def test_describe_marks_invalid_paths(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    assert await describe_secret_request(ws, {"path": "/etc/passwd"}) == {"invalid": True}


@posix_only
@pytest.mark.asyncio
async def test_maybe_annotate_secret_payload(tmp_path: Path) -> None:
    ws = _FakeWorkspace(tmp_path)
    payload = {
        "action_requests": [
            {"name": "request_secret_file", "args": {"path": "hr.token", "prompt": "p"}},
        ]
    }
    await maybe_annotate_secret_payload(payload, ws)
    meta = payload["action_requests"][0]["args"]["_secret_card"]
    assert meta["exists"] is False
    assert meta["path"].endswith(".octop/auth/hr.token")

    # non-secret payloads and missing workspace are untouched
    other = {"action_requests": [{"name": "write_file", "args": {}}]}
    await maybe_annotate_secret_payload(other, ws)
    assert "_secret_card" not in other["action_requests"][0]["args"]
    await maybe_annotate_secret_payload(payload, None)


def test_tool_has_no_secret_argument() -> None:
    (tool,) = build_secret_file_tools()
    assert tool.name == "request_secret_file"
    props = set(tool.args_schema.model_json_schema()["properties"])
    assert props == {"path", "prompt", "title"}
    assert "never" in tool.description.lower() or "NEVER" in tool.description


@pytest.mark.asyncio
async def test_tool_headless_fallback_is_nonblocking() -> None:
    (tool,) = build_secret_file_tools()
    result = await tool.ainvoke({"path": "hr.token", "prompt": "HR token"})
    assert "No interactive credential card" in result
