"""T04 · 治理违规码接线 —— `check_run` 四码（只读侧）+ `scan:*` 事件写入方。

**判据锚（逐字取 PLAN）**
* §2.4：四码只进 `CheckReport.violations`（恒 HTTP 200），**不改** `advance_gate`
  ⇒ 历史 run 不因本批卡死；挂载顺序 `SILENCE_LIST_MISSING → SILENCE_LIST_INCOMPLETE
  → EVIDENCE_ANCHOR_MISSING → EVIDENCE_FRAGMENT_RATCHET`。
* §3 M1/M2：输入是快照键 `review_spec_text` / `evidence_summary`；缺 `review_spec_text`
  ⇒ 按 `""` 判（fail-closed）；`evidence_summary` **整键缺失** ⇒ 不追加证据码（§4 取舍 / R1）。
* §3 M3/M4：快照新增两键并登记进 `RUN_SNAPSHOT_KEYS`。
* §3.1：`write_artifact` 落盘后，**只对本次新增**的 `scan:` 行经 `_record` 追加
  `action="scan:single-source"`、`payload={"id": "<revision>#<行号>", "fact":…, "hits":N}`。

**码映射唯一真源**：证据两码只由 `evidence.ratchet_codes` 产生（下方第 4 组用例把
`check_run` 的输出与该函数逐例比对，复制一份映射即红）。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from octop.config import OctopConfig
from octop.infra.agents.teams import evidence
from octop.infra.agents.teams.pipeline import RUN_SNAPSHOT_KEYS, check_run
from octop.infra.agents.teams.run_service import TeamRunService, revision_of
from octop.infra.agents.teams.service import TeamService
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout

TEAM_ID = "ag-t04-team"
MANIFEST = ".octop/manifest.json"
MEMBERS = [(TEAM_ID, "lead"), ("ag-be", "backend")]
GOOD_REVIEW = (
    "# 规格审查（REVIEW-SPEC）\n\n## 沉默清单（见一个，扫全部）\n\n"
    "| 建议裁定 | 依据 | 风险 |\n| --- | --- | --- |\n| 允许 | PLAN §2.4 | 无 |\n"
)
INCOMPLETE_REVIEW = (
    "# 规格审查（REVIEW-SPEC）\n\n## 沉默清单（见一个，扫全部）\n\n"
    "| 建议裁定 | 依据 | 风险 |\n| --- | --- | --- |\n| 允许 |  | 无 |\n"
)
RUN_LOG = "/team/run/RUN.log.md"


def _base() -> dict[str, Any]:
    """A snapshot that trips **none** of the six pre-existing codes."""
    return {"tasks": [], "finding_rounds": []}


def _codes(run: dict[str, Any]) -> tuple[str, ...]:
    return check_run(run).violations


# ── 1. 沉默清单两码（fail-closed）＋ 历史 run 只新增 1 条 ──────────────────────


def test_history_run_without_the_key_gains_exactly_one_code() -> None:
    """缺 `review_spec_text` ⇒ `SILENCE_LIST_MISSING`，且**只**新增这一条（§3 M1 / I8）。"""
    assert _codes(_base()) == ("SILENCE_LIST_MISSING",)


def test_missing_section_and_empty_section_read_the_same() -> None:
    """`None` 与「有标题无数据行」等价（R2）：都只判 `SILENCE_LIST_MISSING`。"""
    assert _codes({**_base(), "review_spec_text": None}) == ("SILENCE_LIST_MISSING",)
    assert _codes({**_base(), "review_spec_text": "## 沉默清单（见一个，扫全部）\n"}) == (
        "SILENCE_LIST_MISSING",
    )


def test_filled_list_is_green_and_incomplete_list_is_red() -> None:
    """填满三列 ⇒ 无码；缺列 ⇒ `SILENCE_LIST_INCOMPLETE`（且不是 MISSING）。"""
    assert _codes({**_base(), "review_spec_text": GOOD_REVIEW}) == ()
    assert _codes({**_base(), "review_spec_text": INCOMPLETE_REVIEW}) == (
        "SILENCE_LIST_INCOMPLETE",
    )


# ── 2. 证据两码：整键缺失 fail-open；存在时**逐例**等于 ratchet_codes ───────────


def test_evidence_summary_absent_appends_no_evidence_code() -> None:
    """整键缺失 ⇒ 不追加证据码（已批准的取舍，§4 / R1 / H5）。"""
    assert _codes({**_base(), "review_spec_text": GOOD_REVIEW}) == ()
    assert _codes({**_base(), "review_spec_text": GOOD_REVIEW, "evidence_summary": None}) == ()


@pytest.mark.parametrize(
    ("fragment_only", "missing", "baseline"),
    [(0, 0, 0), (0, 1, 0), (1, 0, 0), (3, 2, 1), (1, 0, 1), (5, 0, 1)],
)
def test_evidence_codes_equal_the_single_source_mapping(
    fragment_only: int, missing: int, baseline: int
) -> None:
    """`check_run` 的证据码 == `evidence.ratchet_codes(...)` —— 唯一真源，复制即红。"""
    summary = {
        "exact": 9,
        "fragmentOnly": fragment_only,
        "missing": missing,
        "baseline": baseline,
    }
    expected = evidence.ratchet_codes(fragment_only, missing, baseline)
    assert _codes({**_base(), "review_spec_text": GOOD_REVIEW, "evidence_summary": summary}) == (
        expected
    )
    assert evidence.ratchet_codes(0, 0, 0) == ()
    assert evidence.ratchet_codes(0, 1, 0) == ("EVIDENCE_ANCHOR_MISSING",)
    assert evidence.ratchet_codes(1, 0, 0) == ("EVIDENCE_FRAGMENT_RATCHET",)
    assert evidence.ratchet_codes(1, 0, 1) == ()


def test_all_four_codes_keep_the_frozen_order() -> None:
    """四码追加在既有码之后，顺序逐字（§2.4）。"""
    run = {
        **_base(),
        "review_spec_text": INCOMPLETE_REVIEW,
        "evidence_summary": {"fragmentOnly": 2, "missing": 1, "baseline": 0},
    }
    assert _codes(run) == (
        "SILENCE_LIST_INCOMPLETE",
        "EVIDENCE_ANCHOR_MISSING",
        "EVIDENCE_FRAGMENT_RATCHET",
    )


def test_snapshot_keys_register_both_new_keys() -> None:
    assert {"review_spec_text", "evidence_summary"} <= set(RUN_SNAPSHOT_KEYS)


# ── 3. `scan:*` 事件写入方（§3.1）────────────────────────────────────────────


class FakeWorkspace:
    """harness 形状的替身：`read_text` / `write_text` / `list_dir`（见 `present_artifacts`）。"""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def read_text(self, path: str, *, limit: int = 10_000_000) -> str | None:
        return self.files.get(str(path))

    def write_text(self, path: str, content: str, *, force: bool = False) -> None:
        self.files[str(path)] = content

    def exists(self, path: str) -> bool:
        return str(path) in self.files

    def list_dir(self, path: str = ".") -> list[Any]:
        prefix = "" if str(path) in {"", "."} else str(path).rstrip("/") + "/"
        return [
            {"path": name, "is_dir": False}
            for name in sorted(self.files)
            if name.startswith(prefix) and "/" not in name[len(prefix) :]
        ]


class Actor:
    def __init__(self, user_id: int) -> None:
        self.id = user_id
        self.permissions = ["projects"]
        self.is_admin = False


@dataclass
class Harness:
    services: Any
    service: TeamRunService
    workspace: FakeWorkspace
    user: Actor
    run: Any


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    monkeypatch.setenv("OCTOP_HOME", str(tmp_path / "home"))
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    uid = services.user_repo.create(username="owner", password_hash="h", role="user")
    services.agent_repo.create(agent_id=TEAM_ID, user_id=uid, name="T04 Team", kind="team")
    workspace = FakeWorkspace()
    workspace.write_text(
        MANIFEST,
        json.dumps(
            {
                "members": [{"agent_id": a, "role": r} for a, r in MEMBERS],
                "lead_agent_id": TEAM_ID,
            }
        ),
    )
    accessor = lambda agent_id: workspace if agent_id == TEAM_ID else None  # noqa: E731
    service = TeamRunService(
        services=services,
        gateway=None,  # type: ignore[arg-type]
        workspace_for=accessor,
        team_service=TeamService(services.repos, workspace_for=accessor),
    )
    run = service.create(team_agent_id=TEAM_ID, goal="T04 scan", tier="quick", user=Actor(uid))
    yield Harness(services=services, service=service, workspace=workspace, user=Actor(uid), run=run)


def _scan_events(harness: Harness) -> list[dict[str, Any]]:
    rows = harness.services.timeline_repo.list_by_project(harness.run.project_id)
    return [row.payload for row in rows if str(row.action) == "scan:single-source"]


def _write(harness: Harness, name: str, content: str, role: str = "backend") -> str:
    """Write *name* through the production entry, CAS-ing against what is on disk.

    ``role`` must be one the ownership table knows (``reviewer`` for ``REVIEW-SPEC.md``,
    which is the artifact's declared owner).
    """
    current = harness.service.read_artifact(harness.run.run_id, name)
    harness.service.write_artifact(
        harness.run.run_id,
        name=name,
        content=content,
        revision=current[1],
        role=role,
        user=harness.user,
    )
    return revision_of(content)


def test_only_newly_added_scan_lines_become_events(harness: Harness) -> None:
    """新增 2 行 ⇒ 2 条事件（三键逐字），重复写同内容 ⇒ 不重复追加。"""
    first = "RUN LOG\nscan:single-source — 违规码表 · 命中 3 处\n普通行\n"
    revision = _write(harness, "RUN.log.md", first)
    assert _scan_events(harness) == [{"id": f"{revision}#2", "fact": "违规码表", "hits": 3}]

    second = first + "scan:single-source — 门禁落点 · 命中 7 处\n"
    second_revision = revision_of(second)
    _write(harness, "RUN.log.md", second)
    assert _scan_events(harness) == [
        {"id": f"{revision}#2", "fact": "违规码表", "hits": 3},
        {"id": f"{second_revision}#4", "fact": "门禁落点", "hits": 7},
    ]

    # 幂等（Q5/I10）：同内容重写 ⇒ 同 `revision`、同 `#行号` ⇒ 事件数不变。
    _write(harness, "RUN.log.md", second)
    assert len(_scan_events(harness)) == 2

    # 非 `scan:` 行与不合格式的行不产生事件。
    _write(harness, "RUN.log.md", second + "scan:single-source — 坏格式\n")
    assert len(_scan_events(harness)) == 2


def test_snapshot_wires_review_spec_text_and_evidence_summary(harness: Harness) -> None:
    """M3/M4 端到端：REVIEW-SPEC.md 落盘 ⇒ 快照两键可读，且 `check_run` 判绿。"""
    _write(harness, "REVIEW-SPEC.md", GOOD_REVIEW, role="reviewer")
    snapshot = harness.service.snapshot(harness.run)
    assert snapshot["review_spec_text"] == GOOD_REVIEW
    assert snapshot["evidence_summary"] == {
        "exact": 0,
        "fragmentOnly": 0,
        "missing": 0,
        "baseline": 0,
    }
    assert check_run(snapshot).violations == ()
    # 空清单（占位未填）走同一条快照链 ⇒ 可见红。
    _write(harness, "REVIEW-SPEC.md", "# 规格审查（REVIEW-SPEC）\n", role="reviewer")
    assert check_run(harness.service.snapshot(harness.run)).violations == ("SILENCE_LIST_MISSING",)
