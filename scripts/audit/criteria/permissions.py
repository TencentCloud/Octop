"""★ `AUD-S4` `perm.discussion_two_lines`（`PLAN §2` · `FIND-6` / `FIND-14`）。"""
import ast
import re

from .. import registry as reg

TARGET_REL = "src/octop/infra/projects/discussion.py"
GOVERN_NAME = "_may_govern"
TOKENS = ("is_admin", "owner_user_id")
RAW_RE = re.compile(r"\bis_admin\b|owner_user_id")


def _judge_points(tree):
    """★ 判定 token 穷尽清单（4 类 AST 形态 · 注释/docstring 天然不计）。"""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in TOKENS:
            hits.append(node.lineno)
        elif isinstance(node, ast.Attribute) and node.attr in TOKENS:
            hits.append(node.lineno)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "getattr" and len(node.args) >= 2:
            arg = node.args[1]
            if isinstance(arg, ast.Constant) and arg.value in TOKENS:
                hits.append(node.lineno)
        elif isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            has_role = any((isinstance(s, ast.Name) and s.id == "role")
                           or (isinstance(s, ast.Attribute) and s.attr == "role") for s in operands)
            has_admin = any(isinstance(s, ast.Constant) and s.value == "admin" for s in operands)
            if has_role and has_admin:
                hits.append(node.lineno)
    return sorted(set(hits))


@reg.criterion("AUD-S4", reg.HARD)
def check_governance_points(ctx):
    path = ctx.repo / TARGET_REL
    try:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return reg.Result("AUD-S4", reg.HARD, reg.UNKNOWN,
                          message="读不到目标文件（%s）⇒ 不得记绿" % exc, files=[TARGET_REL])
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return reg.Result("AUD-S4", reg.HARD, reg.UNKNOWN,
                          message="AST 解析失败（%s）⇒ 读到不认识的格式 ⇒ 不得记绿" % exc,
                          files=[TARGET_REL])
    govern = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == GOVERN_NAME:
            govern = node
            break
    if govern is None:
        return reg.Result("AUD-S4", reg.HARD, reg.UNKNOWN,
                          message="未找到 %s ⇒ 不得记绿" % GOVERN_NAME, files=[TARGET_REL])
    hits = _judge_points(tree)
    if not hits:
        return reg.Result("AUD-S4", reg.HARD, reg.UNKNOWN,
                          message="判定点零命中 ⇒ 不得记绿", files=[TARGET_REL])
    raw_lines = sum(1 for text in lines if RAW_RE.search(text))
    inside = [h for h in hits if govern.lineno <= h <= govern.end_lineno]
    outside = [h for h in hits if not (govern.lineno <= h <= govern.end_lineno)]
    skipped = max(0, raw_lines - len(hits))
    if outside:
        return reg.Result("AUD-S4", reg.HARD, reg.FAIL, checked=len(inside), skipped=skipped,
                          message="区间外判定点 %d 处（%s）⇒ 治理门被绕过"
                                  % (len(outside), ", ".join(":%d" % n for n in outside)),
                          files=[TARGET_REL])
    if len(inside) == 2:
        return reg.Result("AUD-S4", reg.HARD, reg.OK, checked=2, skipped=skipped,
                          message="治理判定点 2 处（均在 %s 内）" % GOVERN_NAME, files=[TARGET_REL])
    if len(inside) > 2:
        return reg.Result("AUD-S4", reg.HARD, reg.FAIL, checked=len(inside), skipped=skipped,
                          message="n_judge = %d ≥ 3 ⇒ 违反上界断言（多出第 3 处）" % len(inside),
                          files=[TARGET_REL])
    return reg.Result("AUD-S4", reg.HARD, reg.UNKNOWN, checked=len(inside), skipped=skipped,
                      message="n_judge = %d < 2 ⇒ 判定点变少（fail-closed ⇒ 不得记绿）" % len(inside),
                      files=[TARGET_REL])
