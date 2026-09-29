#!/usr/bin/env python3
"""★ 判据注册表 + 未知格式守卫（`AUD-G1`）· 只用标准库（`PLAN §8`）。

★ 唯一契约来源 = `team/2026-09-29-103507/PLAN.md`（`§2` / `§4` / `§5` / `§8`）。
★ 本模块**只读**被审计文件 · **不落盘**（落盘只走显式 `--out`）。
"""
import hashlib
import json
import pathlib
import re
import subprocess

OK = "OK"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"

HARD = "hard"
GUARD = "guard"
REGRESSION = "regression"

STATE_LABEL = {OK: "绿", FAIL: "红", UNKNOWN: "未知"}

# ★ 冻结的 10 条 id（`SL-1` · `K` 批追加 `AUD-S6`）· 冻结的 8 条硬判（`SL-2`）
# ★ `FROZEN_IDS` 有顺序语义（`current_tree.py` 按它排序）⇒ `AUD-S6` 追加在末尾，不打乱既有顺序
FROZEN_IDS = ("AUD-1", "AUD-2", "AUD-S1", "AUD-S2", "AUD-S3", "AUD-S4", "AUD-S5", "AUD-G1", "AUD-G2",
              "AUD-S6")
HARD_IDS = ("AUD-1", "AUD-2", "AUD-S1", "AUD-S2", "AUD-S3", "AUD-S4", "AUD-S5", "AUD-S6")

# ★ `AUD-G2` 的冻结锚点（`Makefile @207` 逐字）
MAKEFILE_NAME = "Makefile"
MAKEFILE_FROZEN_LINENO = 207
MAKEFILE_FROZEN_LINE = "all: format-all lint typecheck test test-frontend"

EXEMPTIONS_REL = "scripts/audit/exemptions.json"
EXEMPTION_SCHEMA = "octop.audit.exemptions/1"
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

# ★ 各判据的「调用点」正则（豁免 `H5` / `SL-4` 用）
CALLSITE_RE = {
    "AUD-S3": re.compile(r"\.(?:get_or_create|rotate)\("),
    "AUD-S5": re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=\s*[\"']"),
}
EXEMPTION_CONSUMERS = ("AUD-S3", "AUD-S5")

REGISTRY = []


def criterion(cid, kind):
    """★ 注册一条判据（`PLAN §8`：每条判据一个 `check_*` 函数）。"""
    def deco(fn):
        if any(item["id"] == cid for item in REGISTRY):
            raise ValueError("duplicate criterion id: %s" % cid)
        REGISTRY.append({
            "id": cid,
            "kind": kind,
            "fn": fn,
            "check_name": fn.__name__,
            "module": fn.__module__,
        })
        return fn
    return deco


class Result:
    """★ 判据结果（三态 + 计数 + 证据文件）；★ `UNKNOWN` 绝不等于绿。"""

    def __init__(self, cid, kind, state, checked=0, skipped=0, exempted=0,
                 message="", files=None, hints=None):
        self.id = cid
        self.kind = kind
        self.state = state
        self.checked = checked
        self.skipped = skipped
        self.exempted = exempted
        self.message = message
        self.files = sorted(set(files or []))
        self.hints = list(hints or [])

    def as_dict(self, digest):
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "checked": self.checked,
            "skipped": self.skipped,
            "exempted": self.exempted,
            "input_digest": {"files": self.files, "sha256": digest},
            "messages": [self.message] if self.message else [],
            "hints": self.hints,
        }


class Ctx:
    """★ 判据运行上下文（只读）。"""

    def __init__(self, repo, docs, exempt_index, head):
        self.repo = repo
        self.docs = docs
        self.exempt_index = exempt_index
        self.head = head

    def exempted(self, cid, relpath, line):
        return (cid, relpath, line) in self.exempt_index


def repo_root():
    return pathlib.Path(__file__).resolve().parents[2]


def rel(root, path):
    return pathlib.Path(path).resolve().relative_to(pathlib.Path(root).resolve()).as_posix()


def read_source(path):
    """★ 读原文（★ `ast` 必须用原文 ⇒ **不得**用重新拼接的行）。"""
    return pathlib.Path(path).read_text(encoding="utf-8")


