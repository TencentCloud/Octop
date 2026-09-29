"""T-60 · 14 条门的 **HTTP 层**可达性（补 `VERIFY-GATES.md §7` 的系统性盲区）。

## 为什么单独立一份
`VERIFY-GATES.md §7` 的原话：**15 条门的拒绝断言全部在"服务层"，只有 G6 触到了 HTTP 层。**
而 T-24 的 P1 证明：**服务层抛得对、序列化层崩** ⇒ **只测一层的绿不能外推到另一层。**
本文件把其余的门**推到真实 HTTP**（真 server + 真路由 + `to_envelope` 序列化）。

## 每条的判据（三样都要，缺一不可）
1. **HTTP 状态码** —— 只断言它不足以区分"哪条门"；
2. **`error.code`** —— 码才证明是哪条门；
3. **i18n 消息**（`Accept-Language: zh`）—— 证明它经**本地化**路径出来，而不是原样透传 message。
外加 **正对照**：同一路由在**不该触发该门**的输入下必须成功/给出**不同的码**
（否则"我构造的前提确实是原因"就没有证据）。

## ⚠️ 本文件的时效标注：**task-86 之前**
`task-86`（`details` 键与 `error_message` 形参 `code` 撞名）**尚未落地**（我实测仍抛）。
⇒ 本文件里 G6 那一条断言的是 **"今天会炸"**；**task-86 落地后必须把该用例翻转成"正常返回 409"**，
并重跑本文件（`SMOKE.md`/`VERIFY-GATES.md` 的同类标注一并更新）。
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from octop.infra.gateway.threads import ThreadRegistry
from tests.support.auth import create_agent

TEAM_MEMBERS = 2
FILLED_SPEC = (
    "# SPEC\n\n## 边界与禁止项\n\n| 边界 | 处置 |\n| --- | --- |\n| 不新增错误码 | 复用 |\n"
)
ZH = {"Accept-Language": "zh"}


class _FakeWorkspace:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        """Same shape as the harness — ``{"path", "is_dir"}``, never basenames (T-72)."""
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


class _RoomGateway:
    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo, thread_repo=services.thread_repo
        )


@pytest.fixture
async def run_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> tuple[httpx.AsyncClient, dict[str, str], str]:
    client, srv, auth = env
    members = [await create_agent(client, auth, name=f"m{i}") for i in range(TEAM_MEMBERS)]
    resp = await client.post(
        "/api/teams", headers=auth, json={"name": "HTTP Gates", "member_ids": members}
    )
    assert resp.status_code in (200, 201), resp.text
    team_id = str(resp.json()["agent_id"])

    workspace = _FakeWorkspace()
    workspace.write_text(
        ".octop/manifest.json",
        json.dumps(
            {
                "members": [
                    {"agent_id": team_id, "role": "lead"},
                    {"agent_id": members[0], "role": "backend"},
                    {"agent_id": members[1], "role": "qa"},
                ]
            }
        ),
    )
    service = srv.services.team_run_service()
    service.bind_runtime(
        gateway=_RoomGateway(srv.services),  # type: ignore[arg-type]
        workspace_for=lambda agent_id: workspace,
    )
    monkeypatch.setattr(type(srv.services), "team_run_service", lambda self: service)
    return client, auth, team_id, srv


async def _run(client: httpx.AsyncClient, auth: dict[str, str], team_id: str, **ov: Any) -> str:
    body = {"team_agent_id": team_id, "goal": "gates", "tier": "quick", **ov}
    r = await client.post("/api/team/runs", headers=auth, json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["run_id"])


async def _run_and_project(
    client: httpx.AsyncClient, auth: dict[str, str], team_id: str
) -> tuple[str, str]:
    body = {"team_agent_id": team_id, "goal": "gates", "tier": "quick"}
    r = await client.post("/api/team/runs", headers=auth, json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["run_id"]), str(r.json()["project_id"])


def _err(resp: httpx.Response) -> dict[str, Any]:
    return dict(resp.json()["error"])


# ─────────────────────────────────────────────────────────────────────────────
# G2 —— 非法阶段迁移
# ─────────────────────────────────────────────────────────────────────────────


async def test_g2_illegal_transition_over_http(run_env: tuple[Any, ...]) -> None:
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    r = await client.post(
        f"/api/team/runs/{run_id}:advance",
        headers={**auth, **ZH},
        json={"to_phase": "deliver"},
    )
    assert r.status_code == 409, r.text
    err = _err(r)
    assert err["code"] == "TEAM_RUN_PHASE_INVALID"
    assert err["message"] == "阶段迁移不合法。" or "阶段" in err["message"], err["message"]

    # 正对照：换成**合法**的那一跳，码必须不同（证明上面拒的是"这一跳非法"，不是别的门）
    ok = await client.post(
        f"/api/team/runs/{run_id}:advance",
        headers={**auth, **ZH},
        json={"to_phase": "implement"},
    )
    assert ok.status_code == 409
    assert _err(ok)["code"] == "TEAM_SPEC_BOUNDARY_EMPTY", "换成合法迁移应落到 G4，而不是 G2"


# ─────────────────────────────────────────────────────────────────────────────
# G4 —— 规格边界门（拒 + 填表后放行，走 HTTP）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g4_spec_boundary_over_http(run_env: tuple[Any, ...]) -> None:
    """G4（边界表）**并且**是 T-72 的端到端判据：写进去的工件必须被门看见。

    这条用例一直是"填表后放行"的证据，但过去它**在错误的形状上绿**：本文件的
    ``_FakeWorkspace.list_dir`` 返回 ``SimpleNamespace(name="SPEC.md")``（basename），
    而生产的 ``BackendWorkspace.list_dir`` 返回 ``{"path": <workspace-relative>, "is_dir"}``
    ⇒ ``present_artifacts`` 取不到名字 ⇒ 门报 ``missing=["SPEC.md"]`` ⇒ **写侧说写成了、门说没有**。
    替身改成与 harness 同形之后，这条用例才真的在验生产形状（T-72）。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    blocked = await client.post(
        f"/api/team/runs/{run_id}:advance",
        headers={**auth, **ZH},
        json={"to_phase": "implement"},
    )
    assert blocked.status_code == 409
    err = _err(blocked)
    assert err["code"] == "TEAM_SPEC_BOUNDARY_EMPTY"
    assert err["message"] == "规格的「边界与禁止项」为空，不得进入实现阶段。", err["message"]
    assert err["details"]["state"] == "missing"

    # 经 HTTP 把 SPEC.md 写成"边界表已填"
    put = await client.put(
        f"/api/team/runs/{run_id}/artifacts/SPEC.md",
        headers=auth,
        json={"content": FILLED_SPEC, "revision": "", "role": "pm"},
    )
    assert put.status_code == 200, put.text

    # 正对照：同一个请求现在必须放行
    ok = await client.post(
        f"/api/team/runs/{run_id}:advance", headers=auth, json={"to_phase": "implement"}
    )
    assert ok.status_code == 200, ok.text


