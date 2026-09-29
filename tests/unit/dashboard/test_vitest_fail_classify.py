"""★ 可测性门（`D-8`）的回归用例 · run `2026-09-29-130721`（卡 `T-D8-EMPTY-FALSE-GREEN` · `I1`）。

★★ 目的：把分类器的**四级退出码**（`0`/`1`/`2`/`3`）**钉死** —— ★ 本文件**不依赖真实 vitest** ✓
（★ 用 `sys.executable` 跑脚本、从 `stdin` 喂样本 · ★ 断言的是**退出码**，不是输出文本）。

★ 契约：`team/2026-09-29-130721/PLAN.md §3`（`P2'`）· `§5`（八条逐字钉回）· `§11-①`（`AC-9`）· `§6`（用例落点）。
★ 注意：★ `P2'` 支路 ② 【不得】只认 `:n` 键 —— 只认它会把**真绿**（`218 passed (218)`）判成「无输入 ⇒ 3」✗
  ⇒ 故本文件**必须**有「正常全绿 ⇒ 0」这一档（见 `test_green_summary_forms_are_input`）。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "dashboard" / "scripts" / "vitest-fail-classify.py"
SAMPLE_7FAILED = REPO_ROOT / "team" / "2026-09-29-075707" / "samples" / "vitest-run1-7failed.txt"

GREEN = " Test Files  218 passed (218)\n      Tests  1347 passed (1347)\n"
SUITE_LOAD = (
    " FAIL  src/x.test.tsx [ src/x.test.tsx ]\n"
    " Test Files  1 failed | 217 passed (218)\n"
    "      Tests  1347 passed (1347)\n"
)
CASE_FAIL = (
    " FAIL  src/x.test.tsx > suite > case\n"
    " Test Files  1 failed | 217 passed (218)\n"
    "      Tests  2 failed | 1345 passed (1347)\n"
)
AC9_A = "Test Files  1 passed (1)\nTests  2 failed | 5 passed (7)\n"
AC9_B = "Tests  3 failed | 10 passed (13)\n"


def run_classifier(stdin_text: str, *args: str) -> int:
    """★ 跑分类器 ⇒ 返回**退出码**（★ `input=` 喂样本 ⇒ 不依赖 shell / cwd / 平台 ✓）。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode


# ---- ① 无输入 / 无法解析 ⇒ 3 ------------------------------------------------


def test_empty_input_is_three() -> None:
    assert run_classifier("") == 3


def test_garbage_input_is_three() -> None:
    assert run_classifier("hello world\n") == 3


def test_junk_summary_lines_are_three() -> None:
    """★ `FIND-1` 三条反例：★★ 只判行前缀的 `P2` 会被它们骗过（旧行为 = `0`）✗。"""
    assert run_classifier(" Test Files  oops\n") == 3
    assert run_classifier(" Tests  ???\n") == 3
    assert run_classifier(" Tests  abc failed nope\n") == 3


# ---- ② 有输入的三档 ⇒ 0 / 1 / 2 ---------------------------------------------


def test_green_summary_forms_are_input() -> None:
    """★★ 「正常全绿 ⇒ `0`」：★ 若支路 ② 只认 `:n` 键 ⇒ 本档会变 `3`（**假红**）⇒ 必须钉住 ✓。"""
    assert run_classifier(GREEN) == 0


def test_suite_load_failure_is_one() -> None:
    assert run_classifier(SUITE_LOAD) == 1


def test_case_failure_is_two() -> None:
    assert run_classifier(CASE_FAIL) == 2


def test_fail_line_without_summary_is_not_three() -> None:
    """★ `SL-2`：★ 只有 `FAIL` 行、摘要行缺失 ⇒ ★ **按 `FAIL` 形态定档 · 绝不判 `3`** ✓。"""
    assert run_classifier(" FAIL  src/x.test.tsx > suite > case\n") == 2
    assert run_classifier(" FAIL  src/x.test.tsx [ src/x.test.tsx ]\n") == 1


# ---- ③ `AC-9` 守卫（`counts` 报失败而分类为空）⇒ 1 ---------------------------


def test_ac9_counts_failed_but_nothing_classified_is_one() -> None:
    """★★ 修前两条都是 `0`（假绿：摘要写 `2 failed` 而门报绿）· ★ 修后必须 `1` ✓。"""
    assert run_classifier(AC9_A) == 1
    assert run_classifier(AC9_B) == 1


def test_original_guard_branch_still_holds() -> None:
    """★ 原 `classified < files_failed` 那一支**保留**（★ 两支并存）⇒ `999 failed` 仍 `1` ✓。"""
    assert run_classifier(" Test Files  999 failed (218)\n") == 1


def test_unclassified_fail_line_is_one() -> None:
    """★ `FIND-7`（`repair-2` · 第 10 条落绿路径）：★ 有 `FAIL` 行但**归类不了** ⇒ ★ **必须 `1`** ✓。

    ★★ 修前 = `0`（假绿：`FAIL` 行既不进 `sl`/`cf`，摘要又无失败计数 ⇒ 落 fall-through ✗）。
    ★ 两种形态：① 不匹配完整 `FAIL` 正则（`FAIL x ??? weird`）
                ② 匹配但**无可归类组**（裸 `FAIL  src/x.test.tsx` · 既无 `[ … ]` 也无 `> …`）。
    ★ 语义：★ 「**读到了 `FAIL` 行但读不懂**」⇒ `1`（★ 与 `3` 的「没读到输入」不同 ✓）。
    """
    assert (
        run_classifier(
            "FAIL src/x.test.tsx ??? weird\n"
            " Test Files  218 passed (218)\n"
            "      Tests  1347 passed (1347)\n"
        )
        == 1
    )
    assert run_classifier(" FAIL  src/x.test.tsx\n") == 1


# ---- ④ `--sample` / `--self-test` ------------------------------------------


def test_self_test_is_zero() -> None:
    assert run_classifier("", "--self-test") == 0


def test_real_sample_is_one() -> None:
    assert SAMPLE_7FAILED.is_file(), f"真实样本缺失：{SAMPLE_7FAILED}"
    assert run_classifier("", "--sample", str(SAMPLE_7FAILED)) == 1


def test_empty_sample_file_is_three(tmp_path: pathlib.Path) -> None:
    """★ `SL-3`：★ 空 `--sample`（修前 `0`）⇒ ★ 修后应 `3` ✓。"""
    empty = tmp_path / "empty-sample.txt"
    empty.write_text("", encoding="utf-8")
    assert run_classifier("", "--sample", str(empty)) == 3
