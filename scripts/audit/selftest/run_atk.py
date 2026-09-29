#!/usr/bin/env python3
"""★ `AUD-S6` 反攻击探针族（`AC-3` · **仓库件** · 可复跑）· 入口 = 本文件。

★ 用法：`python3 scripts/audit/selftest/run_atk.py`          （逐个 `ATK` 输出 `PASS`/`FAIL`）
        `python3 scripts/audit/selftest/run_atk.py --only ATK1pp,ATK3`
        `python3 scripts/audit/selftest/run_atk.py --keep`     （保留 `/tmp/k_ac3/**` 便于复核）
★ 退出码：★ 全部 `PASS` ⇒ `0` · ★ 任一被【放行】⇒ `1`（`PLAN §3`）。
★ 副本树配方：`git clone -q --no-hardlinks <repo> <dest>`（★ 必须带 `.git`：无 `.git` ⇒ 判据取不到
  git 元数据 ⇒「未知格式守卫」⇒ `exit 2` · `PLAN:107` 实测）★ 并覆盖【工作树现行 `scripts/audit`】
  （★ 因本批改动尚未提交 ⇒ 只 clone 会拿到旧判据 —— 如实登记该配方偏差）。
★ 信号口径：★ **全量** `python3 scripts/audit/current_tree.py` 的 `[AUD-S6]` 行（★ `--only` 不可用 · `PLAN §6`）。
★ 不打印任何真实凭据值（★ 注入样本一律 `sk-DUMMY-*` 自造串）。

逐条期望（`PLAN §3` · `Lead` 裁定）
  `ATK1''` 零修复 + 顶层永不被调用的同名诱饵/同名绑定 ⇒ `[AUD-S6]` 必须【非绿】（★ 最关键）
  `ATK2`   `db/repos/` **之外**的明文写入 ⇒ 必须非绿（输入面 = 全仓）
  `ATK3`   写入点改成 f-string 动态 SQL ⇒ 必须 `UNKNOWN`（★ 不得绿）
  `ATK4`   新增**明文**列但命名 `*_enc` ⇒ 必须非绿（★ 命名型排除已禁 · 值形态验证）
  `ATK5`   新列**只加在 pg 侧** ⇒ 必须非绿（`sqlite ∪ pg` 并集）
  `ATK6`   列名**去关键词**（结构性盲区）⇒ ★ 显式盲区登记 ∧ 不得绿（★ 不得用绿冒充覆盖）
"""
import argparse
import ast
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import reference_fix  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
WORK = pathlib.Path("/tmp/k_ac3")
STATE_RE = re.compile(r"^\[AUD-S6\] (绿|红|未知)")
COUNT_RE = re.compile(r"已判 (\d+) ·")
BASELINE_COUNTED = None   # ★ 前置自检实测（`主树 已判 N`）· ★ 3.9 兼容：不写注解
DUMMY = "sk-DUMMY-ATK-000000000000"  # ★ 自造样本（非真实凭据）


def make_tree(name, *, reference=False):
    """★ 带 `.git` 的副本树（+ 工作树现行 `scripts/audit`；`reference=True` ⇒ 打参照修复）。"""
    dest = WORK / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(dest)], check=True)
    # ★★ 覆盖【工作树】的 `scripts/**` + `src/octop/**`：本批改动未提交 ⇒ 只 clone 会拿到旧代码
    #    （★ 判据要审的是【当前工作树】· 与 `git status` 的语义一致）
    shutil.copytree(ROOT / "scripts", dest / "scripts", dirs_exist_ok=True)
    shutil.copytree(ROOT / "src" / "octop", dest / "src" / "octop", dirs_exist_ok=True)
    # ★ 补 `.venv` 软链：F-L1(b)/(c) 子进程需要 `cryptography`；★ 子进程 `cwd=clone` 且自动
    #   `sys.path.insert(0, "src")` ⇒ 导入的仍是【clone 的源码】（不是 venv 里的可编辑安装）
    venv = ROOT / ".venv"
    if venv.is_dir() and not (dest / ".venv").exists():
        os.symlink(venv, dest / ".venv")
    if reference:
        reference_fix.apply(dest)
    return dest


