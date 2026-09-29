"""★ `AUD-S2` `audit_log.append_only`（`PLAN §2` · `FIND-7` 收紧 DELETE 口径）。"""
import re

from .. import registry as reg

TABLE = "audit_log"
TIME_COLUMNS = ("ts", "created_at", "at", "created")
INSERT_RE = re.compile(r"\bINSERT\s+INTO\s+audit_log\b", re.IGNORECASE)
REPLACE_RE = re.compile(r"\bREPLACE\s+INTO\s+audit_log\b", re.IGNORECASE)
DELETE_RE = re.compile(
    r"DELETE\s+FROM\s+audit_log\s+WHERE\s+(ts|created_at|at|created)\s*<\s*(\?|%s|['\"]?[\w:.\- ]+['\"]?)\s*$",
    re.IGNORECASE,
)
BAD_RE = re.compile(r"\b(UPDATE\s+audit_log|DROP\s+TABLE\s+audit_log|TRUNCATE\s+audit_log)\b", re.IGNORECASE)
OR_RE = re.compile(r"\bOR\b|1\s*=\s*1", re.IGNORECASE)
STRING_RE = re.compile(r'"([^"]*)"|\'([^\']*)\'')


def _sql_text(line):
    """★ 取该行里的 SQL 文本（字符串字面量拼接）⇒ 判据只看 SQL，不看 Python 外壳。"""
    parts = []
    for m in STRING_RE.finditer(line):
        parts.append(m.group(1) if m.group(1) is not None else m.group(2))
    return " ".join(parts).strip()


@reg.criterion("AUD-S2", reg.HARD)
def check_append_only(ctx):
    mentions = []
    dml = []
    for path in reg.iter_py(ctx.repo, "src/octop"):
        try:
            lines = reg.read_lines(path)
        except (OSError, UnicodeDecodeError):
            return reg.Result("AUD-S2", reg.HARD, reg.UNKNOWN,
                              message="读不到 %s ⇒ 不得记绿" % reg.rel(ctx.repo, path))
        name = reg.rel(ctx.repo, path)
        for line_no, text in enumerate(lines, 1):
            if TABLE not in text:
                continue
            mentions.append((name, line_no))
            sql = _sql_text(text)
            if INSERT_RE.search(sql):
                dml.append(("INSERT", name, line_no))
            elif REPLACE_RE.search(sql):
                dml.append(("REPLACE", name, line_no))
            elif re.search(r"\bDELETE\s+FROM\s+audit_log\b", sql, re.IGNORECASE):
                dml.append(("DELETE", name, line_no))
            elif BAD_RE.search(sql):
                dml.append(("BAD", name, line_no))
    files = sorted({name for name, _ in mentions})
    if not mentions:
        return reg.Result("AUD-S2", reg.HARD, reg.UNKNOWN, message="全仓无 audit_log 命中 ⇒ 不得记绿")
    bad = []
    for kind, name, line_no in dml:
        if kind in ("BAD", "REPLACE"):
            bad.append("%s:%d ⇒ 非白名单 DML（%s）" % (name, line_no, kind))
    for kind, name, line_no in dml:
        if kind != "DELETE":
            continue
        sql = _sql_text(reg.read_lines(ctx.repo / name)[line_no - 1])
        if OR_RE.search(sql):
            bad.append("%s:%d ⇒ DELETE 含 OR / 1=1（判红）" % (name, line_no))
        elif not DELETE_RE.search(sql):
            bad.append("%s:%d ⇒ DELETE 非「时间列 < 参数/常量」形态" % (name, line_no))
    inserts = sum(1 for k, _, _ in dml if k == "INSERT")
    deletes = sum(1 for k, _, _ in dml if k == "DELETE")
    if bad:
        return reg.Result("AUD-S2", reg.HARD, reg.FAIL, checked=len(dml),
                          message="审计表可改写：%s" % " · ".join(bad), files=files)
    return reg.Result("AUD-S2", reg.HARD, reg.OK, checked=len(dml),
                      message="DML = INSERT %d / 带窗 DELETE %d" % (inserts, deletes), files=files)
