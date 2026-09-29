#!/usr/bin/env python3
"""★ 当前树纪律审计入口（`make audit`）—— 只读 · 只用标准库 · 不绑 `runDir`。

★ 契约来源 = `team/2026-09-29-103507/PLAN.md`（`§2`–`§8`）· `SPEC.md` · `AUTHORITY.md`。
★ 退出码 = `0` 全绿 / `1` 判据红 / `2` 未知格式守卫（fail-closed）/ `3` 用法或环境错误
  ⇒ ★ 优先级 `3 > 2 > 1 > 0` · ★ **任何非 0 = 红** · ★ 不使用 `|| true`。
"""
import argparse
import datetime
import json
import pathlib
import sys

sys.dont_write_bytecode = True   # ★ 只读：禁写 __pycache__（AC-5）

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    from scripts.audit import registry as reg
    from scripts.audit.criteria import docs_numbers
    import scripts.audit.criteria  # noqa: F401  ★ 导入即注册 7 条判据
else:
    from . import registry as reg
    from .criteria import docs_numbers  # noqa: F401
    from . import criteria  # noqa: F401

SCHEMA = "octop.audit/1"
EXIT_OK, EXIT_RED, EXIT_UNKNOWN, EXIT_USAGE = 0, 1, 2, 3
EXEMPTIONS_HINT = "★ 逐字坐标见 %s" % reg.EXEMPTIONS_REL


def build_parser():
    ap = argparse.ArgumentParser(prog="scripts/audit/current_tree.py")
    ap.add_argument("--json", action="store_true", help="输出单个 JSON（默认模式不含时刻/绝对路径）")
    ap.add_argument("--stamp", action="store_true", help="★ 追加 time/repo（★ 不参与幂等验收）")
    ap.add_argument("--out", default=None, help="★ 显式落盘 JSON（make audit 不传）")
    ap.add_argument("--only", default=None, help="只跑指定 id（逗号分隔；其余计入 skipped）")
    ap.add_argument("--repo", default=None, help="仓库根覆盖（默认 = parents[2]）")
    ap.add_argument("--doc", action="append", default=None, help="共享文档覆盖（可重复）")
    ap.add_argument("--list", action="store_true", help="列出冻结 id")
    return ap


def _normalize(res, item):
    """★ 三态守卫 + 空输入守卫（`input_digest.files` 为空 ⇒ `FAIL`）。"""
    if res.state not in (reg.OK, reg.FAIL, reg.UNKNOWN):
        return reg.Result(item["id"], item["kind"], reg.UNKNOWN,
                          message="判据返回了不认识的状态 ⇒ 不得记绿"), True
    if not res.files:
        fixed = reg.Result(item["id"], item["kind"], reg.FAIL, checked=res.checked,
                           skipped=res.skipped, exempted=res.exempted,
                           message="输入清单为空 ⇒ FAIL（%s）" % res.message,
                           hints=res.hints)
        return fixed, True
    return res, False


def run(repo, docs, only):
    table, table_violations = reg.load_exemptions(repo)
    index = reg.exemption_index(table)
    ctx = reg.Ctx(repo, docs, index, reg.head_commit(repo))
    results, bad_states, empty_inputs, not_run = [], [], [], []
    for item in reg.REGISTRY:
        if item["id"] == reg.GUARD_ID:
            continue
        if only and item["id"] not in only:
            not_run.append(item["id"])
            continue
        res, bad = _normalize(item["fn"](ctx), item)
        if bad:
            (bad_states if res.state == reg.UNKNOWN else empty_inputs).append(item["id"])
        results.append(res)
    coverage = {res.id: set(res.files) for res in results}
    deep = reg.deep_exemption_violations(repo, table, coverage)
    guard_facts = reg.registry_guard_facts(bad_states, empty_inputs)
    guard_facts["violations"].extend(table_violations + deep)
    guard_item = next(item for item in reg.REGISTRY if item["id"] == reg.GUARD_ID)
    ctx.guard_facts = guard_facts
    guard = guard_item["fn"](ctx)
    if only and reg.GUARD_ID not in only:
        not_run.append(reg.GUARD_ID)
    else:
        results.append(guard)
    if table_violations or deep:
        detail = " · ".join(table_violations + deep)
        for res in results:
            if res.id in reg.EXEMPTION_CONSUMERS:
                res.state = reg.FAIL
                res.message = "%s · ★ 豁免表校验：%s" % (res.message, detail)
    order = {cid: i for i, cid in enumerate(reg.FROZEN_IDS)}
    results.sort(key=lambda res: order.get(res.id, len(order)))
    return results, guard, sorted(set(not_run))


