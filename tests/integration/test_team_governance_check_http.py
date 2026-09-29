"""T05 · 治理四码的 **HTTP 面**：`GET /{run_id}/check` 的只读侧新增码。

权威 = `team/2026-09-30-020000/PLAN.md` §2.4（四码）· §6 验收命令 · §7 R1
（历史 run 的取舍）＋ `SPEC.md` B1（沉默清单）/ B2（单源化）/ B3（证据锚点）。
实现侧 = `pipeline.py @1231-1248`（只读判定）· `silence_list.py` · `evidence.py`。

本文件覆盖 4 个新码，**每个码都经真 HTTP 打真路由**（`httpx` → FastAPI →
`TeamRunService.check` → 纯 gate），断言对象是**响应体** `violations`：

| 格 | 触发构造（真 run 快照） | 断言 |
|---|---|---|
| `SILENCE_LIST_MISSING` ① | run 目录**没有** `REVIEW-SPEC.md` ⇒ `review_spec_text is None` | 码逐字 · HTTP 200 |
| `SILENCE_LIST_MISSING` ② | 有文本但**无 `## 沉默清单`** 章节 | 码逐字 · HTTP 200 |
| `SILENCE_LIST_INCOMPLETE` | 缺 `依据` 列 / 裁定非法（`待定`）/ 51 行 | 码逐字 · 且**无** MISSING |
| `EVIDENCE_ANCHOR_MISSING` | 编造锚点（目标文件不存在）⇒ `MISSING` | 码逐字 · 且**无** RATCHET |
| `EVIDENCE_FRAGMENT_RATCHET` | 真文件 + 片段命中（`alpha_beta_token`）· 基线 0 | 码逐字 · 且**无** MISSING |
| 历史 run（§7 R1） | 有历史（`RUN.log.md` 已写）但两键皆空 | 只新增 **1 条**码，证据侧**不追加** |

**只读侧**：四码全部走 `GET`，所以期望 **200**（不是 4xx）——`advance` 才拦截，
`check` 只报告（`PLAN §2.4`）。每格同时断言「本批四码的集合**恰好**是预期那一格」，
这就是「只新增这一条」的强断言形式（既不多、也不少）。

**仅本地可观测**：临时 `OCTOP_HOME`（`tmp_octop_home`）内的假 workspace ＋ `tmp_path`
作为锚点根，不触网、不碰用户目录、不启第二个服务。
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

#: 本批新增的四个码，逐字（PLAN §2.4 / SPEC B1·B3）。
SILENCE_MISSING = "SILENCE_LIST_MISSING"
SILENCE_INCOMPLETE = "SILENCE_LIST_INCOMPLETE"
ANCHOR_MISSING = "EVIDENCE_ANCHOR_MISSING"
FRAGMENT_RATCHET = "EVIDENCE_FRAGMENT_RATCHET"
BATCH_B = (SILENCE_MISSING, SILENCE_INCOMPLETE, ANCHOR_MISSING, FRAGMENT_RATCHET)

#: A filled, legal 沉默清单: three columns, verdict starts with 允许 ⇒ no silence code.
#: The evidence cases use it so the only thing they can move is the evidence side.
VALID_SILENCE = """## 沉默清单

