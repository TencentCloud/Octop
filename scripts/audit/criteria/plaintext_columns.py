"""★ `AUD-S6` 结构化凭据列：明文落库（列面 · `K` 批 `PLAN §2` 八条硬要求 · 逐条落实）。

★ 谓词（逐字）：扫 `migrations/*.sql` 取 `(table, col) ∈ CRED_PAT × {TEXT, VARCHAR, BLOB}` 且排除
  `*_hash` ⇒ 在全仓（`src/octop/**` + `scripts/**`）定位该表的 `INSERT`/`UPDATE` 参数表达式 ⇒
  `ast` 判该值是否经【已验证导入源】的 `encrypt_credentials`/`encrypt_secret` ⇒
  非加密 = 红 · 候选列 = ∅ ⇒ `UNKNOWN`（空转守卫 · 不得记绿）。

★ 八条硬要求 → 实现落点（命令 + 期望失败信号见 `team/2026-09-29-225033/PLAN.md §2`）：
  ① 输入面【全仓】：`_iter_py` 扫 `src/octop` **和** `scripts`（非仅 `db/repos`）⇒ ATK2 能被抓。
  ② 动态 SQL / f-string ⇒ `UNKNOWN`：`_site` 只在 SQL 实参是**单个 `ast.Constant`** 时判值；
     其余（f-string/`.format`/`%`/变量）⇒ 动态站点 ⇒ `UNKNOWN`（**不得默认绿**）⇒ ATK3。
  ③ 【表绑定】：动态站点的表**只从字面量片段**绑定；绑不到 ⇒ 显式登记（hint）且不计入判定面
     ⇒ 红点坐标只落在【已绑定的表】上（绝不把 `providers.api_key` 报到别的表的行上）。
  ④ 【作用域感知】：变量回溯只用 `_Scope`（同一函数体 + 语句链支配关系 · 无「向上 N 行」文本窗口）
     ⇒ `ATK1''`（顶层永不被调用的同名诱饵）无法翻转结论。
  ⑤ 【禁名字单判】：`encrypt_*` 必须能解析**导入源**为 `octop.infra.connectors.crypto` /
     `octop.infra.auth.sso.crypto`；同文件自造同名函数 ⇒ 不认 ⇒ 红。
  ⑥ 【排除项须验值形态】：`*_enc`/`*_blob` **不按名字排除** —— 只有【可静态解析的写入值全部为
     已验证加密调用】才移出判定面；否则照判 ⇒ ATK4（明文列命名 `*_enc`）能被抓。
  ⑦ 【`sqlite ∪ pg` 并集】：两侧 DDL 都解析（`BYTEA` ≡ `BLOB`）⇒ 仅 pg 侧新列不漏 ⇒ ATK5。
  ⑧ 【空转守卫 + 接线】：候选列 = ∅ ⇒ `UNKNOWN`；绿时必须打印候选列数 + 已判写入点数；
     `AUD-S6` 已进 `registry.FROZEN_IDS`/`HARD_IDS`（否则 `AUD-G1` 整跑假红）。
  ⑨ 【不可见即未知】：非常量 SQL ∧ 表绑不到 ⇒ 记 `UNKNOWN`（★ 不静默丢站点）。
  ⑩ 【已判写入点 = 真有判决的站点数】：`cols == {}` 的静态站点归 `UNKNOWN` 且**不计入覆盖数**。
  ⑪ 【执行器调用不可见即未知】（`repair-3`）：`execute`/`executemany`/`executescript` 的 SQL 实参
     **非常量** ⇒ ★ **不得**以「文本含写关键字」为前置（`conn.execute(build_sql(), …)` 的文本根本
     读不到）⇒ 一律登记为【不透明站点 ⇒ `UNKNOWN`】。
  ⑫ 【站点级判决】（`repair-3`）：每个站点**只用它自己的值**判决 —— 同一 `(表, 列)` 其它站点的
     「不可判」**不得传染**本站点（旧口径按 `(表, 列)` 汇总 ⇒ 一处的 UNKNOWN 会连坐同表同列）。

★★ 残余盲区（`repair-3` · `Lead` 的**终止条件**）—— ★ 静态分析的能力边界**不可能穷尽**
  ★ 本判据**不声称完备**；下列形态**看不见或不判定**，且已【写进文档 + 每次运行打印】：
  ① 动态代码生成 SQL（`getattr`/`eval`/`exec`/模板引擎）· ② 跨函数/跨模块**返回**的 SQL
  （只能记 `UNKNOWN`，**不是**判定）· ③ 数据驱动表名/列名（dict/配置/RPC）· ④ 更深间接
  （多层包装/元编程）· ⑤ 列名不含凭据关键词的凭据列（`ATK6` 名面盲区）· ⑥ `JSON` 载体
  （`extra_json`/`models_json`）内嵌凭据 · ⑦ 非 `.py`/`.sql` 载体的写入 · ⑧ 库里**已有数据**
  （本判据只看代码写入点）· ⑨ 等价加密实现的漏认（只认两个已验证导入源的助手）。
  ⇒ ★★ 故**坚持打印覆盖计数**（`已判写入点` = 真有判决的站点数）与 `UNKNOWN` 站点数，
     让能力边界被【输出暴露】，而不是用绿冒充完备。

★ 已知限制（如实登记 · 不用绿冒充覆盖）
  · **名面结构性盲区**（`ATK6`）：列名不含凭据关键词的凭据列（如 `providers.auth`）**不在判据面内**
    ⇒ 每次运行都打印盲区 hint，且【不】声明已覆盖 ⇒ 见 `hints`。
  · 表绑定不可静态确定的站点（如 `f"UPDATE {tbl} SET …"`）⇒ ★ **计入 `UNKNOWN`**（不计入覆盖数）。
  · 载体面：只看 `.sql` DDL 的列名 + `.py` 写入点；`JSON` 载体（`extra_json` / `models_json`）内嵌
    凭据、以及非 `TEXT/VARCHAR/BLOB/BYTEA` 载体的凭据**不在本判据面内**。
  · `AUD-S6` 只覆盖【代码写入点】·**不覆盖库里已有数据** ⇒ 「判据变绿 ≠ 已加密」（存量可能仍明文）。
"""
import ast
import pathlib
import re