def summarize(results, not_run):
    states = [res.state for res in results]
    return {
        "checked": sum(res.checked for res in results),
        "skipped": sum(res.skipped for res in results) + len(not_run),
        "unknown_format": states.count(reg.UNKNOWN),
        "exempted": sum(res.exempted for res in results),
        "green": states.count(reg.OK),
        "red": states.count(reg.FAIL),
        "unknown": states.count(reg.UNKNOWN),
    }


def exit_code(results):
    states = [res.state for res in results]
    if reg.UNKNOWN in states:
        return EXIT_UNKNOWN
    if reg.FAIL in states:
        return EXIT_RED
    return EXIT_OK


def emit_human(results, summary, not_run, exempt_table, code, head, stamp):
    head_text = "★ 当前树纪律审计（只读 · 不绑 runDir）· at = %s" % (head or "unknown")
    if stamp:
        head_text += " · time = %s · repo = %s" % (datetime.datetime.now().astimezone().isoformat(timespec="seconds"), reg.repo_root())
    print(head_text)
    for res in results:
        print("[%s] %s · 已检查 %d · 跳过 %d · 豁免 %d · %s"
              % (res.id, reg.STATE_LABEL[res.state], res.checked, res.skipped, res.exempted, res.message))
        for hint in res.hints:
            print("    · 提示 [%s] %s" % (res.id, hint))
    if not_run:
        print("★ 未跑 %d 条（--only 排除 · 计入 skipped）：%s" % (len(not_run), ", ".join(not_run)))
    print("★ 汇总：已检查 %d · 跳过 %d · 未知格式 %d · 已豁免 %d · 判据 绿 %d / 红 %d / 未知 %d"
          % (summary["checked"], summary["skipped"], summary["unknown_format"], summary["exempted"],
             summary["green"], summary["red"], summary["unknown"]))
    entries = (exempt_table or {}).get("entries", [])
    print("★ 已豁免 %d 处（%s）" % (len(entries), EXEMPTIONS_HINT))
    for entry in entries:
        print("    · [%s] %s:%s「%s」⇒ 记账 = %s"
              % (entry.get("criterion"), entry.get("path"), entry.get("line"),
                 entry.get("anchor"), entry.get("ledger_card")))
        print("      · value_fragment = %s · reason = %s" % (entry.get("value_fragment"), entry.get("reason")))
    if code == EXIT_OK:
        print("★ 结论：全绿 ⇒ exit %d" % code)
    elif code == EXIT_UNKNOWN:
        print("★ 结论：★ 未知格式守卫触发（fail-closed）⇒ exit %d" % code)
    else:
        print("★ 结论：★ 有判据红 ⇒ exit %d" % code)


def main(argv=None):
    args = build_parser().parse_args(argv)
    repo = pathlib.Path(args.repo).resolve() if args.repo else reg.repo_root()
    if not repo.is_dir():
        print("★ 用法/环境错误：仓库根不存在：%s ⇒ exit %d" % (repo, EXIT_USAGE), file=sys.stderr)
        return EXIT_USAGE
    if args.list:
        for cid in reg.FROZEN_IDS:
            print(cid)
        return EXIT_OK
    only = None
    if args.only:
        only = {part.strip() for part in args.only.split(",") if part.strip()}
        unknown = sorted(only - set(reg.FROZEN_IDS))
        if not only or unknown:
            print("★ 用法错误：--only 含未知 id %s ⇒ exit %d" % (unknown or "（空）", EXIT_USAGE), file=sys.stderr)
            return EXIT_USAGE
    docs = [pathlib.Path(item) for item in (args.doc or list(docs_numbers.DEFAULT_DOCS))]
    results, _guard, not_run = run(repo, docs, only)
    summary = summarize(results, not_run)
    code = exit_code(results)
    table, _ = reg.load_exemptions(repo)
    payload = {
        "schema": SCHEMA,
        "at": {"commit": reg.head_commit(repo) or "unknown"},
        "criteria": [res.as_dict(reg.digest_files(repo, res.files)) for res in results],
        "summary": summary,
        "exit_code": code,
        "not_run": not_run,
    }
    if args.stamp:
        payload["at"]["time"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        payload["at"]["repo"] = str(repo)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=False))
        if not_run:
            print("★ 未跑 %d 条（--only 排除 · 计入 skipped）：%s" % (len(not_run), ", ".join(not_run)),
                  file=sys.stderr)
    else:
        emit_human(results, summary, not_run, table, code, payload["at"]["commit"], args.stamp)
    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
