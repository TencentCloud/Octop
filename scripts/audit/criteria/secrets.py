"""★ `AUD-S3` `secrets.write_encrypted` · `AUD-S5` `secrets.no_hardcoded_literal`（`PLAN §2`）。

★ `repair-5`：① 噪声表改为**内容锚定**（`FIND-20`）；② 值分类改为**语法级**（`ast` · `FIND-21`）；
★ 两者都**不再**用「坐标即跳过」或「子串匹配」✗。
"""
import ast
import re

from .. import registry as reg

CALL_RE = re.compile(r"\.(get_or_create|rotate)\(")
CALL_ATTRS = ("get_or_create", "rotate")

# ★ 噪声表（逐行声明 · ★ 每条带 verbatim `anchor` ⇒ ★ 只有该行【仍逐字含 anchor】才跳过）
NOISE = {
    ("src/octop/infra/server.py", 72): {
        "anchor": "super().rotate(source, dest)",
        "reason": "super().rotate = 日志轮转（非 secrets 表）· 方法名巧合",
    },
    ("src/octop/infra/browser/setup.py", 442): {
        "anchor": "profile = pm.get_or_create(profile_name)",
        "reason": "Playwright ProfileManager（非 secrets 表）",
    },
    ("src/octop/infra/browser/setup.py", 452): {
        "anchor": "return Path(ProfileManager().get_or_create(profile_name).data_dir)",
        "reason": "同上（同一 API 的第二处）",
    },
    ("src/octop/infra/gateway/threads.py", 223): {
        "anchor": "return await self.get_or_create(",
        "reason": "线程仓储（非 secrets 表）· 多行调用",
    },
}

ENC_NAMES = frozenset(("encrypt_credentials", "encrypt_secret"))
ENC_ATTRS = frozenset(("encrypt_credentials", "encrypt_secret", "encrypt"))

SQL_WRITE_RE = re.compile(r"(INSERT|REPLACE)\s+INTO\s+secrets\b|\bUPDATE\s+secrets\b", re.IGNORECASE)
SQL_PARAM_RE = re.compile(r"\?|%s")
ASSIGN_RE = re.compile(r'^\s*([A-Za-z_][\w.]*)\s*=\s*(["\'])([A-Za-z0-9+/=_-]+)\2\s*$')
LHS_RE = re.compile(r"(?i)(secret|token|password|passwd|api_?key|credential|fernet_?key|encryption_?key)")
BLIND_SPOT = "★ AUD-S5 盲区（不判）：非赋值 / 拼接 / 多行 / 变量传递 / 非 .py 载体 / len<20"


def _calls_by_line(source):
    """★ 每行的 `get_or_create` / `rotate` 调用节点（语法级 · 不用子串判值）。"""
    tree = ast.parse(source)
    mapping = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in CALL_ATTRS:
            mapping.setdefault(node.lineno, []).append(node)
    return mapping


def _classify(node, lines, depth=0):
    """★ 语法级值分类 ⇒ `(state, why)`；★ `ast.Constant` 字面量 ⇒ **红**（`FIND-21`）。"""
    if node is None:
        return "RED", "无法取到值表达式"
    if depth > 4:
        return "RED", "变量中转超过 4 层"
    if isinstance(node, ast.Constant):
        return "RED", "字面量常量（str/bytes）"
    if isinstance(node, ast.Lambda):
        return _classify(node.body, lines, depth + 1)
    if isinstance(node, ast.Attribute):
        if node.attr == "generate_key":
            return "GREEN", "Fernet.generate_key"
        return "RED", "属性（变量）.%s" % node.attr
    if isinstance(node, ast.Name):
        pattern = re.compile(r"^\s*%s\s*=\s*(.+)$" % re.escape(node.id))
        for i in range(node.lineno - 2, max(-1, node.lineno - 61), -1):
            match = pattern.match(lines[i])
            if match:
                try:
                    rhs = ast.parse(match.group(1).strip(), mode="eval").body
                except SyntaxError:
                    return "RED", "变量 %s 的 RHS 无法解析" % node.id
                return _classify(rhs, lines, depth + 1)
        return "RED", "变量 %s（无同文件赋值）" % node.id
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in ENC_NAMES:
            return "GREEN", func.id
        if isinstance(func, ast.Attribute) and func.attr in ENC_ATTRS:
            return "GREEN", "." + func.attr
        if isinstance(func, ast.Attribute) and func.attr == "urandom":
            return "GREEN", "os.urandom"
        return "RED", "非加密调用（%s）" % type(func).__name__
    return "RED", "其它节点 %s" % type(node).__name__


