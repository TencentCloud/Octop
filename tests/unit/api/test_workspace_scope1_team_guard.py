"""★ 范围① 单元矩阵：``.octop/team/**`` 对「建目录 / 删除 / 搬出 / 文档转换器覆写」必须 409。

契约依据：``PLAN.md`` §2.2（段折叠唯一折点 = ASCII 大小写折叠）/ §2.3（判据顺序冻结：
根 → team 面 → builtin 面）/ §3（接入表：四端点走单入口）/ §7.2（范围①段）·
``SPEC.md`` B17 · ``TASKS.json`` ``T97-3``。

★ 仅本地可观测。

★ 为什么测单入口而不是直接调 handler：``mkdir_workspace_dir`` / ``delete_workspace_file`` /
``move_workspace_file`` / ``write_doc`` 都是 FastAPI handler（``Depends`` 注入 server / user），
直接调用需伪造整个运行面，且无法证明「端点确实走了这条判据」。卡面允许的等价口径是：
**判据侧**驱动唯一入口 ``_assert_workspace_write_allowed``（三拼写 / 目录本身 / 大小写折叠 /
两面与根分支对照 / 正对照），**接入侧**用 AST 断言 6 个端点都调用它、实参形态与判据侧的
调用形态一致（见本文件末段），并对 ``move`` 断言源与目标各判一次。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from octop.api.routers import workspace as ws_router
from octop.infra.errors import ErrorCode, OctopError

TEAM_REL = ".octop/team/LEARNINGS.md"

_SPELLING_KINDS = ("relative", "host_absolute", "file_url")

#: 范围① 四个端点的接入形态（与源码调用点逐字一致，由 ``test_scope1_call_sites_*`` 反查）。
_ENDPOINT_CALL_SHAPES: dict[str, dict[str, object]] = {
    "mkdir_workspace_dir": {"from_workspace": True},
    "delete_workspace_file": {"from_workspace": True},
    "move_workspace_file": {"from_workspace": True},
    "write_doc": {"from_workspace": True},
}


def _spelling(root: Path, kind: str) -> tuple[str, bool]:
    """同一目标的三种拼写 => ``(path, from_workspace)``。"""
    abs_target = (root / ".octop" / "team" / "LEARNINGS.md").as_posix()
    if kind == "relative":
        return TEAM_REL, True
    if kind == "host_absolute":
        return abs_target, False
    return f"file://{abs_target}", False


def _deny(path: str, *, workspace_dir: Path | None, **kwargs: object) -> OctopError:
    """调唯一入口并断言抛错，返回异常对象（调用方再断言 code / status）。"""
    with pytest.raises(OctopError) as excinfo:
        ws_router._assert_workspace_write_allowed(  # type: ignore[arg-type]
            path, workspace_dir=workspace_dir, **kwargs
        )
    return excinfo.value


def _allow(path: str, *, workspace_dir: Path | None, **kwargs: object) -> str:
    """调唯一入口并断言放行，返回它判给调用者落盘的那个串。"""
    return ws_router._assert_workspace_write_allowed(  # type: ignore[arg-type]
        path, workspace_dir=workspace_dir, **kwargs
    )


def _assert_team_409(err: OctopError) -> None:
    assert err.code is ErrorCode.TEAM_ARTIFACT_OWNERSHIP_DENIED
    assert err.status == 409


def _assert_builtin_403(err: OctopError) -> None:
    assert err.code is ErrorCode.FORBIDDEN
    assert err.status == 403
    assert "_builtin_skills" in str(err)


# --------------------------------------------------------------------------------------
# 格 1：三拼写（相对 / 主机绝对 / ``file://``）⇒ 409 TEAM_ARTIFACT_OWNERSHIP_DENIED
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", _SPELLING_KINDS)
def test_team_three_spellings_denied_409(tmp_path: Path, kind: str) -> None:
    path, from_workspace = _spelling(tmp_path, kind)
    err = _deny(path, workspace_dir=tmp_path, from_workspace=from_workspace)
    _assert_team_409(err)


@pytest.mark.parametrize("endpoint", sorted(_ENDPOINT_CALL_SHAPES))
def test_scope1_four_endpoints_deny_relative_spelling(tmp_path: Path, endpoint: str) -> None:
    """范围① 四端点各自的判定形态（相对拼写）⇒ 全部 409。"""
    kwargs = dict(_ENDPOINT_CALL_SHAPES[endpoint])
    err = _deny(TEAM_REL, workspace_dir=None, **kwargs)
    _assert_team_409(err)


@pytest.mark.parametrize("kind", _SPELLING_KINDS)
def test_team_spellings_denied_without_workspace_dir(tmp_path: Path, kind: str) -> None:
    """★ 范围① 四端点调用点**不传** ``workspace_dir`` ⇒ 三拼写仍须 409（段对与根无关）。"""
    path, from_workspace = _spelling(tmp_path, kind)
    err = _deny(path, workspace_dir=None, from_workspace=from_workspace)
    _assert_team_409(err)


# --------------------------------------------------------------------------------------
# 格 2：目录**本身**（不带尾段 / 带尾斜杠 / 冗余分隔符 + ``..`` 折叠）⇒ 409
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [".octop/team", ".octop/team/", "//.octop//team//", "x/../.octop/team", ".octop/team\\"],
)
def test_team_directory_itself_denied_409(tmp_path: Path, path: str) -> None:
    err = _deny(path, workspace_dir=tmp_path, from_workspace=True)
    _assert_team_409(err)


@pytest.mark.parametrize("suffix", ["", "/"])
def test_team_directory_host_absolute_and_file_url_denied_409(tmp_path: Path, suffix: str) -> None:
    abs_dir = (tmp_path / ".octop" / "team").as_posix() + suffix
    _assert_team_409(_deny(abs_dir, workspace_dir=tmp_path, from_workspace=False))
    _assert_team_409(_deny(f"file://{abs_dir}", workspace_dir=tmp_path, from_workspace=False))


# --------------------------------------------------------------------------------------
# 格 3：大小写折叠（唯一折点 = ASCII 大小写折叠，PLAN §2.2）⇒ 409
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        ".OCTOP/TEAM/x.md",
        ".Octop/Team/x.md",
        ".oCTOP/tEAM/LEARNINGS.md",
        ".OCTOP/Team",
        ".Octop/TEAM/",
    ],
)
def test_team_case_folded_denied_409(tmp_path: Path, path: str) -> None:
    err = _deny(path, workspace_dir=tmp_path, from_workspace=True)
    _assert_team_409(err)


@pytest.mark.parametrize("seg_pair", [(".Octop", "Team"), (".OCTOP", "TEAM")])
def test_team_case_folded_host_absolute_and_file_url_denied_409(
    tmp_path: Path, seg_pair: tuple[str, str]
) -> None:
    abs_target = (tmp_path / seg_pair[0] / seg_pair[1] / "x.md").as_posix()
    _assert_team_409(_deny(abs_target, workspace_dir=tmp_path, from_workspace=False))
    _assert_team_409(_deny(f"file://{abs_target}", workspace_dir=tmp_path, from_workspace=False))


# --------------------------------------------------------------------------------------
# 格 4：同一条入口上的两面对照 —— builtin 面仍 403 · 根分支 403
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["_builtin_skills/x.md", ".octop/_builtin_skills/x.md", "./_BUILTIN_SKILLS/x.md"],
)
def test_builtin_skills_face_still_403_on_same_entry(tmp_path: Path, path: str) -> None:
    _assert_builtin_403(_deny(path, workspace_dir=tmp_path, from_workspace=True))


@pytest.mark.parametrize("path", [".", "", "/", "./"])
def test_workspace_root_branch_still_403(tmp_path: Path, path: str) -> None:
    err = _deny(path, workspace_dir=tmp_path, from_workspace=True)
    assert err.code is ErrorCode.FORBIDDEN
    assert err.status == 403
    assert "workspace root" in str(err)


# --------------------------------------------------------------------------------------
# 格 5：正对照（必须放行）——相邻段对**精确**、非前缀、非「任一段相等」
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (".octop/sessions/x.json", ".octop/sessions/x.json"),
        (".octop/auth/token.json", ".octop/auth/token.json"),
        ("notes/.octop/team_backup/x.md", "notes/.octop/team_backup/x.md"),
        ("notes/_builtin_skills/x.md", "notes/_builtin_skills/x.md"),
        ("SOUL.md", "SOUL.md"),
    ],
)
def test_allowed_controls_relative(tmp_path: Path, path: str, expected: str) -> None:
    assert _allow(path, workspace_dir=tmp_path, from_workspace=True) == expected


@pytest.mark.parametrize("name", [".octop/sessions/x.json", ".octop/auth/token.json", "SOUL.md"])
def test_allowed_controls_host_absolute_and_file_url(tmp_path: Path, name: str) -> None:
    """主机绝对 / ``file://`` 形态经 ``workspace_dir`` 相对化后同样放行。"""
    abs_target = (tmp_path / name).as_posix()
    assert _allow(abs_target, workspace_dir=tmp_path, from_workspace=False) == abs_target
    assert (
        _allow(f"file://{abs_target}", workspace_dir=tmp_path, from_workspace=False) == abs_target
    )


