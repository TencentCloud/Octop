"""A1: the team-memory injection must actually be called, from a call site that passes it.

原断言（T-46 未落地时）：`build_host_memory_block(` 在 `manager.py` 里出现 **0 次**，
且没有任何 `_apply_team_host_config(..., host_workspace=…)` 调用点 —— 注入侧**在生产里没有调用者**。
T-46 落地后翻转为下面的三条（**翻转，不删除**：上面这段即原断言的记录）。

★ **为什么不数 `host_workspace=` 的出现次数**（lead 的措辞在此处被实测纠正）：正确实现下它是
**2 次** —— `@3375` 的调用点传参 + `@3460` 内层 `build_host_memory_block(host_workspace=…)`
的关键字同名 ⇒ **断"恰好 1 处"会假红**。判据必须绑到**调用点形态**，而不是关键字计数：
判据的字面范围必须与它想覆盖的范围重合。

★ 判别力（双向）用**运行时替换**证明（零写入）：见本卡报告的 mutation 记录 —— 删掉调用点传参
⇒ ② 红；恢复 ⇒ 绿。
"""

from __future__ import annotations

from pathlib import Path

MANAGER = Path(__file__).resolve().parents[3] / "src" / "octop" / "infra" / "agents" / "manager.py"

#: 调用点形态：唯一调用者把 harness 侧 workspace 传进去（生产必须传）。
CALL_SITE = "_apply_team_host_config(applied, row, host_workspace=harness_workspace)"


def _source() -> str:
    return MANAGER.read_text()


def test_the_injection_is_called_exactly_once() -> None:
    """① 函数体内调用恰 1 次（0 次 = 未接线；2 次 = 第二处口径）。"""
    count = _source().count("build_host_memory_block(")
    assert count == 1, f"manager.py 里 build_host_memory_block( 出现 {count} 次（应为 1）"


def test_the_single_call_site_passes_the_host_workspace() -> None:
    """② 调用点形态恰 1 次 —— 防"将来有人加了第二个调用者却忘了传"（那会让注入静默不发生）。"""
    count = _source().count(CALL_SITE)
    assert count == 1, f"manager.py 里调用点形态出现 {count} 次（应为 1）：{CALL_SITE}"


def test_the_wiring_helper_has_one_definition_and_one_call_site() -> None:
    """③ `_apply_team_host_config(` 恰 2 次 = 1 个 def + 1 个调用点（多出来的就是新调用者）。"""
    count = _source().count("_apply_team_host_config(")
    assert count == 2, f"_apply_team_host_config( 出现 {count} 次（应为 2 = 1 def + 1 调用点）"