# ─────────────────────────────────────────────────────────────────────────────
# G10 —— 档位取值（HTTP 400 + 正对照 201）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g10_unknown_tier_is_shadowed_by_the_http_schema(run_env: tuple[Any, ...]) -> None:
    """★ **发现：`TEAM_TIER_INVALID` 在 `POST /team/runs` 上不可达** —— 被 HTTP schema 抢先。

    服务层的 `normalize_tier` 承诺"认不出**不猜、不静默退回默认**"（G10），而
    `POST /team/runs` 的请求体把 `tier` 声明成
    `Literal["quick", "standard", "strict"] | None`（`team_runs.py` 的 `mode` 字段）
    ⇒ **任何别的取值在进服务层之前就被 Pydantic 判成 422**，`TEAM_TIER_INVALID` **永远返回不了**。

    ⇒ 这是"**服务层可达、HTTP 层不可达**"的干净实例（本卡要抓的那一类），
    且与 P1 **不同根因**：P1 是序列化层炸，这里是**门根本没被调用到**。
    **口径**：不是缺陷（422 对客户端同样明确），但**"G10 有 HTTP 面"这个假设不成立** ——
    该码的 HTTP 可达性**未证实**（是否有别的路由以**非 Literal** 的 tier 入参，我没查 ⇒ 沉默清单）。
    """
    client, auth, team_id, _srv = run_env

    bad = await client.post(
        "/api/team/runs",
        headers={**auth, **ZH},
        json={"team_agent_id": team_id, "goal": "g", "tier": "quickk"},
    )
    assert bad.status_code == 422, bad.text
    detail = bad.json()["detail"][0]
    assert detail["loc"] == ["body", "tier"]
    assert detail["type"] == "literal_error"
    assert "TEAM_TIER_INVALID" not in bad.text, "422 说明服务层的 G10 根本没被调到"

    # 正对照：合法档位 ⇒ 201（同一个端点、同一个字段）
    good = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "g", "tier": "quick"},
    )
    assert good.status_code == 201, good.text


# ─────────────────────────────────────────────────────────────────────────────
# G14 —— 工件归属 + 版本 CAS（两种拒绝必须可分辨）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g14_ownership_and_cas_over_http(run_env: tuple[Any, ...]) -> None:
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    created = await client.put(
        f"/api/team/runs/{run_id}/artifacts/SPEC.md",
        headers=auth,
        json={"content": "# v1", "revision": "", "role": "pm"},
    )
    assert created.status_code == 200, created.text
    revision = str(created.json()["revision"])

    denied = await client.put(
        f"/api/team/runs/{run_id}/artifacts/SPEC.md",
        headers={**auth, **ZH},
        json={"content": "# hijack", "revision": revision, "role": "backend"},
    )
    assert denied.status_code == 409, denied.text
    err = _err(denied)
    assert err["code"] == "TEAM_ARTIFACT_OWNERSHIP_DENIED"
    assert err["message"] == "你不是该工件的归属写者。", err["message"]

    # 同一条路由、**负责人**身份、但旧 revision ⇒ 必须是**另一个**码（CAS，不是归属）
    stale = await client.put(
        f"/api/team/runs/{run_id}/artifacts/SPEC.md",
        headers={**auth, **ZH},
        json={"content": "# v2", "revision": "deadbeefdeadbeef", "role": "pm"},
    )
    assert stale.status_code == 409, stale.text
    assert _err(stale)["code"] == "TEAM_ARTIFACT_STALE"
    assert _err(stale)["message"] == "工件已被他人修改，请重新加载后重试。"

    # 正对照：负责人 + 正确 revision ⇒ 200
    ok = await client.put(
        f"/api/team/runs/{run_id}/artifacts/SPEC.md",
        headers=auth,
        json={"content": "# v3", "revision": revision, "role": "pm"},
    )
    assert ok.status_code == 200, ok.text


