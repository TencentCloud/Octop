"""`T-71` 第三件 · **A2：KB 归档注入口的「接线存在且唯一」**（integration 层的正当主张）。

**三问**
* **关切面** = `kb_archiver_factory` 这个注入口在**生产装配**里是否存在、是否唯一；
* **一致性** = 与 `run_service.py:1485` 归档跳的守卫同口径（`if self._kb_archiver_factory is not None and kb_id and user is not None:`）——
  即：**注入口存在是那一跳能发生的前提**；
* **入口** = **生产装配源码**（`infra/server.py`）+ **`bind_runtime` 的签名**，不启动服务、不连库。

**第四问 · 前置自证**（本 run 新立）：这里被断言的是"接线"，它的"前置产物"就是**那一行装配本身** ⇒
自证 = 直接读回**那一行**并断言其参数形态（而不是断言"某个 mock 被调用"、也不是断言"某个下游字段非空"）。
三档表（同 `T-60`）：①只断言 stub 被调用 ❌ · ②只断言下游字段 ❌ · ③**经真实读口读回前置产物** ✅ —— 本文件用 ③（读的是生产源码这一"真实产物"）。

★ **本文件断言的是【装配事实】，其自证读回的是【生产源码本身】**（那一行 `bind_runtime(...)`）——**判据锚在生产源码上，不在任何 mock 上**。

★ **本文件不断言"归档真的发生了"** —— 那需要**已下载的嵌入模型**（`infra/knowledge/gate.py:71`
`model_downloaded = bool(selected_model and is_model_downloaded(selected_model))`，`:85` `usable = feature_enabled and prerequisites_ok`），
而测试环境没有 ⇒ **该断言属于 unit 层**（既有 `test_memory_kb_reference_bridge.py` 的假 settings 短路了能力门）。
★ **删除条件**：当测试环境提供嵌入模型、或 gate 出现可注入的 stub 点时，本文件可升格为"归档发生"的集成断言。
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "src" / "octop" / "infra" / "server.py"


def _server_src() -> str:
    return SERVER.read_text(encoding="utf-8")


def test_the_kb_archiver_factory_is_injected_exactly_once() -> None:
    """★ absence 绊线：`kb_archiver_factory=` 在 `bind_runtime(...)` 里**恰好 1 处**。

    多一处 ⇒ 有两个装配点（"唯一注入口"这个主张不成立）；
    零处 ⇒ T-45 的归档跳在生产上**永远是死代码**（`kb_document_id` 永不写入）——
    这正是 T-71 之前的状态，也正是本卡存在的原因。
    """
    src = _server_src()
    hits = re.findall(r"kb_archiver_factory\s*=", src)
    assert len(hits) == 1, (
        f"期望恰好 1 处 `kb_archiver_factory=`, 实得 {len(hits)} ⇒ "
        "要么注入口不唯一，要么它没被装配（后者会让归档跳在生产上成为死代码）"
    )


def test_the_injection_point_passes_the_server_own_factory() -> None:
    """装配形态：注入口拿的是 **server 自己的** `self._kb_archiver_factory`（不是别人给的、也不是 None）。"""
    src = _server_src()
    block = re.search(r"team_run_service\.bind_runtime\((.*?)\)", src, re.S)
    assert block is not None, "没找到 `team_run_service.bind_runtime(...)` 这一处装配"
    body = block.group(1)
    flat = "".join(body.split())
    assert "kb_archiver_factory=self._kb_archiver_factory" in flat, (
        f"装配体里没有 `kb_archiver_factory=self._kb_archiver_factory`，实得：{body[:300]}"
    )
    # 该工厂必须真的存在（不是占位符）
    assert "def _kb_archiver_factory(" in src, "`_kb_archiver_factory` 未定义"


def test_bind_runtime_accepts_the_archiver_factory() -> None:
    """签名面：`bind_runtime` **接受** `kb_archiver_factory`（否则装配那一行会 TypeError）。"""
    from octop.infra.agents.teams.run_service import TeamRunService

    params = inspect.signature(TeamRunService.bind_runtime).parameters
    assert "kb_archiver_factory" in params, (
        f"`bind_runtime` 不接受 kb_archiver_factory，实得参数：{sorted(params)}"
    )
