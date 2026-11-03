#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""番茄章节体检：一条命令同时查「字数」和「AI 味痕迹」。

用法::

    python check_chapter_tomato.py 第01章.md
    python check_chapter_tomato.py 第01章.md --preset male
    python check_chapter_tomato.py --all novels/某书/
    python check_chapter_tomato.py --all novels/某书/ --preset male --strict
    python check_chapter_tomato.py 第01章.md 2200 2500      # 显式指定字数区间（两个一起给）
    python check_chapter_tomato.py --all novels/某书/ 2500  # 只改下限，上限沿用默认
    python check_chapter_tomato.py 第01章.md --words-only
    python check_chapter_tomato.py 第01章.md --ai-only
    python check_chapter_tomato.py --json 第01章.md

字数区间::

    （默认，等同 --preset female）  2200-2500   女频 / 双主角 / 群像 / 还没定频道
    --preset male                  2500-3000   男频：战神 / 赘婿 / 系统 / 玄幻

退出码：0 = 跑完（非严格模式）；1 = 加了 --strict 且存在字数不合格或文件缺失；
2 = 参数错误。**AI 味命中不计入退出码**，请读输出。

统计口径：只统计「## 正文」小节的**汉字**，不含标点、不含围栏代码块，
所以这里报的是平台字数的**下界**。没有 `## 正文` 标记时，退回「标题行之外的全部内容，
再整段排除标题里含 概要/备注/说明 的小节」。

编码：优先 UTF-8（含 BOM），失败退回 GB18030，退回时会在 stderr 提示。

AI 味检查逐处报点（`L行号 类型 说明`），改到清零；少数命中可人工确认保留。
阈值都在下面的常量里，按自己的风格调。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------- 字数阈值
DEFAULT_RANGE = (2200, 2500)
PRESETS = {
    "male": (2500, 3000),
    "female": DEFAULT_RANGE,   # 与默认同档；显式写出，免得有人敲 --preset female 撞报错
}

SHORT_HINT = (
    "提示：低于下限时先查「本章是否缺一个核心事件 / 一场冲突」，补事件而不是补描写"
    "——注水直接杀完读率。"
)

# ---------------------------------------------------------------- AI 味阈值
# 出现即报：这些词在正文里基本没有正当理由
BANNED_WORDS = (
    "此外", "然而", "值得注意的是", "总而言之", "综上所述", "由此可见",
    "不禁", "不由得", "嘴角勾起", "勾起一抹", "眸中", "瞳孔骤缩",
    "空气仿佛凝固", "空气凝固", "五味杂陈", "思绪万千", "扑面而来",
    "时间仿佛静止", "眼中闪过一丝",
)
# 超过 OVERUSED_MIN 次才报：这些词本身合法，堆多了才是 AI 味
OVERUSED_WORDS = (
    "仿佛", "彷佛", "缓缓", "轻轻", "微微", "淡淡", "深深", "莫名",
    "似乎", "一丝", "一抹", "瞬间",
)
OVERUSED_MIN = 3
AI_PATTERNS = (
    (r"不仅.{0,12}而且", "「不仅…而且」句式"),
    (r"不是.{0,12}而是", "「不是…而是」句式"),
    (r"与其说.{0,12}不如说", "「与其说…不如说」句式"),
    (r"在.{0,10}的同时", "「在…的同时」句式"),
)
DE_PER_SENTENCE = 3       # 单句「的」达到几次就报
PARA_MAX_CHARS = 180      # 单段汉字数上限（移动端文字墙）
DIALOG_MIN_RATIO = 0.10   # 对话行占比下限
SAME_SENT_RUN = 3         # 连续几句长度相近就报
SAME_SENT_TOL = 2         # 「相近」的容差
MAX_ISSUES = 12           # 每章最多报几条
MAX_LINES_PER_ISSUE = 4   # 每条最多列几个行号

# ---------------------------------------------------------------- 正则
_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_HEAD = re.compile(r"^#{1,6}\s")
_META = ("概要", "备注", "说明", "摘要", "元数据", "frontmatter")
_SENT = re.compile(r"[。！？!?…]+")
_DIALOG = re.compile(r'[\u201c\u201d\u300c\u300d\u300e\u300f"]')
_FOUR = re.compile(r"[\u4e00-\u9fff]{4}[，、][\u4e00-\u9fff]{4}[，、]")
_FENCE = re.compile(r"^\s*```")


