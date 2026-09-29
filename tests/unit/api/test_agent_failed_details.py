"""T-74 ①：``AGENT_FAILED``（500）必须让**只看 HTTP 响应的人**也能自诊。

背景（`qa` 在 T-67 冒烟 R8 实测）：派工 500 时客户端只拿到
``{"error":{"code":"AGENT_FAILED","message":"Agent 启动失败。","details":{}}}``
—— **看不出是哪个 agent、为什么**。

根因（本文件同时钉住）：``OctopError.to_envelope`` 在给了 locale 时用 i18n 文案
**整条替换** raise 点的 message（`errors.py @434-442` / `localized_message @409-414`），
所以 raise 点写进 message 的 ``agent_id`` **到不了客户端**；只有 ``details`` 会存活。
⇒ 修法是让事实走 ``details``（与 ``corrupt_config_error`` 同一形态）。

断言分三层，逐层收紧：
1. **HTTP**：状态码 + ``error.code`` + ``details`` 关键字段（卡里的三样断言）；
2. **本地化存活**：带 ``Accept-Language: zh`` 时 message 被换掉，而 ``details`` **仍在**
   —— 这条正是旧形态会红的地方；
3. **判据有牙**：一条**不带 details** 的同类错误，其信封里 ``details`` 确实是 ``{}``
   ⇒ 证明上面第 1 层的断言**不是恒真**。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from tests.support.app import ensure_control_plane_bound, write_octop_config

from octop.api.app import build_app
from octop.infra.agents.manager import AgentManager
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.server import OctopServer

AGENT = "AG-FAILED-1"


def _failed_agent_error(agent_id: str = AGENT) -> OctopError:
    """**生产的**抛出点：用真 ``AgentManager._unavailable_error`` 配一个失败的 row。

    不手搓 ``OctopError``，否则测的是"我能不能写 details"，而不是"生产会不会带"。
    """
    fake_self = SimpleNamespace(
        get_row=lambda _aid: SimpleNamespace(agent_id=agent_id, last_state="failed")
    )
    return AgentManager._unavailable_error(fake_self, agent_id)  # noqa: SLF001


def _running_agent_error(agent_id: str = AGENT) -> OctopError:
    """正对照：同一 helper、状态正常 ⇒ 不得报 ``AGENT_FAILED``。"""
    fake_self = SimpleNamespace(
        get_row=lambda _aid: SimpleNamespace(agent_id=agent_id, last_state="running")
    )
    return AgentManager._unavailable_error(fake_self, agent_id)  # noqa: SLF001


@pytest.fixture
async def client(tmp_path: Path):
    # 与 `test_exception_handlers.py` 同一形态：关掉 dashboard，免 SPA 通配抢先匹配。
    write_octop_config(tmp_path, enable_dashboard=False)
    srv = OctopServer(home=tmp_path)
    await srv.start()
    await ensure_control_plane_bound(srv)
    app = build_app(srv)

    # 放在 /api 之外，避免 JWT 中间件拦截（本用例只测信封，不测鉴权）。
    @app.get("/_test/agent-failed")
    async def _failed() -> None:
        raise _failed_agent_error()

    @app.get("/_test/agent-running")
    async def _running() -> None:
        raise _running_agent_error()

    @app.get("/_test/agent-failed-bare")
    async def _bare() -> None:
        # 旧形态（无 details）—— 用来证明"判据有牙"。
        raise OctopError(ErrorCode.AGENT_FAILED, f"agent {AGENT!r} failed to start")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c
    await srv.stop()


async def test_agent_failed_over_http_carries_the_agent_id(
    client: httpx.AsyncClient,
) -> None:
    """① 经 HTTP 三样断言：状态码 + ``error.code`` + ``details`` 关键字段。"""
    r = await client.get("/_test/agent-failed", headers={"Accept-Language": "zh"})

    assert r.status_code == 500
    body = r.json()["error"]
    assert body["code"] == "AGENT_FAILED"
    # ★ 可自诊的关键字段：哪个 agent、处于什么状态
    assert body["details"]["agent_id"] == AGENT
    assert body["details"]["last_state"] == "failed"


async def test_details_survive_localization_where_the_message_does_not(
    client: httpx.AsyncClient,
) -> None:
    """② message 被 i18n 换掉，而 ``details`` 仍在 —— 修好之前丢的就是这一段。"""
    r = await client.get("/_test/agent-failed", headers={"Accept-Language": "zh"})

    body = r.json()["error"]
    # 本地化确实生效（raise 点的英文 message 不再出现）
    assert body["message"] == "Agent 启动失败。"
    assert AGENT not in body["message"]
    # 但事实并没有随之丢失
    assert body["details"]["agent_id"] == AGENT


async def test_a_details_less_agent_failed_would_not_satisfy_the_assertion(
    client: httpx.AsyncClient,
) -> None:
    """③ 判据有牙：不带 details 的同类 500 ⇒ ``details`` 就是 ``{}``。

    这条不依赖改动后的代码路径，而是直接钉住"旧形态过不了第 ① 条断言"。
    """
    r = await client.get("/_test/agent-failed-bare", headers={"Accept-Language": "zh"})

    assert r.status_code == 500
    body = r.json()["error"]
    assert body["code"] == "AGENT_FAILED"
    assert body["details"] == {}  # ⇒ 第 ① 条的 details 断言在旧形态下必红


async def test_healthy_agent_is_not_reported_as_failed(client: httpx.AsyncClient) -> None:
    """正对照：同一 helper、状态正常 ⇒ 不误报 ``AGENT_FAILED``。"""
    r = await client.get("/_test/agent-running", headers={"Accept-Language": "zh"})

    assert r.json()["error"]["code"] != "AGENT_FAILED"
    assert r.json()["error"]["code"] == "AGENT_NOT_RUNNING"