# ─────────────────────────────────────────────────────────────────────────────
# G5 —— DAG 依赖门（HTTP 层：拒 + 上游 done 后放行）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g5_unmet_dependency_over_http(run_env: tuple[Any, ...]) -> None:
    client, auth, team_id, _srv = run_env
    run_id, project_id = await _run_and_project(client, auth, team_id)

    up = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "upstream", "owner": "backend"},
    )
    assert up.status_code == 201, up.text
    up_id = str(up.json()["id"])

    down = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "downstream", "owner": "backend", "dependsOn": [up_id]},
    )
    assert down.status_code == 201, down.text
    down_id = str(down.json()["id"])

    blocked = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{down_id}",
        headers={**auth, **ZH},
        json={"attemptId": "", "op": "claim"},
    )
    assert blocked.status_code == 409, blocked.text
    err = _err(blocked)
    assert err["code"] == "TEAM_TASK_DEPS_UNMET"
    assert err["details"]["unmet"] == [up_id]
    assert err["message"] == "上游任务尚未完成。", err["message"]

    # 正对照：把上游经**合法迁移**推到 done（todo → doing → review → done）
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{up_id}",
        headers=auth,
        json={"attemptId": "", "op": "claim"},
    )
    assert claimed.status_code == 200, claimed.text
    # ⚠️ 状态迁移**不在 team-runs 路由上**：它的 `op` 枚举只有
    # claim|start|report|complete|fail|rework（我实测 `op="status"` ⇒ 422）。
    # 状态机走**项目**路由：`PATCH /api/projects/{project_id}/tasks/{task_id}`。
    # 且必须**逐格走**：`_TASK_TRANSITIONS` 里 todo → {doing,…}，跳过 doing 直接到 review
    # 会被拒（我实测拿到 409 PROJECT_TASK_STATUS_INVALID）。
    # 另注：team-runs 的 `op:"claim"` 只做 CAS 认领，**不动 status** —— status 归状态机。
    for target in ("doing", "review", "done"):
        step = await client.patch(
            f"/api/projects/{project_id}/tasks/{up_id}",
            headers=auth,
            json={"status": target},
        )
        assert step.status_code == 200, (target, step.text)

    unlocked = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{down_id}",
        headers=auth,
        json={"attemptId": "", "op": "claim"},
    )
    assert unlocked.status_code == 200, unlocked.text


# ─────────────────────────────────────────────────────────────────────────────
# G6 —— 图结构门：**今天在 HTTP 层炸**（P1；task-86 之前）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g6_graph_refusal_over_http(run_env: tuple[Any, ...]) -> None:
    """**T-65 落地后的翻转**（旧名：`test_g6_graph_refusal_over_http_is_broken_before_task_86`）。

    旧用例断言的是"**修前的坏状态**"（序列化层 `TypeError` ⇒ 客户端拿不到 409）。
    T-65 已落地 ⇒ 现在断言**修好的状态**，三样齐备（T-60 建立的形态）：
    **HTTP 状态 + `error.code` + zh 消息**；并配**正对照**（不构成图拒绝的请求仍 201）。

    另：`backend` 在 `tests/integration/test_team_runs_api.py` 的参数化用例里覆盖了同样的面
    （四样：409 + 码 + `details["code"]` 具体理由 + zh 消息含"任务依赖图"）。
    ★ 而**独立复核**发现它那句"the board has no endpoint that rewrites `dependsOn`"**不属实** ——
    见同文件 `test_g6_is_bypassable_through_the_projects_task_patch`。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    bad = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers={**auth, **ZH},
        json={"title": "ghost-dep", "owner": "backend", "dependsOn": ["no-such-task"]},
    )
    assert bad.status_code == 409, bad.text
    err = _err(bad)
    assert err["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert err["details"]["code"] == "missing-id"
    assert "任务依赖图" in err["message"], err["message"]

    # 正对照：同一个端点、**不构成图拒绝**的输入 ⇒ 201（证明不是"一律 409"）
    ok = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "fine", "owner": "backend"},
    )
    assert ok.status_code == 201, ok.text


# ─────────────────────────────────────────────────────────────────────────────
# 序列化路径的两条"同类风险"实证（lead 点名）
# ─────────────────────────────────────────────────────────────────────────────


def test_every_error_code_has_a_status_mapping() -> None:
    """`_DEFAULT_STATUS` **每码都有映射** —— 否则某码在 HTTP 面没有状态可映射（新缺陷）。"""
    from octop.infra.errors import _DEFAULT_STATUS, ErrorCode

    missing = [c.name for c in ErrorCode if c not in _DEFAULT_STATUS]
    assert missing == [], f"这些码没有 HTTP 状态映射：{missing}"
    assert len(_DEFAULT_STATUS) == len(list(ErrorCode))
    assert all(isinstance(v, int) and 400 <= v <= 599 for v in _DEFAULT_STATUS.values())


def test_only_one_details_site_can_collide_with_the_signature() -> None:
    """**把 P1 扫成一类**：`details` 里凡是键与 `error_message(code, locale, **kw)` 形参同名的都会撞。

    结论（源码级扫描，`src/` 全量）：
    * 字面量 `details={...}` 站点里，**只有 1 处**用了撞名键 ——
      `pipeline.py` 里 G6 四条码那个 `"code"` **⇒ 这就是 P1 的全部爆炸半径**；
    * **没有任何站点用 `locale`**（lead 点名的同族风险，实测为空）；
    * 非字面量站点里唯一与门禁相关的是 `pipeline.py` 的 `as_details()`（G16），
      它产出 `{title, rounds, raw_titles, decision}` ⇒ **不撞名**。
    ⇒ 所以"其余 14 条门会被这个根因波及"**不成立**；受影响的只有 **G6**。

    **不绑定行号**：断言唯一撞名站点 = `pipeline.py` 的 `code` 键 —— 对形如
    `"<file>:<line>:<key>"` 的串按 `:` 切分后比 `file` 与 `key`，**不比 `line`**；
    行号随实现漂移不构成回归（「恰好 1 处 + 文件 + 键」三约束一个都没放宽）。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "src"
    literal = re.compile(r"details\s*=\s*\{([^}]*)\}", re.S)
    collisions: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in literal.finditer(text):
            for key in re.findall(r"[\"'](\w+)[\"']\s*:", m.group(1)):
                if key in ("code", "locale"):
                    collisions.append(f"{path.name}:{text[: m.start()].count(chr(10)) + 1}:{key}")

    # 约束一：**恰好 1 处**撞名站点（不放宽成 "≤1" / "包含"）
    assert len(collisions) == 1, f"撞名站点不是恰好 1 处：{collisions}"
    # 约束二/三：只比 `<file>` 与 `<key>`，**不比 `<line>`**（行号随实现漂移不构成回归）
    sites = []
    for entry in collisions:
        parts = entry.rsplit(":", 2)
        sites.append((parts[0], parts[2]))
    assert sites == [("pipeline.py", "code")], (
        f"唯一撞名站点变了（应为 pipeline.py 的 code 键）：{collisions}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-60 余量：把 5 条"廉价可构造"的门也推到 HTTP 层（lead 授权我挑便宜的）
# ─────────────────────────────────────────────────────────────────────────────


async def test_g9_member_limit_over_http(run_env: tuple[Any, ...]) -> None:
    """G9：`RunCreateBody.roles` 显式给出**超该档 roleCap** 的编制 ⇒ 409。

    正对照：同一端点、同档位、**不超**的编制 ⇒ 201。
    """
    client, auth, team_id, _srv = run_env
    over = await client.post(
        "/api/team/runs",
        headers={**auth, **ZH},
        json={
            "team_agent_id": team_id,
            "goal": "g",
            "tier": "quick",
            "roles": ["backend", "qa", "docs", "sec"],  # quick 的 roleCap 是 3
        },
    )
    assert over.status_code == 409, over.text
    err = _err(over)
    assert err["code"] == "TEAM_RUN_MEMBER_LIMIT"
    assert err["message"] == "本次运行的成员数已达上限。", err["message"]

    ok = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "g", "tier": "quick", "roles": ["backend", "qa"]},
    )
    assert ok.status_code == 201, ok.text