def test_notes_prefixed_team_pair_is_denied_409_by_contract(tmp_path: Path) -> None:
    """★ 口径点（需 lead 确认）：``notes/.octop/team`` 并非工作区根的 ``.octop/team``。

    契约把判据定义为「**任意位置**相邻段对 ``(".octop", "team")``」（``PLAN.md`` §2.2 ·
    ``SPEC.md`` B17 · 源码 ``_team_memory_pair_hit``）。本例按**实测行为 + 契约依据**断言
    409：这是契约规定的行为，本轮**不改产品**；作为口径点上报 lead。
    """
    err = _deny("notes/.octop/team", workspace_dir=tmp_path, from_workspace=True)
    _assert_team_409(err)


# --------------------------------------------------------------------------------------
# 格 6：接入侧（调用点）—— 6 个端点都走唯一入口；``move`` 源与目标各判一次
# --------------------------------------------------------------------------------------

_SINGLE_ENTRY = "_assert_workspace_write_allowed"
_WRITE_ENDPOINTS = (
    "write_file",
    "upload_file",
    "mkdir_workspace_dir",
    "delete_workspace_file",
    "move_workspace_file",
    "write_doc",
)
_RETIRED_GUARDS = ("_assert_workspace_mutable", "_assert_team_memory_writable")