def read_lines(path):
    """★ 按 `\\n` 切行（★ 不用 `splitlines()`：它在 U+2028 / U+000C 等处会误切）；★ 读不到 ⇒ 抛给调用方。"""
    return read_source(path).split("\n")


def iter_py(root, subdir="src/octop"):
    base = pathlib.Path(root) / subdir
    return sorted(p for p in base.rglob("*.py") if p.is_file())


def head_commit(root):
    """★ 当前 `HEAD`（短 sha）；★ `git` 不可用 ⇒ `None`（调用方按未知处理）。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=8", "HEAD"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    head = out.stdout.strip()
    return head or None


def _git(root, args):
    """★ 只读 git 调用；★ 不可用 ⇒ `None`（调用方按 fail-closed 处理）。"""
    try:
        return subprocess.run(["git", "-C", str(root)] + args, capture_output=True, text=True, check=False)
    except OSError:
        return None


def is_ancestor(root, ancestor, descendant):
    """★ `ancestor` 是否为 `descendant` 的祖先（★ 只读 · `merge-base --is-ancestor`）。

    ★ 返回 `None` = git 不可用（⇒ 调用方 fail-closed）；`True`/`False` = 判定结果。
    """
    out = _git(root, ["merge-base", "--is-ancestor", str(ancestor), str(descendant)])
    if out is None:
        return None
    if out.returncode == 0:
        return True
    if out.returncode == 1:
        return False
    return False          # ★ 129 = 对象不存在 / 其它错误 ⇒ ★ 一律按「非祖先」判红（fail-closed）


def changed_since(root, since, path):
    """★ `path` 自 `since` 到 `HEAD` 是否【有改动】（★ 只读 · `git diff --quiet`）。

    ★ 返回 `None` = git 不可用（⇒ fail-closed）；`True` = 有改动（⇒ 判红）；`False` = 未改动。
    """
    out = _git(root, ["diff", "--quiet", "%s..HEAD" % since, "--", str(path)])
    if out is None:
        return None
    return out.returncode != 0      # ★ 0 = 无改动 · 非 0（含 128 路径/版本错误）= 判红（fail-closed）


def load_exemptions(root):
    """★ 载入豁免表 + 结构级校验（`H1`/`H2`/`H9`/`H10`）⇒ (table|None, violations)。

    ★★ `H2`（`repair-6` · 提交态可用）：① `at_commit` 必须是 **`HEAD` 的祖先**；
    ② ★ **且**被豁免坐标**所在文件**自 `at_commit` 起**未被改动** ⇒ 否则 ⇒ **红**。
    ★ 为什么：★ 旧口径「`at_commit` == 当前 `HEAD`」在**提交态下恒红**（= **不动点冲突**，不是判据）✗。
    ★ 无 `.git` 的副本 ⇒ ★ **保持 fail-closed（`exit 2`）不变** ✓。
    """
    path = pathlib.Path(root) / EXEMPTIONS_REL
    if not path.is_file():
        return None, ["豁免表缺失：%s" % EXEMPTIONS_REL]
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, ["豁免表无法解析：%s" % exc]
    violations = []
    if table.get("schema") != EXEMPTION_SCHEMA:
        violations.append("schema != %s（实测 %r）" % (EXEMPTION_SCHEMA, table.get("schema")))
    entries = table.get("entries")
    if not isinstance(entries, list):
        return table, violations + ["entries 不是列表"]
    if table.get("entry_count") != len(entries):
        violations.append("H1 条数上界不符：entry_count=%r 但 len(entries)=%d" % (table.get("entry_count"), len(entries)))
    head = head_commit(root)
    at_commit = table.get("at_commit")
    if head is None:
        violations.append("H2 无法取 HEAD（git 不可用）⇒ 提交态判定不可用 ⇒ fail-closed（不得记绿）")
    elif not isinstance(at_commit, str) or not SHA_RE.match(at_commit):
        violations.append("H2 at_commit 不可用于祖先判定（非空/格式不合法）：%r" % (at_commit,))
    else:
        ancestor = is_ancestor(root, at_commit, "HEAD")
        if ancestor is None:
            violations.append("H2 无法执行祖先判定（git 不可用）⇒ fail-closed（不得记绿）")
        elif not ancestor:
            violations.append(
                "H2 at_commit=%r **不是**当前 HEAD=%r 的祖先（或该对象不存在）⇒ 豁免表的冻结坐标不可信"
                % (at_commit, head))
        else:
            for entry in entries:
                target = entry.get("path")
                if not isinstance(target, str) or not target:
                    continue
                dirty = changed_since(root, at_commit, target)
                if dirty is None:
                    violations.append("H2 无法执行「文件未改动」判定（git 不可用）⇒ fail-closed（不得记绿）")
                elif dirty:
                    violations.append(
                        "H2 **豁免后文件又改了**：%s 自 at_commit=%s 起有改动 ⇒ 豁免必须重新复核/重签" % (target, at_commit))
    frozen_at = table.get("frozen_at")
    if not isinstance(frozen_at, str) or not ISO_RE.match(frozen_at):
        violations.append("H10 frozen_at 非空/格式不合法：%r" % (frozen_at,))
    if not isinstance(at_commit, str) or not SHA_RE.match(at_commit):
        violations.append("H10 at_commit 非空/格式不合法：%r" % (at_commit,))
    for entry in entries:
        cid = entry.get("criterion")
        if cid not in FROZEN_IDS:
            violations.append("H9 criterion=%r 不在冻结 9 条 id 内" % (cid,))
        line = entry.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            violations.append("H4 line 必须 ≥ 1 的整数：%r" % (line,))
    return table, violations


def digest_files(root, relpaths):
    """★ 输入指纹 = 文件清单 + 各文件内容 sha256（确定性 · 与时刻无关）。"""
    h = hashlib.sha256()
    for item in sorted(set(relpaths)):
        h.update(item.encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(hashlib.sha256((pathlib.Path(root) / item).read_bytes()).hexdigest().encode("ascii"))
        except OSError:
            h.update(b"<unreadable>")
        h.update(b"\n")
    return h.hexdigest()


def exemption_index(table):
    index = {}
    if not table:
        return index
    for entry in table.get("entries", []):
        index[(entry.get("criterion"), entry.get("path"), entry.get("line"))] = entry
    return index


def deep_exemption_violations(root, table, coverage):
    """★ 逐条深度校验（`H3`/`H4`/`H5` + `SL-3`/`SL-4`）⇒ violations。

    ★ `coverage` = {criterion: set(仓库相对路径)}（= 该判据的输入面）。
    """
    violations = []
    if not table:
        return violations
    root = pathlib.Path(root).resolve()
    counts = {}
    for entry in table.get("entries", []):
        cid = entry.get("criterion")
        raw = entry.get("path")
        line = entry.get("line")
        anchor = entry.get("anchor")
        fragment = entry.get("value_fragment")
        label = "%s %s:%s" % (cid, raw, line)
        if not isinstance(raw, str) or not raw or raw.endswith("/") or "*" in raw or "?" in raw:
            violations.append("%s ⇒ ① path 非法（禁通配/目录级/空）" % label)
            continue
        target = (root / raw).resolve()
        try:
            inside = target.is_relative_to(root)
        except AttributeError:
            inside = str(target).startswith(str(root))
        if not inside:
            violations.append("%s ⇒ H3 path 归一化后不在仓库内" % label)
            continue
        if not target.is_file():
            violations.append("%s ⇒ H3 path 不存在" % label)
            continue
        relpath = target.relative_to(root).as_posix()
        if relpath not in coverage.get(cid, set()):
            violations.append("%s ⇒ H3 未被该判据的输入面覆盖" % label)
            continue
        try:
            lines = read_lines(target)
        except (OSError, UnicodeDecodeError) as exc:
            violations.append("%s ⇒ 读取失败：%s" % (label, exc))
            continue
        if not isinstance(line, int) or line > len(lines):
            violations.append("%s ⇒ H4 该行不存在（文件共 %d 行）" % (label, len(lines)))
            continue
        text = lines[line - 1]
        callsite = CALLSITE_RE.get(cid)
        if callsite is not None and not callsite.search(text):
            violations.append("%s ⇒ H5 锚点行【已不含】该调用点 ⇒ 豁免过期" % label)
        if not isinstance(anchor, str) or anchor not in text:
            violations.append("%s ⇒ SL-3 anchor 未逐字出现在该行" % label)
        if not isinstance(fragment, str) or len(fragment) < 8:
            violations.append("%s ⇒ SL-3 value_fragment 长度 < 8" % label)
        elif text.count(fragment) != 1:
            violations.append("%s ⇒ SL-3 value_fragment 在该行内不唯一（%d 次）" % (label, text.count(fragment)))
        key = (cid, relpath, line)
        counts[key] = counts.get(key, 0) + 1
    for (cid, relpath, line), n_ex in counts.items():
        try:
            text = read_lines(pathlib.Path(root) / relpath)[line - 1]
        except (OSError, UnicodeDecodeError, IndexError):
            continue
        callsite = CALLSITE_RE.get(cid)
        n_call = len(callsite.findall(text)) if callsite is not None else 0
        if n_call > n_ex:
            violations.append("%s %s:%d ⇒ SL-4 调用点 %d 个 > 豁免 %d 条" % (cid, relpath, line, n_call, n_ex))
    return violations


# ─── AUD-G1：未知格式守卫（★ 横切 · 注册表自检）──────────────────────────────

GUARD_ID = "AUD-G1"


def discover_check_names():
    """★ 扫 `criteria/` 里【定义在该模块内】的 `check_*` 函数名（注册表对照用）。"""
    import importlib
    import types

    pkg = importlib.import_module("scripts.audit.criteria")
    names = set()
    for value in vars(pkg).values():
        if isinstance(value, types.ModuleType) and value.__name__.startswith("scripts.audit.criteria."):
            for attr_name, attr in vars(value).items():
                if attr_name.startswith("check_") and callable(attr) \
                        and getattr(attr, "__module__", "") == value.__name__:
                    names.add(attr_name)
    return names


def registry_guard_facts(bad_states, empty_inputs):
    """★ 组装 `AUD-G1` 事实：id 集合 / 硬判 kind 白名单 / 未注册 `check_*` / 状态 / 空输入。"""
    violations = []
    ids = [item["id"] for item in REGISTRY]
    if len(ids) != len(FROZEN_IDS) or set(ids) != set(FROZEN_IDS):
        violations.append("id 集合与冻结 9 条不符（差集 = %s）"
                          % (sorted(set(ids) ^ set(FROZEN_IDS)) or "重复 id"))
    for item in REGISTRY:
        if item["id"] in HARD_IDS and item["kind"] != HARD:
            violations.append("硬判 %s 的 kind = %r ≠ hard" % (item["id"], item["kind"]))
    unregistered = sorted(discover_check_names() - {item["check_name"] for item in REGISTRY})
    if unregistered:
        violations.append("未注册 check_：%s" % ", ".join(unregistered))
    if bad_states:
        violations.append("判据返回了不认识的状态：%s" % ", ".join(bad_states))
    if empty_inputs:
        violations.append("输入清单为空（⇒ FAIL）：%s" % ", ".join(empty_inputs))
    return {"violations": violations, "unregistered": unregistered,
            "bad_states": list(bad_states), "empty_inputs": list(empty_inputs)}


def guard_result(facts):
    """★ `AUD-G1` 的结果：★ 任一违规 ⇒ `UNKNOWN` ⇒ `exit 2`（fail-closed · 绝不记绿）。"""
    base = "未注册 check_ %d 个" % len(facts["unregistered"])
    if facts["violations"]:
        return Result(GUARD_ID, GUARD, UNKNOWN, checked=len(FROZEN_IDS),
                      message="%s · %s ⇒ 不得记绿" % (base, " · ".join(facts["violations"])))
    return Result(GUARD_ID, GUARD, OK, checked=len(FROZEN_IDS),
                  message="%s · id 集合 = 冻结 9 条 · 硬判 kind 白名单 = 7 条 hard" % base)