async def test_g7_rework_round_limit_over_http(run_env: tuple[Any, ...]) -> None:
    """G7：`round` 超过 `max_review_rounds` 且无升级决策 ⇒ 409（写侧守卫）。

    正对照：`round=1` 的同类质量任务 ⇒ 201。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    over = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers={**auth, **ZH},
        json={"title": "round4", "owner": "qa", "kind": "quality", "round": 4},
    )
    assert over.status_code == 409, over.text
    assert _err(over)["code"] == "TEAM_REWORK_LOOP_LIMIT"

    ok = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "round1", "owner": "qa", "kind": "quality", "round": 1},
    )
    assert ok.status_code == 201, ok.text


async def test_g8_stale_attempt_over_http(run_env: tuple[Any, ...]) -> None:
    """G8：用**不是当前**的 attemptId 回报 ⇒ 409；用当前那个 ⇒ 200。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    task = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "be", "owner": "backend"},
    )
    tid = str(task.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={"attemptId": "", "op": "claim"},
    )
    assert claimed.status_code == 200, claimed.text
    live = str(claimed.json().get("attemptId") or claimed.json().get("attempt_id") or "")

    stale = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers={**auth, **ZH},
        json={"attemptId": "att-from-last-round", "op": "report", "verdict": "pass"},
    )
    assert stale.status_code == 409, stale.text
    assert _err(stale)["code"] == "TEAM_ATTEMPT_STALE"

    ok = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={"attemptId": live, "op": "report", "verdict": "pass"},
    )
    assert ok.status_code == 200, ok.text


