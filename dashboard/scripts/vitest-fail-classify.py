#!/usr/bin/env python3
"""★ 可测性门（`D-8`）：区分 vitest 的三类"红" —— ★ 并把「没跑」与「跑了没过」分开。

★★ 本批的核心问题（`§20.26` 家族的第四级 · 五块之③）：
   vitest 的 `Tests` 口径把 **file-level FAIL 记为【0 个用例】** ✗
   ⇒ 「`6 failed | 1329 passed`」里**完全不含**那 3 个**加载失败**的文件 ✓
   ⇒ ★★ 于是「**没跑**」与「**跑了没过**」在计数上【看起来一样】✗✓

★★ 判别特征（★ 由 `RESEARCH` 给出 · 本文件用【真实输出片段】自证 ✓ —— `L33`）：
   · `FAIL  src/x.test.ts [ src/x.test.ts ]`        ⇒ ★ **带方括号 = 套件【加载失败】**（`suite-load`）
   · `FAIL  src/x.test.ts > suite > case`           ⇒ ★ **无方括号 = 用例失败**（`case-fail`）
   · `Test Files N failed | M passed (T)` / `Tests N failed | M passed (T)` ⇒ ★ 两个口径须【分别报】

用法：
    npx vitest run 2>&1 | python3 tools/vitest-fail-classify.py            # 从 stdin 读
    python3 tools/vitest-fail-classify.py --self-test                      # ★ 自证：真实片段 ⇒ 三类都能分
退出码：★ 有 `suite-load`（= 有文件**根本没跑**）⇒ **1** ✓；只有 `case-fail` ⇒ **2**；全绿 ⇒ **0**。
"""
import argparse
import pathlib
import re
import sys

FAIL = re.compile(r"^\s*FAIL\s+(\S+?)(\s*\[[^\]]*\])?\s*(>.*)?$")
COUNTS = re.compile(r"^\s*(Test Files|Tests)\s+(.*)$")
NFAIL = re.compile(r"(\d+)\s+failed")

# ★★ 真实输出片段（★ 取自 `RESEARCH.md` §C/§A.4 的逐字摘录 ✓）
FIXTURE = """\
 FAIL  src/components/DocumentPreviewCore.docxSanitize.test.ts [ src/components/DocumentPreviewCore.docxSanitize.test.ts ]
ReferenceError: DOMMatrix is not defined
 FAIL  src/api/modules/publishedExperts.test.ts > publishedExpertsApi > lists installed experts
AssertionError: expected [] to deeply equal ['thr_from_a']
 FAIL  src/hooks/useSessions.test.ts > useSessions agent switch > ensureThreadInList returns found when the thread is already listed
 Test Files  6 failed | 212 passed (218)
      Tests  6 failed | 1329 passed (1335)
"""


def classify(text: str):
    """⇒ (suite_load, case_fail, counts)"""
    suite_load, case_fail, counts = [], [], {}
    for line in text.splitlines():
        m = FAIL.match(line)
        if m:
            path, bracket, case = m.group(1), m.group(2), m.group(3)
            (suite_load if bracket else case_fail).append(path if bracket else f"{path}{(case or '')}")
            continue
        c = COUNTS.match(line)
        if c:
            counts[c.group(1)] = c.group(2).strip()
            m2 = NFAIL.search(c.group(2))
            if m2:
                counts[c.group(1) + ":n"] = m2.group(1)
    return sorted(set(suite_load)), sorted(set(case_fail)), counts


def report(suite_load, case_fail, counts):
    print("★★ 可测性门（`D-8`）：vitest 红的【两类】分开报")
    print(f"  · ★ 套件【加载失败】（= 这些文件【根本没跑】）✗ : {len(suite_load)} 个")
    for f in suite_load:
        print(f"      ✗ {f}")
    print(f"  · ★ 用例失败（= 跑了但没过）             : {len(case_fail)} 个")
    for f in case_fail[:10]:
        print(f"      ✗ {f}")
    if counts:
        print("  · ★ 两个计数口径（★ 须分别看 ✗ —— `Tests` 口径【不含】加载失败 ✓）:")
        for k, v in counts.items():
            print(f"      {k}: {v}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true", help="★ 用真实片段自证判据【能红】")
    ap.add_argument("--sample", default=None, help="★ 回放一个样本文件（★ 如 research 跑 1 的 `7 failed` ✓）")
    a = ap.parse_args()
    if a.sample:
        text = pathlib.Path(a.sample).read_text(encoding="utf-8")
        print(f"★★ 回放样本：{a.sample}")
    else:
        text = FIXTURE if a.self_test else sys.stdin.read()
    if a.self_test:
        sl, cf, counts = classify(text)
        ok = (len(sl) == 1 and len(cf) == 2
              and sl[0].endswith("DocumentPreviewCore.docxSanitize.test.ts")
              and counts.get("Test Files", "").startswith("6 failed"))
        print("★★ 门判据【自证】（`L33`）：真实片段 ⇒ 1 套件加载失败 + 2 用例失败 + 两口径")
        report(sl, cf, counts)
        print(f"  ★ 自证结果 = {'PASS ✓' if ok else 'FAIL ✗（判据没抓到该抓的）'}")
        return 0 if ok else 1
    sl, cf, counts = classify(text)
    report(sl, cf, counts)
    # ★★★ L-1①：未知格式守卫 —— 「我读不懂 ≠ 全绿」（★ §20.26 的下一个形态 ✓）
    try:
        files_failed = int(counts.get("Test Files:n", "0"))
        tests_failed = int(counts.get("Tests:n", "0"))
    except ValueError:
        files_failed = tests_failed = 0
    classified = len(set(sl) | {f.split(">")[0].strip() for f in cf})
    if (files_failed or tests_failed) and classified < files_failed:
        print(f"  ✗★ 未知格式守卫：★ counts 报 {files_failed} 个文件失败，"
              f"而分类只认出 {classified} 个 ⇒ ★ 【有 FAIL 行没被识别】✗ ⇒ **不得判全绿** ✓")
        return 1
    if sl:
        print("  ★★ 结论：★ 有文件【没跑】⇒ 门【红】✓（★ 这正是「没跑 ≠ 跑了没过」的落地 ✓）")
        return 1
    if cf:
        print("  ★ 结论：★ 只有【用例失败】⇒ 门报 2（★ 是判据问题，不是「没跑」✗）")
        return 2
    print("  ★ 结论：★ 全绿 ⇒ 门报 0 ✓")
    return 0


if __name__ == "__main__":
    sys.exit(main())
