"""★ `AUD-G2` `Makefile @207` 依赖行冻结（回归判据 · `PLAN §2`）。"""
from .. import registry as reg


@reg.criterion("AUD-G2", reg.REGRESSION)
def check_makefile_freeze(ctx):
    path = ctx.repo / reg.MAKEFILE_NAME
    if not path.is_file():
        return reg.Result("AUD-G2", reg.REGRESSION, reg.UNKNOWN, message="Makefile 读不到 ⇒ 不得记绿")
    try:
        lines = reg.read_lines(path)
    except (OSError, UnicodeDecodeError) as exc:
        return reg.Result("AUD-G2", reg.REGRESSION, reg.UNKNOWN,
                          message="Makefile 读不到（%s）⇒ 不得记绿" % exc)
    lineno = reg.MAKEFILE_FROZEN_LINENO
    if lineno > len(lines):
        return reg.Result("AUD-G2", reg.REGRESSION, reg.FAIL,
                          message="Makefile 仅 %d 行 < %d ⇒ 冻结行缺失" % (len(lines), lineno),
                          files=[reg.MAKEFILE_NAME])
    actual = lines[lineno - 1]
    if actual == reg.MAKEFILE_FROZEN_LINE:
        return reg.Result("AUD-G2", reg.REGRESSION, reg.OK, checked=1,
                          message="Makefile:%d 逐字未变" % lineno, files=[reg.MAKEFILE_NAME])
    elsewhere = [i + 1 for i, text in enumerate(lines) if text == reg.MAKEFILE_FROZEN_LINE]
    drift = "（行号漂移（在 :%d））" % elsewhere[0] if len(elsewhere) == 1 else ""
    return reg.Result("AUD-G2", reg.REGRESSION, reg.FAIL, checked=1,
                      message="Makefile:%d = %r ≠ 冻结字面%s" % (lineno, actual, drift),
                      files=[reg.MAKEFILE_NAME])