from .. import registry as reg

# ★ 凭据语义列名（`R1 §2` 冻结口径 · 大小写不敏感的子串匹配）
CRED_WORDS = ("api_key", "secret", "access_key", "token", "password", "passwd", "credential")
# ★ 不可逆哈希列：不要求加密（`R1` 冻结排除 · 逐条理由见 PLAN §4）
HASH_SUFFIX = "_hash"
# ★ 只扫这些载体类型（`R1` 冻结：一次排除 3 个 INTEGER 误报）· `BYTEA` = pg 侧 `BLOB` 拼法
CRED_TYPES = ("TEXT", "VARCHAR", "BLOB", "BYTEA")
# ★ 已加密候选列的命名指纹（★ 仅当【值形态验证通过】才排除 ⇒ 硬要求⑥）
ENC_SUFFIXES = ("_enc", "_blob")
# ★ 合法非凭据列登记表（★ 逐条【精确坐标 + 理由】· ★ 禁通配/禁后缀模式 ⇒ ATK4 仍被抓）
#   ★ 当前实测 = 【空】—— 仓库今天没有「关键词命中但合法非凭据」的 TEXT/VARCHAR/BLOB 列；
#   ★ 若将来出现（如 `api_token_hint TEXT`：只是提示串、不是凭据）⇒ ★ 必须在此【逐条登记坐标 + 理由】，
#     并在 review 里说明；★ 绝不允许改 `CRED_WORDS` 或加后缀模式来「消红」（那正是 ATK4 的入口）。
BENIGN_COLUMNS = {}

# ★ 已验证的加密助手（硬要求⑤：必须解析导入源 · 禁名字单判）
ENCRYPT_SOURCES = {
    "octop.infra.connectors.crypto": frozenset({"encrypt_credentials"}),
    "octop.infra.auth.sso.crypto": frozenset({"encrypt_secret"}),
}
INPUT_FACES = ("src/octop", "scripts")
DDL_DIR = "src/octop/infra/db/migrations"

INSERT_RE = re.compile(
    r"\bINSERT\s+(?:OR\s+[A-Za-z]+\s+)?INTO\s+(?P<t>[A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE
)
UPDATE_RE = re.compile(
    r"\bUPDATE\s+(?P<t>[A-Za-z_][A-Za-z0-9_]*)\s+SET\b", re.IGNORECASE
)
CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<t>[A-Za-z_][A-Za-z0-9_]*)\s*\(",
    re.IGNORECASE,
)
INSERT_COLS_RE = re.compile(
    r"INSERT\s+(?:OR\s+[A-Za-z]+\s+)?INTO\s+[A-Za-z_][A-Za-z0-9_]*\s*\((?P<cols>[^)]*)\)"
    r"\s*VALUES\s*\((?P<vals>.*?)\)",
    re.IGNORECASE | re.DOTALL,
)
UPDATE_SET_RE = re.compile(r"\bSET\b(?P<body>.*?)(?:\bWHERE\b|$)", re.IGNORECASE | re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\?|%s")
SQL_KEYWORDS = ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "KEY(", "EXCLUDE")

