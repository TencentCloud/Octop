# -*- coding: utf-8 -*-
"""Update the plan doc after the 018 -> 019 renumber.

Only unambiguous references are rewritten. A few lines (the pre-flight checks
"shed 018 must be free") are historical now and are left alone, because
rewriting them would turn a correct past instruction into a wrong present one.
The appended status section explains what actually happened.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PLAN = Path(r"D:\nancc\octop\Octop-总计划与落地开发计划.md")

# (pattern, replacement) applied globally — each is unambiguous.
REWRITES: list[tuple[str, str]] = [
    ("018_projects", "019_projects"),
    ("test_migration_018", "test_migration_019"),
    ("UPDATE _schema_version SET version = 18;", "UPDATE _schema_version SET version = 19;"),
    ("迁移 018", "迁移 019"),
    ("migration 018", "migration 019"),
    ("Migration 018", "Migration 019"),
    ("v18 迁移", "v19 迁移"),
    ("M2 迁移 019（或并入 018，视 M1 是否已发版）", "M2 迁移 020（019 已被 M1 占用并随本分支提交）"),
]

STATUS = """

---

# 附录 H：执行实况（2026-09-27，v2.2 之后）

> 这一节记录**实际做完的部分**与计划原文的偏差。计划正文未逐条改写的地方，以本节为准。

## H.1 已完成并推送（`feature/projects-p0`，8 个提交）

| 提交 | 卡片 | 内容 |
|---|---|---|
| `7858e1b5` | T1.1 + T1.2 | 迁移（**019**，见 H.2）+ 16 处版本断言 |
| `3d7c3b79` | S2 仓储层 | Project / Member / Task repo（按计划附录 C 拆 4 文件） |
| `2f07aaa6` | T2.1 | KB 生命周期（补偿删除）+ 项目状态机 + §4.6 权限矩阵 |
| `c3ac257c` | T2.3 | 任务 CRUD + 任务状态机 + `timeline_events` |
| `9ef2b70d` | **T1.4** | 路由层 + app 注册 + OpenAPI tag + 10 个实体专属错误码 |
| `23bc3a66` | T2.2 | 前端：项目列表 / 详情 / 成员 |
| `a8f808a8` | — | 修复：知识库功能不可用时仍能立项（见 H.3） |
| `c7b57690` | — | 改号 018 → 019（见 H.2） |

**门禁**：`make all` → **3852 passed, 111 skipped**。PG 路径另有三份独立验证脚本。

## H.2 迁移号 018 被上游占用 → 改号 019

计划写的是 `018_projects`。执行期间上游 `develop` 抢走了 018：

```
upstream/develop  9a13f53f
  018_user_role.sql / 018_user_role.pg.sql   ← schema v18 = 角色模板
```

`_discover()` 对重复版本号**直接抛 RuntimeError** —— 两个 018 并存会让**每次数据库操作都失败**（不只是某个测试）。

**改号范围**（`_tools/renumber_018_to_019.py` 一次做完，13 项验证脚本 `_tools/verify_migration_numbering.py` 确认）：

1. `018_projects.{sql,pg.sql}` → `019_projects.{sql,pg.sql}`，水位 18 → 19
2. `_ensure_projects_schema` 读 019 文件对
3. 我方 sqlite 分支 → `if version == 19:`
4. **上游的 `if version == 18:` 与 `_ensure_user_role_schema` 原样保留**
5. 16 处断言 18 → 19（叠加在上游自己的 17 → 18 之上）

> ⚠️ **解冲突时最危险的一点**：`migrate.py` 里两个 `if version == 18:` 因为**位于不同函数**（`_apply_sqlite_migration` 与 `run_migrations`），git **文本上自动合并成功**。表面无冲突，实际第一个分支会吃掉第二个。**必须人工核对，不能只看 git 有没有报冲突。**

## H.3 设计缺口：项目 KB 是「必需」还是「尽力绑定」

**部署到全新 `~/.octop` 时发现的真 bug**：`POST /api/projects` 返回 500 `PROJECT_KB_BIND_FAILED`。

根因：新装 Octop 的 `knowledge_bases_enabled` 默认 **false**，`create_base` 抛 `RuntimeError`；而 T2.1 的 ⓪ 前置校验**只查了权限/数量/重名，没查功能是否可用**。测试漏掉它是因为 fixture 把 `assert_knowledge_usable` 打桩成了 no-op。

**计划自相矛盾**：T2.1 ①③ 要求 KB 失败即补偿删除（暗示必需），但 T3.4 前置写「归档只在 `kb_id IS NOT NULL` 时执行」（暗示可以为 NULL）。

**当前实现**（已在 `a8f808a8` 落地）：

| 知识库功能状态 | 行为 |
|---|---|
| **可用** | 正常绑 KB；③④ 失败仍走补偿删除 → `PROJECT_KB_BIND_FAILED` |
| **不可用** | 项目照建，`kb_id = NULL`，记一条 log |

理由：若强制必需，全新安装**在配好 embedding 模型前建不出任何项目**，T3.4 那句就是死文本。

> **待你裁决**：如果产品上要求「必须先配好知识库才能立项」，把 `create_project` 里 `bind_kb` 为 False 的分支改成抛 `OctopError(KNOWLEDGE_FEATURE_DISABLED)` 即可（一处）。

## H.4 其它实况

- **`git` 只推 `origin`（你的 fork）**；`upstream` 的 pushurl 已设为 `DISABLED` 锁死（`remote.upstream.pushurl = DISABLED`）。
- **pre-commit 钩子成本**：testmon 串行跑 894 个测试要 **20 分钟**；手动 `make all`（xdist 并行全量 3800+）只要 **3.6 分钟**。→ 采用「手动 `make all` 绿 + `SKIP_PRECOMPIT=1 git commit`」。
- **`release/1.0.2b3` 不要合并**：它是 `develop` 的子集（`develop - release = 0` 个提交），唯一提交只改了 CHANGELOG / README / 版本号字符串，**零代码**；且按 AGENTS.md §10 是发完即删的临时冻结分支。
- **本地部署**：`octop init` 后 `octop run --host 127.0.0.1 --port 8088`，SQLite 控制面。`~/.octop` 老库（v18，只有项目表）在重启后**自愈**到 v19 并补齐了上游的 `user_role` 表 —— 这是 `_ensure_*` 幂等 helper 的价值实证。
"""


def main() -> int:
    text = PLAN.read_text(encoding="utf-8")
    for old, new in REWRITES:
        n = text.count(old)
        if n:
            text = text.replace(old, new)
            print(f"  {n:>3}x  {old!r} -> {new!r}")

    if "附录 H：执行实况" in text:
        print("  status section already present; not appending again")
    else:
        text = text.rstrip() + "\n" + STATUS
        print("  appended 附录 H：执行实况")

    PLAN.write_text(text, encoding="utf-8", newline="")

    left = text.count("018_projects") + text.count("test_migration_018")
    print(f"\nremaining stale identifiers: {left}")
    print(f"remaining '018' occurrences: {text.count('018')} (historical references only)")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
