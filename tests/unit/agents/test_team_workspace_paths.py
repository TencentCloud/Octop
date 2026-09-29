"""T-25 ① —— run 工件路径的跨平台契约（Windows CI 上同样成立）。

本文件只钉**契约**，不复制实现：所有期望值都用 `Path` 从**真源**算出来
(`tmp_path` / `PathLayout` / `host_system_dir`)，**不写字面路径形状**、也不用字符串前缀
比较 —— 这是 `AGENTS.md §7「Cross-platform tests」`的硬要求，也是 T-25 的验收口径。

四条契约：

1. `run_directory(row)` 是 run 目录的**唯一来源**：`host_workspace` ⇒ 相对的
   `team/<runId>`；`explicit:<abs>` ⇒ 绝对根 + `<runId>`。API / 中间件 / 导出都从这里解析，
   所以它的平台语义值得钉住。
2. run 工件的读写**经 `BackendWorkspace`**且路径是 **workspace-relative**（`AGENTS.md §7`），
   因此下盘位置必然等于 `workspace_root / <run_directory> / <name>`（`Path` 相等），
   且**不可能**离开 workspace 根。
3. 路径判定与平台无关：`path_in_scope`(G11) 与 `run_scoped_target` 对 `\\` 与 `/` 同语义。
4. `OCTOP_HOME` 用 `monkeypatch.setenv(tmp_path)` 钉住（`AGENTS.md §7` 末条），断言用 `Path` 连接。

**T-52 已修**（原文保留作来路）：`explicit:<abs>` 根带尾部**反斜杠**时，旧的
`rstrip("/")` 去不掉它 ⇒ 曾产出**混合分隔符**（`C:\\x\\team\\` → `C:\\x\\team\\/<runId>`）。
`run_directory` 现在经 `PurePosixPath` **归一**：两种分隔符都被去掉，连接只用一种。
下面那条用例**原为 `@pytest.mark.xfail(strict=False)`**（把已知缺陷焊在契约上，修好后翻成
XPASS），`T-52` 修好后已**翻转为正向断言**、不再 xfail。

本文件**零** `skipif`：全部用例在 POSIX 与 Windows 上跑同一段断言（无平台分支）。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from deepagents.backends.local_shell import LocalShellBackend
from octop_harness.backends.workspace import BackendWorkspace

from octop.api.common.memory_client import memory_db_path_for_cfg
from octop.infra.agents.teams.artifacts import run_scoped_target
from octop.infra.agents.teams.export import PROJECTION_FILES
from octop.infra.agents.teams.run_service import (
    RUN_DIR_PREFIX,
    path_in_scope,
    run_directory,
)
from octop.infra.agents.workspace.dir import host_system_dir
from octop.infra.utils.paths import PathLayout

RUN_ID = "2026-01-02-030405"


def _row(run_root: str) -> SimpleNamespace:
    """`run_directory` 只读 `run_id` / `run_root` 两个字段（与既有用例同法）。"""
    return SimpleNamespace(run_id=RUN_ID, run_root=run_root)


def _workspace(root: Path) -> BackendWorkspace:
    """**真实** `BackendWorkspace`（不是替身）：路径规则由它裁决，测试不复制规则。"""
    backend = LocalShellBackend(root_dir=str(root), virtual_mode=False)
    return BackendWorkspace(backend, root)


# ── 契约 1：run 目录的唯一来源 ───────────────────────────────────────────────


def test_host_workspace_root_is_workspace_relative() -> None:
    """默认根：相对路径，形如 `team/<runId>`（用 `Path` 表达，不写字符串前缀）。"""
    path = Path(run_directory(_row("host_workspace")))

    assert path == Path(RUN_DIR_PREFIX) / RUN_ID
    assert not path.is_absolute()
    assert path.parts == (RUN_DIR_PREFIX, RUN_ID)


def test_explicit_root_is_absolute_and_equals_the_path_join(tmp_path: Path) -> None:
    """显式根：绝对路径，恰为 `<root>/<runId>` —— 根取自 `tmp_path`（本平台真绝对路径）。"""
    path = Path(run_directory(_row(f"explicit:{tmp_path}")))

    assert path == tmp_path / RUN_ID
    assert path.is_absolute()
    assert path.parent == tmp_path


def test_explicit_root_without_a_base_falls_back_to_the_run_id() -> None:
    """`explicit:` 后为空 ⇒ 只有 runId（不产出悬空的 `/` 前缀）。"""
    path = Path(run_directory(_row("explicit:")))

    assert path == Path(RUN_ID)
    assert not path.is_absolute()


def test_explicit_root_with_a_trailing_separator_yields_one_separator() -> None:
    """T-52（已修）：explicit 根无论用哪种分隔符 / 有没有尾部，都只产出一种分隔符。

    原为 `@pytest.mark.xfail(strict=False)`（记录已知缺陷：混合分隔符）；`T-52` 修好
    `run_directory` 后**翻转为正向断言** —— 旧句保留在此，作为这条覆盖的来路。


    输入**故意用 Windows 形状**：`run_directory` 是纯字符串函数，这段代码路径在
    POSIX 上同样命中（本机实测 `C:\\x\\team\\/2026-...`），因此该用例在两个平台上
    结果一致 —— 不会变成"只在 Windows 红"的用例。
    """
    produced = run_directory(_row("explicit:C:\\x\\team\\"))

    # 契约：<runId> 之前恰好一个分隔符，不得出现 `\\/` 或 `/\\`。
    assert "\\/" not in produced
    assert "/\\" not in produced


# ── 契约 2：工件经 BackendWorkspace、workspace-relative ─────────────────────


def test_run_artifacts_land_at_the_workspace_relative_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """四份工件落在 `workspace_root / team / <runId> / <name>`，且不逃出 workspace。"""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))
    workspace = _workspace(tmp_path)
    row = _row("host_workspace")
    run_dir = run_directory(row)

    # 契约前提：workspace-relative 的路径**不可能**通过"绝对路径"越出根。
    assert not Path(run_dir).is_absolute()

    run_path = tmp_path / RUN_DIR_PREFIX / RUN_ID
    for name in PROJECTION_FILES:
        workspace.write_text(f"{run_dir}/{name}", f"# {name}\n", force=True)

    for name in PROJECTION_FILES:
        on_disk = run_path / name
        assert on_disk.is_file()
        assert on_disk.read_text(encoding="utf-8") == f"# {name}\n"
        assert workspace.exists(f"{run_dir}/{name}")
        assert workspace.read_text(f"{run_dir}/{name}") == f"# {name}\n"

    # 只落了这四份，没有额外产物；且 run 目录确实在 workspace 之内。
    assert sorted(p.name for p in run_path.iterdir()) == sorted(PROJECTION_FILES)
    assert run_path.is_relative_to(tmp_path)
    assert run_path.parent == tmp_path / RUN_DIR_PREFIX


def test_artifact_path_join_is_pure_pathlib(tmp_path: Path) -> None:
    """期望值用 `Path` 连接算出来（不是拼字符串）：`/` 与 `os.sep` 都不出现。"""
    workspace_root = tmp_path / "ws"
    expected_dir = workspace_root / RUN_DIR_PREFIX / RUN_ID

    assert expected_dir == workspace_root.joinpath(RUN_DIR_PREFIX, RUN_ID)
    assert expected_dir / "SPEC.md" == expected_dir.joinpath("SPEC.md")
    # 逐级父目录相等 —— 这正是"路径相等"该有的断言形态。
    assert (expected_dir / "SPEC.md").parent == expected_dir
    assert expected_dir.parent == workspace_root / RUN_DIR_PREFIX


# ── 契约 3：路径判定与平台无关 ──────────────────────────────────────────────


def test_path_in_scope_treats_backslash_like_slash() -> None:
    """G11 的作用域判定对 `\\` 与 `/` 同语义（本 run 的合规范例：显式 `replace("\\\\", "/")`）。"""
    assert path_in_scope("src\\octop\\infra\\db\\repos\\x.py", ["src/octop/infra/db"])
    assert path_in_scope("src/octop/infra/db/repos/x.py", ["src\\octop\\infra\\db"])
    assert path_in_scope("./src/octop/infra/db/x.py", ["src/octop/infra/db"])
    assert not path_in_scope("src/octop/api/x.py", ["src/octop/infra/db"])
    # 空目标 = 不限制（既有语义，钉住以免被"顺手收紧"）。
    assert path_in_scope("   ", ["src/octop/infra/db"])


def test_run_scoped_target_requires_exactly_two_segments(tmp_path: Path) -> None:
    """恰好两段（runId + 文件名）才算 run 作用域目标；更深/更浅/越出根一律不拦（None）。"""
    run_dir = tmp_path / RUN_ID
    target = run_scoped_target(run_dir / "SPEC.md", tmp_path)

    assert target is not None
    assert target.run_id == RUN_ID
    assert target.base == "SPEC.md"
    assert Path(target.path) == Path(os.path.normpath(str(run_dir / "SPEC.md")))

    assert run_scoped_target(run_dir / "sub" / "SPEC.md", tmp_path) is None
    assert run_scoped_target(tmp_path / "SPEC.md", tmp_path) is None
    assert run_scoped_target(tmp_path.parent / "SPEC.md", tmp_path) is None
    assert run_scoped_target("", tmp_path) is None
    assert run_scoped_target(run_dir / "SPEC.md", "") is None


def test_run_scoped_target_refuses_a_target_on_another_root() -> None:
    """不同根的写目标 ⇒ None（Windows 盘符不同时靠 `except ValueError` 兜住）。

    跨盘符在 POSIX 上不会抛 `ValueError`（没有盘符概念），但相对化后必然含 `..` ——
    两条路径都返回 `None`，所以**这条断言在两个平台上同义**。
    """
    assert run_scoped_target("D:\\other\\SPEC.md", "C:\\runs") is None
    assert run_scoped_target("/other/SPEC.md", "/srv/runs") is None


# ── 契约 4：OCTOP_HOME 钉住安装根（真源算期望值）────────────────────────────


def test_octop_home_pins_the_workspace_layout_from_the_single_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`OCTOP_HOME` ⇒ 安装根；agent 工作区与记忆库路径都从**同一个真源**派生。"""
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path))

    layout = PathLayout.from_env()
    assert layout.root == tmp_path
    assert layout.agents_dir == tmp_path / "agents"

    agent_ws = layout.agents_dir / "agent-x"
    # 新布局：system 文件在 `{workspace}/.octop`（`AGENTS.md §7`）。
    new_cfg = {"system_files_path": ".octop"}
    assert host_system_dir(agent_ws, new_cfg) == agent_ws / ".octop"
    # 单一权威：`memory_db_path_for_cfg` 必须**就是** `host_system_dir` 的派生，
    # 不是第二份拼法（本 run 反复在治的病；T-57 的落点也须复用它）。
    assert memory_db_path_for_cfg(agent_ws, new_cfg) == (
        host_system_dir(agent_ws, new_cfg) / "memory.sqlite"
    )
    assert memory_db_path_for_cfg(agent_ws, new_cfg) == agent_ws / ".octop" / "memory.sqlite"
    # legacy：无 system 前缀 ⇒ 落在 workspace 根（两种布局都要能算）。
    assert memory_db_path_for_cfg(agent_ws, None) == agent_ws / "memory.sqlite"