BLIND_SPOT = (
    "★ 盲区登记（ATK6）：列名不含凭据关键词的凭据列（如 `providers.auth`）**不在判据面内** "
    "⇒ 不得用绿冒充覆盖；本判据只覆盖【名面命中 ∧ 类型命中】的列"
)
CARRIER_BLIND_SPOT = (
    "★ 载体盲区：JSON 载体（`extra_json`/`models_json`）内嵌凭据与非 TEXT/VARCHAR/BLOB/BYTEA "
    "载体的凭据不在本判据面内；且本判据只覆盖【代码写入点】，不覆盖库里已有数据"
)
# ★★ 终止条件（`repair-3` · `Lead` 裁定）：静态分析的能力边界**不可能穷尽** ⇒
#    ★ 不无限追新形态，而是把【残余盲区】**写进文档 + 每次运行打印出来**，并**坚持打印覆盖计数**。
RESIDUAL_BLIND_SPOTS = (
    "动态代码生成 SQL（`getattr` / `eval` / `exec` / 模板引擎）",
    "跨函数/跨模块【返回】的 SQL（本判据只能把它们记成 `UNKNOWN`，**不是**判定）",
    "数据驱动表名/列名（dict / 配置 / RPC 传来的标识符）",
    "更深间接（多层包装 / 元编程 / 序列化后拼接）",
    "列名不含凭据关键词的凭据列（名面盲区 · 见 `ATK6`）",
    "JSON 载体（`extra_json` / `models_json`）内嵌凭据",
    "非 `.py`/`.sql` 载体的写入（外部工具直接改库）",
    "库里【已有数据】（本判据只看代码写入点）",
    "等价加密实现的漏认（只认两个已验证导入源的 `encrypt_credentials`/`encrypt_secret`）",
)
COVERAGE_NOTE = (
    "★ 覆盖计数（★ 坚持打印 · 不得用绿冒充完备）：已判写入点 = %d（真有判决：红 / 全加密）· "
    "UNKNOWN = %d（不可判/不透明站点 · **不计入覆盖**）⇒ ★ 本判据**不是**完备证明"
)
BLIND_SPOTS_HINT = "★ 残余盲区枚举（★ 不可能穷尽 · 写下来并被输出暴露 · 不声称完备）：" + " · ".join(
    "%d) %s" % (i + 1, item) for i, item in enumerate(RESIDUAL_BLIND_SPOTS)
)


def _iter_py(root):
    """★ 硬要求①：输入面 = 全仓 `src/octop/**` + `scripts/**`（非仅 `db/repos`）。"""
    out = []
    for face in INPUT_FACES:
        out.extend(reg.iter_py(root, face))
    return out


def _strip_sql_comments(text):
    return re.sub(r"--[^\n]*", "", text)


def _split_top_level(text):
    """★ 按顶层逗号切分（跳过括号内逗号）。"""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def _ddl_candidates(root):
    """★ 扫两侧 DDL ⇒ `({(table, col): …}, ddl_files, skipped)`（硬要求⑦ 并集）。

    ★ `skipped` = 关键词命中但被【`*_hash` / 类型】排除的列 ⇒ 误报面【逐条登记 + 给理由】
    （★ 不是「命名型排除」：`*_hash`/类型是 `R1` 冻结规则，且每一条都在输出里逐条打印）。
    """
    out = {}
    skipped = []
    ddl_dir = pathlib.Path(root) / DDL_DIR
    if not ddl_dir.is_dir():
        return out, [], skipped
    files = sorted(ddl_dir.glob("*.sql"))
    for path in files:
        side = "pg" if path.name.endswith(".pg.sql") else "sqlite"
        try:
            text = _strip_sql_comments(
                path.read_text(encoding="utf-8", errors="replace")
            )
        except OSError:
            continue
        for match in CREATE_TABLE_RE.finditer(text):
            table = match.group("t").lower()
            depth, idx = 1, match.end()
            while idx < len(text) and depth:
                if text[idx] == "(":
                    depth += 1
                elif text[idx] == ")":
                    depth -= 1
                idx += 1
            body = text[match.end() : idx - 1]
            for item in _split_top_level(body):
                tokens = item.split()
                if len(tokens) < 2:
                    continue
                name, kind = tokens[0].strip('"'), tokens[1].upper()
                if any(name.upper().startswith(k) for k in SQL_KEYWORDS):
                    continue
                lowered = name.lower()
                if not any(word in lowered for word in CRED_WORDS):
                    continue
                base_type = kind.split("(")[0]
                if lowered.endswith(HASH_SUFFIX):
                    skipped.append((table, lowered, "`*_hash` 不可逆哈希 ⇒ 不要求加密"))
                    continue
                if base_type not in CRED_TYPES:
                    skipped.append((table, lowered, f"类型 {base_type} 不在 TEXT/VARCHAR/BLOB/BYTEA"))
                    continue
                entry = out.setdefault((table, lowered), {"types": set(), "sides": set()})
                entry["types"].add(base_type)
                entry["sides"].add(side)
    return out, files, skipped