def _fix_console() -> None:
    """Windows 控制台默认 GBK，直接 print 中文可能报错。只调用一次。"""
    if sys.platform != "win32":
        return
    import io

    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is not None and hasattr(stream, "buffer"):
            setattr(sys, name, io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"))


# ---------------------------------------------------------------- 读文件
def read_text_smart(path: Path):
    """返回 (文本, 实际编码)。优先 UTF-8（含 BOM），失败退回 GB18030。

    老编辑器存的中文稿子常是 GBK，直接按 UTF-8 读会抛 UnicodeDecodeError 让整个脚本崩掉。
    退回编码时调用方应该提示用户，避免静默按错误编码统计。
    """
    data = path.read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8/replace"


# ---------------------------------------------------------------- 取正文
def extract_body_lines(text: str):
    """返回 [(原始行号, 行内容)]，只含正文，行号可直接用于定位。"""
    all_lines = text.splitlines()

    section = {}          # 行号 -> 当前所属小节标题
    is_heading = set()    # 属于标题行的行号
    cur = None
    for i, line in enumerate(all_lines):
        if _HEAD.match(line):
            cur = line
            is_heading.add(i)
            section[i] = line
        else:
            section[i] = cur

    def is_body_head(h):
        return bool(h) and "正文" in h and not any(m in h for m in _META)

    explicit = any(is_body_head(h) for h in section.values())

    out = []
    for i, line in enumerate(all_lines):
        head = section[i]
        if explicit:
            if i in is_heading:
                continue                      # 标题行本身不计
            if is_body_head(head):
                out.append((i + 1, line))
        else:
            if head and any(m in head for m in _META):
                continue                      # 概要/备注小节整段不计
            if i in is_heading:
                continue                      # 标题行本身不计
            out.append((i + 1, line))
    return out


def strip_fenced(lines):
    """整块剔除 ``` 围栏代码块，让字数和 AI 味用同一口径。"""
    out = []
    in_fence = False
    for n, line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append((n, line))
    return out


def count_words(lines) -> int:
    return len(_CJK.findall("\n".join(l for _, l in lines)))


# ---------------------------------------------------------------- AI 味
def scan_ai(lines):
    lines = strip_fenced(lines)
    issues = []

    def add(lineno, kind, detail, hit_lines=None):
        issues.append({
            "line": lineno,
            "kind": kind,
            "detail": detail,
            "lines": hit_lines or [lineno],
        })

    non_empty = [(n, l.strip()) for n, l in lines if l.strip()]

    for w in BANNED_WORDS:
        hits = [n for n, l in non_empty if w in l]
        if hits:
            add(hits[0], "禁用词", "「%s」共 %d 处" % (w, len(hits)), hits)

    for w in OVERUSED_WORDS:
        hits = [n for n, l in non_empty if w in l]
        total = sum(l.count(w) for _, l in non_empty)
        if total >= OVERUSED_MIN:
            add(hits[0], "高频词", "「%s」出现 %d 次" % (w, total), hits)

    for n, l in non_empty:
        for sent in _SENT.split(l):
            if sent.count("的") >= DE_PER_SENTENCE:
                add(n, "的字密集", "一句里 %d 个「的」：%s" % (sent.count("的"), sent[:18]))
                break

    for n, l in non_empty:
        if _FOUR.search(l):
            add(n, "四字格", "疑似四字短语连用")

    for n, l in non_empty:
        for pat, label in AI_PATTERNS:
            if re.search(pat, l):
                add(n, "AI 句式", label)

    for n, l in non_empty:
        cnt = len(_CJK.findall(l))
        if cnt > PARA_MAX_CHARS:
            add(n, "长段落", "%d 字（建议 ≤%d，移动端文字墙）" % (cnt, PARA_MAX_CHARS))

    if non_empty:
        ratio = sum(1 for _, l in non_empty if _DIALOG.search(l)) / len(non_empty)
        if ratio < DIALOG_MIN_RATIO:
            add(non_empty[0][0], "对话偏少",
                "含对话的行占 %.0f%%（建议 ≥%d%%）" % (ratio * 100, DIALOG_MIN_RATIO * 100))

    for n, l in non_empty:
        lens = [len(_CJK.findall(s)) for s in _SENT.split(l) if _CJK.findall(s)]
        run = 1
        for i in range(1, len(lens)):
            if abs(lens[i] - lens[i - 1]) <= SAME_SENT_TOL:
                run += 1
                if run == SAME_SENT_RUN:
                    seg = lens[i - run + 1 : i + 1]
                    add(n, "句子节奏", "连续 %d 句长度相近（%s 字）" % (run, "/".join(str(x) for x in seg)))
                    break
            else:
                run = 1

    issues.sort(key=lambda x: (x["line"], x["kind"]))
    return issues


def format_issues(issues) -> str:
    if not issues:
        return "AI味 0"

    def loc(item):
        nums = item.get("lines") or [item["line"]]
        text = "L" + ",L".join(str(x) for x in nums[:MAX_LINES_PER_ISSUE])
        if len(nums) > MAX_LINES_PER_ISSUE:
            text += " 等 %d 处" % len(nums)
        return text

    shown = issues[:MAX_ISSUES]
    body = " | ".join("%s %s %s" % (loc(i), i["kind"], i["detail"]) for i in shown)
    rest = issues[MAX_ISSUES:]
    if rest:
        more = "、".join("L%d" % r["line"] for r in rest[:10])
        body += " | …另有 %d 处：%s" % (len(rest), more)
        if len(rest) > 10:
            body += " 等"
    return "AI味 %d: %s" % (len(issues), body)


# ---------------------------------------------------------------- 检查
def _parse_range(rest, default_lo, default_hi):
    """位置参数解析：[] 用默认；[min] 只改下限；[min, max] 全改。区间倒挂直接报错。"""

    def to_int(v, label):
        try:
            return int(v)
        except ValueError:
            raise ValueError("%s必须是整数，收到「%s」" % (label, v))

    if len(rest) >= 2:
        lo, hi = to_int(rest[0], "最小字数"), to_int(rest[1], "最大字数")
    elif len(rest) == 1:
        lo, hi = to_int(rest[0], "最小字数"), default_hi
    else:
        lo, hi = default_lo, default_hi

    if lo > hi:
        raise ValueError(
            "下限 %d 大于上限 %d。只给一个数字时上限沿用默认值 %d，要改上限请把两个数一起给出"
            % (lo, hi, default_hi)
        )
    return lo, hi


def check(path: Path, lo, hi, do_words=True, do_ai=True) -> dict:
    if not path.is_file():
        return {"file": str(path), "words": 0, "status": "missing", "detail": "文件不存在", "issues": []}

    text, enc = read_text_smart(path)
    if enc not in ("utf-8-sig", "utf-8"):
        print("提示：%s 不是 UTF-8，已按 %s 解码" % (path.name, enc), file=sys.stderr)

    lines = extract_body_lines(text)
    body = strip_fenced(lines)
    words = count_words(body) if do_words else 0
    if not do_words:
        status, detail = "skipped", "未检查"
    elif words < lo:
        status, detail = "short", "低于下限 %d 字" % (lo - words)
    elif words > hi:
        status, detail = "long", "超出上限 %d 字" % (words - hi)
    else:
        status, detail = "pass", "达标"
    issues = scan_ai(lines) if do_ai else []
    return {"file": str(path), "words": words, "status": status, "detail": detail, "issues": issues}


_ICON = {"pass": "OK", "short": "短", "long": "长", "missing": "缺", "skipped": "--"}


def main() -> int:
    raw = list(sys.argv[1:])
    as_json = "--json" in raw
    strict = "--strict" in raw
    flags = ("--json", "--strict", "--words-only", "--ai-only")

    if "--words-only" in raw and "--ai-only" in raw:
        print("错误：--words-only 与 --ai-only 不能同时使用", file=sys.stderr)
        return 2

    preset = None
    if "--preset" in raw:
        i = raw.index("--preset")
        if i + 1 >= len(raw):
            print("错误：--preset 需要 male 或 female", file=sys.stderr)
            return 2
        preset = raw[i + 1].lower()
        del raw[i : i + 2]

    if preset is not None and preset not in PRESETS:
        print("错误：未知频道「%s」。可选 %s；女频与默认同档，直接省略 --preset 即可。"
              % (preset, " / ".join(PRESETS)), file=sys.stderr)
        return 2
    default_lo, default_hi = PRESETS.get(preset, DEFAULT_RANGE)

    is_all = "--all" in raw
    pos = [a for a in raw if a not in flags and a != "--all"]

    try:
        if is_all:
            if not pos:
                print("错误：--all 需要指定目录", file=sys.stderr)
                return 2
            directory = Path(pos[0])
            lo, hi = _parse_range(pos[1:], default_lo, default_hi)
            files = sorted(directory.glob("第*.md")) if directory.is_dir() else []
            if not files:
                print("没有找到章节文件：%s/第*.md" % directory, file=sys.stderr)
                return 2
        else:
            if not pos:
                print(__doc__)
                return 2
            lo, hi = _parse_range(pos[1:], default_lo, default_hi)
            files = [Path(pos[0])]
    except ValueError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2

    do_words = "--ai-only" not in raw
    do_ai = "--words-only" not in raw
    results = [check(f, lo, hi, do_words, do_ai) for f in files]

    if as_json:
        payload = {"preset": preset or "default", "range": [lo, hi], "results": results}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if do_words:
                print("%s %s: %d 字 (%s, 区间 %d-%d)"
                      % (_ICON[r["status"]], Path(r["file"]).name, r["words"], r["detail"], lo, hi))
            elif r["status"] == "missing":
                print("%s（文件不存在）" % Path(r["file"]).name)
            else:
                print(Path(r["file"]).name)
            if do_ai:
                print("   " + format_issues(r["issues"]))

        checked = [r for r in results if r["status"] not in ("skipped", "missing")]
        passed = [r for r in checked if r["status"] == "pass"]
        bad = [r for r in results if r["status"] in ("short", "long", "missing")]
        dirty = [r for r in results if r["issues"]]

        if len(results) > 1:
            if do_words:
                print("-- 共 %d 个文件：%d 章字数达标，%d 个不合格，已查字数 %d"
                      % (len(results), len(passed), len(bad), sum(r["words"] for r in checked)))
                print("   %d 章有 AI 味命中" % len(dirty))
            else:
                print("-- 共 %d 个文件，%d 章有 AI 味命中" % (len(results), len(dirty)))
        if do_words and bad:
            print("字数需处理：" + "、".join(Path(r["file"]).name for r in bad))
        if do_words and any(r["status"] == "short" for r in results):
            print(SHORT_HINT)

    return 1 if (strict and any(r["status"] in ("short", "long", "missing") for r in results)) else 0


if __name__ == "__main__":
    _fix_console()
    sys.exit(main())
