"""★ `AUD-G1` 未知格式守卫（横切 · 注册表自检 · `PLAN §2`/`§8`）。

★ 事实由入口在跑完其余 8 条判据后注入（`ctx.guard_facts`）⇒ ★ 因此本判据在注册表里**排最后**。
"""
from .. import registry as reg


@reg.criterion("AUD-G1", reg.GUARD)
def check_registry_guard(ctx):
    """★ 违规 ⇒ `UNKNOWN` ⇒ `exit 2`（fail-closed · ★ 绝不记绿）。"""
    facts = getattr(ctx, "guard_facts", None)
    if facts is None:
        facts = reg.registry_guard_facts([], [])
    return reg.guard_result(facts)