async def test_g11_scope_violation_over_http(run_env: tuple[Any, ...]) -> None:
    """G11：`changedPaths` 落在 `inScope` 之外 ⇒ 409；落在之内 ⇒ 200。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    task = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "qa-task", "owner": "qa", "inScope": ["tests/**"]},
    )
    tid = str(task.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={"attemptId": "", "op": "claim"},
    )
    live = str(claimed.json().get("attemptId") or claimed.json().get("attempt_id") or "")

    outside = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers={**auth, **ZH},
        json={
            "attemptId": live,
            "op": "complete",
            "changedPaths": ["src/octop/secret.py"],
        },
    )
    assert outside.status_code == 409, outside.text
    assert _err(outside)["code"] == "TEAM_SCOPE_VIOLATION"
    assert _err(outside)["message"] == "变更文件超出任务范围。"

    inside = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={"attemptId": live, "op": "complete", "changedPaths": ["tests/unit/db/test_x.py"]},
    )
    assert inside.status_code == 200, inside.text


async def test_g12_requires_findings_over_http(run_env: tuple[Any, ...]) -> None:
    """★ **已翻转**（原 `test_g12_and_g13_are_unreachable_because_no_route_calls_verdict`，T-68/task-102）。

    `op:"report"` **带 `verdict`** 时经 `verdict()` 落地 ⇒ G12 在 HTTP 面上真的生效：
    `needs_revision` 不带 findings ⇒ **409 + `TEAM_VERDICT_FINDINGS_REQUIRED` + zh 消息**。
    （翻转前这里断言 200 且 `verdict` 被记下 —— 那时路由调的是 `report()`，绕过了门。）
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    tid, live = await _review_task(client, auth, run_id)

    resp = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers={**auth, **ZH},
        json={"attemptId": live, "op": "report", "verdict": "needs_revision", "findings": []},
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TEAM_VERDICT_FINDINGS_REQUIRED"
    # 三样都断言：状态码 + code + **本地化消息**（zh 由 Accept-Language 决定）
    assert resp.json()["error"]["message"] == "非通过裁决必须至少带一条问题记录。"


