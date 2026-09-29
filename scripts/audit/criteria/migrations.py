"""★ `AUD-S1` `migration.pg_pair`（`PLAN §2`）。"""
from .. import registry as reg

MIGRATIONS_REL = "src/octop/infra/db/migrations"
SQL_KEYWORDS = ("CREATE", "ALTER", "UPDATE", "DELETE", "INSERT", "DROP")


@reg.criterion("AUD-S1", reg.HARD)
def check_pg_pairing(ctx):
    base = ctx.repo / MIGRATIONS_REL
    if not base.is_dir():
        return reg.Result("AUD-S1", reg.HARD, reg.UNKNOWN, message="迁移目录不存在 ⇒ 不得记绿")
    sql_files = sorted(p for p in base.glob("*.sql") if p.is_file())
    non_pg = sorted({p.name[:-len(".sql")] for p in sql_files if not p.name.endswith(".pg.sql")})
    pg = sorted({p.name[:-len(".pg.sql")] for p in sql_files if p.name.endswith(".pg.sql")})
    files = [reg.rel(ctx.repo, p) for p in sql_files]
    if not non_pg or not pg:
        return reg.Result("AUD-S1", reg.HARD, reg.UNKNOWN,
                          message="两侧任一为空（非 pg = %d · pg = %d）⇒ 不得记绿" % (len(non_pg), len(pg)),
                          files=files)
    hints = []
    for name in pg:
        path = base / (name + ".pg.sql")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return reg.Result("AUD-S1", reg.HARD, reg.UNKNOWN,
                              message="读不到 %s ⇒ 不得记绿" % reg.rel(ctx.repo, path), files=files)
        if not text.strip() or not any(k in text.upper() for k in SQL_KEYWORDS):
            hints.append("%s ⇒ 空文件 / 无 SQL 关键字（提示级）" % reg.rel(ctx.repo, path))
    delta = sorted(set(non_pg) ^ set(pg))
    if delta:
        return reg.Result("AUD-S1", reg.HARD, reg.FAIL, checked=len(non_pg),
                          message="双后端迁移【不成对】差集 = {%s}" % ", ".join(delta),
                          files=files, hints=hints)
    return reg.Result("AUD-S1", reg.HARD, reg.OK, checked=len(non_pg),
                      message="双后端迁移成对（差集 = 0）· 内容提示 %d" % len(hints),
                      files=files, hints=hints)
