"""T05 · 单源化节的 **HTTP 面**：`GET /{run_id}/metrics` 的两态 + 端到端写入方。

权威 = `team/2026-09-30-020000/PLAN.md` §2.4 / §3.1 / §6 验收命令 ＋ `SPEC.md`
A6（无事件时的**逐字**空态）/ A7（登记写入方）。实现侧 =
`metrics.py _single_source_scan` · `metrics_sources.py section_states` ·
`run_service.py @2116-2123`（唯一的写入方 `write_artifact → _append_timeline`）。

本文件把 `B2`「不再空转」证到底，三段：

1. **无事件** ⇒ 该节逐字携带 `暂无 scan:single-source 事件族`。实读实现后确认为
   `f"- （{SINGLE_SOURCE_EMPTY}）"`，即该串**被 `- （…）` 包裹** —— 两行都断言
   （包裹后的整行 ＋ 裸串本身），所以「改了包裹样式」和「删了那句」都会红。
2. **端到端写入方** ⇒ `PUT …/artifacts/RUN.log.md` 追加
   `scan:single-source — <事实名> · 命中 N 处` ⇒ 再查 `metrics` 出现**实数**
   （`已登记扫描…N 条` / `命中 N 处`）。这是 `B2` 的**唯一生产路径**。
3. **负向对照** ⇒ 直接把同样一行写进 run 目录（绕过 service）⇒ 该节**仍然**是空态。
   证明数字只可能来自 timeline 事件，不可能来自文件本身。

**仅本地可观测**：临时 `OCTOP_HOME`（`tmp_octop_home`）内的假 workspace，不触网、
不碰用户目录、不启第二个服务。
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from octop.infra.gateway.threads import ThreadRegistry
from octop.infra.utils.ulid import new_short_id
from tests.support.auth import create_agent, create_user

#: SPEC A6：无 `scan:*` 事件时该节必须逐字携带的串。
SINGLE_SOURCE_EMPTY = "暂无 scan:single-source 事件族"
#: 空态在实现里被 `- （…）` 包裹（实读 `metrics.py`），逐字锁死包裹后的整行。
SINGLE_SOURCE_EMPTY_LINE = f"- （{SINGLE_SOURCE_EMPTY}）"
#: 该节标题（`metrics_sources.SECTION_NOTES` 的键，逐字）。
SECTION_TITLE = "单源化总扫（见一个，扫全部）"


class _FakeWorkspace:
    """Same dict-backed stand-in the sibling integration files use."""

    def __init__(self, root: Path) -> None:
        self.files: dict[str, str] = {}
        self.workspace_dir = str(root)

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": n, "is_dir": False}
            for n in sorted(self.files)
            if n.startswith(prefix) and "/" not in n[len(prefix) :]
        ]


class _RoomGateway:
    """Just enough gateway for the run's room thread (a **real** ``ThreadRegistry``)."""

    def __init__(self, services: Any) -> None:
        self.thread_registry = ThreadRegistry(
            session_repo=services.session_repo, thread_repo=services.thread_repo
        )


