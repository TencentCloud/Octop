"""★ `AUD-1` 水位锚定 · `AUD-2` 文档数字坐标（`PLAN §2`）。"""
import re

from .. import registry as reg

RECIPE = r'(_schema_version|schema_version|version\(db\)|result\["schema_version"\])\s*==\s*(\d+)'
RECIPE_RE = re.compile(RECIPE)
NUM_RE = re.compile(r"`?(\d+)\s*处\s*/\s*(\d+)\s*文件")
COORD_RE = re.compile(r"@\s*`?[0-9a-f]{7,40}`?")
SOFT_COORD_RE = re.compile(r"\b(grep|shasum|sed|python3?)\b|\d{4}-\d{2}-\d{2}|\d{2}:\d{2}")
AUTHORITATIVE = "当前权威值"
DEFAULT_DOCS = ("team/REPOWIKI.md", "team/LEARNINGS.md")


def _display(root, path):
    """★ 只输出【仓库相对路径】；★ 树外 ⇒ 只给文件名（★ 默认输出禁绝对路径）。"""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def _scan_anchored(repo):
    """★ 锚定形态命中 ⇒ `(行数, 文件清单)`；★ 读不到 ⇒ `None`（不得记绿）。"""
    hits = []
    files = set()
    for path in reg.iter_py(repo, "tests"):
        try:
            lines = reg.read_lines(path)
        except (OSError, UnicodeDecodeError):
            return None
        name = _display(repo, path)
        for line_no, text in enumerate(lines, 1):
            if RECIPE_RE.search(text):
                hits.append((name, line_no))
                files.add(name)
    return hits, sorted(files)


def _doc_scan(ctx):
    """★ 扫共享文档 ⇒ `{targets, missing, hints, files}`（确定性 · 与时刻无关）。"""
    targets, missing, hints, files = [], [], [], []
    for doc in ctx.docs:
        path = doc if doc.is_absolute() else ctx.repo / doc
        if not path.is_file():
            continue
        try:
            lines = reg.read_lines(path)
        except (OSError, UnicodeDecodeError):
            continue
        name = _display(ctx.repo, path)
        files.append(name)
        for line_no, text in enumerate(lines, 1):
            matches = list(NUM_RE.finditer(text))
            if not matches:
                continue
            authoritative = AUTHORITATIVE in text
            has_sha = bool(COORD_RE.search(text))
            has_soft = bool(SOFT_COORD_RE.search(text))
            for match in matches:
                if authoritative:
                    if match.group(0) != matches[0].group(0):
                        hints.append('%s:%d「%s」⇒ 保留的未锚定值（只比本行第一个数字）' % (name, line_no, match.group(0)))
                        continue
                    targets.append((name, line_no, int(match.group(1)), int(match.group(2))))
                    if not has_sha:
                        missing.append((name, line_no, text))
                        if has_soft:
                            hints.append('%s:%d ⇒ ★ 命令词 / 时刻【不能替代】`@ <sha>`（硬项收紧 · `FIND-19`）'
                                          % (name, line_no))
                elif not (has_sha or has_soft):
                    hints.append('%s:%d「%s」⇒ 解释性数字，未带坐标' % (name, line_no, match.group(0)))
    return {"targets": targets, "missing": missing, "hints": hints, "files": sorted(set(files))}


@reg.criterion("AUD-1", reg.HARD)
def check_watermark(ctx):
    scanned = _scan_anchored(ctx.repo)
    if scanned is None:
        return reg.Result("AUD-1", reg.HARD, reg.UNKNOWN, message="tests/ 读取失败 ⇒ 不得记绿")
    hits, files = scanned
    docs = _doc_scan(ctx)
    if not hits:
        return reg.Result("AUD-1", reg.HARD, reg.UNKNOWN, message="锚定正则零命中 ⇒ 不得记绿", files=docs["files"])
    if not docs["targets"]:
        return reg.Result("AUD-1", reg.HARD, reg.UNKNOWN, message="未找到「当前权威值」行 ⇒ 不得记绿", files=docs["files"])
    count, file_count = len(hits), len(files)
    for name, line_no, doc_count, doc_files in docs["targets"]:
        if (doc_count, doc_files) != (count, file_count):
            return reg.Result(
                "AUD-1", reg.HARD, reg.FAIL, checked=count,
                message="锚定形态 %d 处 / %d 文件 ≠ 文档值 %d 处 / %d 文件（%s:%d）" % (
                    count, file_count, doc_count, doc_files, name, line_no),
                files=files + docs["files"])
    return reg.Result(
        "AUD-1", reg.HARD, reg.OK, checked=count,
        message="锚定形态 %d 处 / %d 文件 = 文档值" % (count, file_count),
        files=files + docs["files"])


@reg.criterion("AUD-2", reg.HARD)
def check_doc_coords(ctx):
    docs = _doc_scan(ctx)
    if not docs["targets"]:
        return reg.Result("AUD-2", reg.HARD, reg.UNKNOWN,
                          message="未找到「当前权威值」行 ⇒ 不得记绿", files=docs["files"])
    if docs["missing"]:
        name, line_no, _ = docs["missing"][0]
        return reg.Result(
            "AUD-2", reg.HARD, reg.FAIL, checked=len(docs["targets"]),
            message="硬项缺坐标 %d 处（首个 %s:%d）" % (len(docs["missing"]), name, line_no),
            files=docs["files"], hints=docs["hints"])
    return reg.Result(
        "AUD-2", reg.HARD, reg.OK, checked=len(docs["targets"]),
        message="硬项 0 红 · 提示 %d 条" % len(docs["hints"]),
        files=docs["files"], hints=docs["hints"])