def _endpoint_funcs() -> dict[str, ast.AsyncFunctionDef]:
    source = Path(str(ws_router.__file__)).read_text(encoding="utf-8")
    return {
        node.name: node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AsyncFunctionDef) and node.name in _WRITE_ENDPOINTS
    }


def _entry_calls(func: ast.AsyncFunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(func)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == _SINGLE_ENTRY
    ]


def _kwargs(call: ast.Call) -> dict[str, str]:
    return {kw.arg: ast.unparse(kw.value) for kw in call.keywords if kw.arg is not None}


def test_call_sites_all_six_endpoints_go_through_single_entry() -> None:
    funcs = _endpoint_funcs()
    assert set(_WRITE_ENDPOINTS) <= set(funcs), (
        f"端点函数缺失: {set(_WRITE_ENDPOINTS) - set(funcs)}"
    )
    for name in _WRITE_ENDPOINTS:
        calls = _entry_calls(funcs[name])
        lines = [call.lineno for call in calls]
        assert calls, f"{name} 未调用唯一入口 {_SINGLE_ENTRY}（lines={lines}）"
        called = {
            node.func.id
            for node in ast.walk(funcs[name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not (called & set(_RETIRED_GUARDS)), f"{name} 仍调用旧守卫: {called}"


def test_call_sites_move_judges_source_and_destination() -> None:
    calls = _entry_calls(_endpoint_funcs()["move_workspace_file"])
    assert len(calls) == 2, f"move 必须源/目标各判一次，实测 {len(calls)} 次"
    assert [ast.unparse(call.args[0]) for call in calls] == ["path", "body.destination"]


def test_call_sites_kwarg_shapes_match_scope1_endpoints() -> None:
    """范围① 四端点 ``from_workspace=True`` 且不传 ``workspace_dir``；两写口传工作区根。"""
    funcs = _endpoint_funcs()
    for name, expected in _ENDPOINT_CALL_SHAPES.items():
        calls = _entry_calls(funcs[name])
        want = 2 if name == "move_workspace_file" else 1  # move: 源 + 目标
        assert len(calls) == want, f"{name}: 期望 {want} 次调用，实测 {len(calls)}"
        for call in calls:
            assert _kwargs(call) == {key: str(value) for key, value in expected.items()}
            assert "workspace_dir" not in _kwargs(call)
    for name in ("write_file", "upload_file"):
        assert "workspace_dir" in _kwargs(_entry_calls(funcs[name])[0])
