"""T03 / B3 — evidence anchors: three-level verdict + fragment ratchet (PLAN §2.2, §4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from octop.infra.agents.teams import evidence
from octop.infra.agents.teams.evidence import (
    EVIDENCE_ANCHOR_MISSING,
    EVIDENCE_FRAGMENT_RATCHET,
    Verdict,
    anchors,
    load_baseline,
    ratchet_codes,
)

TARGET = "src/octop/infra/agents/teams/target.py"
TARGET_BODY = "第一行\n唯一绿条件：锚点整串逐字命中\ntail\n"
VERBATIM = "锚点整串逐字命中"
GHOST = "src/ghost.py · 完全编造的证据锚点\n"


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    target = tmp_path / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_BODY, encoding="utf-8")
    return tmp_path


def _use_baseline_file(monkeypatch: pytest.MonkeyPatch, path: Path) -> None:
    monkeypatch.setattr(evidence, "_baseline_path", lambda: path)


# --- §4.2 three-level verdict -------------------------------------------------


def test_exact_is_the_only_green(root: Path) -> None:
    report = anchors(f"- {TARGET} · {VERBATIM}\n", root, None)
    assert report.exact == 1
    assert (report.fragment_only, report.missing) == (0, 0)
    assert report.codes == ()
    assert report.hits[0].verdict == Verdict.EXACT
    assert report.hits[0].line is None
    assert report.details == (f"{TARGET} · {VERBATIM} · EXACT · verbatim hit",)


def test_one_character_change_is_not_exact(root: Path) -> None:
    near_miss = VERBATIM[:-1] + "申"
    report = anchors(f"{TARGET} · {near_miss}\n", root, None)
    assert report.exact == 0
    assert report.hits[0].verdict == Verdict.MISSING
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


def test_fragment_only_is_weak_evidence(root: Path) -> None:
    fragment = f"{VERBATIM} 另外的词"
    report = anchors(f"{TARGET} · {fragment}\n", root, None)
    assert report.hits[0].verdict == Verdict.FRAGMENT_ONLY
    assert (report.exact, report.fragment_only, report.missing) == (0, 1, 0)
    assert report.baseline == 0
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)
    assert report.details == (f"{TARGET} · {fragment} · FRAGMENT_ONLY · token={VERBATIM}",)


def test_fragment_at_baseline_is_green(root: Path) -> None:
    report = anchors(f"{TARGET} · {VERBATIM} 另外的词\n", root, 1)
    assert report.fragment_only == 1
    assert report.baseline == 1
    assert report.codes == ()


def test_no_anchor_line_yields_empty_report(root: Path) -> None:
    report = anchors("## 沉默清单\n没有锚点的一行\n", root, None)
    assert report.hits == ()
    assert (report.exact, report.fragment_only, report.missing) == (0, 0, 0)
    assert (report.codes, report.details) == ((), ())


def test_pure_and_idempotent(root: Path) -> None:
    text = f"{TARGET} · {VERBATIM}\n{GHOST}"
    first = anchors(text, root, None)
    second = anchors(text, root, None)
    assert first == second
    assert hash(first) == hash(second)


# --- §4.1 P1–P4 hard rejects --------------------------------------------------


def test_bare_filename_is_missing_without_suffix_matching(root: Path) -> None:
    report = anchors(f"target.py · {VERBATIM}\n", root, None)
    assert report.hits[0].verdict == Verdict.MISSING
    assert "bare filename" in report.hits[0].reason


def test_missing_path_has_no_token_fallback(root: Path) -> None:
    (root / "src" / "other.py").write_text(TARGET_BODY, encoding="utf-8")
    report = anchors(f"src/ghost.py · {VERBATIM}\n", root, None)
    assert report.hits[0].verdict == Verdict.MISSING
    assert report.hits[0].reason == "path not found under root"


def test_directory_path_is_missing(root: Path) -> None:
    report = anchors("src/octop · 一些锚点\n", root, None)
    assert report.hits[0].verdict == Verdict.MISSING
    assert report.hits[0].reason == "path is not a file"


@pytest.mark.parametrize(
    "embedded",
    [
        f"{VERBATIM} 见 110-122 行",  # 行号语义（见 / 行）⇒ 仍硬拒
        f"{VERBATIM} L12-L34",  # L 前缀行号形态 ⇒ 仍硬拒
        f"{VERBATIM}（12）",
        f"{VERBATIM} (12-14)",
    ],
)
def test_anchor_embedding_a_line_number_is_missing(root: Path, embedded: str) -> None:
    report = anchors(f"{TARGET} · {embedded}\n", root, None)
    assert report.hits[0].verdict == Verdict.MISSING
    assert "embeds a line number" in report.hits[0].reason


@pytest.mark.parametrize(
    "released",
    [
        "会议 2026-09-30 决议",  # T06 缺陷① 探针：锚点与正文逐字同含 CJK 日期
        "覆盖 110-122 区间",  # 普通区间：无行号语义
        "会议（2026-09-30）决议",  # 括号里的日期不是行号
    ],
)
def test_date_and_plain_range_are_not_line_numbers(root: Path, released: str) -> None:
    """收窄后（T06 缺陷①）：日期 / 普通区间的**真·逐字命中**必须放行，不得假红。"""
    (root / TARGET).write_text(TARGET_BODY + released + "\n", encoding="utf-8")
    report = anchors(f"{TARGET} · {released}\n", root, None)
    hit = report.hits[0]
    assert hit.verdict == Verdict.EXACT
    assert hit.reason == "verbatim hit"
    assert (report.exact, report.fragment_only, report.missing) == (1, 0, 0)
    assert report.codes == ()


def test_backticks_stripped_and_line_slot_parsed(root: Path) -> None:
    report = anchors(f"{TARGET} · `{VERBATIM}` @ 12-14\n", root, None)
    assert report.hits[0].anchor == VERBATIM
    assert report.hits[0].line == "12-14"
    assert report.hits[0].verdict == Verdict.EXACT


# --- §4.1 P2 fences: paired exempts, unclosed does not ------------------------


def test_paired_fence_block_is_exempt(root: Path) -> None:
    text = f"```\n{GHOST}```\n{TARGET} · {VERBATIM}\n"
    report = anchors(text, root, None)
    assert (report.exact, report.missing) == (1, 0)
    assert report.codes == ()


def test_unclosed_fence_does_not_exempt(root: Path) -> None:
    text = f"```\n{GHOST}{TARGET} · {VERBATIM}\n"
    report = anchors(text, root, None)
    assert (report.exact, report.missing) == (1, 1)
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


# --- §2.2 / §4.3 ratchet: single code source + fail-closed baseline -----------


@pytest.mark.parametrize(
    ("fragment_only", "missing", "baseline", "expected"),
    [
        (0, 0, None, ()),
        (1, 0, None, (EVIDENCE_FRAGMENT_RATCHET,)),
        (1, 0, 1, ()),
        (2, 0, 1, (EVIDENCE_FRAGMENT_RATCHET,)),
        (0, 1, None, (EVIDENCE_ANCHOR_MISSING,)),
        (1, 1, 0, (EVIDENCE_ANCHOR_MISSING, EVIDENCE_FRAGMENT_RATCHET)),
    ],
)
def test_ratchet_codes_boundaries(
    fragment_only: int, missing: int, baseline: int | None, expected: tuple[str, ...]
) -> None:
    assert ratchet_codes(fragment_only, missing, baseline) == expected


def test_report_codes_are_delegated_to_ratchet_codes(root: Path) -> None:
    cases = (
        (f"{TARGET} · {VERBATIM}\n", None),
        (f"{TARGET} · {VERBATIM} 另外的词\n", None),
        (GHOST, 3),
    )
    for text, baseline in cases:
        report = anchors(text, root, baseline)
        assert report.codes == ratchet_codes(report.fragment_only, report.missing, baseline)


def test_module_has_no_write_surface() -> None:
    module_file = evidence.__file__
    assert module_file is not None
    source = Path(module_file).read_text(encoding="utf-8")
    for token in ("write_text", "INSERT", "UPDATE", "session"):
        assert token not in source


def test_load_baseline_missing_file_is_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _use_baseline_file(monkeypatch, tmp_path / "absent.json")
    assert load_baseline(tmp_path, "run-1") == 0


@pytest.mark.parametrize("payload", ["{not json", "[1, 2]", '"7"', '{"default": "3"}'])
def test_load_baseline_broken_payload_is_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(payload, encoding="utf-8")
    _use_baseline_file(monkeypatch, path)
    assert load_baseline(tmp_path, "run-1") == 0


def test_load_baseline_priority_is_run_then_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"default": 3, "runs": {"run-1": 5}}), encoding="utf-8")
    _use_baseline_file(monkeypatch, path)
    assert load_baseline(tmp_path, "run-1") == 5
    assert load_baseline(tmp_path, "run-2") == 3
    assert load_baseline(tmp_path) == 3


def test_load_baseline_without_default_or_run_key_is_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps({"runs": {"other": 7}}), encoding="utf-8")
    _use_baseline_file(monkeypatch, path)
    assert load_baseline(tmp_path, "run-1") == 0
    assert load_baseline(tmp_path) == 0


def test_load_baseline_respects_the_constant_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "custom.json"
    path.write_text(json.dumps({"default": 4}), encoding="utf-8")
    monkeypatch.setattr(evidence, "BASELINE_FILE", str(path))
    assert load_baseline(tmp_path, "run-1") == 4


def test_shipped_baseline_is_zero_for_every_run(tmp_path: Path) -> None:
    assert load_baseline(tmp_path) == 0
    assert load_baseline(tmp_path, "2026-09-30-020000") == 0


def test_missing_baseline_file_ratchets_the_fragment_probe_red(
    monkeypatch: pytest.MonkeyPatch, root: Path
) -> None:
    _use_baseline_file(monkeypatch, root / "absent.json")
    report = anchors(f"{TARGET} · {VERBATIM} 另外的词\n", root, load_baseline(root, "run-1"))
    assert report.baseline == 0
    assert report.hits[0].verdict == Verdict.FRAGMENT_ONLY
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)