@pytest.fixture(autouse=True)
def _unique_run_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ids unique per test: `run_id_for` is second-precision by design (SPEC R22)."""
    counter = itertools.count(1)
    monkeypatch.setattr(
        "octop.infra.agents.teams.run_service.run_id_for",
        lambda now=None: f"2026-01-02-{next(counter):06d}",
    )


@pytest.fixture
async def metrics_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[httpx.AsyncClient, dict[str, str], str, _FakeWorkspace]:
    """Team owned by a regular user + the memoised run service the router resolves."""
    client, srv, admin = env
    owner = await create_user(client, admin, username=f"metrics-{new_short_id()}")
    members = [await create_agent(client, owner, name=f"metrics-member-{i}") for i in range(2)]
    resp = await client.post(
        "/api/teams", headers=owner, json={"name": "Metrics Team", "member_ids": members}
    )
    assert resp.status_code in (200, 201), resp.text
    team_id = str(resp.json()["agent_id"])

    workspace = _FakeWorkspace(tmp_path)
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
    service.bind_runtime(  # type: ignore[call-arg]
        gateway=_RoomGateway(srv.services),
        workspace_for=lambda agent_id: workspace,
    )
    monkeypatch.setattr(type(srv.services), "team_run_service", lambda self: service)
    return client, owner, team_id, workspace


async def _create_run(client: httpx.AsyncClient, auth: dict[str, str], team_id: str) -> str:
    resp = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "单源化节的真数", "tier": "standard"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["run_id"])


async def _single_source_lines(
    client: httpx.AsyncClient, auth: dict[str, str], run_id: str
) -> tuple[list[str], str, dict[str, Any]]:
    """★ The section under test: its lines, the rendered document, and the section meta."""
    resp = await client.get(f"/api/team/runs/{run_id}/metrics", headers=auth)
    assert resp.status_code == 200, resp.text
    body = dict(resp.json())
    section = next((item for item in body["sections"] if item["title"] == SECTION_TITLE), None)
    assert section is not None, [item["title"] for item in body["sections"]]
    return list(section["lines"]), str(body["rendered"]), dict(section)


async def _put_artifact(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    run_id: str,
    name: str,
    content: str,
    revision: str = "",
) -> str:
    """★ The one production path of `B2`: the service write that appends the event."""
    resp = await client.put(
        f"/api/team/runs/{run_id}/artifacts/{name}",
        headers=auth,
        json={"content": content, "revision": revision, "role": "qa"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["revision"])


def _scan_line(fact: str, hits: int) -> str:
    """SPEC R11 verbatim: ``scan:single-source — <事实名> · 命中 N 处``."""
    return f"scan:single-source — {fact} · 命中 {hits} 处"


def _bullet(lines: list[str], text: str) -> bool:
    """Does one rendered bullet carry *text*? The section renders ``- <句>`` 每行一条。"""
    return any(line == f"- {text}" for line in lines)


# ── 态 ①：无事件 ⇒ 逐字空态 ─────────────────────────────────────────────────


async def test_metrics_single_source_is_verbatim_empty_without_scan_events(
    metrics_env: tuple[httpx.AsyncClient, dict[str, str], str, _FakeWorkspace],
) -> None:
    """没有 `scan:*` 事件时，该节必须**显式**写那句话（静默省略即为红）。"""
    client, auth, team_id, _workspace = metrics_env
    run_id = await _create_run(client, auth, team_id)

    lines, rendered, section = await _single_source_lines(client, auth, run_id)

    assert lines[0] == SINGLE_SOURCE_EMPTY_LINE, lines
    assert SINGLE_SOURCE_EMPTY in rendered
    assert not [line for line in lines if "已登记扫描" in line], lines
    assert section["state"] == "measured", section
    assert "write_artifact" in str(section["note"]), section


# ── 态 ②：端到端写入方 ⇒ 实数（B2 不再空转）────────────────────────────────


async def test_artifact_write_registers_scan_events_as_real_numbers(
    metrics_env: tuple[httpx.AsyncClient, dict[str, str], str, _FakeWorkspace],
) -> None:
    """`PUT …/artifacts/RUN.log.md` 追加两行 ⇒ `metrics` 报实数，空态那句消失。"""
    client, auth, team_id, _workspace = metrics_env
    run_id = await _create_run(client, auth, team_id)

    before, _rendered, _section = await _single_source_lines(client, auth, run_id)
    assert before[0] == SINGLE_SOURCE_EMPTY_LINE, before

    revision = await _put_artifact(
        client,
        auth,
        run_id,
        "RUN.log.md",
        f"# RUN.log\n\n{_scan_line('团队事实名', 3)}\n",
    )
    revision = await _put_artifact(
        client,
        auth,
        run_id,
        "RUN.log.md",
        f"# RUN.log\n\n{_scan_line('团队事实名', 3)}\n{_scan_line('单源化口径', 5)}\n",
        revision,
    )
    assert revision

    lines, rendered, _section = await _single_source_lines(client, auth, run_id)

    assert _bullet(lines, "已登记扫描（按 `payload.id` 去重）：2 条"), lines
    assert _bullet(lines, "`团队事实名`：命中 3 处"), lines
    assert _bullet(lines, "`单源化口径`：命中 5 处"), lines
    assert _bullet(lines, "覆盖事实：2 个 · 命中合计：8 处"), lines
    assert SINGLE_SOURCE_EMPTY_LINE not in lines, lines
    assert SINGLE_SOURCE_EMPTY not in rendered


async def test_a_rewrite_of_the_same_body_does_not_double_count(
    metrics_env: tuple[httpx.AsyncClient, dict[str, str], str, _FakeWorkspace],
) -> None:
    """同一 body 重写一次：`_new_scan_lines` 只认**新增**行 ⇒ 条数不翻倍。"""
    client, auth, team_id, _workspace = metrics_env
    run_id = await _create_run(client, auth, team_id)
    body = f"# RUN.log\n\n{_scan_line('团队事实名', 3)}\n"

    first = await _put_artifact(client, auth, run_id, "RUN.log.md", body)
    second = await _put_artifact(client, auth, run_id, "RUN.log.md", body, first)
    assert second

    lines, _rendered, _section = await _single_source_lines(client, auth, run_id)

    assert _bullet(lines, "已登记扫描（按 `payload.id` 去重）：1 条"), lines
    assert _bullet(lines, "`团队事实名`：命中 3 处"), lines


# ── 态 ③：负向对照 —— 文件不是数据源，timeline 才是 ────────────────────────


async def test_scan_line_written_behind_the_service_stays_empty(
    metrics_env: tuple[httpx.AsyncClient, dict[str, str], str, _FakeWorkspace],
) -> None:
    """同样的行直接落进 run 目录（绕过 service）⇒ 该节**仍然**是空态。

    这条对照把「唯一生产路径」钉死：数字只能来自 `write_artifact` 记的 timeline 事件，
    不能来自文件本身（否则 `metrics` 就成了一个偷偷读盘的函数）。
    """
    client, auth, team_id, workspace = metrics_env
    run_id = await _create_run(client, auth, team_id)
    workspace.write_text(
        f"team/{run_id}/RUN.log.md", f"# RUN.log\n\n{_scan_line('团队事实名', 3)}\n"
    )

    lines, rendered, _section = await _single_source_lines(client, auth, run_id)

    assert lines[0] == SINGLE_SOURCE_EMPTY_LINE, lines
    assert SINGLE_SOURCE_EMPTY in rendered
    assert not [line for line in lines if "已登记扫描" in line], lines
