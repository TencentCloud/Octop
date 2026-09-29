"""T06 / B3 — 双向变异验证：正向变异体 · 假阴性探针 · 模糊匹配反例。

契约：``team/2026-09-30-020000/PLAN.md`` §4（判定式与棘轮）· §6 验收命令 #10；
``SPEC.md`` B3 / A7 / A8 / A9。被测实现 = ``src/octop/infra/agents/teams/evidence.py``
（T03 已交付：``anchors()`` / ``ratchet_codes()`` / ``load_baseline()`` / 三级判定）。

★ 全部断言「仅本地可观测」：纯函数 + ``tmp_path`` 夹具，无网络、无真 HTTP、无 git、
不写 ``src/**``。两条判别性对照（[M1] 模糊匹配变异体 · [M2] ``>`` → ``>=``）一律用
``monkeypatch`` 在内存里注入，被测源文件逐字不动（sha256 自证见交付回报）。

★ 覆盖三面（``SKILL.md:135``「只验证能抓真缺陷不够，还要验证不会漏」）：
正向变异体（编造锚点 ⇒ 必红）· 假阴性探针（片段命中 ⇒ 弱证据必被抓住）·
模糊匹配反例（**一字之差**必 ``MISSING``，且该反例经 [M1] 证明有判别力）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from octop.infra.agents.teams import evidence
from octop.infra.agents.teams.evidence import (
    EVIDENCE_ANCHOR_MISSING,
    EVIDENCE_FRAGMENT_RATCHET,
    EvidenceReport,
    Verdict,
    anchors,
    load_baseline,
    ratchet_codes,
)

# --- 夹具常量（仅本地可观测） --------------------------------------------------

TARGET = "src/pkg/target.py"
VERBATIM = "锚点整串逐字命中"
ABSENT_TOKEN = "QANonexistentProbe"  # 编造符号名：任何目标文件都不含
FRAGMENT_PROBE = f"function {ABSENT_TOKEN}"  # A8 形态：整串不命中，token `function` 命中
KEYWORDLESS = "src/pkg/keywordless.py"

# 目标文件正文：含整串锚点，且含 `function` 关键字（A8 的片段命中源）
TARGET_BODY = f"第一行\n{VERBATIM}\nfunction target_helper() {{ return 1; }}\ntail\n"
# 同一正文但剔除 `function`：证明 A7 字面形态的判定依赖目标正文
KEYWORDLESS_BODY = f"第一行\n{VERBATIM}\ntail\n"

# 「一字之差」反例：同长度单字符替换（子串语义下不可能是 EXACT）
ONE_CHAR_SUBSTITUTED = VERBATIM[:-1] + "申"
# 「一字之差」反例：单字符插入
ONE_CHAR_INSERTED = VERBATIM[:4] + "申" + VERBATIM[4:]
# 「少一字」：在子串语义下**本就是**合法 EXACT（P1 只要求整串逐字出现），
# 故它不是模糊匹配反例，单独登记，防止有人误把子串语义改成词边界。
ONE_CHAR_DELETED = VERBATIM[:-1]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """最小工作区：一个目标文件 · 一个无关键字同形文件 · 一个目录 · 一个裸文件名。"""
    target = tmp_path / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_BODY, encoding="utf-8")
    (tmp_path / KEYWORDLESS).write_text(KEYWORDLESS_BODY, encoding="utf-8")
    (tmp_path / "src" / "pkg" / "dir").mkdir()
    (tmp_path / "floating.py").write_text(TARGET_BODY, encoding="utf-8")
    return tmp_path


def _line(path: str, anchor: str, line: str | None = None) -> str:
    """构造一条锚点行（canonical 形式 ``<path> · <anchor> @ <line>``）。"""
    slot = f" @ {line}" if line is not None else ""
    return f"- {path} · {anchor}{slot}\n"


def _only(report: EvidenceReport) -> evidence.AnchorHit:
    assert len(report.hits) == 1, report.hits
    return report.hits[0]


def _assert_fabricated_anchor_is_red(report: EvidenceReport) -> None:
    """编造锚点=判红的冻结期望（正向变异体的公共断言，对照复用）。"""
    assert report.exact == 0
    assert _only(report).verdict == Verdict.MISSING
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)
    assert EVIDENCE_FRAGMENT_RATCHET not in report.codes


def _assert_one_char_off_is_missing(root: Path, anchor: str) -> None:
    """一字之差 ⇒ ``MISSING`` 的冻结期望（模糊匹配反例的公共断言，[M1] 复用）。"""
    report = anchors(_line(TARGET, anchor), root, 0)
    assert report.exact == 0
    assert _only(report).verdict == Verdict.MISSING
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


def _assert_ratchet_boundary_is_green() -> None:
    """``fragment_only == baseline`` ⇒ 不报码（棘轮边界格的公共断言，[M2] 复用）。

    ★ 经 ``evidence.ratchet_codes`` 解析（与 ``anchors()`` 内部同一解析路径），
    这样内存变异体才能作用到这条断言上。
    """
    assert evidence.ratchet_codes(2, 0, 2) == ()
    assert evidence.ratchet_codes(0, 0, 0) == ()


# =====================================================================
# 1. ★★ 正向变异体：编造锚点 ⇒ 必须判红（仅本地可观测）
# =====================================================================


def test_mutation_nonexistent_path_is_red(root: Path) -> None:
    """形态 a：路径不存在（编造路径 + 编造锚点）⇒ MISSING + EVIDENCE_ANCHOR_MISSING。"""
    report = anchors(_line("src/pkg/ghost_probe.py", ABSENT_TOKEN), root, 0)
    _assert_fabricated_anchor_is_red(report)
    assert _only(report).reason == "path not found under root"


def test_mutation_existing_path_absent_content_is_red(root: Path) -> None:
    """形态 b：路径存在但正文不存在该内容（编造符号名）⇒ MISSING + 判红。"""
    assert ABSENT_TOKEN not in TARGET_BODY  # 夹具自证：目标正文确实不含该符号
    report = anchors(_line(TARGET, ABSENT_TOKEN), root, 0)
    _assert_fabricated_anchor_is_red(report)
    assert _only(report).reason == "no token hit"


def test_mutation_a7_literal_form_is_never_green(root: Path) -> None:
    """A7 字面形态 ``function QANonexistentProbe``：目标含 `function` ⇒ 弱证据（仍红）。

    ★ 登记取舍：A7 的字面串只有在目标正文**不含** token `function` 时才走 ``MISSING``；
    含该 token 时降级为 ``FRAGMENT_ONLY`` + 棘轮判红。两条路径都不是绿 ⇒ A7 的
    「判红」意图成立，但「必 ``MISSING``」的字面读法对 Python/JS 目标过强。
    """
    with_keyword = anchors(_line(TARGET, FRAGMENT_PROBE), root, 0)
    assert _only(with_keyword).verdict == Verdict.FRAGMENT_ONLY
    assert with_keyword.exact == 0
    assert with_keyword.codes == (EVIDENCE_FRAGMENT_RATCHET,)

    without_keyword = anchors(_line(KEYWORDLESS, FRAGMENT_PROBE), root, 0)
    _assert_fabricated_anchor_is_red(without_keyword)


# =====================================================================
# 2. ★★ 假阴性探针：整串不命中但 token（≥2 字符）命中 ⇒ 弱证据必被抓住
# =====================================================================


def test_false_negative_probe_is_weak_evidence_with_explicit_zero_baseline(root: Path) -> None:
    """A8：片段命中 ⇒ ``FRAGMENT_ONLY``；基线 0 ⇒ ``EVIDENCE_FRAGMENT_RATCHET``。"""
    report = anchors(_line(TARGET, FRAGMENT_PROBE), root, 0)
    hit = _only(report)
    assert hit.verdict == Verdict.FRAGMENT_ONLY
    assert hit.reason == "token=function"
    assert (report.exact, report.fragment_only, report.missing) == (0, 1, 0)
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)
    assert EVIDENCE_ANCHOR_MISSING not in report.codes


def test_false_negative_probe_cjk_fragment_is_weak_evidence(root: Path) -> None:
    """中文口径（R9）：整串多出尾巴 ⇒ 切出的 CJK token 逐字命中 ⇒ 弱证据。"""
    report = anchors(_line(TARGET, f"{VERBATIM} 之外的尾巴"), root, 0)
    hit = _only(report)
    assert hit.verdict == Verdict.FRAGMENT_ONLY
    assert hit.reason == f"token={VERBATIM}"
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)


def test_fragment_token_shorter_than_two_chars_is_discarded(root: Path) -> None:
    """长度阈值边界：唯一「命中」的 token 长度 < 2 ⇒ 丢弃 ⇒ 判 ``MISSING``。"""
    report = anchors(_line(TARGET, f"{VERBATIM[0]} 甲"), root, 0)
    assert _only(report).verdict == Verdict.MISSING
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


def test_false_negative_probe_ratchets_red_when_baseline_file_is_absent(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """基线缺失 ⇒ ``load_baseline`` = 0 ⇒ 第一条弱证据即红（fail-closed，I7）。"""
    monkeypatch.setattr(evidence, "_baseline_path", lambda: tmp_path / "no_such_baseline.json")
    baseline = load_baseline(root, "T06-run")
    assert baseline == 0
    report = anchors(_line(TARGET, FRAGMENT_PROBE), root, baseline)
    assert report.baseline == 0
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)


def test_false_negative_probe_with_none_baseline_is_red(root: Path) -> None:
    """``baseline=None`` 与 0 同口径 ⇒ 弱证据判红（§2.2 / §4.3）。"""
    report = anchors(_line(TARGET, FRAGMENT_PROBE), root, None)
    assert report.baseline == 0
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)


# =====================================================================
# 3. ★★ 模糊匹配反例（核心）：一字之差必须 MISSING（仅本地可观测）
# =====================================================================


def test_one_char_substitution_is_missing(root: Path) -> None:
    """同长度单字符替换（「命」→「申」）⇒ 整串不命中 ⇒ 判 ``MISSING``。"""
    _assert_one_char_off_is_missing(root, ONE_CHAR_SUBSTITUTED)


def test_one_char_insertion_is_missing(root: Path) -> None:
    """单字符插入 ⇒ 整串不命中 ⇒ 判 ``MISSING``（禁止编辑距离兜底）。"""
    _assert_one_char_off_is_missing(root, ONE_CHAR_INSERTED)


def test_one_char_deletion_is_exact_by_substring_semantics(root: Path) -> None:
    """★ 口径登记：少一字 ⇒ 该串**是**目标正文的子串 ⇒ 依 P1 合法 ``EXACT``。

    这不是模糊匹配反例（子串语义下逐字命中成立），登记它是为了防止有人把
    「一字之差必红」误读成「必须词边界匹配」——后者会把合法的子串收紧成假红。
    """
    report = anchors(_line(TARGET, ONE_CHAR_DELETED), root, 0)
    assert _only(report).verdict == Verdict.EXACT
    assert report.codes == ()


# --- [M1] 判别性对照：注入「模糊匹配变异体」（仅内存，不改源文件） -------------------


def _levenshtein(left: str, right: str) -> int:
    """朴素 DP 编辑距离（只服务于变异体，绝不进入被测实现）。"""
    previous = list(range(len(right) + 1))
    for row, char_left in enumerate(left, start=1):
        current = [row]
        for column, char_right in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (char_left != char_right),
                )
            )
        previous = current
    return previous[-1]


def _has_window_within_edit_distance_one(anchor: str, text: str) -> bool:
    """``anchor`` 与 ``text`` 的某个窗口（长度 ±1）编辑距离 ≤ 1。"""
    for width in (len(anchor) - 1, len(anchor), len(anchor) + 1):
        if width <= 0:
            continue
        for start in range(len(text) - width + 1):
            if _levenshtein(anchor, text[start : start + width]) <= 1:
                return True
    return False


def _fuzzy_classify(
    original: Callable[[Path, str, str, str | None], evidence.AnchorHit],
) -> Callable[[Path, str, str, str | None], evidence.AnchorHit]:
    """变异体 [M1]：把 ``EXACT`` 判定换成「编辑距离 ≤ 1 的窗口存在」。

    只在**原实现判 MISSING 且已通过 P1–P4 硬拒**的位置接管，因此变异体不是
    「永远判绿」的退化体：编造锚点仍判 ``MISSING``（对照内自证）。
    """

    def classify(root: Path, path: str, anchor: str, line: str | None) -> evidence.AnchorHit:
        hit = original(root, path, anchor, line)
        if hit.verdict != Verdict.MISSING:
            return hit
        if "/" not in path or not anchor or hit.reason == "anchor embeds a line number":
            return hit
        target = Path(root) / path
        if not target.is_file():
            return hit
        if _has_window_within_edit_distance_one(anchor, target.read_text(encoding="utf-8")):
            return evidence.AnchorHit(
                path=path,
                anchor=anchor,
                line=line,
                verdict=Verdict.EXACT,
                reason="fuzzy mutant: edit distance <= 1",
            )
        return hit

    return classify


def test_contrast_m1_fuzzy_mutant_turns_the_one_char_case_green(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[M1] 模糊匹配变异体注入 ⇒ 第 3 条反例**必须红**（证明该用例有判别力）。

    ``仅本地可观测``：只 monkeypatch ``evidence._classify``；还原后再次断言冻结期望，
    证明变异不残留。
    """
    # [1] 真实现：冻结期望成立。
    _assert_one_char_off_is_missing(root, ONE_CHAR_SUBSTITUTED)

    # [2] 内存注入变异体（不触碰 src/**）。
    original = evidence._classify
    monkeypatch.setattr(evidence, "_classify", _fuzzy_classify(original))

    # [3] 变异体非退化：编造锚点仍判 MISSING（故 [4] 变绿只能归因于模糊匹配）。
    assert _only(anchors(_line(TARGET, ABSENT_TOKEN), root, 0)).verdict == Verdict.MISSING

    # [4] 同一条冻结断言在变异体下必须失败 ⇒ 一字之差反例抓得住模糊匹配。
    with pytest.raises(AssertionError):
        _assert_one_char_off_is_missing(root, ONE_CHAR_SUBSTITUTED)
    with pytest.raises(AssertionError):
        _assert_one_char_off_is_missing(root, ONE_CHAR_INSERTED)

    # [5] 变异体下的假绿：一字之差被升级成 EXACT 且无码（= 被抓住的那种缺陷）。
    mutant_report = anchors(_line(TARGET, ONE_CHAR_SUBSTITUTED), root, 0)
    assert _only(mutant_report).verdict == Verdict.EXACT
    assert _only(mutant_report).reason == "fuzzy mutant: edit distance <= 1"
    assert mutant_report.codes == ()

    # [6] 还原 ⇒ 冻结期望重新成立（无残留）。
    monkeypatch.undo()
    _assert_one_char_off_is_missing(root, ONE_CHAR_SUBSTITUTED)
    assert evidence._classify is original