async def test_g13_refuses_a_self_audit_pass_over_http(run_env: tuple[Any, ...]) -> None:
    """★ **已翻转**（同上那条绊线的另一半，T-68/task-102）。

    同一个角色先认领实现、又认领审阅 ⇒ 它对 `pass` 的自审被 **G13** 挡下：
    **409 + `TEAM_REVIEW_SELF_AUDIT` + zh 消息**。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    work = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "实现", "owner": "backend"},
    )
    work_id = str(work.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{work_id}",
        headers=auth,
        json={"attemptId": "", "op": "claim", "role": "backend"},
    )
    assert claimed.status_code == 200, claimed.text
    tid, live = await _review_task(client, auth, run_id, role="backend")

    resp = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers={**auth, **ZH},
        json={
            "attemptId": live,
            "op": "report",
            "role": "backend",
            "verdict": "pass",
            "findings": [{"severity": "low", "title": "自审放行尝试"}],
        },
    )

    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["code"] == "TEAM_REVIEW_SELF_AUDIT"
    assert resp.json()["error"]["message"] == "审查者不得审查自己的产出。"


# ─────────────────────────────────────────────────────────────────────────────
# T-68/task-102 落地：判词只经一条路（G12/G13 生效 · findings 真的落库 · 正对照）
# ─────────────────────────────────────────────────────────────────────────────


async def _review_task(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    run_id: str,
    *,
    role: str = "reviewer",
) -> tuple[str, str]:
    """一个已认领的 review 任务 ⇒ ``(task_id, live attempt)``。"""
    review = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "审", "owner": role, "kind": "review"},
    )
    assert review.status_code in (200, 201), review.text
    tid = str(review.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={"attemptId": "", "op": "claim", "role": role},
    )
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    live = str(body.get("attemptId") or body.get("attempt_id") or "")
    return tid, live


async def test_findings_reach_the_service_and_are_persisted_over_http(
    run_env: tuple[Any, ...],
) -> None:
    """★ **已翻转**（原 `test_findings_cannot_be_created_over_http_at_all`，T-68/task-102）。

    这是"两个面都闭"的直接证据：`op:"report"` 的 `findings` 过去被**静默丢弃**
    （`report()` 没有这个形参）⇒ 现在经 `verdict()` **真的落库**，字段逐项对齐
    ⇒ **G16 的前提（两轮同标题 finding）在 HTTP 面上可建立**（T-24 那族第三次收口）。
    """
    client, auth, team_id, srv = run_env
    run_id = await _run(client, auth, team_id)
    tid, live = await _review_task(client, auth, run_id)

    before = len(srv.services.task_finding_repo.list_by_run(run_id))
    assert before == 0, "前置：这个 run 还不该有 finding"

    resp = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={
            "attemptId": live,
            "op": "report",
            "verdict": "needs_revision",
            "findings": [
                {"severity": "high", "title": "FIND-24", "detail": "d", "round": None},
            ],
        },
    )

    assert resp.status_code == 200, resp.text
    stored = srv.services.task_finding_repo.list_by_run(run_id)
    assert len(stored) == 1, f"finding 没落库：{before} -> {len(stored)}"
    assert stored[0].title == "FIND-24"
    assert stored[0].severity == "high"
    assert stored[0].detail == "d"
    assert stored[0].verdict == "needs_revision"
    assert stored[0].task_id == tid


async def test_positive_controls_still_pass_over_http(run_env: tuple[Any, ...]) -> None:
    """正对照：**合法判词不得因为新校验变红**（非自审 + 带 findings ⇒ 200）。"""
    client, auth, team_id, srv = run_env
    run_id = await _run(client, auth, team_id)
    tid, live = await _review_task(client, auth, run_id)

    resp = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{tid}",
        headers=auth,
        json={
            "attemptId": live,
            "op": "report",
            "role": "reviewer",
            "verdict": "needs_revision",
            "findings": [{"severity": "medium", "title": "FIND-1", "detail": "缺少回归"}],
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["verdict"] == "needs_revision"
    # `pass` 也放行（同一个 review 任务上，只要不是自审）—— 用独立审查者。
    other = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "复审", "owner": "reviewer", "kind": "review"},
    )
    other_id = str(other.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{other_id}",
        headers=auth,
        json={"attemptId": "", "op": "claim", "role": "reviewer"},
    )
    live2 = str(claimed.json().get("attemptId") or claimed.json().get("attempt_id") or "")
    passed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{other_id}",
        headers=auth,
        json={"attemptId": live2, "op": "report", "verdict": "pass", "findings": []},
    )
    assert passed.status_code == 200, passed.text
    assert len(srv.services.task_finding_repo.list_by_run(run_id)) == 1  # 只第一条落了 finding


async def test_report_without_a_verdict_is_unchanged_over_http(run_env: tuple[Any, ...]) -> None:
    """★ 边界：**不带 verdict 的 report 仍然 200**（进度报告不是判词，两道门都不适用）。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    work = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers=auth,
        json={"title": "实现", "owner": "backend"},
    )
    work_id = str(work.json()["id"])
    claimed = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{work_id}",
        headers=auth,
        json={"attemptId": "", "op": "claim", "role": "backend"},
    )
    live = str(claimed.json().get("attemptId") or claimed.json().get("attempt_id") or "")

    resp = await client.patch(
        f"/api/team/runs/{run_id}/tasks/{work_id}",
        headers=auth,
        json={"attemptId": live, "op": "report", "changedPaths": []},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json().get("verdict") in (None, "")


def test_verdict_has_exactly_the_route_as_its_caller() -> None:
    """★ **已翻转**（原 `test_verdict_has_no_caller_in_production_source`，T-68/task-102）。

    它原来是"零引用"守卫（`verdict()` 无调用者 ⇒ 两道门不可达）。翻转后它守**反方向**：
    `verdict()` **必须有且只有一个生产调用者** —— 就是任务更新的路由。
    两侧都会红：**再没人调**（门又不可达）或**多出第二个调用者**（多了一条判词入口）。
    """
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[2] / "src"
    callers: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"\.verdict\s*\(", text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : text.find("\n", m.start())]
            if "def verdict" in line:
                continue  # the definition itself
            callers.append(f"{path.name}:{text[: m.start()].count(chr(10)) + 1}")

    assert [c.split(":")[0] for c in callers] == ["team_runs.py"], (
        f"`verdict()` 的生产调用者应当是任务路由（唯一入口），实得 {callers}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T-60 余量（更正）：最后那条不是"不便宜"，而是**与 G12/G13 同根因的不可达**
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# ★★ 独立复核 lead 转述的那句 `cycle` 留白 —— **它不属实，而且后果比"可达"更重**
# ─────────────────────────────────────────────────────────────────────────────


async def test_g6_is_enforced_on_the_projects_task_patch(run_env: tuple[Any, ...]) -> None:
    """★ **已翻转**（原 `test_g6_is_bypassable_through_the_projects_task_patch`，T-70/task-104）。

    原文保留（便于追溯）：`backend` 在 `test_team_runs_api.py` 的参数化用例里**故意不含
    `cycle`**，理由是 "**the board has no endpoint that rewrites `dependsOn`**" —— **那句不属实**：
    `api/routers/projects.py · TaskPatch` 有 `deps`，`patch_task` 把它经
    `model_dump(exclude_unset=True)` 原样交给 `ProjectService.update_task`，而后者当时**不过 G6**
    ⇒ **同一张任务图有两条写入口，只有一条过门**（`validate_task_graph` 当时全仓只有一个调用点）。

    **现在**：合法 `deps` 更新 ⇒ 200；反向写环 ⇒ **409 + `TEAM_TASK_GRAPH_INVALID`（`details.code == "cycle"`）
    + zh 消息**；且**板未被改写**（拒绝发生在 repo 写入之前）。
    """
    client, auth, team_id, _srv = run_env
    run_id, project_id = await _run_and_project(client, auth, team_id)

    a = await client.post(
        f"/api/team/runs/{run_id}/tasks", headers=auth, json={"title": "A", "owner": "backend"}
    )
    b = await client.post(
        f"/api/team/runs/{run_id}/tasks", headers=auth, json={"title": "B", "owner": "backend"}
    )
    aid, bid = str(a.json()["id"]), str(b.json()["id"])

    # 正对照：B 依赖 A 是合法的 ⇒ 200（证明这一跳不是"一律拒"）
    first = await client.patch(
        f"/api/projects/{project_id}/tasks/{bid}", headers=auth, json={"deps": [aid]}
    )
    assert first.status_code == 200, first.text
    assert [str(d) for d in first.json().get("deps", [])] == [aid], first.text

    # 环：A 依赖 B ⇒ A→B→A
    second = await client.patch(
        f"/api/projects/{project_id}/tasks/{aid}",
        headers={**auth, **ZH},
        json={"deps": [bid]},
    )

    assert second.status_code == 409, second.text
    err = _err(second)
    assert err["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert err["details"]["code"] == "cycle", err
    assert "任务依赖图" in err["message"], err["message"]

    # 被拒 ⇒ **板没被改写**（A 的 deps 仍为空；B 仍依赖 A）
    board = await client.get(f"/api/projects/{project_id}/tasks", headers=auth)
    assert board.status_code == 200, board.text
    by_id = {str(t["task_id"]): t for t in board.json()}
    assert [str(d) for d in by_id[aid].get("deps", [])] == [], "被拒的写入不得落盘"
    assert [str(d) for d in by_id[bid].get("deps", [])] == [aid]


async def test_the_other_g6_invariants_are_enforced_on_the_projects_route(
    run_env: tuple[Any, ...],
) -> None:
    """同一道门守的**不止 `cycle`**：`missing-id` 与 `self-dependency` 也必须在项目路由上被拒。

    （这条是"扫一类"的证据：如果只补了环检测，这两个会漏过去 —— 而它们与 `cycle` 是同一道
    `validate_task_graph` 的四条不变式。）
    """
    client, auth, team_id, _srv = run_env
    run_id, project_id = await _run_and_project(client, auth, team_id)
    task = await client.post(
        f"/api/team/runs/{run_id}/tasks", headers=auth, json={"title": "A", "owner": "backend"}
    )
    aid = str(task.json()["id"])

    missing = await client.patch(
        f"/api/projects/{project_id}/tasks/{aid}",
        headers={**auth, **ZH},
        json={"deps": ["no-such-task"]},
    )
    assert missing.status_code == 409, missing.text
    assert _err(missing)["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert _err(missing)["details"]["code"] == "missing-id"
    assert "任务依赖图" in _err(missing)["message"]

    self_dep = await client.patch(
        f"/api/projects/{project_id}/tasks/{aid}",
        headers={**auth, **ZH},
        json={"deps": [aid]},
    )
    assert self_dep.status_code == 409, self_dep.text
    assert _err(self_dep)["details"]["code"] == "self-dependency"


async def test_both_entries_refuse_the_same_broken_graph_with_the_same_code(
    run_env: tuple[Any, ...],
) -> None:
    """★ **本卡的核心判据：门守两条入口，不是守一条。**

    同一个坏图（依赖一个不存在的 id）分别经**团队路由**与**项目路由**提交 ⇒
    **两条入口必须给出同一个码与同一个 `details.code`**（因为它们是**同一道**
    `pipeline.validate_task_graph`，板也同源：`TeamRunService.list_tasks(run_id)`
    就是 `list_by_project(run.project_id)`）。
    """
    client, auth, team_id, _srv = run_env
    run_id, project_id = await _run_and_project(client, auth, team_id)

    # 入口甲：团队路由（建任务时校验）
    via_team = await client.post(
        f"/api/team/runs/{run_id}/tasks",
        headers={**auth, **ZH},
        json={"title": "ghost-dep", "owner": "backend", "dependsOn": ["no-such-task"]},
    )
    # 入口乙：项目路由（更新 deps 时校验）
    task = await client.post(
        f"/api/team/runs/{run_id}/tasks", headers=auth, json={"title": "A", "owner": "backend"}
    )
    via_project = await client.patch(
        f"/api/projects/{project_id}/tasks/{str(task.json()['id'])}",
        headers={**auth, **ZH},
        json={"deps": ["no-such-task"]},
    )

    for label, resp in (("团队路由", via_team), ("项目路由", via_project)):
        assert resp.status_code == 409, f"{label}: {resp.text}"
        err = _err(resp)
        assert err["code"] == "TEAM_TASK_GRAPH_INVALID", label
        assert err["details"]["code"] == "missing-id", label
        assert "任务依赖图" in err["message"], label


# T-69 —— `role` 未认出 ⇒ **不得 fail-open**（PLAN 裁定 (a)：拒覆写、放创建）
#
# HTTP 面的 `role` 是**调用方声明**（AM-31：它不是鉴权凭据）⇒ 认不出它 **不是**"没有权限"，
# 也**不是**"没有属主、随便写" —— 它是**一个未经验证的主张**。裁定 (a)：目标工件**存在**时
# 拒绝（`400 TEAM_ROLE_UNKNOWN`），**创建照旧放行**（首个成员要一次性落 13 份骨架）。
# ─────────────────────────────────────────────────────────────────────────────


async def _put_artifact(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    run_id: str,
    *,
    name: str,
    role: str,
    content: str = "# v1",
    revision: str = "",
) -> httpx.Response:
    return await client.put(
        f"/api/team/runs/{run_id}/artifacts/{name}",
        headers={**auth, **ZH},
        json={"content": content, "revision": revision, "role": role},
    )


async def test_unknown_role_cannot_overwrite_an_existing_artifact(
    run_env: tuple[Any, ...],
) -> None:
    """① 未认出的 `role` + 工件**存在** ⇒ **400 + `TEAM_ROLE_UNKNOWN` + zh 消息**。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    created = await _put_artifact(client, auth, run_id, name="SPEC.md", role="pm")
    assert created.status_code == 200, created.text
    revision = str(created.json()["revision"])

    resp = await _put_artifact(
        client,
        auth,
        run_id,
        name="SPEC.md",
        role="ghost",
        content="# hijack",
        revision=revision,
    )

    assert resp.status_code == 400, resp.text
    assert _err(resp)["code"] == "TEAM_ROLE_UNKNOWN"
    assert _err(resp)["message"] == "该角色不在固定角色表内。"
    # 拒绝了就必须**没写成**（裁定要求"拒覆写"，不是"写完之后报错"）
    after = await _put_artifact(
        client, auth, run_id, name="SPEC.md", role="pm", content="# v2", revision=revision
    )
    assert after.status_code == 200, after.text


async def test_unknown_role_is_refused_before_the_revision_check(
    run_env: tuple[Any, ...],
) -> None:
    """★ 顺序：未认出角色 + **过期 revision** ⇒ 仍是 `400`（不是 `TEAM_ARTIFACT_STALE`）。

    门必须**先**于 CAS —— 否则调用方能从两个不同错误码里推断"我这一版 revision 对不对"。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    await _put_artifact(client, auth, run_id, name="SPEC.md", role="pm")

    resp = await _put_artifact(
        client, auth, run_id, name="SPEC.md", role="ghost", revision="deadbeefdeadbeef"
    )

    assert resp.status_code == 400, resp.text
    assert _err(resp)["code"] == "TEAM_ROLE_UNKNOWN"


async def test_recognised_non_owner_is_still_409(run_env: tuple[Any, ...]) -> None:
    """② 正对照：**已认出但不是 owner** ⇒ 仍是 `409`（证明 ① 没把这条吃掉）。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    created = await _put_artifact(client, auth, run_id, name="SPEC.md", role="pm")
    revision = str(created.json()["revision"])

    resp = await _put_artifact(
        client,
        auth,
        run_id,
        name="SPEC.md",
        role="backend",
        content="# hijack",
        revision=revision,
    )

    assert resp.status_code == 409, resp.text
    assert _err(resp)["code"] == "TEAM_ARTIFACT_OWNERSHIP_DENIED"
    assert _err(resp)["message"] == "你不是该工件的归属写者。"


async def test_legal_owner_still_passes(run_env: tuple[Any, ...]) -> None:
    """③ 正对照：合法 owner ⇒ 通过（新校验不得误伤）。"""
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)
    created = await _put_artifact(client, auth, run_id, name="SPEC.md", role="pm")
    revision = str(created.json()["revision"])

    resp = await _put_artifact(
        client, auth, run_id, name="SPEC.md", role="pm", content="# v2", revision=revision
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["revision"] != revision


async def test_unknown_role_may_still_create_a_new_artifact(
    run_env: tuple[Any, ...],
) -> None:
    """④ ★ 边界（**按裁定，不顺手改成一律拒**）：未认出角色 + 工件**不存在** ⇒ 放行。

    理由（裁定原文）：建 run 时首个成员要一次性落 13 份骨架，其中大多数不属于它 ⇒
    "角色 ≠ 负责人就拦"会**直接打死建 run**。⇒ 判据恒为"**已存在**且写者不是负责人"。
    """
    client, auth, team_id, _srv = run_env
    run_id = await _run(client, auth, team_id)

    resp = await _put_artifact(
        client, auth, run_id, name="NOTES-T69.md", role="ghost", content="# new file"
    )

    assert resp.status_code == 200, resp.text


async def test_the_projects_create_verb_also_runs_g6(run_env: tuple[Any, ...]) -> None:
    """★ T-70 ④：项目路由的 **create** 支也过 G6（第三个写入口）。

    实测缺口（修前）：`POST /api/projects/{pid}/tasks {"deps": ["no-such-task"]}` ⇒ **201**
    且悬空依赖被原样落盘 ⇒ 与 PATCH 同族。现在：**409 + 码 + `details.code` + zh**，
    并且 **`create_task` 那句"拒绝的请求不留半成品"要有读数** —— 拒绝后按标题查板 ⇒ **行不存在**。
    """
    client, auth, team_id, _srv = run_env
    _run_id, project_id = await _run_and_project(client, auth, team_id)

    resp = await client.post(
        f"/api/projects/{project_id}/tasks",
        headers={**auth, **ZH},
        json={"title": "ghost-create", "deps": ["no-such-task"]},
    )

    assert resp.status_code == 409, resp.text
    err = _err(resp)
    assert err["code"] == "TEAM_TASK_GRAPH_INVALID"
    assert err["details"]["code"] == "missing-id", err
    assert "任务依赖图" in err["message"], err["message"]

    # ★ "拒绝"与"没写"是两件事：按标题查一次板 ⇒ 不许留下半成品行
    board = await client.get(f"/api/projects/{project_id}/tasks", headers=auth)
    assert board.status_code == 200, board.text
    titles = [str(row.get("title") or "") for row in board.json()]
    assert "ghost-create" not in titles, f"被拒的 create 留下了半成品行：{titles}"


async def test_the_projects_create_verb_still_accepts_a_legal_graph(
    run_env: tuple[Any, ...],
) -> None:
    """正对照：**合法的 deps 的 create ⇒ 201**（证明 ④ 不是"一律拒"）。"""
    client, auth, team_id, _srv = run_env
    _run_id, project_id = await _run_and_project(client, auth, team_id)

    first = await client.post(
        f"/api/projects/{project_id}/tasks", headers=auth, json={"title": "A"}
    )
    assert first.status_code == 201, first.text
    aid = str(first.json()["task_id"])

    second = await client.post(
        f"/api/projects/{project_id}/tasks", headers=auth, json={"title": "B", "deps": [aid]}
    )

    assert second.status_code == 201, second.text
    assert [str(d) for d in second.json()["deps"]] == [aid]

    # 另一条不变式经 create 也可达：**悬空依赖**（`missing-id`）—— 已在上面那条用例断言。
    # 注：`self-dependency` 经 create **不可达**（id 由仓储分配，调用方无法提前指定自己），
    # 它由 PATCH 那条用例覆盖（`test_the_other_g6_invariants_are_enforced_on_the_projects_route`）。
    board = await client.get(f"/api/projects/{project_id}/tasks", headers=auth)
    assert "B" in [str(row.get("title") or "") for row in board.json()], "合法 create 必须落行"
