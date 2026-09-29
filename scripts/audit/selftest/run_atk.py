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
DUMMY = "sk-DUMMY-ATK-000000000000"  # ★ 自造样本（非真实凭据）


def make_tree(name, *, reference=False):
    """★ 带 `.git` 的副本树（+ 工作树现行 `scripts/audit`；`reference=True` ⇒ 打参照修复）。"""
    dest = WORK / name
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(ROOT), str(dest)], check=True)
    shutil.copytree(ROOT / "scripts/audit", dest / "scripts/audit", dirs_exist_ok=True)
    if reference:
        reference_fix.apply(dest)
    return dest


def audit(tree):
    """⇒ `(state, s6_line, hints, stdout)`；★ `state ∈ {"绿","红","未知","<无>"}`。"""
    proc = subprocess.run(["python3", "scripts/audit/current_tree.py"], cwd=str(tree),
                          capture_output=True, text=True, check=False)
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
    """★ 最关键：零修复 + 顶层永不被调用的同名诱饵 ⇒ 判据必须仍然【红】。"""
    tree = make_tree("atk1pp")
    inject_top_level(
        tree / "src/octop/infra/db/repos/providers.py",
        'def encrypt_secret(repo, plain):\n'
        '    return plain.encode("utf-8")   # 诱饵：永不被调用\n\n\n'
        'api_key = b"gAAAAA-decoy-never-called"   # 诱饵：模块级同名绑定\n\n\n',
        expect_name="encrypt_secret",
    )
    state, line, _, _ = audit(tree)
    ok = state == "红" and "FAIL 3" in line
    return ok, state, line, "诱饵已注入（顶层 + 可解析）⇒ 期望仍【红 · FAIL 3】"


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
    ok = state != "绿" and registered and not claimed
    return ok, state, line, ("盲区显式登记 = %s · 是否被声称覆盖 = %s ⇒ ★ 该类列名**不在判据面内**"
                             "（结构性盲区 · 不构成覆盖证据）" % (registered, claimed))


def atk_name():
    """★ 补充探针（硬要求⑤）：写入值**未经加密**但函数名像加密（同文件自造同名包装）⇒ 必须【红】。"""
    tree = make_tree("atk_name", reference=True)
    path = tree / "src/octop/infra/db/repos/providers.py"
    inject_top_level(
        path,
        "def encrypt_secret(repo, plain):   # 同名包装：只做 encode，永不做加密\n"
        '    return plain.encode("utf-8")\n\n\n',
        expect_name="encrypt_secret",
    )
    old = "encrypt_secret(SecretRepo(self._db), api_key) if api_key else None"
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 2:
        raise AssertionError("ATK-NAME：锚点命中 %d 次（期望 2）" % text.count(old))
    path.write_text(text.replace(old, "encrypt_secret(None, api_key) if api_key else None"),
                    encoding="utf-8")
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


def _h_probe(name, source, *, expect):
    """★ `H1`/`H2` 公共断言：站点**必须可见** · 状态 ∈ `expect` · **覆盖率计数不得增加**（硬要求⑩）。"""
    tree = make_tree(name, reference=True)
    rel = "src/octop/infra/agents/%s.py" % name.lower().replace("-", "_")
    inject(tree, rel, source)
    state, line, _, _ = audit(tree)
    counted = "已判写入点 6" in line   # ★ 参照修复基线的【真有判决】站点数 = 6（★ 不得 +1）
    ok = state in expect and rel in line and counted
    why = ("修复后：站点可见 ∧ 状态 = %s ∧ ★ 覆盖率计数【未增加】（`已判写入点 6` = %s）"
           % ("/".join(sorted(expect)), counted))
    return ok, state, line, why


def h1_module():
    """★ `H1` 形态一：**模块级**变量持 SQL ⇒ 必须【未知或红】（★ 不得静默不可见）。"""
    return _h_probe("H1-MODULE", h1_writer("h1_module", "providers", "api_key", module_level=True),
                    expect={"未知", "红"})


def h1_local():
    """★ `H1` 形态二：**局部**变量持 SQL ⇒ 必须【未知或红】。"""
    return _h_probe("H1-LOCAL", h1_writer("h1_local", "providers", "api_key", module_level=False),
                    expect={"未知", "红"})


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


def h3_cross_fn():
    """★ `H3a`：跨函数返回的 SQL ⇒ 必须【未知】（★ 此前【连站点都不建】⇒ 假绿且无 hint）。"""
    return _h_probe("H3-CROSS-FN", h3_writer("h3_cross_fn", "cross_fn"), expect={"未知"})


def h3_var_table():
    """★ `H3b`：f-string **变量表名** ⇒ 必须【未知】（★ 此前站点被登记但 `UNKNOWN 0`）。"""
    return _h_probe("H3-VAR-TABLE", h3_writer("h3_var_table", "var_table"), expect={"未知"})


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