# =====================================================================
# 4. ★ 棘轮边界：``fragment_only > baseline`` 才报码（严格大于 · 仅本地可观测）
# =====================================================================


@pytest.mark.parametrize(
    ("fragment_only", "baseline"),
    [(0, 0), (1, 1), (2, 2), (0, 3), (1, 5)],
)
def test_ratchet_equal_or_below_baseline_is_green(fragment_only: int, baseline: int) -> None:
    """``fragment_only == baseline``（及低于基线）⇒ **不**报码。"""
    assert ratchet_codes(fragment_only, 0, baseline) == ()


@pytest.mark.parametrize(
    ("fragment_only", "baseline"),
    [(1, 0), (2, 1), (3, 2), (1, None)],
)
def test_ratchet_strictly_above_baseline_is_red(fragment_only: int, baseline: int | None) -> None:
    """``fragment_only > baseline``（``None`` 按 0）⇒ 报 ``EVIDENCE_FRAGMENT_RATCHET``。"""
    assert ratchet_codes(fragment_only, 0, baseline) == (EVIDENCE_FRAGMENT_RATCHET,)


def test_missing_anchor_code_ignores_the_fragment_baseline() -> None:
    """``missing >= 1`` ⇒ 必报 ``EVIDENCE_ANCHOR_MISSING``，与基线高低无关。"""
    assert ratchet_codes(0, 1, 99) == (EVIDENCE_ANCHOR_MISSING,)
    assert ratchet_codes(5, 1, 5) == (EVIDENCE_ANCHOR_MISSING,)


