"""`PLAN.md` 门 + 显式 settle 的**读侧投影**补测（qa · T10 终验缺口）。

`tests/integration/test_team_plan_gate.py` 已经覆盖了门本身与 DB 行（`/tasks`）。
本文件只补它**没有**断言的那一面：`GET …/export/TASKS.json` 这条**只读投影**在
`:approve` / `:settle` 之后是否如实体现在产物里。

为什么这算缺口而不算重复：

* `run_service.py:1724` 明说 `:approve` **不写** `TASKS.json`（运行时独占投影），
  所以「投影未被写」不能靠 grep 文件绕过 —— 它必须由导出这一步物化后才可观测；
* 既有 `test_team_runs_api.py::test_export_returns_the_requested_projection` 只导
  一个**空 run**，从未验证草稿批准后的任务集是否出现在投影里（`d-1` 流到产物）；
* `test_team_runs_api.py` 里那句「`"authority": "db"` 尚未由 `export.py` 发出」的
  注释已经过期（`export.py:137` 现在正是发这个标记），这里顺手把它钉死。

复用姊妹模块的 `gate_env` fixture 与纯 helper，避免复制 240 行假件（`tests/` 是包，
跨模块导入 fixture 是 pytest 支持的用法）。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.integration import test_team_plan_gate as _plan_gate
from tests.integration.test_team_plan_gate import (
    _add_task,
    _create_run,
    _draft,
    _strand,
)

#: 姊妹模块的 fixture 挂到本模块命名空间（pytest 按**模块属性**注册 fixture）。
#: 直接 `from … import gate_env` 会与下面的测试形参同名 ⇒ ruff F811 会红；
#: 而 `request.getfixturevalue("gate_env")` 在 pytest-asyncio 下取不到这个 async fixture。
gate_env = _plan_gate.gate_env


async def _project_tasks_json(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str
) -> dict[str, Any]:
    """导出一次 `TASKS.json` 并解析出文档本体（`content` 是 JSON 文本）。"""
    resp = await client.get(f"/api/team/runs/{run_id}/export/TASKS.json", headers=auth)
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["name"] == "TASKS.json"
    return dict(json.loads(payload["content"]))


async def test_approve_materialises_the_board_projection_with_the_approved_draft(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`:approve` 后 `TASKS.json` 投影 = 草稿任务集（旧行被取代，`authority: db`）。"""
    client, auth, _outsider, team_id, _service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    superseded = await _add_task(client, auth, run_id, title="将被取代", owner="backend")

    before = await _project_tasks_json(client, auth, run_id)
    assert [row["id"] for row in before["tasks"]] == [superseded["id"]]

    staged = await client.post(
        f"/api/team/runs/{run_id}:plan", headers=auth, json={"draft": _draft("d-1")}
    )
    assert staged.status_code == 200, staged.text
    # 草稿只是候选：未批准前投影**不得**先动（否则门就是假的）。
    assert [row["id"] for row in (await _project_tasks_json(client, auth, run_id))["tasks"]] == [
        superseded["id"]
    ]

    approved = await client.post(f"/api/team/runs/{run_id}:approve", headers=auth)
    assert approved.status_code == 200, approved.text

    after = await _project_tasks_json(client, auth, run_id)
    assert after["authority"] == "db", "投影必须自带机器可读的来源标记"
    assert [row["id"] for row in after["tasks"]] == ["d-1"]
    draft_row = after["tasks"][0]
    assert draft_row["title"] == "草稿任务 d-1"
    # ⚠️ 投影对 `owner` 一律发空串（`_task_row` 取 `owner`/`role` 两个键，DB 行两个
    # 都没有）—— 见 TEST.md「发现」，本文件只把**观测到的事实**钉住，不假装它是
    # `backend`。
    assert draft_row["owner"] == "", "若哪天 owner 修好了，这条会红 —— 那是好消息"
    assert draft_row["attempt"] == 0
    assert draft_row["round"] == 1


async def test_settle_projection_shows_the_rearmed_row_back_at_todo(
    gate_env: tuple[httpx.AsyncClient, dict[str, str], dict[str, str], str, Any, Any],
) -> None:
    """`:settle` 后投影里的行回到**创建时那个 status token**，且 `attempt + 1`。"""
    client, auth, _outsider, team_id, service, _srv = gate_env
    run_id = await _create_run(client, auth, team_id)
    task = await _add_task(client, auth, run_id, title="重启后搁浅", owner="backend")

    fresh = (await _project_tasks_json(client, auth, run_id))["tasks"][0]
    assert fresh["attempt"] == 0

    _strand(service, str(task["id"]))
    stranded = (await _project_tasks_json(client, auth, run_id))["tasks"][0]
    assert stranded["status"] != fresh["status"], "搁浅必须在投影里看得见（否则补测无意义）"

    settled = await client.post(
        f"/api/team/runs/{run_id}:settle", headers=auth, json={"taskIds": [task["id"]]}
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["settled"] == [task["id"]]

    rearmed = (await _project_tasks_json(client, auth, run_id))["tasks"][0]
    assert rearmed["id"] == task["id"]
    assert rearmed["status"] == fresh["status"], "必须回到 todo（= 创建时那个 token）"
    assert rearmed["attempt"] == 2, "claim 0→1，settle 再 +1 ⇒ 2（真重试）"