def audit(tree, env=None):
    """⇒ `(state, s6_line, hints, stdout)`；★ `state ∈ {"绿","红","未知","<无>"}`。

    ★ `env` 用于**运行期绑定替换**类探针（`PYTHONPATH` 带 `sitecustomize`）。
    """
    proc = subprocess.run(["python3", "scripts/audit/current_tree.py"], cwd=str(tree),
                          capture_output=True, text=True, check=False,
                          env={**os.environ, **(env or {})})
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("[AUD-S6]")), "")
    hints = [ln.strip() for ln in proc.stdout.splitlines()
             if ln.strip().startswith("· 提示 [AUD-S6]")]
    match = STATE_RE.match(line)
    return (match.group(1) if match else "<无>"), line, hints, proc.stdout


def inject(tree, rel, text, *, anchor=None):
    """★ 写注入文件；`anchor` 给定 ⇒ 在锚点行后**插入**（DDL 场景）。"""
    path = tree / rel
    if anchor is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return
    original = path.read_text(encoding="utf-8")
    if original.count(anchor) != 1:
        raise AssertionError("%s：锚点命中 %d 次（期望 1）" % (rel, original.count(anchor)))
    path.write_text(original.replace(anchor, anchor + text), encoding="utf-8")


def inject_top_level(path, block, *, expect_name=None):
    """★ 在【模块顶层第一个 def/class/@ 之前】插入；`expect_name` ⇒ 断言该 def 在顶层。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines)
                 if line.startswith(("def ", "class ", "@")) and not line.startswith((" ", "\t")))
    lines.insert(index, block)
    path.write_text("".join(lines), encoding="utf-8")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    top = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    if expect_name is not None:
        assert expect_name in top, "诱饵不在模块顶层 ⇒ 探针无效（顶层 = %s）" % top[:5]


def plaintext_writer(func_name, table, columns):
    """★ 生成「repos 之外的明文写入点」源码 ⇒ 生成的 SQL 在副本树里是**单条字面量**（可判红）。

    ★★ 本函数体内**不得**出现含完整写语句的常量 —— 否则判据会把**探针自己**当成写入点
      （`scripts/**` 也在输入面内）⇒ SQL 一律在**运行时**拼（本文件里没有任何一处常量含完整语句）。
    """
    cols = ", ".join(columns)
    holes = ", ".join("?" * len(columns))
    sql = "INSERT" + " INTO " + table + "(" + cols + ") VALUES (" + holes + ")"
    fillers = ["name", '"openai"', '"http://localhost"']
    params = ", ".join(fillers[: len(columns) - 1] + ["key"])
    return (
        "from octop.infra.db.pool import DatabasePool\n\n\n"
        "def %s(db: DatabasePool, name: str) -> None:\n"
        '    key = "%s"\n'
        "    with db.transaction() as conn:\n"
        "        conn.execute(%r, (%s))\n" % (func_name, DUMMY, sql, params)
    )


def atk1pp():
    """★ 最关键：**顶层永不被调用的同名诱饵**（`def encrypt_secret` + 模块级同名绑定）**不得掩盖**
    一个真实的【明文】写入点 ⇒ 判据必须仍然【红】（★ `L` 批后本仓已自带加密 ⇒ 探针自带被掩盖的明文站点）。"""
    tree = make_tree("atk1pp")
    rel = "src/octop/infra/agents/atk1pp_decoy.py"
    inject(tree, rel, (
        'def encrypt_secret(repo, plain):   # 诱饵：顶层、永不被调用\n'
        '    return plain.encode("utf-8")\n\n\n'
        'api_key = b"gAAAAA-decoy-never-called"   # 诱饵：模块级同名绑定\n\n\n'
        "from octop.infra.db.pool import DatabasePool\n\n\n"
        "def atk1pp_write(db: DatabasePool, name: str) -> None:\n"
        '    key = "%s"\n' % DUMMY
        + "    with db.transaction() as conn:\n"
        '        conn.execute("%s", (name, "openai", key))\n'
        % ("INSERT" + " INTO " + "providers" + "(name, kind, api_key) VALUES (?, ?, ?)")
    ))
    state, line, _, _ = audit(tree)
    ok = state == "红" and rel in line
    return ok, state, line, "顶层诱饵 + 一个真实明文写入点 ⇒ 期望【红】且红点含该路径（★ 诱饵不得掩盖明文）"


def atk2():
    """★ `db/repos/` 之外的明文写入 ⇒ 必须非绿（输入面 = 全仓）。"""
    tree = make_tree("atk2", reference=True)
    rel = "src/octop/infra/agents/atk2_outside_repos.py"
    inject(tree, rel, plaintext_writer("atk2_write", "providers",
                                       ["name", "kind", "base_url", "api_key"]))
    state, line, _, _ = audit(tree)
    ok = state == "红" and rel in line
    return ok, state, line, "repos 外明文写入点已注入 ⇒ 期望【红】且红点含该路径"


def atk3():
    """★ 写入点改成 f-string 动态 SQL ⇒ 必须 `UNKNOWN`（★ 不得绿）。"""
    tree = make_tree("atk3", reference=True)
    rel = "src/octop/infra/db/repos/providers.py"
    path = tree / rel
    old = '"INSERT INTO providers(name, kind, base_url, api_key, "'
    new = 'f"INSERT INTO providers(name, kind, base_url, {_ATK3_COL}, "'
    if path.read_text(encoding="utf-8").count(old) != 1:
        raise AssertionError("ATK3：锚点命中数 != 1")
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    inject_top_level(path, '_ATK3_COL = "api_key"   # 动态列名（探针用）\n\n\n')
    state, line, _, _ = audit(tree)
    ok = state == "未知" and "结构性 UNKNOWN" in line and "providers" in line
    return ok, state, line, "providers 的 INSERT 已改为 f-string ⇒ 期望【未知 · 非常量 SQL】"


def atk4():
    """★ 新增明文列但命名 `*_enc` ⇒ 必须非绿（★ 命名型排除已禁 · 只认值形态）。"""
    tree = make_tree("atk4", reference=True)
    inject(tree, "src/octop/infra/db/migrations/001_initial.sql", "  sso_token_enc TEXT,\n",
           anchor="  api_key     TEXT,\n")
    rel = "src/octop/infra/agents/atk4_enc_named.py"
    inject(tree, rel, plaintext_writer("atk4_write", "providers", ["name", "kind", "sso_token_enc"]))
    state, line, _, _ = audit(tree)
    ok = state == "红" and "sso_token_enc" in line
    return ok, state, line, "`sso_token_enc TEXT` + 明文写入 ⇒ 期望【红】（命名不得豁免）"


def atk5():
    """★ 新列只加在 pg 侧 ⇒ 必须非绿（`sqlite ∪ pg` 并集）。"""
    tree = make_tree("atk5", reference=True)
    inject(tree, "src/octop/infra/db/migrations/001_initial.pg.sql", "  edge_secret_key TEXT,\n",
           anchor="  secret_key  TEXT,\n")
    rel = "src/octop/infra/agents/atk5_pg_only.py"
    inject(tree, rel, plaintext_writer("atk5_write", "storage_backends",
                                       ["name", "kind", "endpoint", "edge_secret_key"]))
    state, line, _, _ = audit(tree)
    ok = state == "红" and "edge_secret_key" in line
    return ok, state, line, "仅 pg 侧新列 + 明文写入 ⇒ 期望【红】（并集）"


def atk6():
    """★ 列名去关键词（结构性盲区）⇒ ★ 显式盲区登记 ∧ 不得绿 ∧ 不得声称覆盖。

    ★ 口径（如实）：名字面判据**不可能**抓到无关键词的列 ⇒ 本探针**不**要求抓到它；
      PASS = ① 输出里有【盲区登记】hint ∧ ② 该列**未**被声称覆盖 ∧ ③ 整跑**非绿**
      （★ 即：不得用「绿」冒充「已覆盖」）。
    """
    tree = make_tree("atk6")
    inject(tree, "src/octop/infra/db/migrations/001_initial.sql", "  auth TEXT,\n",
           anchor="  api_key     TEXT,\n")
    rel = "src/octop/infra/agents/atk6_keywordless.py"
    inject(tree, rel, plaintext_writer("atk6_write", "providers", ["name", "kind", "auth"]))
    state, line, hints, _ = audit(tree)
    registered = any("盲区登记" in hint for hint in hints)
    claimed = "providers.auth" in line
    # ★ L 批后主树已绿 ⇒ 本探针的「不得绿冒充覆盖」形态 = ① 盲区显式登记 ∧ ② 该列未被声称覆盖
    #   ∧ ③ **绿行必须逐字带覆盖计数护栏**（`已判 N · UNKNOWN M（已声明边界）`）
    guarded = ("已判 " in line) and ("（已声明边界）" in line)
    ok = registered and not claimed and guarded
    return ok, state, line, ("盲区显式登记 = %s · 是否被声称覆盖 = %s ⇒ ★ 该类列名**不在判据面内**"
                             "（结构性盲区 · 不构成覆盖证据）" % (registered, claimed))


def atk_name():
    """★ 补充探针（硬要求⑤）：写入值**未经加密**但函数名像加密（同文件自造同名包装）⇒ 必须【红】。"""
    tree = make_tree("atk_name", reference=True)
    path = tree / "src/octop/infra/db/repos/providers.py"
    # ★ L 树形态：**同文件伪造 `secret_codec`**（模块名遮蔽）⇒ `secret_codec.encrypt_value` 变成
    #   「只 encode」的假助手 ⇒ ★ 判据必须判【红】（导入源/遮蔽检查）
    inject_top_level(
        path,
        "class _FakeCodec:   # 探针：伪造 secret_codec（恒等「加密」）\n"
        "    @staticmethod\n"
        "    def encrypt_value(key, plain):\n"
        '        return plain.encode("utf-8")\n\n\n'
        "secret_codec = _FakeCodec()   # ★ 遮蔽上面的 import\n\n\n",
        expect_name="_FakeCodec",
    )
    state, line, _, _ = audit(tree)
    ok = state == "红" and "providers" in line
    return ok, state, line, "同名包装已遮蔽 import ⇒ 期望【红】（★ 禁名字单判 · 须解析导入源）"


def guard_empty():
    """★ 补充探针（硬要求⑧）：候选列 = 0 ⇒ 必须 `UNKNOWN`（空转守卫 · 不得记绿）。"""
    tree = make_tree("guard_empty")
    for path in (tree / "src/octop/infra/db/migrations").glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        renamed = re.sub(r"\b(api_key|secret_key|access_key|client_secret_enc|credential_blob)\b",
                         "col_neutral", text)
        if renamed != text:
            path.write_text(renamed, encoding="utf-8")
    state, line, _, _ = audit(tree)
    ok = state == "未知" and "候选列 = 0" in line
    return ok, state, line, "候选列清零（DDL 列名去关键词）⇒ 期望【未知 · 空转守卫】"


def h1_writer(func_name, table, column, *, module_level):
    """★ `H1` 载荷：SQL 存在**变量**里（模块级 / 局部）⇒ 站点此前【完全不可见】（假绿）。"""
    sql = "UPDATE " + table + " SET " + column + " = ? WHERE id = ?"
    head = "from octop.infra.db.pool import DatabasePool\n\n\n"
    if module_level:
        return (
            head
            + "STMT = %r\n\n\n" % sql
            + "def %s(db: DatabasePool, name: str) -> None:\n" % func_name
            + '    key = "%s"\n' % DUMMY
            + "    with db.transaction() as conn:\n"
            + "        conn.execute(STMT, (key, 1))\n"
        )
    return (
        head
        + "def %s(db: DatabasePool, name: str) -> None:\n" % func_name
        + '    key = "%s"\n' % DUMMY
        + "    STMT = %r\n" % sql
        + "    with db.transaction() as conn:\n"
        + "        conn.execute(STMT, (key, 1))\n"
    )


def h2_writer(func_name, table, column, form):
    """★ `H2` 载荷：**静态 SQL** + **非单元素元组/列表字面量**参数 ⇒ 此前「被判但零判决」（假覆盖）。"""
    sql = "UPDATE " + table + " SET " + column + " = ? WHERE id = ?"
    named = "UPDATE " + table + " SET " + column + " = :k WHERE id = :i"
    calls = {
        "dict": "        conn.execute(%r, {\"k\": key, \"i\": 1})\n" % sql,
        "named": "        conn.execute(%r, {\"k\": key, \"i\": 1})\n" % named,
        "executemany": "        conn.executemany(%r, [(key, 1), (key, 2)])\n" % sql,
        "tuple": "        conn.execute(%r, tuple([key, 1]))\n" % sql,
    }
    return (
        "from octop.infra.db.pool import DatabasePool\n\n\n"
        + "def %s(db: DatabasePool, name: str) -> None:\n" % func_name
        + '    key = "%s"\n' % DUMMY
        + "    with db.transaction() as conn:\n"
        + calls[form]
    )


def _h_probe(name, source, *, expect, forbid_growth=True):
    """★ `H1`/`H2`/`H3` 公共断言：站点**必须可见** · 状态 ∈ `expect`。

    `forbid_growth` ⇒ ★ 还要求【覆盖率计数不增加】（硬要求⑩）：★ 不可判/不透明站点**不得**计入 `已判`。
    """
    tree = make_tree(name, reference=True)
    rel = "src/octop/infra/agents/%s.py" % name.lower().replace("-", "_")
    inject(tree, rel, source)
    state, line, _, _ = audit(tree)
    counted = (BASELINE_COUNTED is None) or ("已判 %s" % BASELINE_COUNTED) in line
    ok = state in expect and rel in line and (counted or not forbid_growth)
    why = ("修复后：站点可见 ∧ 状态 = %s ∧ ★ 覆盖率计数【未增加】（`已判写入点 6` = %s）"
           % ("/".join(sorted(expect)), counted))
    return ok, state, line, why


def h1_module():
    """★ `H1` 形态一：**模块级**变量持 SQL ⇒ 必须【未知或红】（★ 不得静默不可见）。"""
    return _h_probe("H1-MODULE", h1_writer("h1_module", "providers", "api_key", module_level=True),
                    expect={"未知", "红"}, forbid_growth=False)


def h1_local():
    """★ `H1` 形态二：**局部**变量持 SQL ⇒ 必须【未知或红】。"""
    return _h_probe("H1-LOCAL", h1_writer("h1_local", "providers", "api_key", module_level=False),
                    expect={"未知", "红"}, forbid_growth=False)


def h2_dict():
    """★ `H2` 变体一：静态 SQL + `dict` 参数 ⇒ 必须【未知】且**不计入**覆盖率。"""
    return _h_probe("H2-DICT", h2_writer("h2_dict", "providers", "api_key", "dict"),
                    expect={"未知"})


def h2_named():
    """★ `H2` 变体二：静态 SQL + 具名 `:name` + `dict` ⇒ 必须【未知】且**不计入**覆盖率。"""
    return _h_probe("H2-NAMED", h2_writer("h2_named", "providers", "api_key", "named"),
                    expect={"未知"})


def h2_executemany():
    """★ `H2` 变体三：静态 SQL + `executemany` + 行列表 ⇒ 必须【未知】且**不计入**覆盖率。"""
    return _h_probe("H2-EXECUTEMANY",
                    h2_writer("h2_executemany", "providers", "api_key", "executemany"),
                    expect={"未知"})


def h2_tuple():
    """★ `H2` 变体四：静态 SQL + `tuple([...])` ⇒ 必须【未知】且**不计入**覆盖率。"""
    return _h_probe("H2-TUPLE", h2_writer("h2_tuple", "providers", "api_key", "tuple"),
                    expect={"未知"})


def h3_writer(func_name, form):
    """★ `H3a`/`H3b` 载荷：① 跨函数**返回**的 SQL（`conn.execute(build_sql(), …)`）；② `f-string`
    **变量表名**（`f"UPDATE {tbl} SET …"`）—— 两者此前都【不可见 / 不计入 UNKNOWN】。"""
    sql = "UPDATE " + "providers" + " SET api_key = ? WHERE id = ?"
    head = "from octop.infra.db.pool import DatabasePool\n\n\n"
    if form == "cross_fn":
        return (
            head
            + "def _build_sql() -> str:\n    return %r\n\n\n" % sql
            + "def %s(db: DatabasePool, name: str) -> None:\n" % func_name
            + '    key = "%s"\n' % DUMMY
            + "    with db.transaction() as conn:\n"
            + "        conn.execute(_build_sql(), (key, 1))\n"
        )
    return (
        head
        + "def %s(db: DatabasePool, name: str, tbl: str) -> None:\n" % func_name
        + '    key = "%s"\n' % DUMMY
        + "    with db.transaction() as conn:\n"
        + '        conn.execute(f"UPDATE {tbl} SET api_key = ? WHERE id = ?", (key, 1))\n'
    )


def _h3_probe(name, source):
    """★ `H3` 断言：**未知** ∧ 覆盖率计数**不增** ∧ 边界**差分可见**（★ 新增不透明站点触发）。"""
    tree = make_tree(name, reference=True)
    rel = "src/octop/infra/agents/%s.py" % name.lower().replace("-", "_")
    inject(tree, rel, source)
    state, line, hints, stdout = audit(tree)
    counted = (BASELINE_COUNTED is None) or ("已判 %s" % BASELINE_COUNTED) in line
    visible = ("差分" in stdout) or (rel in stdout)
    ok = state == "未知" and counted and visible
    return ok, state, line, ("站点可见（边界差分/坐标） ∧ 状态 = 未知 ∧ ★ 覆盖率计数未增加"
                             "（`已判 %s` = %s）" % (BASELINE_COUNTED, counted))


def h3_cross_fn():
    """★ `H3a`：跨函数返回的 SQL ⇒ 必须【未知】（★ 此前【连站点都不建】⇒ 假绿且无 hint）。"""
    return _h3_probe("H3-CROSS-FN", h3_writer("h3_cross_fn", "cross_fn"))


def h3_var_table():
    """★ `H3b`：f-string **变量表名** ⇒ 必须【未知】（★ 此前站点被登记但 `UNKNOWN 0`）。"""
    return _h3_probe("H3-VAR-TABLE", h3_writer("h3_var_table", "var_table"))


# ★★ 第三条假加密形态（`SR1`/`REVIEW-SPEC`）：**运行期替换绑定**
RUNTIME_PATCH = '''"""探针载荷：把 `secret_codec` 的加解密换成【恒等映射】（运行期 · 源码不变）。

