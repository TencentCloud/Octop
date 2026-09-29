"""卡 `T99-1`：解析闸门（`T-99` 相位 B）的守卫行为矩阵。

契约：`PLAN.md` §4.2（闸门 + 判定码逐字）/ §4.4（退化不得静默）/ §4.5（残余登记）·
`SPEC · B14` · 定稿③（用户拍板：本地解析并拒 + 远端登记）。

★ 仅本地可观测：符号链接面**只在闸门开**（宿主路径类后端）时可判；闸门关（远端虚拟键 /
docker `sandbox_fs` / 拿不到后端类型信息）⇒ 不解析 ⇒ 软链别名**判不出**（§4.5 逐字登记，
不是「已覆盖」）。硬链接同 inode 别名 `Path.resolve()` **也不解析** ⇒ 登记残余，不是缺陷。

本文件**只**断言行为，不重复实现路径规则（`AGENTS.md` §7：判据唯一落点在内核）。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from octop.api.routers.workspace import (
    _assert_workspace_write_allowed,
    _assert_workspace_write_resolved,
    _host_resolve_enabled,
)
from octop.infra.errors import ErrorCode, OctopError

posix_only = pytest.mark.skipif(
    os.name != "posix", reason="symlink/hardlink semantics require a POSIX host"
)

_LOGGER = "octop.api.routers.workspace"
_SKIPPED = "workspace-guard-resolve-skipped"
_OUTSIDE = "workspace-guard-resolve-outside"
_ERROR = "workspace-guard-resolve-error"

_TEAM_MSG = "cannot modify '.octop/team' paths"
_BUILTIN_MSG = "cannot modify '_builtin_skills' paths"


class _FakeWorkspace:
    """轻量 fake：只提供闸门读的两个口（`backend` / `workspace_dir`），不起真服务。"""

    def __init__(self, backend: object, workspace_dir: str | Path | None = None) -> None:
        self.backend = backend
        self.workspace_dir = workspace_dir


class _NoBackendWorkspace:
    """★ 无 `backend` 属性 ⇒ 拿不到后端类型信息 ⇒ 闸门必须关。"""

    workspace_dir = None


def _deny(exc_info: pytest.ExceptionInfo[OctopError], *, code: ErrorCode, message: str) -> None:
    """★ 判定码 + 文案逐字（`PLAN` §4.2 第 4/5 条；命中内核 ⇒ 同码同文案）。"""
    err = exc_info.value
    assert str(err) == message, f"message drifted: {str(err)!r}"
    got = getattr(err, "code", None)
    assert got is code, f"code {got!r} != {code!r}"


def _team_ws(tmp_path: Path) -> Path:
    """真工作区根 + 真 `.octop/team` 面（软链目标须真实存在，`resolve` 才走得通）。"""
    (tmp_path / ".octop" / "team" / "memory").mkdir(parents=True)
    return tmp_path


@posix_only
def test_gate_on_symlink_alias_to_team_memory_denied(tmp_path: Path) -> None:
    """★ 格 1：闸门开 + 软链别名指向 `.octop/team` ⇒ 409 `TEAM_ARTIFACT_OWNERSHIP_DENIED`。

    别名串 `shortcut/memory/x.md` 文本上**不含** `.octop/team` ⇒ 只有真实解析才能判出；
    §4.2 第 5 条：命中 §2.2 同一内核 ⇒ 同码同文案（`_team_memory_pair_hit` ⇒ 409）。
    """
    ws = _team_ws(tmp_path)
    (ws / "shortcut").symlink_to(".octop/team", target_is_directory=True)
    with pytest.raises(OctopError) as exc:
        _assert_workspace_write_resolved("shortcut/memory/x.md", workspace_dir=ws, resolve_ok=True)
    _deny(exc, code=ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED, message=_TEAM_MSG)


@posix_only
def test_gate_on_benign_symlink_returns_resolved_target(tmp_path: Path) -> None:
    """★ 格 1 正例：软链指向普通目录 ⇒ 放行，且返回**解析后的相对串**（= 落盘串，`INV-3`）。"""
    ws = _team_ws(tmp_path)
    (ws / "notes").mkdir()
    (ws / "shortcut2").symlink_to("notes", target_is_directory=True)
    got = _assert_workspace_write_resolved("shortcut2/ok.md", workspace_dir=ws, resolve_ok=True)
    assert got == "notes/ok.md"


def test_gate_on_target_outside_workspace_denied(tmp_path: Path) -> None:
    """★ 格 2：闸门开 + 解析后越出工作区根 ⇒ 403 `cannot modify paths outside the workspace`。"""
    ws = _team_ws(tmp_path)
    escaping = str(ws / ".." / "outside.md")
    with pytest.raises(OctopError) as exc:
        _assert_workspace_write_resolved(escaping, workspace_dir=ws, resolve_ok=True)
    _deny(exc, code=ErrorCode.FORBIDDEN, message="cannot modify paths outside the workspace")


@posix_only
def test_gate_on_resolve_failure_denied(tmp_path: Path) -> None:
    """★ 格 3：解析抛错（自引用软链 ⇒ `ELOOP`/`RuntimeError: Symlink loop`）⇒ 403 拒绝。

    ★ 绝不 500、绝不放行（§4.2 第 4 条）：文案 `cannot resolve write target`（常量，不回显 path）。
    """
    ws = _team_ws(tmp_path)
    (ws / "loop").symlink_to("loop")
    with pytest.raises(OctopError) as exc:
        _assert_workspace_write_resolved("loop", workspace_dir=ws, resolve_ok=True)
    _deny(exc, code=ErrorCode.FORBIDDEN, message="cannot resolve write target")


@pytest.mark.parametrize("gate_off", ["resolve_ok_false", "root_missing", "root_not_absolute"])
def test_gate_off_does_not_resolve_and_returns_input_verbatim(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, gate_off: str
) -> None:
    """★ 格 4：闸门关（§4.2 第 1/2 条三种形态）⇒ 不解析、原样返回入参 + 留痕 token。

    ★ 逐字登记「符号链接面未覆盖」：这是**不解析**，不是**放行**——放行与否仍由文本口径判。
    """
    ws = _team_ws(tmp_path)
    if gate_off == "resolve_ok_false":
        kwargs: dict[str, object] = {"workspace_dir": str(ws), "resolve_ok": False}
    elif gate_off == "root_missing":
        kwargs = {"workspace_dir": None, "resolve_ok": True}
    else:
        kwargs = {"workspace_dir": "relative/root", "resolve_ok": True}
    caplog.set_level(logging.WARNING, logger=_LOGGER)
    got = _assert_workspace_write_resolved("notes/ok.md", **kwargs)  # type: ignore[arg-type]
    assert got == "notes/ok.md", "闸门关必须原样返回入参（未解析）"
    assert _SKIPPED in caplog.text
    assert "symlink surface uncovered (text-only judgement)" in caplog.text


def test_gate_off_is_not_a_pass_for_text_judgeable_targets(tmp_path: Path) -> None:
    """★ 格 4 反向：闸门关 ⇒ **绝不**放行「文本可判」的受保护目标（三拼写同判）。

    路径走相位 A → 相位 B 的真链（`file://` 由相位 A 折成宿主绝对形态）；无论哪一相位开口，
    判定码与文案都必须逐字一致（§2.2 同一内核）。
    """
    ws = _team_ws(tmp_path)
    spellings = [
        ".octop/team/memory/x.md",
        str(ws / ".octop" / "team" / "memory" / "x.md"),
        f"file://{ws}/.octop/team/memory/x.md",
    ]
    for raw in spellings:
        with pytest.raises(OctopError) as exc:
            _assert_workspace_write_resolved(
                _assert_workspace_write_allowed(raw, from_workspace=True, workspace_dir=ws),
                workspace_dir=ws,
                resolve_ok=False,
            )
        _deny(exc, code=ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED, message=_TEAM_MSG)
    with pytest.raises(OctopError) as exc:
        _assert_workspace_write_resolved(
            _assert_workspace_write_allowed(
                f"file://{ws}/_builtin_skills/x.md", from_workspace=True, workspace_dir=ws
            ),
            workspace_dir=ws,
            resolve_ok=False,
        )
    _deny(exc, code=ErrorCode.FORBIDDEN, message=_BUILTIN_MSG)


def test_host_resolve_gate_reads_backend_type_only(tmp_path: Path) -> None:
    """★ 格 5：闸门判定（轻量 fake，不起真服务）= 宿主路径类后端 True / 其余 False。"""
    from deepagents.backends.filesystem import FilesystemBackend

    class _SubclassBackend(FilesystemBackend):
        pass

    assert _host_resolve_enabled(_FakeWorkspace(FilesystemBackend(root_dir=str(tmp_path)))) is True
    assert _host_resolve_enabled(_FakeWorkspace(_SubclassBackend(root_dir=str(tmp_path)))) is True
    assert _host_resolve_enabled(_NoBackendWorkspace()) is False
    assert _host_resolve_enabled(_FakeWorkspace(object(), str(tmp_path))) is False


@posix_only
def test_hardlink_alias_is_registered_residual_not_caught(tmp_path: Path) -> None:
    """★ 格 6：`os.link` 同 inode 别名 ⇒ 解析相位**拦不住** = §4.5 登记残余（不是缺陷）。

    `Path.resolve()` 不解析硬链接 ⇒ 别名串解析后仍在工作区内 ⇒ 文本口径放行。仅本地可观测。
    """
    ws = _team_ws(tmp_path)
    secret = ws / ".octop" / "team" / "memory" / "secret.md"
    secret.write_text("team memory", encoding="utf-8")
    alias = ws / "alias.md"
    os.link(secret, alias)
    assert alias.stat().st_ino == secret.stat().st_ino, "硬链接必须同 inode"
    assert alias.resolve() != secret.resolve(), "resolve() 不解析硬链接（残余机理）"
    got = _assert_workspace_write_resolved("alias.md", workspace_dir=ws, resolve_ok=True)
    assert got == "alias.md"