def test_ratchet_boundary_end_to_end(root: Path) -> None:
    """端到端边界格：两条弱证据 · ``baseline=2`` 绿 / ``baseline=1`` 红。"""
    text = _line(TARGET, FRAGMENT_PROBE) * 2
    at_baseline = anchors(text, root, 2)
    assert (at_baseline.exact, at_baseline.fragment_only, at_baseline.missing) == (0, 2, 0)
    assert (at_baseline.baseline, at_baseline.codes) == (2, ())
    assert anchors(text, root, 1).codes == (EVIDENCE_FRAGMENT_RATCHET,)
    assert anchors(text, root, 5).codes == ()  # 棘轮只收紧：基线高于实测仍绿


def test_judge_is_pure_and_deterministic(root: Path) -> None:
    """SPEC「级联与计数」硬断言：判据无状态 ⇒ ``f(x) == f(x)``。"""
    text = _line(TARGET, VERBATIM) + _line(TARGET, FRAGMENT_PROBE) + _line(TARGET, ABSENT_TOKEN)
    assert anchors(text, root, 1) == anchors(text, root, 1)


def _snapshot(root: Path) -> list[tuple[str, int, int]]:
    return sorted(
        (item.relative_to(root).as_posix(), item.stat().st_size, item.stat().st_mtime_ns)
        for item in root.rglob("*")
        if item.is_file()
    )