@reg.criterion("AUD-S3", reg.HARD)
def check_at_rest_ciphertext(ctx):
    call_hits, sql_hits, hints = [], [], []
    for path in reg.iter_py(ctx.repo, "src/octop"):
        try:
            source = reg.read_source(path)
            lines = source.split("\n")
        except (OSError, UnicodeDecodeError) as exc:
            return reg.Result("AUD-S3", reg.HARD, reg.UNKNOWN,
                              message="读不到源文件（%s）⇒ 不得记绿" % exc)
        name = reg.rel(ctx.repo, path)
        site_lines = [(i, text) for i, text in enumerate(lines, 1) if CALL_RE.search(text)]
        sql_lines = [(i, text) for i, text in enumerate(lines, 1) if SQL_WRITE_RE.search(text)]
        if not site_lines and not sql_lines:
            continue
        # ★ 只在【需要分类】时才解析 AST（噪声行不需分类）⇒ ★ 输入面最小化（见 §10 已知限制）
        need_ast = False
        for line_no, text in site_lines:
            entry = NOISE.get((name, line_no))
            if entry is None or entry["anchor"] not in text or len(CALL_RE.findall(text)) != 1:
                need_ast = True
                break
        calls = {}
        if need_ast:
            try:
                calls = _calls_by_line(source)
            except SyntaxError as exc:
                return reg.Result("AUD-S3", reg.HARD, reg.UNKNOWN,
                                  message="%s AST 解析失败（%s）⇒ 读到不认识的格式 ⇒ 不得记绿" % (name, exc),
                                  files=[name])
        for line_no, text in site_lines:
            call_hits.append((name, line_no, text, lines, calls.get(line_no, [])))
        for line_no, text in sql_lines:
            sql_hits.append((name, line_no, text))
    if not call_hits and not sql_hits:
        return reg.Result("AUD-S3", reg.HARD, reg.UNKNOWN, message="调用点 0 个 ⇒ 不得记绿")

    writes, noise = [], []
    for name, line_no, text, lines, nodes in call_hits:
        entry = NOISE.get((name, line_no))
        n_call = len(CALL_RE.findall(text))
        if entry is not None:
            if entry["anchor"] in text and n_call == 1:
                noise.append((name, line_no))
                continue
            hints.append("%s:%d ⇒ ★ 噪声表过期（`path:line` 内容已变 ⇒ 不得跳过）" % (name, line_no))
            elsewhere = [i + 1 for i, item in enumerate(lines) if entry["anchor"] in item]
            if elsewhere and line_no not in elsewhere:
                hints.append("%s:%d ⇒ ★ 坐标漂移（anchor 现在 :%d）" % (name, line_no, elsewhere[0]))
        writes.append((name, line_no, text, lines, nodes))

    files = sorted({name for name, _, _, _, _ in call_hits} | {name for name, _, _ in sql_hits})
    exempted, reds, new_reds = 0, [], []
    for name, line_no, _text, lines, nodes in writes:
        if not nodes:
            state, why = "RED", "该行未解析出调用点节点"
        else:
            arg = nodes[0].args[1] if len(nodes[0].args) >= 2 else None
            state, why = _classify(arg, lines)
        if state == "GREEN":
            continue
        reds.append("%s:%d（%s）" % (name, line_no, why))
        if ctx.exempted("AUD-S3", name, line_no):
            exempted += 1
        else:
            new_reds.append("%s:%d（%s）" % (name, line_no, why))

    sql_reds, sql_parameters = [], 0
    for name, line_no, text in sql_hits:
        if SQL_PARAM_RE.search(text) and "{" not in text and "% (" not in text:
            sql_parameters += 1
        else:
            sql_reds.append("%s:%d ⇒ 非全参数化 SQL（明文可静态读到）" % (name, line_no))
    checked = len(call_hits) + len(sql_hits)
    if new_reds or sql_reds:
        return reg.Result("AUD-S3", reg.HARD, reg.FAIL, checked=checked, exempted=exempted,
                          message="未豁免明文 %s" % " · ".join(new_reds + sql_reds),
                          files=files, hints=hints)
    return reg.Result(
        "AUD-S3", reg.HARD, reg.OK, checked=checked, exempted=exempted,
        message="明文命中 %d 处【均已逐字豁免】· 封装层 %d 处 · 噪声 %d 处（逐行内容锚定）· 新明文 0"
                % (len(reds), sql_parameters, len(noise)),
        files=files, hints=hints)


@reg.criterion("AUD-S5", reg.HARD)
def check_literal_floor(ctx):
    hits, files = [], []
    for path in reg.iter_py(ctx.repo, "src/octop"):
        try:
            lines = reg.read_lines(path)
        except (OSError, UnicodeDecodeError) as exc:
            return reg.Result("AUD-S5", reg.HARD, reg.UNKNOWN,
                              message="读不到源文件（%s）⇒ 不得记绿" % exc, hints=[BLIND_SPOT])
        name = reg.rel(ctx.repo, path)
        for line_no, text in enumerate(lines, 1):
            match = ASSIGN_RE.match(text)
            if not match:
                continue
            lhs, rhs = match.group(1), match.group(3)
            if not LHS_RE.search(lhs) or len(rhs) < 20:
                continue
            if not (any(c.isupper() for c in rhs) and any(c.islower() for c in rhs)
                    and any(c.isdigit() for c in rhs)):
                continue
            hits.append((name, line_no))
            files.append(name)
    if not hits:
        return reg.Result("AUD-S5", reg.HARD, reg.UNKNOWN,
                          message="赋值面零命中 ⇒ 不得记绿（fail-closed）", hints=[BLIND_SPOT])
    new = [item for item in hits if not ctx.exempted("AUD-S5", item[0], item[1])]
    exempted = len(hits) - len(new)
    if new:
        return reg.Result("AUD-S5", reg.HARD, reg.FAIL, checked=len(hits), exempted=exempted,
                          message="新字面量 %d 处（未豁免）：%s" % (len(new), ", ".join("%s:%d" % h for h in new)),
                          files=files, hints=[BLIND_SPOT])
    return reg.Result("AUD-S5", reg.HARD, reg.OK, checked=len(hits), exempted=exempted,
                      message="真命中 %d 处【已逐字豁免】· 新字面量 0" % len(hits),
                      files=files, hints=[BLIND_SPOT])