| 编号 | 问题 | 建议裁定 | 依据 | 风险 |
|---|---|---|---|---|
| S1 | 「团队事实名」的判定粒度未定义 | 允许按子串匹配 | SPEC R9 | 宁可多算 |
"""


class _FakeWorkspace:
    """Dict-backed stand-in, plus a **real** ``workspace_dir`` for anchor resolution.

    ``workspace_dir`` is what makes ``B3`` observable over HTTP: the service resolves
    every anchor path against it, so a file that exists there is a real ``EXACT`` hit
    and a file that does not is a real ``MISSING``.
    """

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
    """Run ids unique per test: `run_id_for` is second-precision by design (SPEC R22).

    Two ``POST /team/runs`` inside the same second are the plan's duplicate-``runId``
    conflict, so a loop that builds several runs would collide with itself. Only the
    clock is stubbed — the shape (`YYYY-MM-DD-HHMMSS`) stays exactly what R22 wants.
    """
    counter = itertools.count(1)
    monkeypatch.setattr(
        "octop.infra.agents.teams.run_service.run_id_for",
        lambda now=None: f"2026-01-02-{next(counter):06d}",
    )


@pytest.fixture
async def gov_env(
    env: tuple[httpx.AsyncClient, Any, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace]:
    """A team owned by a regular user + the memoised run service the router resolves."""
    client, srv, admin = env
    owner = await create_user(client, admin, username=f"gov-{new_short_id()}")
    members = [await create_agent(client, owner, name=f"gov-member-{i}") for i in range(2)]
    resp = await client.post(
        "/api/teams", headers=owner, json={"name": "Governance Team", "member_ids": members}
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
    return client, owner, team_id, service, workspace


async def _create_run(client: httpx.AsyncClient, auth: dict[str, str], team_id: str) -> str:
    resp = await client.post(
        "/api/team/runs",
        headers=auth,
        json={"team_agent_id": team_id, "goal": "治理四码的 HTTP 面", "tier": "standard"},
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["run_id"])


async def _check(client: httpx.AsyncClient, auth: dict[str, str], run_id: str) -> dict[str, Any]:
    """★ The endpoint under test. Read side ⇒ 200, never a 4xx refusal."""
    resp = await client.get(f"/api/team/runs/{run_id}/check", headers=auth)
    assert resp.status_code == 200, resp.text
    body = dict(resp.json())
    assert isinstance(body.get("violations"), list)
    return body


def _batch_b(body: dict[str, Any]) -> set[str]:
    """Exactly the four governance codes this run carries — nothing else counts."""
    return {str(code) for code in body["violations"] if str(code) in BATCH_B}


def _spec_path(run_id: str) -> str:
    """`run_directory` for a host-workspace run: ``team/<runId>`` (SPEC R22)."""
    return f"team/{run_id}/REVIEW-SPEC.md"


async def _put(
    client: httpx.AsyncClient,
    auth: dict[str, str],
    run_id: str,
    name: str,
    content: str,
    revision: str = "",
) -> str:
    resp = await client.put(
        f"/api/team/runs/{run_id}/artifacts/{name}",
        headers=auth,
        json={"content": content, "revision": revision, "role": "qa"},
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["revision"])


# ── 格 1：SILENCE_LIST_MISSING ───────────────────────────────────────────────


async def test_silence_missing_when_no_review_spec_artifact(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """`review_spec_text is None` ⇒ MISSING（fail-closed，I8）。

    一个**从未携带** `REVIEW-SPEC.md` 的 run 不能声称清单已填；只读侧只报告，HTTP 仍 200。
    """
    client, auth, team_id, _service, _workspace = gov_env
    run_id = await _create_run(client, auth, team_id)

    body = await _check(client, auth, run_id)

    assert SILENCE_MISSING in body["violations"], body["violations"]
    assert _batch_b(body) == {SILENCE_MISSING}, body["violations"]


async def test_silence_missing_when_text_has_no_silence_section(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """文本存在但无 `沉默清单` 章节 ⇒ 同一个码（R2：空态 ≡ 缺席）。"""
    client, auth, team_id, _service, workspace = gov_env
    run_id = await _create_run(client, auth, team_id)
    workspace.write_text(
        _spec_path(run_id),
        "# REVIEW-SPEC\n\n## 评审口径\n\n- 只判可机检项\n",
    )

    body = await _check(client, auth, run_id)

    assert SILENCE_MISSING in body["violations"], body["violations"]
    assert _batch_b(body) == {SILENCE_MISSING}, body["violations"]


# ── 格 2：SILENCE_LIST_INCOMPLETE ────────────────────────────────────────────


def _table(*rows: str, header: str = "| 编号 | 问题 | 建议裁定 | 依据 | 风险 |") -> str:
    return "## 沉默清单\n\n" + "\n".join([header, "|---|---|---|---|---|", *rows]) + "\n"


async def test_silence_incomplete_missing_column_illegal_verdict_and_too_many_rows(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """R3–R5 的三个触发面：缺列 / 裁定非法 / 超 50 行 —— 都只出 INCOMPLETE。"""
    client, auth, team_id, _service, workspace = gov_env

    cases: dict[str, str] = {
        "missing-column": _table("| S1 | 粒度未定义 | 允许子串 |  | 多算 |"),
        "illegal-verdict": _table("| S1 | 粒度未定义 | 待定 | SPEC R9 | 多算 |"),
        "too-many-rows": _table(
            *(f"| S{i} | 问题 {i} | 允许子串 | SPEC R9 | 多算 |" for i in range(1, 52))
        ),
    }

    for label, text in cases.items():
        run_id = await _create_run(client, auth, team_id)
        workspace.write_text(_spec_path(run_id), text)

        body = await _check(client, auth, run_id)

        assert SILENCE_INCOMPLETE in body["violations"], (label, body["violations"])
        assert SILENCE_MISSING not in body["violations"], (label, body["violations"])
        assert _batch_b(body) == {SILENCE_INCOMPLETE}, (label, body["violations"])


# ── 格 3：EVIDENCE_ANCHOR_MISSING / EVIDENCE_FRAGMENT_RATCHET ────────────────


async def test_evidence_anchor_missing_for_fabricated_anchor(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """编造锚点（目标文件不存在）⇒ `MISSING` ⇒ 码逐字；片段侧不动。"""
    client, auth, team_id, _service, workspace = gov_env
    run_id = await _create_run(client, auth, team_id)
    workspace.write_text(
        _spec_path(run_id),
        VALID_SILENCE + "\n## 证据锚点\n\n- src/octop/teams/ghost.py · 凭空捏造的锚点文字\n",
    )

    body = await _check(client, auth, run_id)

    assert ANCHOR_MISSING in body["violations"], body["violations"]
    assert FRAGMENT_RATCHET not in body["violations"], body["violations"]
    assert _batch_b(body) == {ANCHOR_MISSING}, body["violations"]


async def test_evidence_fragment_ratchet_over_baseline(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """片段命中（整串不在、某个 ≥2 字 token 在）且超基线 0 ⇒ RATCHET。

    `evidence_fragment_baseline.json` 的 `default` 为 0，新 run 又不在 `runs` 里，
    所以第一条弱证据就是红的（fail-closed，I7）。
    """
    client, auth, team_id, _service, workspace = gov_env
    run_id = await _create_run(client, auth, team_id)
    target = Path(workspace.workspace_dir) / "src/octop/teams/real.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("alpha_beta_token = 1\n", encoding="utf-8")
    workspace.write_text(
        _spec_path(run_id),
        VALID_SILENCE
        + "\n## 证据锚点\n\n- src/octop/teams/real.py · alpha_beta_token omega_delta\n",
    )

    body = await _check(client, auth, run_id)

    assert FRAGMENT_RATCHET in body["violations"], body["violations"]
    assert ANCHOR_MISSING not in body["violations"], body["violations"]
    assert _batch_b(body) == {FRAGMENT_RATCHET}, body["violations"]


# ── 格 4：历史 run 兼容（PLAN §7 R1）────────────────────────────────────────


async def test_historical_run_gains_exactly_one_code_and_no_evidence_code(
    gov_env: tuple[httpx.AsyncClient, dict[str, str], str, Any, _FakeWorkspace],
) -> None:
    """历史 run：两键皆空 ⇒ **只**新增 `SILENCE_LIST_MISSING` 1 条，证据侧不追加。

    「两键皆空」在 HTTP 面的等价物：run 目录里没有 `REVIEW-SPEC.md`，于是
    `review_spec_text is None`（⇒ 唯一的那个码），`evidence_summary` 计数全 0
    （⇒ **一个证据码都不加**，这正是 §7 R1 批准的取舍）。

    判别性对照在同一个 run 内完成：补上一份**合法**清单后，该码必须消失且四码集合为空
    —— 证明确实只有「缺失」这一条，而不是别的 gate 顺带变红。
    """
    client, auth, team_id, service, workspace = gov_env
    run_id = await _create_run(client, auth, team_id)
    # 历史：run 已有产物与时间线，只是当年还没有 REVIEW-SPEC.md 这条规则。
    await _put(client, auth, run_id, "RUN.log.md", "# RUN.log\n\n- 首轮产出已落盘\n")

    before = await _check(client, auth, run_id)

    assert SILENCE_MISSING in before["violations"], before["violations"]
    assert _batch_b(before) == {SILENCE_MISSING}, before["violations"]
    assert ANCHOR_MISSING not in before["violations"], before["violations"]
    assert FRAGMENT_RATCHET not in before["violations"], before["violations"]

    run = service._runs.get(run_id)
    assert run is not None
    summary = dict(service.snapshot(run)["evidence_summary"])
    assert summary == {"exact": 0, "fragmentOnly": 0, "missing": 0, "baseline": 0}, summary

    workspace.write_text(_spec_path(run_id), VALID_SILENCE)
    after = await _check(client, auth, run_id)

    assert _batch_b(after) == set(), after["violations"]
    assert set(after["violations"]) - set(before["violations"]) == set(), after["violations"]