def test_judge_is_read_only(root: Path) -> None:
    """I3：判据只读——判定前后 ``tmp_path`` 内文件集合 / size / mtime 逐字不变。"""
    before = _snapshot(root)
    anchors(_line(TARGET, VERBATIM) + _line(TARGET, ABSENT_TOKEN), root, 0)
    assert _snapshot(root) == before


# --- [M2] 判别性对照：把 ``>`` 改成 ``>=``（仅内存，不改源文件） -----------------------


def _ge_ratchet_codes(fragment_only: int, missing: int, baseline: int | None) -> tuple[str, ...]:
    """变异体 [M2]：与 ``ratchet_codes`` 逐字相同，唯一改动是 ``>`` → ``>=``。"""
    codes: list[str] = []
    if missing >= 1:
        codes.append(EVIDENCE_ANCHOR_MISSING)
    if fragment_only >= (baseline or 0):
        codes.append(EVIDENCE_FRAGMENT_RATCHET)
    return tuple(codes)


def test_contrast_m2_ge_ratchet_breaks_the_boundary_cell(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[M2] ``>`` → ``>=`` ⇒ 第 4 条的 ``==`` 边界格**必须红**（仅本地可观测）。"""
    # [1] 真实现：``==`` 边界格绿。
    _assert_ratchet_boundary_is_green()

    # [2] 内存注入 ``>=`` 变异体。
    monkeypatch.setattr(evidence, "ratchet_codes", _ge_ratchet_codes)

    # [3] 同一条冻结断言必须失败 ⇒ 边界格有判别力。
    with pytest.raises(AssertionError):
        _assert_ratchet_boundary_is_green()

    # [4] 端到端假红：全绿报告（fragment_only == baseline == 2）被追加棘轮码。
    text = _line(TARGET, VERBATIM) + _line(TARGET, FRAGMENT_PROBE) * 2
    mutant_report = anchors(text, root, 2)
    assert (mutant_report.exact, mutant_report.fragment_only, mutant_report.missing) == (1, 2, 0)
    assert mutant_report.codes == (EVIDENCE_FRAGMENT_RATCHET,)

    # [5] 还原 ⇒ 边界格重新为绿（无残留）。
    monkeypatch.undo()
    assert anchors(text, root, 2).codes == ()
    assert evidence.ratchet_codes is ratchet_codes


# =====================================================================
# 5. ★ MISSING 的硬拒（P1–P4 逐格 · 仅本地可观测）
# =====================================================================


@pytest.mark.parametrize(
    ("path", "anchor", "reason"),
    [
        pytest.param(
            "floating.py",
            VERBATIM,
            "bare filename (path must contain a directory)",
            id="bare-filename",
        ),
        pytest.param(
            TARGET, f"{VERBATIM} 见 12-34 行", "anchor embeds a line number", id="embedded-range"
        ),
        pytest.param(
            TARGET, f"{VERBATIM}（12）", "anchor embeds a line number", id="embedded-paren-line"
        ),
        pytest.param(
            "src/pkg/../../../t06_outside_probe.py",
            VERBATIM,
            "path escapes root",
            id="dotdot-escape",
        ),
        pytest.param(
            "src/pkg/ghost.py", VERBATIM, "path not found under root", id="path-not-found"
        ),
        pytest.param("src/pkg/dir", VERBATIM, "path is not a file", id="not-a-file"),
        pytest.param(TARGET, "``", "empty anchor", id="empty-anchor"),
    ],
)
def test_missing_hard_rejects(root: Path, path: str, anchor: str, reason: str) -> None:
    report = anchors(_line(path, anchor), root, 0)
    hit = _only(report)
    assert hit.verdict == Verdict.MISSING
    assert hit.reason == reason
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


def test_dotdot_escape_is_missing_even_when_the_target_really_hits(root: Path) -> None:
    """T06 缺陷② 判别性正对照：root **之外**真实存在的逐字命中文件 ⇒ 仍必须硬拒。

    修前该格为 ``EXACT / 'verbatim hit' / codes=()``（越界文件被当证据）；修后包含性
    硬拒先于读取与逐字匹配。``仅本地可观测``：探针文件建在 ``tmp_path.parent``。
    """
    outside = root.parent / "t06_outside_probe.py"
    outside.write_text(TARGET_BODY, encoding="utf-8")
    try:
        report = anchors(_line("src/pkg/../../../t06_outside_probe.py", VERBATIM), root, 0)
        hit = _only(report)
        assert hit.verdict == Verdict.MISSING
        assert hit.reason == "path escapes root"
        assert report.codes == (EVIDENCE_ANCHOR_MISSING,)
    finally:
        outside.unlink()


def test_bare_filename_has_no_suffix_matching(root: Path) -> None:
    """P1 判别性正对照：同一锚点换成 ``./floating.py``（含 ``/``）⇒ ``EXACT``。

    故「裸文件名」格的 ``MISSING`` 只能归因于 P1 本身——锚点内容其实是找得到的，
    实现没有做后缀兜底。
    """
    assert _only(anchors(_line("floating.py", VERBATIM), root, 0)).verdict == Verdict.MISSING
    assert _only(anchors(_line("./floating.py", VERBATIM), root, 0)).verdict == Verdict.EXACT


def test_hard_rejects_beat_the_token_fallback(root: Path) -> None:
    """硬拒优先：被硬拒的锚点即便 token 真命中目标正文也**不得**降级为弱证据。"""
    report = anchors(_line("floating.py", f"{VERBATIM} 尾巴"), root, 0)
    assert _only(report).verdict == Verdict.MISSING
    assert (report.fragment_only, report.missing) == (0, 1)
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


# =====================================================================
# 6. ★ 围栏豁免：成对闭合才豁免 · 未闭合 ⇒ 其后照常判定（仅本地可观测）
# =====================================================================


def test_paired_fence_exempts_the_reference_inside(root: Path) -> None:
    """A9 半边：成对闭合 ⇒ 块内锚点不抽取、不计分 ⇒ ``MISSING`` 计数 **0**。"""
    text = f"```\n{_line(TARGET, ABSENT_TOKEN)}```\n"
    report = anchors(text, root, 0)
    assert report.hits == ()
    assert (report.exact, report.fragment_only, report.missing) == (0, 0, 0)
    assert report.codes == ()


def test_unclosed_fence_exempts_nothing(root: Path) -> None:
    """A9 另半边：未闭合围栏 ⇒ 其后全部行照常判定（fail-closed）⇒ 计数 **1**。"""
    text = f"```\n{_line(TARGET, ABSENT_TOKEN)}"
    report = anchors(text, root, 0)
    assert (report.exact, report.fragment_only, report.missing) == (0, 0, 1)
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


def test_fence_pair_exempts_only_its_inside(root: Path) -> None:
    """闭合对只豁免**块内**：块内 EXACT 行不计数，块外 MISSING 行照常判红。"""
    text = f"```\n{_line(TARGET, VERBATIM)}```\n{_line(TARGET, ABSENT_TOKEN)}"
    report = anchors(text, root, 0)
    assert (report.exact, report.fragment_only, report.missing) == (0, 0, 1)
    assert report.codes == (EVIDENCE_ANCHOR_MISSING,)


# =====================================================================
# 7. ★ 基线 fail-closed：缺失 / 坏 JSON / 非对象 / 无 run 键 / 非整数 ⇒ 按 0
# =====================================================================


def _use_baseline_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: str | None
) -> Path:
    path = tmp_path / "baseline_probe.json"
    if payload is not None:
        path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(evidence, "_baseline_path", lambda: path)
    return path


@pytest.mark.parametrize(
    ("payload", "run_id"),
    [
        pytest.param(None, None, id="file-missing"),
        pytest.param("{not json", None, id="bad-json"),
        pytest.param("[1, 2, 3]", None, id="json-array"),
        pytest.param("3", None, id="json-number"),
        pytest.param('"0"', None, id="json-string"),
        pytest.param(json.dumps({"default": 0, "runs": {}}), "T06-run", id="no-run-key"),
        pytest.param(json.dumps({"runs": {"other": 3}}), "T06-run", id="other-run-key-only"),
        pytest.param(json.dumps({"default": "3"}), None, id="string-default"),
        pytest.param(json.dumps({"default": 1.5}), None, id="float-default"),
        pytest.param(json.dumps({"default": True}), None, id="bool-default"),
        pytest.param(json.dumps({"runs": {"T06-run": True}}), "T06-run", id="bool-run"),
        pytest.param(json.dumps({"default": None}), None, id="null-default"),
    ],
)
def test_baseline_fails_closed_to_zero(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: str | None,
    run_id: str | None,
) -> None:
    _use_baseline_payload(monkeypatch, tmp_path, payload)
    assert load_baseline(root, run_id) == 0


def test_baseline_priority_is_run_then_default(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """正对照：``runs[run_id]`` → ``default`` → 0（证明上面的 0 不是「恒 0」）。"""
    _use_baseline_payload(monkeypatch, tmp_path, json.dumps({"default": 1, "runs": {"T06-run": 2}}))
    assert load_baseline(root, "T06-run") == 2
    assert load_baseline(root, "absent-run") == 1
    assert load_baseline(root) == 1


def test_shipped_baseline_is_zero_for_every_run(root: Path) -> None:
    """出厂基线 ``{"default": 0, "runs": {}}`` ⇒ 任何 run 都是 0（首条弱证据即红）。

    ★ canary：若要把基线**上调**（§4.3 升级条件②），必须同一 PR 内改这里并说明，
    否则本用例转红即为「悄悄放宽棘轮」的显式信号。
    """
    assert load_baseline(root) == 0
    assert load_baseline(root, "T03") == 0
    assert load_baseline(root, "T06-never-seen") == 0


def test_broken_baseline_still_ratchets_the_probe_red(
    root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """端到端 fail-closed：坏 JSON ⇒ 基线 0 ⇒ 假阴性探针仍判红（不因坏文件而漏）。"""
    _use_baseline_payload(monkeypatch, tmp_path, "{not json")
    report = anchors(_line(TARGET, FRAGMENT_PROBE), root, load_baseline(root, "T06-run"))
    assert report.baseline == 0
    assert report.codes == (EVIDENCE_FRAGMENT_RATCHET,)