★ 后果：源码 sha 不变（F-L1(a) 失效）· 真助手往返正常（F-L1(b) 失效）⇒ ★ 只有【数据面抽检】(c) 能拦。
"""

import importlib

try:
    _codec = importlib.import_module("octop.infra.db.secret_codec")
except Exception:  # pragma: no cover - 探针环境问题
    _codec = None

if _codec is not None:
    # ★★ 经典假形态：**把 base64 当加密**（★ 往返自洽 ⇒ 只有「解码后 Fernet.decrypt」能识破）
    _codec.encrypt_value = lambda key, plain: __import__("base64").urlsafe_b64encode(
        plain.encode("utf-8")
    ).decode("ascii")
    _codec.decrypt_value = lambda key, blob: __import__("base64").urlsafe_b64decode(
        blob if isinstance(blob, bytes) else str(blob).encode("utf-8")
    ).decode("utf-8")
'''


def h4_runtime_patch():
    """★ 第三条形态：**运行期替换绑定** ⇒ ★ 期望「判据行 = 绿 ∧ 数据面抽检 = 拦下」。

    ★★ 结论：**判据不可单独作为「已加密」的证据**（★ 三合一验收里，(c) 是唯一防线）。
    """
    tree = make_tree("h4_runtime_patch")
    (tree / "sitecustomize.py").write_text(RUNTIME_PATCH, encoding="utf-8")
    env = {"PYTHONPATH": os.pathsep.join([str(tree / "src"), str(tree)])}
    state, line, hints, _ = audit(tree, env=env)
    data_face = next((h for h in hints if "数据面抽检" in h), "")
    blocked = "拦下" in data_face
    ok = state == "绿" and blocked
    return ok, state, line, ("运行期替换绑定已生效 ⇒ 判据行 = %s（静态判据被绕过）· 数据面抽检 = %s"
                             "（★ 唯一防线）" % (state, "拦下" if blocked else "未拦下"))


PROBES = [
    ("ATK1pp", atk1pp),
    ("ATK2", atk2),
    ("ATK3", atk3),
    ("ATK4", atk4),
    ("ATK5", atk5),
    ("ATK6", atk6),
    ("ATK-NAME", atk_name),
    ("GUARD-EMPTY", guard_empty),
    # ★ `V1` 自造的两个绕过面（`repair-2` 收成永久探针 · 硬要求⑨⑩）
    ("H1-MODULE", h1_module),
    ("H1-LOCAL", h1_local),
    ("H2-DICT", h2_dict),
    ("H2-NAMED", h2_named),
    ("H2-EXECUTEMANY", h2_executemany),
    ("H2-TUPLE", h2_tuple),
    # ★ `V1b` 自造的两条新不可见形态（`repair-3` 收成永久探针 · 硬要求⑪⑫）
    ("H3-CROSS-FN", h3_cross_fn),
    ("H3-VAR-TABLE", h3_var_table),
    # ★ 第三条假加密形态（L 批 · `SR1` 裁定 · 「判据行绿 ∧ 数据面抽检拦下」）
    ("H4-RUNTIME-PATCH", h4_runtime_patch),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="AUD-S6 反攻击探针族（可复跑 · 逐个 ATK 报 PASS/FAIL）")
    parser.add_argument("--only", default=None, help="只跑指定 ATK（逗号分隔，如 ATK1pp,ATK3）")
    parser.add_argument("--keep", action="store_true", help="保留 /tmp/k_ac3/** 便于人工复核")
    args = parser.parse_args(argv)
    wanted = {item.strip() for item in args.only.split(",")} if args.only else None
    print("★ AUD-S6 反攻击探针族 · 仓库 = %s · 工作目录 = %s" % (ROOT, WORK))
    print("★ 信号 = 全量 `python3 scripts/audit/current_tree.py` 的 [AUD-S6] 行（★ --only 不可用）")
    results = []
    # ★ 前置自检：探针族自身也在 `scripts/**`（判据输入面内）⇒ 其载荷**不得**被判据当成写入点，
    #   否则探针会污染判据输出（`AC-1` 的 `3 FAIL + 3 UNKNOWN` 会被算歪）。
    _, main_line, _, _ = audit(ROOT)
    global BASELINE_COUNTED
    match = COUNT_RE.search(main_line)
    BASELINE_COUNTED = match.group(1) if match else None
    polluted = "scripts/audit/selftest" in main_line
    print("\n[前置自检] %s · 探针族自身是否污染判据输出 = %s"
          % ("PASS" if not polluted else "FAIL", polluted))
    results.append(("前置自检", not polluted))
    for name, fn in PROBES:
        if wanted is not None and name not in wanted:
            continue
        ok, state, line, why = fn()
        results.append((name, ok))
        print("\n[%s] %s · 实测 [AUD-S6] = %s" % (name, "PASS" if ok else "FAIL", state))
        print("   · %s" % why)
        print("   · %s" % line)
    failed = [name for name, ok in results if not ok]
    print("\n★ 汇总：%d/%d PASS%s" % (len(results) - len(failed), len(results),
                                    "" if not failed else " · 被放行 = " + ", ".join(failed)))
    if not args.keep:
        for name, _ in PROBES:
            shutil.rmtree(WORK / name, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
