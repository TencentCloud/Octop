"""B2 · T01 — the single-source scanner and its METRICS rendering.

Covers SPEC A4 / A5 (exit-code matrix 0/1/2/3 + ``--json`` six keys), R7–R10 (five
definition shapes, substring口径, by-line counting) and I3/I4/I5 (pure read, exit-code
process face, ``_single_source_scan`` stays pure rendering). Every test runs on
``tmp_path`` so the suite stays cross-platform.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from octop.infra.agents.teams import metrics, single_source
from octop.infra.agents.teams.metrics import RollupSources, rollup
from octop.infra.agents.teams.metrics_sources import load_sources
from octop.infra.agents.teams.single_source import (
    DEFINITION_FORMS,
    EXIT_DUPLICATE,
    EXIT_EMPTY,
    EXIT_OK,
    EXIT_USAGE,
    main,
    scan,
)

FACT = "单源探针"
SCAN_TITLE = metrics.SECTION_TITLES[9]
JSON_KEYS = (
    "matchedFacts",
    "defsInAuthority",
    "defsElsewhereTotal",
    "duplicateFacts",
    "refsTotal",
    "scannedFiles",
)


def _write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _section(text: str, title: str) -> str:
    start = text.index(f"## {title}\n")
    rest = text[start:]
    end = rest.find("\n## ", 1)
    return rest if end == -1 else rest[:end]


def _scan_event(key: str, fact: str, hits: int, at: int = 1) -> dict[str, Any]:
    return {
        "action": "scan:single-source",
        "at": at,
        "payload": {"id": key, "fact": fact, "hits": hits},
    }


# --------------------------------------------------------------------------- scan()


def test_the_five_definition_forms_are_all_detected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "AUTHORITY.md",
        "## 探针甲\n**探针乙**：定义\n| 探针丙 | 定义 |\n「探针丁」：定义\n- 探针戊：定义\n",
    )
    report = scan(tmp_path, ["探针甲", "探针乙", "探针丙", "探针丁", "探针戊"])
    assert report.matched_facts == 5
    assert report.duplicate_facts == 0
    assert report.defs_in_authority == 5
    assert report.defs_elsewhere_total == 0
    assert {d.form for d in report.definitions} == set(DEFINITION_FORMS)
    assert {d.line for d in report.definitions} == {1, 2, 3, 4, 5}


def test_duplicate_fact_is_counted_per_place_including_a_copy_in_the_authority(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    _write(tmp_path, "docs/a.md", f"**{FACT}**：定义\n")
    report = scan(tmp_path, [FACT])
    assert (report.matched_facts, report.duplicate_facts) == (1, 1)
    assert (report.defs_in_authority, report.defs_elsewhere_total) == (1, 1)
    assert [(d.path, d.line) for d in report.definitions] == [("AUTHORITY.md", 1), ("docs/a.md", 1)]


def test_references_are_counted_by_line_and_definitions_are_not_references(tmp_path: Path) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    _write(
        tmp_path,
        "notes.md",
        f"引用 {FACT} 两次同样只算一行：{FACT}\n另起一行再引用 {FACT}\n",
    )
    report = scan(tmp_path, [FACT])
    assert report.refs_total == 2
    assert report.defs_elsewhere_total == 0


def test_authority_filter_is_renameable_and_counts_the_rest_as_elsewhere(tmp_path: Path) -> None:
    _write(tmp_path, "TRUTH.md", f"## {FACT}\n")
    _write(tmp_path, "b.md", f"「{FACT}」：定义\n")
    report = scan(tmp_path, [FACT], authority="TRUTH.md")
    assert (report.defs_in_authority, report.defs_elsewhere_total) == (1, 1)


def test_scan_is_pure_idempotent_and_never_writes(tmp_path: Path) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    _write(tmp_path, "notes.md", f"引用 {FACT}\n")

    def snapshot() -> list[tuple[str, int, int]]:
        return sorted(
            (p.relative_to(tmp_path).as_posix(), p.stat().st_size, p.stat().st_mtime_ns)
            for p in tmp_path.rglob("*")
            if p.is_file()
        )

    before = snapshot()
    first = scan(tmp_path, [FACT])
    assert first == scan(tmp_path, [FACT])  # SPEC Q7: 无跨调用状态
    assert first == scan(tmp_path, [FACT, FACT])  # 事实名去重后同结果
    assert snapshot() == before  # 只读：不新增、不改写任何文件


def test_module_never_writes_or_opens_a_session() -> None:
    source = Path(single_source.__file__).read_text(encoding="utf-8")
    for token in ("write_text", "INSERT", "UPDATE", "session"):
        assert token not in source  # SPEC A10 / PLAN I3


# ---------------------------------------------------------------------------- CLI


def test_duplicate_fixture_exits_one_and_lists_every_place(tmp_path: Path, capsys: Any) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    _write(tmp_path, "b.md", f"**{FACT}**：定义\n")
    code = main([str(tmp_path), "--fact", FACT])
    out = capsys.readouterr().out
    assert code == EXIT_DUPLICATE == 1
    assert "AUTHORITY.md:1" in out
    assert "b.md:1" in out
    assert "duplicateFacts=1" in out


def test_clean_fixture_exits_zero(tmp_path: Path, capsys: Any) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    code = main([str(tmp_path), "--fact", FACT])
    out = capsys.readouterr().out
    assert code == EXIT_OK == 0
    assert "duplicateFacts=0" in out
    assert "AUTHORITY.md:1" in out


def test_fact_that_bites_nothing_exits_three(tmp_path: Path, capsys: Any) -> None:
    _write(tmp_path, "AUTHORITY.md", "## 另一个\n")
    code = main([str(tmp_path), "--fact", "从不存在的探针名"])
    out = capsys.readouterr().out
    assert code == EXIT_EMPTY == 3
    assert "matchedFacts=0 defsInAuthority=0 defsElsewhereTotal=0" in out
    assert "空转绿" in out


def test_usage_errors_exit_two_and_never_degrade_to_one(tmp_path: Path, capsys: Any) -> None:
    cases = [
        [],
        [str(tmp_path)],
        [str(tmp_path / "不存在"), "--fact", FACT],
        [str(tmp_path), "--fact"],
        [str(tmp_path), "--fact", FACT, "--bogus"],
        [str(tmp_path), "--fact", FACT, "多余"],
    ]
    for argv in cases:
        assert main(argv) == EXIT_USAGE == 2, argv
    assert "用法错" in capsys.readouterr().out


def test_json_ships_the_six_camel_case_keys_and_no_exit_code(tmp_path: Path, capsys: Any) -> None:
    _write(tmp_path, "AUTHORITY.md", f"## {FACT}\n")
    _write(tmp_path, "b.md", f"引用 {FACT}\n")
    code = main([str(tmp_path), "--fact", FACT, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == EXIT_OK
    assert set(JSON_KEYS) <= set(payload)
    assert payload["matchedFacts"] == 1
    assert payload["defsInAuthority"] == 1
    assert payload["refsTotal"] == 1
    assert payload["scannedFiles"] == 2
    assert [d["path"] for d in payload["definitions"]] == ["AUTHORITY.md"]
    assert not {"rc", "exit", "exitCode"} & set(payload)


# ------------------------------------------------------- METRICS rendering (A6)


def test_section_renders_real_numbers_from_scan_events() -> None:
    src = RollupSources(events=[_scan_event("rev1#7", FACT, 3)])
    section = _section(rollup(src).render(), SCAN_TITLE)
    assert "已登记扫描（按 `payload.id` 去重）：1 条" in section
    assert f"- `{FACT}`：命中 3 处" in section
    assert "覆盖事实：1 个 · 命中合计：3 处" in section


def test_same_event_twice_does_not_double_count_and_a_missing_id_is_not_counted() -> None:
    doubled = RollupSources(
        events=[_scan_event("rev1#7", FACT, 3), _scan_event("rev1#7", FACT, 3, at=2)]
    )
    section = _section(rollup(doubled).render(), SCAN_TITLE)
    assert "去重）：1 条" in section
    assert "命中合计：3 处" in section

    no_id = RollupSources(
        events=[{"action": "scan:single-source", "at": 1, "payload": {"fact": FACT, "hits": 9}}]
    )
    assert metrics.SINGLE_SOURCE_EMPTY in _section(rollup(no_id).render(), SCAN_TITLE)


def test_section_without_events_carries_the_verbatim_empty_string() -> None:
    section = _section(rollup(RollupSources()).render(), SCAN_TITLE)
    assert metrics.SINGLE_SOURCE_EMPTY == "暂无 scan:single-source 事件族"
    assert metrics.SINGLE_SOURCE_EMPTY in section
    assert "无单源化总扫登记" not in section


def test_discriminant_a_renderer_that_ignores_events_loses_the_numbers(monkeypatch: Any) -> None:
    """③ 判别性对照：把 `_single_source_scan` 换成忽略事件的旧渲染 ⇒ 实数消失（能红）。"""
    events = [_scan_event("rev1#7", FACT, 3)]
    assert "命中 3 处" in _section(rollup(RollupSources(events=events)).render(), SCAN_TITLE)

    def _ignores_events(_src: RollupSources) -> list[str]:
        return ["- （无单源化总扫登记：`scan:single-source` 事件一个都还没写过）"]

    builders = list(metrics._SECTION_BUILDERS)
    builders[builders.index(metrics._single_source_scan)] = _ignores_events
    monkeypatch.setattr(metrics, "_SECTION_BUILDERS", tuple(builders))
    broken = _section(rollup(RollupSources(events=events)).render(), SCAN_TITLE)
    assert "命中 3 处" not in broken
    assert "无单源化总扫登记" in broken


# --------------------------------------------- M5: events reach the rollup unfiltered


@dataclass
class _EventRow:
    action: str
    at: int
    payload: dict[str, Any]


class _TimelineRepo:
    def list_by_project(self, project_id: str) -> list[_EventRow]:
        assert project_id == "proj-1"
        return [
            _EventRow(
                action="scan:single-source", at=7, payload={"id": "rev1#7", "fact": FACT, "hits": 3}
            )
        ]


class _EmptyRepo:
    def list_by_project(self, project_id: str) -> list[_EventRow]:
        return []

    def list_by_run(self, run_id: str) -> list[_EventRow]:
        return []


def test_load_sources_pipes_scan_events_without_a_whitelist() -> None:
    services = SimpleNamespace(
        timeline_repo=_TimelineRepo(),
        project_task_repo=_EmptyRepo(),
        task_finding_repo=_EmptyRepo(),
    )
    run = SimpleNamespace(
        project_id="proj-1", run_id="run-1", room_thread_id=None, team_agent_id="agent-1"
    )
    sources = load_sources(services=services, run=run)
    assert [row["action"] for row in sources.events] == ["scan:single-source"]
    assert "命中 3 处" in _section(rollup(sources).render(), SCAN_TITLE)