def _imports(tree):
    """★ `local name → 完整模块路径`（硬要求⑤：解析导入源）。"""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = f"{node.module}.{alias.name}"
                out.setdefault(alias.asname or alias.name, node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out[alias.asname or alias.name.split(".")[0]] = alias.name
    return out


def _module_bindings(tree):
    """★ 模块顶层【自己绑定】的名字（`def`/`class`/赋值）⇒ ★ 会**遮蔽**同名 import。

    ★ 硬要求⑤：`encrypt_*` 光看 import 不够 —— 同文件自造同名函数（`SEC1` 的 `C1`）必须判【红】。
    """
    bound = set()
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            bound.add(node.target.id)
    return bound


def _is_verified_encrypt(call, imports, shadowed=frozenset()):
    """★ 硬要求⑤：只认【导入源已验证 ∧ 未被本模块同名绑定遮蔽】的加密助手。"""
    func = call.func
    if isinstance(func, ast.Name):
        if func.id in shadowed:
            return False
        source = imports.get(func.id)
        if source is None:
            return False
        return any(source == f"{mod}.{name}"
                   for mod, names in ENCRYPT_SOURCES.items() for name in names)
    if isinstance(func, ast.Attribute):
        owner = func.value
        if isinstance(owner, ast.Name):
            if owner.id in shadowed:
                return False
            base = imports.get(owner.id)
            if base is not None:
                return any(
                    func.attr in names and base in (mod, f"{mod}.{func.attr}")
                    for mod, names in ENCRYPT_SOURCES.items()
                )
    return False


class _Scope:
    """★ 作用域感知上下文（硬要求④：同函数体 + 语句链支配 · 无文本窗口）。"""

    def __init__(self, tree, path, imports, func, chains):
        self.path = path
        self.imports = imports
        self.shadowed = _module_bindings(tree)
        self.func = func
        self.chains = chains
        self.params = []
        self.param_index = {}
        if func is not None:
            all_args = list(func.args.posonlyargs) + list(func.args.args) + list(func.args.kwonlyargs)
            for i, arg in enumerate(all_args):
                self.params.append(arg.arg)
                self.param_index[arg.arg] = i

    def method_name(self):
        return self.func.name if self.func is not None else None

    def find_assignments(self, name, lineno):
        """★ 支配该用点的赋值集合（硬要求④：同函数体 + 支配关系）。

        ★ =【最近一处直接赋值】∪【支配性条件块内的赋值】—— 后者覆盖
        `if c: x = encrypt(...)` 这种「条件路径」，避免把「有条件加密 ⇒ 值必为 None」误判。
        """
        values, best = [], None
        for stmts in self.chains:
            for stmt in stmts:
                if stmt.lineno >= lineno:
                    continue
                value = self._direct_value(stmt, name)
                if value is not None and (best is None or stmt.lineno > best[0]):
                    best = (stmt.lineno, value)
                if isinstance(stmt, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                    values.extend(self._nested_values(stmt, name))
        if best is not None:
            values.insert(0, best[1])
        return values

    @staticmethod
    def _direct_value(stmt, name):
        targets, value = [], None
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
            targets, value = [stmt.target], stmt.value
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return value
        return None

    @classmethod
    def _nested_values(cls, stmt, name, depth=0):
        if depth > 2:
            return []
        out = []
        for field in ("body", "orelse", "finalbody"):
            for sub in getattr(stmt, field, None) or []:
                value = cls._direct_value(sub, name)
                if value is not None:
                    out.append(value)
                out.extend(cls._nested_values(sub, name, depth + 1))
        for handler in getattr(stmt, "handlers", None) or []:
            for sub in handler.body:
                value = cls._direct_value(sub, name)
                if value is not None:
                    out.append(value)
                out.extend(cls._nested_values(sub, name, depth + 1))
        return out


def _enclosing_func(tree, node):
    best = None
    for item in ast.walk(tree):
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if item.lineno <= node.lineno <= (item.end_lineno or item.lineno):
            if best is None or item.lineno > best.lineno:
                best = item
    return best


def _statement_chains(tree, node):
    """★ 包含 `node` 的所有语句列表（从模块到最内层 · 支配判定的依据）。"""
    chains = []

    def contains(block):
        return any(
            isinstance(stmt, ast.stmt)
            and stmt.lineno <= node.lineno
            and (stmt.end_lineno or stmt.lineno) >= node.lineno
            for stmt in block
        )

    def visit(item):
        if isinstance(item, ast.Module):
            chains.append(item.body)
            for stmt in item.body:
                visit(stmt)
            return
        if not hasattr(item, "lineno"):
            return
        if item.lineno > node.lineno or (getattr(item, "end_lineno", 0) or 0) < node.lineno:
            return
        for field in ("body", "orelse", "finalbody"):
            block = getattr(item, field, None)
            if isinstance(block, list) and block and contains(block):
                chains.append(block)
                for stmt in block:
                    visit(stmt)

    visit(tree)
    return chains


def _scope_of(tree, rel, imports, func, node):
    """★ 构造作用域（硬要求④：链只从【所在函数】起算 ⇒ 模块级/类体赋值不参与局部名字回溯）。"""
    base = func if func is not None else tree
    return _Scope(tree, rel, imports, func, _statement_chains(base, node))


def _resolve(expr, scope, path, depth=0):
    """⇒ `(verdict, why)`；verdict ∈ ENCRYPTED / PLAINTEXT / PARAM / NULL / UNRESOLVED。"""
    if expr is None:
        return "UNRESOLVED", "无值表达式"
    if depth > 3:
        return "UNRESOLVED", "变量回溯超过 3 层"
    if isinstance(expr, ast.Constant):
        if expr.value is None or expr.value == "" or expr.value == b"":
            return "NULL", "空值/None"
        return "PLAINTEXT", "字面量常量（未加密）"
    if isinstance(expr, ast.IfExp):
        left = _resolve(expr.body, scope, path, depth + 1)
        right = _resolve(expr.orelse, scope, path, depth + 1)
        kinds = {left[0], right[0]}
        if "ENCRYPTED" in kinds and kinds <= {"ENCRYPTED", "NULL"}:
            return "ENCRYPTED", "条件表达式两侧均为加密或空值"
        if "ENCRYPTED" in kinds:
            return "PLAINTEXT", "条件表达式存在未加密分支"
        return _aggregate([left, right], "条件表达式")
    if isinstance(expr, ast.Call):
        if _is_verified_encrypt(expr, scope.imports, scope.shadowed):
            return "ENCRYPTED", "已验证的加密调用"
        name = _call_name(expr)
        return "PLAINTEXT", f"调用 `{name}` 未经验证为加密助手"
    if isinstance(expr, ast.JoinedStr):
        return "PLAINTEXT", "f-string 拼接值（未加密）"
    if isinstance(expr, ast.BinOp):
        return "PLAINTEXT", "运算/拼接值（未加密）"
    if isinstance(expr, ast.Name):
        values = scope.find_assignments(expr.id, expr.lineno)
        if values:
            return _aggregate([_resolve(value, scope, path, depth + 1) for value in values],
                              "同作用域赋值")
        if expr.id in scope.params:
            return "PARAM", expr.id
        return "UNRESOLVED", f"名字 `{expr.id}` 无同作用域绑定"
    if isinstance(expr, ast.Attribute):
        return "PLAINTEXT", f"属性取值 `{ast.unparse(expr)[:40]}` 未证明加密"
    if isinstance(expr, ast.Subscript):
        return "PLAINTEXT", "下标取值未证明加密"
    return "UNRESOLVED", f"不认识的值表达式 `{type(expr).__name__}`"


def _aggregate(items, why):
    kinds = {item[0] for item in items}
    if "PLAINTEXT" in kinds:
        return "PLAINTEXT", why + "存在明文分支"
    if kinds & {"UNRESOLVED", "PARAM"}:
        return "UNRESOLVED", why + "含不可判分支"
    if "ENCRYPTED" in kinds:
        return "ENCRYPTED", why + "均为加密/空值"
    return "NULL", why + "均为空值"


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return type(func).__name__


def _literal_parts(expr):
    return [n.value for n in ast.walk(expr) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _table_of(text):
    match = UPDATE_RE.search(text)
    if match:
        return match.group("t").lower()
    match = INSERT_RE.search(text)
    if match:
        return match.group("t").lower()
    return None


def _module_assignments(tree):
    """★ 模块顶层赋值 ⇒ `{name: [value 表达式]}`（★ 供 SQL 变量回溯 · 硬要求⑨）。"""
    out = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.setdefault(target.id, []).append(node.value)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            out.setdefault(node.target.id, []).append(node.value)
    return out


def _sql_texts(expr, scope, module_assigns, depth=0):
    """★ SQL 实参可能持有的 SQL 文本候选 ⇒ `(texts, is_constant)`（硬要求⑨「不可见即未知」）。

    ★ 解析面：常量 · **变量**（同函数支配赋值 ∪ 模块顶层赋值）· f-string **占位**（一层）·
      拼接字面量（join）⇒ ★ 只有【单个 `ast.Constant`】才算静态可判，其余一律 `is_constant=False`。
    """
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return [expr.value], True
    if depth > 2:
        return [], False
    if isinstance(expr, ast.JoinedStr):
        parts = []
        for value in expr.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                sub, _ = _sql_texts(value.value, scope, module_assigns, depth + 1)
                parts.append(sub[0] if len(sub) == 1 else "\x00")
            else:
                parts.append("\x00")
        return ["".join(parts)], False
    if isinstance(expr, ast.Name):
        values = scope.find_assignments(expr.id, expr.lineno) if scope is not None else []
        if not values:
            values = module_assigns.get(expr.id, [])
        out = []
        for value in values:
            sub, _ = _sql_texts(value, scope, module_assigns, depth + 1)
            out.extend(sub)
        return out, False
    return [" ".join(_literal_parts(expr))], False


def _sql_argument(node):
    """⇒ `(sql_arg, sql_index|None, is_executor)`；★ 两类站点：

    ① **DB 执行方法**（`execute`/`executemany`/`executescript` ⇒ 方法名口径，含 `cursor`/`conn`）
       ⇒ 第 1 个位置参数（或 `sql=` 关键字）**恒为该语句**（★ 非常量也算 ⇒ 硬要求⑨⑪）。
    ② **助手形调用**（如 `insert_returning_id(conn, sql, params)`）⇒ 取**字面量含写语句**的那个实参。
    """
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr in {"execute", "executemany", "executescript"}:
        if node.args:
            return node.args[0], 0, True
        for kw in node.keywords:
            if kw.arg in {"sql", "query", "statement"}:
                return kw.value, None, True
        return None, None, True
    for idx, arg in enumerate(node.args):
        parts = _literal_parts(arg)
        if any(INSERT_RE.search(part) or UPDATE_RE.search(part) for part in parts):
            return arg, idx, False
    for kw in node.keywords:
        if kw.arg in {"sql", "query", "statement"}:
            parts = _literal_parts(kw.value)
            if any(INSERT_RE.search(part) or UPDATE_RE.search(part) for part in parts):
                return kw.value, None, False
    return None, None, False


def _write_tables(text):
    """★ 一段 SQL 文本里的写目标表（`INSERT INTO` / `UPDATE … SET`）。"""
    found = [match.group("t").lower() for match in INSERT_RE.finditer(text)]
    found += [match.group("t").lower() for match in UPDATE_RE.finditer(text)]
    return found


def _sites_in_file(path, rel, target_tables):
    """⇒ 该文件里、落在候选表上的写入站点（★ 静态 SQL 判值；**非常量 SQL ⇒ `UNKNOWN`**）。"""
    try:
        source = reg.read_source(path)
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    imports = _imports(tree)
    module_assigns = _module_assignments(tree)
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        sql_arg, sql_index, is_executor = _sql_argument(node)
        if sql_arg is None:
            continue
        func = _enclosing_func(tree, node)
        scope = _scope_of(tree, rel, imports, func, node)
        texts, is_constant = _sql_texts(sql_arg, scope, module_assigns)
        tables = [table for text in texts for table in _write_tables(text)]
        bound = next((table for table in tables if table in target_tables), None)
        if bound is None:
            # ★ 硬要求⑨⑪「不可见即未知」：**非常量** SQL 且表**完全绑不到** ⇒ 记 `UNKNOWN`
            #   （显式登记 · 不静默丢站点）；★★ 执行器调用**不得**以「文本含写关键字」为前置
            #   （`conn.execute(build_sql(), …)` 的文本根本读不到 ⇒ 旧口径会【连站点都不建】）。
            # ★ 表**已绑定**（含绑到非候选表）或 SQL 是常量 ⇒ 明确不是本判据面 ⇒ 跳过。
            if not is_constant and not tables and (is_executor or any(
                re.search(r"\b(INSERT|REPLACE|UPDATE)\b", text, re.I) for text in texts
            )):
                sites.append({"table": None, "rel": rel, "line": sql_arg.lineno, "dynamic": True,
                              "cols": {}})
            continue
        dynamic = not is_constant
        cols = {}
        if not dynamic:
            value_args = list(node.args[(sql_index + 1) if sql_index is not None else 0 :])
            value_args += [kw.value for kw in node.keywords if kw.arg not in {"sql", "query", "statement"}]
            cols = _bind_columns(sql_arg.value, value_args, scope)
        sites.append({"table": bound, "rel": rel, "line": sql_arg.lineno, "dynamic": dynamic,
                      "cols": cols, "scope": scope})
    return sites


def _params_of(value_args, scope):
    """★ 参数元组 ⇒ 元素表达式列表（仅认 `(a, b, c)` / `[a, b, c]` 字面量或同作用域绑定）。"""
    if len(value_args) != 1:
        return None
    arg = value_args[0]
    if isinstance(arg, (ast.Tuple, ast.List)):
        if any(isinstance(e, (ast.Tuple, ast.List)) for e in arg.elts):
            return None
        return list(arg.elts)
    if isinstance(arg, ast.Name):
        nearest = scope.find_assignments(arg.id, arg.lineno)
        bound = nearest[0] if nearest else None
        if isinstance(bound, (ast.Tuple, ast.List)):
            return list(bound.elts)
    return None


def _bind_columns(sql, value_args, scope):
    """★ 静态 SQL ⇒ `{column: value_expr}`（列 ↔ 占位符 ↔ 参数元组 逐位对齐）。"""
    params = _params_of(value_args, scope)
    if params is None:
        return {}
    out = {}
    insert = INSERT_COLS_RE.search(sql)
    if insert:
        columns = [c.strip().strip('"').lower() for c in insert.group("cols").split(",")]
        values = _split_top_level(insert.group("vals"))
        if len(columns) != len(values):
            return {}
        for idx, column in enumerate(columns):
            if idx < len(params) and PLACEHOLDER_RE.fullmatch(values[idx].strip()):
                out[column] = params[idx]
        return out
    update = UPDATE_SET_RE.search(sql)
    if update:
        index = 0
        for item in _split_top_level(update.group("body")):
            if "=" not in item:
                continue
            column, _, remainder = item.partition("=")
            column = column.strip().strip('"').lower()
            holes = len(PLACEHOLDER_RE.findall(remainder))
            if holes:
                if index < len(params):
                    out[column] = params[index]
                index += holes
        return out
    return {}


def _caller_args(root, py_files, method_name, param_name, param_index):
    """★ 硬要求③/④：把【函数形参】回溯到调用点实参（限定同参数名 / 同位置 · 失败即不可判）。"""
    found = []
    if not method_name:
        return found
    for path in py_files:
        try:
            tree = ast.parse(reg.read_source(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        imports = _imports(tree)
        rel = reg.rel(root, path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != method_name:
                continue
            expr = None
            for kw in node.keywords:
                if kw.arg == param_name:
                    expr = kw.value
            if expr is None and param_index >= 1 and len(node.args) >= param_index:
                expr = node.args[param_index - 1]
            if expr is None:
                continue
            func_def = _enclosing_func(tree, node)
            scope = _scope_of(tree, rel, imports, func_def, node)
            found.append((expr, scope, rel))
    return found


def _resolve_param_leaves(root, py_files, scope, param_name, seen, depth=0):
    """★ 形参 ⇒ 调用点实参（★ 有界递归 · 深度 ≤ 2 · 防自递归）⇒ **叶子判决列表**。

    ★★ 叶子 = 每个可解析调用点实参的判决（不再聚合）⇒ 供【值形态验证】区分
    「全不可判」与「有加密证据且无明文证据」（硬要求⑥）。
    """
    if depth > 2:
        return [("UNRESOLVED", "形参回溯超过 2 层")]
    signature = (scope.method_name(), param_name)
    if signature in seen:
        return [("UNRESOLVED", "形参回溯出现环（%s.%s）" % signature)]
    args = _caller_args(root, py_files, scope.method_name() or "", param_name,
                        scope.param_index.get(param_name, -1))
    if not args:
        return [("UNRESOLVED", "无调用点可回溯")]
    leaves = []
    for expr, caller_scope, rel in args:
        verdict = _resolve(expr, caller_scope, rel)
        if verdict[0] == "PARAM":
            leaves.extend(_resolve_param_leaves(root, py_files, caller_scope, verdict[1],
                                                seen | {signature}, depth + 1))
        else:
            leaves.append(verdict)
    return leaves


@reg.criterion("AUD-S6", reg.HARD)
def check_plaintext_columns(ctx):
    """★ `AUD-S6` 主判据（三态 + 计数 + 逐条 `表.列@path:line`）。"""
    root = pathlib.Path(ctx.repo)
    candidates, ddl_files, skipped_cols = _ddl_candidates(root)
    files = list(ddl_files)
    py_files = _iter_py(root)
    files.extend(py_files)
    rel_files = sorted({reg.rel(root, p) for p in files})

    hints = [BLIND_SPOT, CARRIER_BLIND_SPOT, BLIND_SPOTS_HINT]
    if skipped_cols:
        hints.append(
            "★ 误报面登记（关键词命中但被冻结规则排除 · 逐条理由）："
            + " · ".join("%s.%s（%s）" % item for item in sorted(set(skipped_cols)))
        )
    hints.append(
        "★ 合法非凭据列登记表 `BENIGN_COLUMNS` = %d 条（★ 逐条坐标 + 理由 · 禁通配 · "
        "新增必须过 review；★ 不得用它给【值形态为明文】的列开脱）：%s"
        % (len(BENIGN_COLUMNS), " · ".join("%s.%s（%s）" % (t, c, why)
                                          for (t, c), why in sorted(BENIGN_COLUMNS.items())) or "（空）")
    )
    if not candidates:
        return reg.Result(
            "AUD-S6", reg.HARD, reg.UNKNOWN, checked=0,
            message="候选列 = 0（空转守卫）⇒ 不得记绿（硬要求⑧）", files=rel_files, hints=hints,
        )

    judged, verified, single_side = {}, {}, []
    for key, meta in sorted(candidates.items()):
        if len(meta["sides"]) == 1:
            single_side.append("%s.%s（仅 %s 侧）" % (key[0], key[1], sorted(meta["sides"])[0]))
        judged[key] = meta
    if single_side:
        hints.append("★ 仅单侧存在的候选列（并集已纳入 · 另一侧 DDL 缺失）：" + " · ".join(single_side))

    sites = []
    target_tables = {key[0] for key in judged}
    for path in py_files:
        found = _sites_in_file(path, reg.rel(root, path), target_tables)
        sites.extend(found)
    # ★ 硬要求③（`repair-3` 修订措辞 · 以更严的 ⑨⑪ 为准）：表绑定不可静态确定的站点
    #   **不再丢弃** ⇒ 进入下面的判定循环并记 `UNKNOWN`（**计入 UNKNOWN · 不计入覆盖数**）。
    unbound = [s for s in sites if s["table"] is None]
    if unbound:
        hints.append(
            "★ 不透明站点（非常量 SQL ∧ 表不可静态绑定）%d 处 ⇒ ★ 计入 `UNKNOWN`（**不计入覆盖数** · "
            "硬要求③⑨⑪）：%s%s"
            % (len(unbound), " · ".join("%s:%d" % (s["rel"], s["line"]) for s in unbound[:5]),
               " …" if len(unbound) > 5 else "")
        )

    # ★ 硬要求⑥：`*_enc`/`*_blob` 只在【值形态验证通过】时移出判定面
    verdicts = {}
    leaf_verdicts = {}
    for site in sites:
        for column, expr in site["cols"].items():
            key = (site["table"], column)
            if key not in judged:
                continue
            verdict, why = _resolve(expr, site["scope"], site["rel"])
            if verdict == "PARAM":
                param = why
                leaves = _resolve_param_leaves(root, py_files, site["scope"], param, frozenset())
                verdict, extra = _aggregate(leaves, "调用点实参")
                why = "形参 `%s` ⇒ %s" % (param, extra)
            else:
                leaves = [(verdict, why)]
            verdicts.setdefault(key, []).append((site, verdict, why))
            leaf_verdicts.setdefault(key, []).extend(leaves)

    # ★ 硬要求⑥：`*_enc`/`*_blob` 的【值形态验证】—— 叶子判决里【有加密证据 ∧ 无明文证据】
    #   ⇒ 移出判定面；不可判调用点【登记为残余】但不阻断排除。
    for key in sorted(judged):
        if not key[1].endswith(ENC_SUFFIXES):
            continue
        kinds = [v for v, _ in leaf_verdicts.get(key, [])]
        if "ENCRYPTED" in kinds and "PLAINTEXT" not in kinds:
            verified[key] = kinds
    for key in verified:
        judged.pop(key, None)
        verdicts.pop(key, None)
    if verified:
        parts = []
        for key in sorted(verified):
            kinds = verified[key]
            parts.append("%s.%s（加密 %d · 明文 0 · 不可判 %d）"
                         % (key[0], key[1], kinds.count("ENCRYPTED"),
                            sum(1 for k in kinds if k in {"UNRESOLVED", "NULL"})))
        hints.append(
            "★ 已加密正例（★ 值形态验证通过 ⇒ 移出判定面 · 硬要求⑥）：" + " · ".join(parts)
            + " ⇒ ★ 残余不确定性：上列「不可判」调用点（如无调用点的透传包装）已登记，"
              "不阻断排除但也不得当作「已全覆盖」的证据"
        )

    # ★ FAIL/UNKNOWN 一律【逐写入点】计数（★ 一个站点写多列只计一处）；
    # ★★ 硬要求⑩：`已判写入点` **只计真有判决的站点**（红 / 全加密）—— 不可判/不透明/列绑定不了的
    #    站点归 `UNKNOWN` 且**不**计入覆盖数（★ 不得用「计数 +1」冒充「已覆盖」）。
    # ★★ 硬要求⑪/站点级隔离（`repair-3`）：★ 每个站点**只用它自己的值判决** —— 同一 `(表, 列)`
    #    的其它站点的「不可判」**不得传染**本站点（旧口径按 `(表, 列)` 汇总 ⇒ 一处的 UNKNOWN 会把
    #    同表同列的其它站点一起降级）。
    fails, unknown_entries, judged_sites, unknown_sites, opaque = [], [], [], 0, []
    for site in sites:
        if site["table"] is None:
            opaque.append(site)
            continue
        if site["table"] not in {k[0] for k in judged}:
            continue
        label = "%s@%s:%d" % (site["table"], site["rel"], site["line"])
        if site["dynamic"]:
            unknown_entries.append("%s（非常量 SQL ⇒ 结构性 UNKNOWN · 硬要求②⑨）" % label)
            unknown_sites += 1
            continue
        if not site["cols"]:
            unknown_entries.append("%s（列绑定不可静态确定：参数形态非单元素元组/列表字面量 ⇒ 硬要求⑩）"
                                   % label)
            unknown_sites += 1
            continue
        plain, undecided = [], []
        for column, expr in sorted(site["cols"].items()):
            if (site["table"], column) not in judged:
                continue
            for entry_site, verdict, why in verdicts.get((site["table"], column), []):
                if entry_site is not site:      # ★ 站点级隔离：只认【本站点】的判决
                    continue
                if verdict == "PLAINTEXT":
                    plain.append("%s（%s）" % (column, why))
                elif verdict == "UNRESOLVED":
                    undecided.append("%s（%s）" % (column, why))
        if plain:
            fails.append("%s（未加密：%s）" % (label, " · ".join(plain)))
            judged_sites.append((site["rel"], site["line"]))
        elif undecided:
            unknown_entries.append("%s（不可判：%s）" % (label, " · ".join(undecided)))
            unknown_sites += 1
        else:
            judged_sites.append((site["rel"], site["line"]))

    unknown_sites += len(opaque)
    if opaque:
        unknown_entries.append(
            "不透明执行器站点 %d 处（非常量 SQL ∧ 表不可静态绑定 ⇒ ★ 不可见即未知 · 硬要求⑨⑪）：%s%s"
            % (len(opaque), " · ".join("%s:%d" % (s["rel"], s["line"]) for s in opaque[:6]),
               " …" if len(opaque) > 6 else "")
        )

    counts = ("候选列 %d（判定面 %d · 已加密正例 %d）· 已判写入点 %d · FAIL %d · UNKNOWN %d"
              % (len(candidates), len(judged), len(verified), len(judged_sites),
                 len(fails), unknown_sites))
    detail = " · ".join(fails + unknown_entries) if (fails or unknown_entries) else "写入值均经已验证的加密调用"
    if fails:
        state = reg.FAIL
    elif unknown_sites:
        state = reg.UNKNOWN
    else:
        state = reg.OK
    hints.append(COVERAGE_NOTE % (len(judged_sites), unknown_sites))
    return reg.Result("AUD-S6", reg.HARD, state, checked=len(judged_sites),
                      message="%s · %s" % (counts, detail), files=rel_files, hints=hints)
