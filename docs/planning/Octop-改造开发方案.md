# Octop 改造开发方案（可落地版）

> 基于《Octop-项目管理与跨团队协作-可行性分析》的全部结论 + 已锁定的 6 项决策
> 目标：**每张任务卡都能直接派工**，含文件路径、接口契约、DDL、验收命令

---

## 0. 阶段总览与依赖

```
                  ┌─────────────────────────────────────────┐
                  │  里程碑 M1「项目管理可用」（可独立交付）      │
                  │                                         │
S0 聊天列表改造 ──┤  （可并行，或后置）                        │
                  │                                         │
S1 项目域地基 ────┤  迁移 018 + repo + 权限键 + 空壳路由        │
                  │                                         │
S2 项目/成员/任务/看板 ─────────────────────────────────────┤
                  │                                         │
S2.5 评论/打标/需求节点/Owner 闸门 ──────────────────────────┤
                  └─────────────────────────────────────────┘
                              │
                              ▼
                  ┌──── 等上游 infra/agents 重构稳定后 ────┐
                  │                                     │
                  │  S3 项目记忆                         │
                  │  S4 跨团队房间 + 工具放开             │
                  │  S5 派单 + 交付物                    │
                  └─────────────────────────────────────┘
```

**关键约束**

| 约束 | 说明 |
|---|---|
| **S0 与 S1/S2 互不依赖** | 可并行，也可先做项目域、S0 后补 |
| **S2 之后按需推进** | S3/S4/S5 互相独立 |
| **S3/S4/S5 建议推迟** | 它们要改 `infra/agents/**`，而**上游正在重构该目录**（`refactor(infra): group agents modules`，2026-09-25），此时动它 rebase 成本翻倍 |

### 为什么「先做项目功能」是当前最优排序

| # | 理由 | 证据 |
|---|---|---|
| 1 | **冲突面最小** | S1+S2 只碰 **5 个高 churn 文件**，且全是 i18n JSON + `errors.py`（**追加式改动，低冲突**）；而 S3/S4/S5 要碰的 `manager.py` / `memory_backend.py` / `memory_client.py` / `memory_portable.py` **全部是高 churn 功能文件** |
| 2 | **它是所有后续阶段的前置** | S3/S4/S5 都依赖项目域存在 |
| 3 | **正好错开上游重构窗口** | 上游正在重构 `infra/agents`（我们 S4/S5 的目标区），而项目域**完全不碰那个目录** |

### M1 交付范围界定

| ✅ 包含 | ❌ 不包含（留给后续） |
|---|---|
| 立项 / 编辑 / 归档 | 项目记忆（S3） |
| 成员与角色（真人 / 专家 / 团队） | 跨**用户**协作（S4） |
| 任务分解（父子 / 依赖 / 优先级 / 指派） | commit 回写（S5） |
| 任务看板（状态列 + 拖拽） | 记忆增量注入 |
| 任务讨论线（**复用现有 thread**） | |
| **派单给专家（同用户，现成能力）** | |
| 评论 / 打标 / 需求节点池 | |
| Owner 确认闸门（**接 HITL**） | |
| 资料归档（写项目 KB） | |
| 会话列表项目分组 + 「项目会话」标签 | |

> ⚠️ **重要澄清：派单在同用户内是现成能力，不需要 harness 补丁。**
> `ask_agent` + 团队 room 机制已经可用；harness 的 `bind_peer_scope` 补丁只是为了**跨用户**可见性（S4）。
> 所以 M1 内就能实现需求 M12「任务派给指定专家/团队，派工消息自动携带任务上下文」。

---

## 1. 全局工程纪律（每个任务卡都适用）

| # | 纪律 | 说明 |
|---|---|---|
| 1 | **Ship bar = `make all` 绿** | `format-all + lint + mypy + pytest`；前端另跑 `cd dashboard && npx tsc -b` |
| 2 | **迁移必须成对** | `018_x.sql` + `018_x.pg.sql`，文件末尾写 `UPDATE _schema_version SET version = 18;` |
| 3 | **迁移号断言 7 处** | [test_db_pool.py](Octop-develop/tests/unit/db/test_db_pool.py) 的 `assert v == 17` 全部改 `== 18` |
| 4 | **权限键三处同步** | 后端 `PERMISSIONS` + 前端 `PERM`/`NAV_PERMISSIONS`/`pathPermissionKeys` + 测试 `GATED_FILES` |
| 5 | **i18n 双语键对齐** | 后端 `src/octop/i18n/{en,zh}.json`；前端 `dashboard/src/locales/{en,zh}.json`；跑 `uv run pytest tests/unit/i18n -q` |
| 6 | **只加不改优先** | 新表/新路由/新页面优先；核心文件改动控制在个位数行 |
| 7 | **不改 `threads` 表** | 项目关联靠 `project_rooms` / `project_tasks` 反查 |
| 8 | **不动既有 per-agent 接口** | `GET /agents/{agent_id}/threads` 有 430+ 测试与多处前端依赖，新端点纯新增 |
| 9 | **资源表 id 约定** | 整数 `id` PK + 对外字符串 `{entity}_id` UNIQUE；子表 FK **字符串 id** |
| 10 | **交叉平台测试** | 涉及文件系统的测试用 `tmp_path` / `Path`，POSIX 专用行为加 `skipif(os.name != "posix")` |

---

## 2. S0：聊天列表改造（**可立即开工，独立上线**）

### 2.1 现状与问题

| 问题 | 证据 |
|---|---|
| 侧栏是**扁平 agent 列表**：只有当前 agent 展开显示会话，其余只是一行 | [SessionList.tsx:612-651](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:612)（`ActiveAgentCard` vs `InactiveAgentRow`） |
| **自己的专家藏不掉** | [useHiddenSharedExperts.ts:18](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:18) docstring：*"Owned experts are never treated as hideable"* |
| **进页面发 N 次请求** | [MinimalAgentSessionNav.tsx:359](Octop-develop/dashboard/src/pages/Chat/components/MinimalAgentSessionNav.tsx:359) `Promise.all(agents.map(...))` |
| 默认布局是 classic | [layoutModeStorage.ts:18](Octop-develop/dashboard/src/layouts/layoutModeStorage.ts:18) `return "classic"` |

### 2.2 S0-A 后端：新增跨 agent 会话端点

**新增文件**：`src/octop/api/routers/chat/sessions.py`

```python
"""Cross-agent conversation list for the chat sidebar."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends

from octop.api.deps import current_user, get_server
from octop.api.routers.chat.history import (
    _hitl_policy_payload,      # 复用，避免两份 payload 漂移
    thread_row_has_messages,
)
from octop.api.common.thread_artifacts import thread_artifacts_payload
from octop.api.common.workspace import _agent_facing_workspace_dir  # 按实际导入路径调整

router = APIRouter()


@router.get("/threads", summary="List conversations across all agents")
async def list_all_threads(
    limit: int = 200,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """One request for the whole sidebar: every thread this user can see."""
    effective_uid = as_user if as_user is not None else user.id
    rows = server.services.thread_repo.list_by_user(user_id=effective_uid, limit=limit + 1)
    truncated = len(rows) > limit
    rows = rows[:limit]
    return {
        "truncated": truncated,
        "threads": [
            {
                "thread_id": r.thread_id,
                "agent_id": r.agent_id,
                "title": r.title,
                "channel_type": r.channel_type,
                "last_active": r.last_active,
                "created_at": r.created_at,
                "has_messages": thread_row_has_messages(r),
                "pinned": r.pinned,
                "conversation_mode": r.conversation_mode or "craft",
                "hitl_policy": _hitl_policy_payload(r),
                **thread_artifacts_payload(
                    r.artifacts,
                    _agent_facing_workspace_dir(server, r.agent_id),
                    default_agent_id=r.agent_id,
                ),
            }
            for r in rows
        ],
    }
```

> ⚠️ 导入路径以实际为准：`thread_artifacts_payload` / `_agent_facing_workspace_dir` 在 [history.py](Octop-develop/src/octop/api/routers/chat/history.py:1) 顶部已有 import，直接照抄其来源。

**注册**：在 [chat/__init__.py](Octop-develop/src/octop/api/routers/chat/__init__.py:7) 加一行

```python
from octop.api.routers.chat.sessions import router as sessions_router
...
router.include_router(sessions_router)
```

路由前綴已是 `/api`（[app.py:219](Octop-develop/src/octop/api/app.py:219) `_RouterMount(chat.router, "/api", ["chat"])`），所以最终路径 = **`GET /api/threads`**。

**新增 repo 方法**：`src/octop/infra/db/repos/threads.py`

```python
def list_by_user(self, *, user_id: int, limit: int = 50) -> list[ThreadRow]:
    """Every thread this user owns, newest first — sidebar aggregation."""
    rows = self._db.connect().execute(
        "SELECT * FROM threads WHERE user_id = ? "
        "ORDER BY pinned DESC, last_active DESC, thread_id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    return [self._row(r) for r in rows]
```

> 排序沿用既有约定（[threads.py:213](Octop-develop/src/octop/infra/db/repos/threads.py:213) `ORDER BY pinned DESC, ...`）。不要按 `agent_id IN (...)` 过滤 —— `threads.user_id` 已经是「发起会话的用户」，共享专家的会话也记在发起人名下。

**为什么这一条端点就够**：前端已有完整 agent 列表（`AgentContext`），只需按 `agent_id` 分组即可算出「哪些 agent 零会话」——不需要在响应里塞 agent 元信息。

### 2.3 S0-B 前端：一次拉取 + 分组 + 标签

**新增 hook**：`dashboard/src/pages/Chat/hooks/useSessionInbox.ts`

```ts
export interface SessionInbox {
  byAgent: Record<string, Session[]>;   // agent_id → 该 agent 的会话
  pinned: Session[];                     // 跨 agent 的置顶会话
  loading: boolean;
}

export function useSessionInbox(agents: OctopAgent[]): SessionInbox
```

- 内部单次 `GET /api/threads?limit=200`，用 `toSession()`（复用 [useSessions.ts:34](Octop-develop/dashboard/src/pages/Chat/hooks/useSessions.ts:34)）归一化。
- 监听既有会话事件（新建/删除/重命名）做本地 patch —— 参照 [MinimalAgentSessionNav.tsx:408-497](Octop-develop/dashboard/src/pages/Chat/components/MinimalAgentSessionNav.tsx:408) 的 `patchLocal` 写法。
- **同一个 `agentKey` 依赖**（[MinimalAgentSessionNav.tsx:283](Octop-develop/dashboard/src/pages/Chat/components/MinimalAgentSessionNav.tsx:283)）避免 agent 列表抖动导致重复请求。

**改造 `SessionList.tsx`** —— 三段式结构：

```
📌 置顶 (n)                         ← pinned 会话，跨 agent 直接列出
💬 会话 (m)                         ← 有会话的 agent
   ├ 交付团队  [群聊]           ▸ 3
   ├ 开发专家                   ▸ 5
   └ ...
📦 未使用 (k)                    ▸   ← 默认折叠，固定排最后
```

具体改动点：

| # | 改动 | 位置 |
|---|---|---|
| 1 | 新增 props：`inboxByAgent: Record<string, Session[]>`、`pinnedSessions: Session[]` | [SessionList.tsx:491](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:491) |
| 2 | `sortedAgents` 拆成「有会话 / 未使用」两组；未使用组默认进 `collapsedGroups` | [:542-547](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:542) |
| 3 | `InactiveAgentRow` 增加该 agent 的会话数徽标 | [:397](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:397) |
| 4 | 新增 `SectionHeader` 组件（可折叠、带计数） | 新增 `components/SessionGroupHeader.tsx` |
| 5 | 未使用组在 `searchQuery` 非空时**强制展开** | [:532](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:532) |
| 6 | 挂 `TeamChatBadge`（群聊标签）到 agent 行 | [:641-650](Octop-develop/dashboard/src/pages/Chat/components/SessionList.tsx:641) |

**判定规则（关键）**：

```ts
// 「用过」= 该 agent 下存在 hasActivity 的会话
const hasActivity = (s: Session) => s.hasActivity;   // useSessions.ts:53 已定义
const used = (agentId: string) => (inboxByAgent[agentId] ?? []).some(hasActivity);
```

> ⚠️ **必须用 `hasActivity`，不能用「存在 thread」** —— 点进去会自动建空 thread，否则一误点就"被用过"，折叠永远不生效。

**放开隐藏能力** —— 改 [useHiddenSharedExperts.ts](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts)：

| 函数 | 现状 | 改为 |
|---|---|---|
| `filterVisible` [:56](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:56) | `if (!isSharedExpertViewer(agent)) return true;` | 删除该行，对所有 agent 生效 |
| `pickHidden` [:66](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:66) | 同上过滤 | 删除过滤 |
| `canHide` [:72](Octop-develop/dashboard/src/pages/Chat/hooks/useHiddenSharedExperts.ts:72) | `isSharedExpertViewer(agent)` | `true`（保留签名） |

**向后兼容**：storage key 不变（`octop:hidden-shared-experts`），已隐藏的共享专家保持隐藏。
建议**同时重命名文件/钩子**为 `useHiddenExperts` 以免语义误导 —— 但那会扩大 diff，**建议保留文件名，只改语义 + 更新 docstring**。

### 2.4 S0-C i18n 词条

| key | zh | en |
|---|---|---|
| `chat.sectionPinned` | 置顶 | Pinned |
| `chat.sectionActive` | 会话 | Conversations |
| `chat.sectionUnused` | 未使用 | Unused |
| `chat.sectionUnusedCount` | 未使用 ({count}) | Unused ({count}) |
| `chat.sectionActiveCount` | 会话 ({count}) | Conversations ({count}) |

前端 `dashboard/src/locales/{en,zh}.json`。`chat.teamBadge` 已存在，直接复用。

### 2.5 S0-D 测试与验收

**新增测试**

| 文件 | 覆盖 |
|---|---|
| `tests/unit/api/test_threads_router.py` | `GET /api/threads` 返回结构、`limit` 截断、`truncated` 标志、权限（未登录 401） |
| `tests/unit/db/test_repo_threads.py`（追加） | `list_by_user` 排序 `pinned DESC, last_active DESC` |
| `dashboard/src/pages/Chat/hooks/useSessionInbox.test.ts` | 分组正确、单次请求、事件 patch |
| `dashboard/src/pages/Chat/components/SessionList.grouping.test.tsx` | 未使用组默认折叠、搜索强制展开、群聊标签渲染 |

**验收清单**

```bash
# 后端
uv run pytest tests/unit/api/test_threads_router.py tests/unit/db -q
uv run pytest tests/unit/i18n -q
make all

# 前端
cd dashboard && npx tsc -b && npm run test -- --run
```

**人工验收**

1. 打开聊天页 → **Network 面板只出现 1 次 `/api/threads`**（改造前是 N 次）
2. 「未使用」组显示正确计数，默认折叠，点击展开
3. 搜索关键词 → 未使用组自动展开且命中项高亮
4. 团队 agent 显示「群聊」徽标
5. 设置里可隐藏**自建专家**（改造前不可）

**预估**：后端 0.5 天 · 前端 1.5 天 · 测试 0.5 天 = **2.5 天**

---

## 3. S1：项目域地基（P0）

### 3.1 迁移 018 —— 完整 DDL

**新增**：`src/octop/infra/db/migrations/018_projects.sql` 与 `018_projects.pg.sql`

```sql
-- Schema v18: project management domain.
-- Threads are NOT altered; project linkage resolves via project_rooms/project_tasks.

CREATE TABLE projects (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id      TEXT NOT NULL UNIQUE,
  name            TEXT NOT NULL,
  goal            TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'draft',   -- draft|active|paused|archived
  owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  memory_namespace TEXT NOT NULL,                  -- "project_{project_id}"
  kb_id           TEXT,
  start_at        INTEGER,
  due_at          INTEGER,
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);
CREATE INDEX idx_projects_owner ON projects(owner_user_id, updated_at DESC);

CREATE TABLE project_members (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  subject_type  TEXT NOT NULL,                     -- user|agent|team
  subject_id    TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'member',    -- owner|admin|member|viewer
  created_at    INTEGER NOT NULL,
  UNIQUE(project_id, subject_type, subject_id)
);
CREATE INDEX idx_project_members_subject ON project_members(subject_type, subject_id);

CREATE TABLE project_tasks (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id         TEXT NOT NULL UNIQUE,
  project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  parent_id       TEXT,
  title           TEXT NOT NULL,
  description     TEXT NOT NULL DEFAULT '',
  status          TEXT NOT NULL DEFAULT 'todo',    -- todo|doing|review|done|blocked|cancelled
  assignee_type   TEXT,                            -- user|agent|team
  assignee_id     TEXT,
  priority        INTEGER NOT NULL DEFAULT 0,
  deps            TEXT NOT NULL DEFAULT '[]',      -- JSON array of task_id
  thread_id       TEXT,
  origin_node_id  TEXT,
  due_at          INTEGER,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  created_by      INTEGER NOT NULL REFERENCES users(id),
  created_at      INTEGER NOT NULL,
  updated_at      INTEGER NOT NULL
);
CREATE INDEX idx_project_tasks_project ON project_tasks(project_id, status, sort_order);
CREATE INDEX idx_project_tasks_thread ON project_tasks(thread_id);

CREATE TABLE project_comments (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id    TEXT NOT NULL UNIQUE,
  project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id       TEXT,
  thread_id     TEXT,
  author_type   TEXT NOT NULL,                     -- user|agent|system
  author_id     TEXT NOT NULL,
  body          TEXT NOT NULL,
  source        TEXT NOT NULL DEFAULT 'dashboard', -- dashboard|im|agent
  node_type     TEXT NOT NULL DEFAULT 'none',      -- none|business|requirement
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE INDEX idx_project_comments_project ON project_comments(project_id, created_at DESC);
CREATE INDEX idx_project_comments_task ON project_comments(task_id, created_at);

CREATE TABLE node_mark_logs (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  comment_id  TEXT NOT NULL,
  from_type   TEXT NOT NULL,
  to_type     TEXT NOT NULL,
  actor       TEXT NOT NULL,
  at          INTEGER NOT NULL
);
CREATE INDEX idx_node_mark_logs_comment ON node_mark_logs(comment_id, at);

CREATE TABLE project_rooms (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id       TEXT NOT NULL UNIQUE,
  project_id    TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  thread_id     TEXT NOT NULL,
  host_agent_id TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'open',      -- open|closed
  created_at    INTEGER NOT NULL
);
CREATE INDEX idx_project_rooms_thread ON project_rooms(thread_id);
CREATE INDEX idx_project_rooms_project ON project_rooms(project_id, status);

CREATE TABLE project_room_members (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  room_id       TEXT NOT NULL REFERENCES project_rooms(room_id) ON DELETE CASCADE,
  subject_type  TEXT NOT NULL,
  subject_id    TEXT NOT NULL,
  joined_at     INTEGER NOT NULL,
  UNIQUE(room_id, subject_type, subject_id)
);

CREATE TABLE artifacts (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  artifact_id     TEXT NOT NULL UNIQUE,
  project_id      TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id         TEXT,
  kind            TEXT NOT NULL,                   -- doc|prd|code|context
  name            TEXT NOT NULL,
  uri             TEXT NOT NULL,
  kb_document_id  TEXT,
  commit_ref      TEXT,
  version         INTEGER NOT NULL DEFAULT 1,
  hash            TEXT NOT NULL DEFAULT '',
  created_by      TEXT NOT NULL,
  created_at      INTEGER NOT NULL
);
CREATE INDEX idx_artifacts_project ON artifacts(project_id, created_at DESC);
CREATE INDEX idx_artifacts_task ON artifacts(task_id);

CREATE TABLE timeline_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
  task_id     TEXT,
  actor       TEXT NOT NULL,
  action      TEXT NOT NULL,
  payload     TEXT NOT NULL DEFAULT '{}',
  at          INTEGER NOT NULL
);
CREATE INDEX idx_timeline_project ON timeline_events(project_id, at DESC);
CREATE INDEX idx_timeline_task ON timeline_events(task_id, at);

UPDATE _schema_version SET version = 18;
```

**PG 版本差异**（`018_projects.pg.sql`）：

| SQLite | PostgreSQL |
|---|---|
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY` |
| `TEXT` | `TEXT`（同） |
| `INTEGER NOT NULL`（时间戳） | `BIGINT NOT NULL` |

**同时必做**

1. [test_db_pool.py](Octop-develop/tests/unit/db/test_db_pool.py) 7 处 `assert v == 17` → `== 18`
2. `migrate.py` 加幂等 helper（若需老库补列）：
   ```python
   def _ensure_projects_schema(db: DatabasePool) -> None: ...
   ```
   并在 `run_migrations` 末尾（`:1750` 前）调用
3. **不需要** PG `if version == 18:` 回填分支（纯新建表）

### 3.2 Repo / Service / Router 骨架

| 新增文件 | 职责 | 约束 |
|---|---|---|
| `src/octop/infra/db/repos/projects.py` | 纯 SQL，一张表一个方法组 | 只许 import `infra/db/_base`、`infra/utils/`（AGENTS.md §5 硬禁） |
| `src/octop/infra/projects/service.py` | 领域逻辑（成员校验、状态机、时间线写入） | 可仿 [`infra/agents/teams/service.py`](Octop-develop/src/octop/infra/agents/teams/service.py) |
| `src/octop/api/routers/projects.py` | 薄 HTTP 层 | 仿 [`api/routers/teams.py`](Octop-develop/src/octop/api/routers/teams.py)；用 `require_permission("projects")` |

**必改核心文件（S1 范围内）**

| # | 文件 | 改什么 |
|---|---|---|
| 1 | [`infra/db/services.py`](Octop-develop/src/octop/infra/db/services.py) | `RepoBundle` 加字段 · `from_pool` 加构造 · `SharedServices` 加 property（**三处**） |
| 2 | [`infra/users/permissions.py`](Octop-develop/src/octop/infra/users/permissions.py:50) | `PERMISSIONS` 加 `"projects"`（category=`settings`），现有 22 键 |
| 3 | [`api/app.py`](Octop-develop/src/octop/api/app.py:203) | import 块 + `_mount_routers` 加 `_RouterMount(projects.router, "/api", ["projects"])` |
| 4 | [`api/openapi_meta.py`](Octop-develop/src/octop/api/openapi_meta.py) | `OPENAPI_TAGS` 加 tag + 描述 |
| 5 | [`infra/errors.py`](Octop-develop/src/octop/infra/errors.py) | `ErrorCode` 加 `PROJECT_*` + `_HTTP_STATUS` 映射 |
| 6 | `src/octop/i18n/{en,zh}.json` | `errors.PROJECT_*`（两语言键必须一致） |
| 7 | [`tests/unit/api/test_acl_gate_coverage.py`](Octop-develop/tests/unit/api/test_acl_gate_coverage.py:12) | `GATED_FILES` 加 `routers/projects.py` |
| 8 | [`tests/unit/db/test_db_pool.py`](Octop-develop/tests/unit/db/test_db_pool.py) | 7 处版本断言 |

### 3.3 S1 验收

```bash
uv run pytest tests/unit/db -q          # 迁移落在 18
uv run pytest tests/unit/api -q          # ACL 守卫通过
uv run pytest tests/unit/i18n -q         # 键对齐
make all
```

**通过标准**：迁移可空库落地、可重复执行幂等、`GET /api/docs` 能看到 projects tag、新路由受 JWT 保护。

**预估**：**3 天**

---

## 4. S2：项目 CRUD + 看板 + 列表接线

### 4.1 接口契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/projects` | 列出我可见的项目（成员表 join，**非成员不可见**） |
| POST | `/api/projects` | 立项（同时写 `project_members` owner 行 + 分配 `memory_namespace`） |
| GET/PATCH/DELETE | `/api/projects/{project_id}` | 详情 / 编辑 / 归档 |
| GET/POST | `/api/projects/{project_id}/members` | 成员列表 / 增删改角色 |
| GET/POST | `/api/projects/{project_id}/tasks` | 任务列表（看板数据源）/ 创建 |
| PATCH/DELETE | `/api/projects/{project_id}/tasks/{task_id}` | 改状态（拖拽）/ 编辑 / 删除 |

**列表接口必须带 `project_id` 反查**（给 S0 的分组用）：

```
GET /api/threads?limit=200
→ thread 增加字段：project_id?, project_name?, task_id?, task_title?,
                   session_kind: "project" | "group" | "direct"
```

**实现方式**（不改 `threads` 表）：

```sql
SELECT t.*, pr.project_id, pr.room_id, p.name AS project_name
  FROM threads t
  LEFT JOIN project_rooms pr ON pr.thread_id = t.thread_id
  LEFT JOIN projects p       ON p.project_id = pr.project_id
 WHERE t.user_id = ?
```

> 任务讨论线（`project_tasks.thread_id`）用第二条 LEFT JOIN 或 UNION，按实际查询计划取舍。

### 4.2 前端

| 新增 | 说明 |
|---|---|
| `dashboard/src/pages/Projects/index.tsx` | 项目列表（仿 `pages/KnowledgeBases/`） |
| `dashboard/src/pages/Projects/Detail/` | 项目详情 + 看板（antd 拖拽列） |
| `dashboard/src/api/modules/projects.ts` + `api/types/projects.ts` | 仿 `modules/teams.ts` |
| 路由 / 侧栏 / 权限 | 5 个 rebase 热点文件（见分析报告 §5.2） |

**看板**：不建议引新拖拽库，用 antd 内置能力 + 状态按钮即可满足 AC-02「10 个任务一屏尽览」。

### 4.3 S2 验收

```bash
uv run pytest tests/integration/test_projects_api.py -q
cd dashboard && npx tsc -b && npm run test -- --run
```

人工：AC-01（建项目含 ≥1 真人/专家/团队）、AC-02（看板一屏 + 改状态实时）、AC-13（非成员全拒）、AC-16（跨项目隔离）。

**预估**：**6 天**

---

## 4.5 S2.5：讨论 / 打标 / 需求节点 / Owner 闸门

> 这是需求文档 M6–M11 的落点，**M1 里程碑内**。它把项目从「任务看板」升级成「需求闭环」。

### 4.5.1 讨论线：复用现有 thread，不新建评论系统

| 做法 | 说明 |
|---|---|
| 每个任务一条讨论线 | 用 `project_tasks.thread_id` 指向一个 **agent thread** |
| 参加者 | 任务的 `assignee_id`（专家）+ 项目成员（真人） |
| 消息存储 | **复用 `thread_messages`**（已有 `role` + `message_json`） |
| 不做 | ❌ 不新建 `project_comments` 之外的评论实体；`project_comments` 只存**结构化的项目级评论**，不重复 thread 内容 |

**关键区分**（需求文档 §4 的"决策点"）：

```text
thread_messages   →  AI 讨论原文 + 真人发言（对话流）
project_comments  →  结构化评论（承载打标、来源、节点关联）
project_comments.thread_id  →  可选外键，指回对话流
```

→ **`project_comments` 是一等公民**（承载打标），thread 承载原始对话。这正是需求文档建议的方案。

### 4.5.2 打标与需求节点

| 接口 | 说明 |
|---|---|
| `POST /api/projects/{id}/comments/{comment_id}:mark` | 打标（`none` / `business` / `requirement`） |
| `GET /api/projects/{id}/requirement-nodes` | 需求节点池（按 status 分组 + 计数） |
| `POST /api/projects/{id}/requirement-nodes/{node_id}:confirm` | Owner 确认闸门 |
| `POST .../{node_id}:reject` | 拒绝 + 原因 |

**状态机**（需求文档 §4 定稿）：

```text
draft → pending_confirm →(Owner 确认) confirmed →(生成任务) split →(验收) closed
                ↓
            rejected（带 rejected_reason）
```

**打标可撤销必须留痕**：每次变更写 `node_mark_logs`（表已在 S1 的迁移 018 建好）。

**AC-07 硬门禁**：未确认的节点在 **UI 与 API 上都没有「生成任务」路径**。
实现方式：生成任务的路由**只接受 `status='confirmed'` 的 node**，越权调用返回 `PROJECT_NODE_NOT_CONFIRMED`。

### 4.5.3 Owner 闸门复用 HITL（不新建审批机制）

需求 M11「仅 Owner/项目管理员可确认」——**不要另造审批流**，用现成的 HITL：

| 复用 | 位置 |
|---|---|
| 策略模型 | [`HitlPolicy`](octop-harness/src/octop_harness/security/models.py:46) |
| 中断注入 | [`agent.py:1369`](octop-harness/src/octop_harness/agent.py:1369) `interrupt_on` |
| 事件 | `AgentEventType.HITL_REQUIRED` |
| 恢复 | [`agent.py:529`](octop-harness/src/octop_harness/agent.py:529) `resume_hitl()` |
| IM 审批卡片 | [`hitl/coordinator.py`](Octop-develop/src/octop/infra/gateway/hitl/coordinator.py) + `format_ask_card` |

**收益**：Owner 在**飞书/企微群里就能拍板**，不用回 Dashboard —— 直接满足你的"拉群 + 项目经理拍板"场景。

### 4.5.4 资料归档

| 做法 | 说明 |
|---|---|
| 任务转 `done` 时 | 把产出写进项目 KB（`kb_id`） |
| 回链 | 写 `artifacts` 表：`task_id` + `kb_document_id` |
| **产物来源** | ⚠️ **复用上游 `thread_artifacts`，不要重新扫描工作区**（见更新日志整理 §影响 1） |

```python
# 归集时读上游已有的 thread artifact，再补业务字段
from octop.infra.agents.thread_artifact import thread_artifacts_payload
```

### 4.5.5 S2.5 验收

```bash
uv run pytest tests/integration/test_project_nodes_api.py -q
```

| AC | 验收条件 |
|---|---|
| AC-05 | 对任一评论打「需求节点」后，需求池 1 次刷新内出现该节点并带来源链接 |
| AC-06 | 撤销打标后节点消失（或转 draft），且 `node_mark_logs` 留痕可查 |
| AC-07 | **对照测试**：未确认节点在 UI 与 API 上均无「生成任务」路径（越权调用被拒） |
| AC-08 | Leader 出草案 → Owner 确认 → 生成 N 个任务，每个任务 `origin_node_id` 可追溯 |
| AC-10 | 任务转 done 时产出出现在项目 KB；KB 条目可跳回任务与来源评论 |
| AC-12 | 任一任务时间线完整有序（状态/派工/产出/评论/记忆变更） |

**预估**：**3 天**

---

## 5. S3：项目记忆（档位 A + PostgreSQL）

### 5.1 核心设计

```
projects.memory_namespace = "project_{project_id}"
        ↓
ProjectMemoryStore（唯一读写门面）
        ↓
octop_memory schema，namespace 隔离，复用全部召回能力
```

### 5.2 新增文件

| 文件 | 职责 |
|---|---|
| `src/octop/infra/projects/memory.py` | **`ProjectMemoryStore`** —— 唯一读写入口 |
| `src/octop/api/routers/project_memory.py` | 只读浏览接口（成员可见） |

**`ProjectMemoryStore` 必须实现**：

```python
class ProjectMemoryStore:
    def __init__(self, *, config, repos, max_cached: int = 64): ...

    def recall(self, project_id: str, query: str, limit: int = 5) -> str:
        """返回 rendered 文本，供派工注入。"""

    def write(self, project_id: str, statement: str, *, topic: str = "") -> str:
        """显式写入一条项目记忆（零 LLM 路径）。"""

    def close_project(self, project_id: str) -> None:
        """显式关闭 backend 连接。"""

    def close_all(self) -> None:
        """进程退出钩子（挂到 launch.py 的 shutdown）。"""
```

### 5.3 四条硬约束

| # | 约束 | 理由 |
|---|---|---|
| 1 | **按 project_id 缓存 `Memory` 实例，带硬上限** | 每个 `Memory` = 1 条裸 PG 连接，无池（[postgres.py:119](octop-memory/src/octop_memory/storage/backends/postgres.py:119)） |
| 2 | **淘汰/关闭时必须显式 `memory.backend.close()`** | Octop 现有 LRU 淘汰时不 close（[memory_client.py:90](Octop-develop/src/octop/api/common/memory_client.py:90)），**不要照抄** |
| 3 | **不挂 `MemoryMiddleware`** | 用 `Memory` + `MemoryService` 轻量门面：无后台 GC 线程、无 segfault 风险、无自动抽取开销 |
| 4 | **不要用 `.hmpkg` pack/adopt** | PG 后端硬拒（HTTP 501，[memory_portable.py:47](Octop-develop/src/octop/api/routers/memory_portable.py:47)）。跨团队共享 = 同一个 namespace |

### 5.4 派工注入（复用现成接缝）

```
派工/拉群时
  → ProjectMemoryStore.recall(project_id, query=任务标题+描述, limit=5)
  → rendered 文本
  → bind_peer_session(prepare=...) 覆写 PeerSession.message
```

`bind_peer_session` 的 docstring 原话就是为此设计的（[team_manager.py:94](octop-harness/src/octop_harness/teams/team_manager.py:94)）。
**注意**：`prepare` 只能改写 `thread_id / session_key / message / configurable`，身份键（`agent_id/user/thread_id/source`）会被过滤防冒充（[util.py:16](octop-harness/src/octop_harness/teams/util.py:16)）——**不要绕过**。

### 5.5 增量注入与版本号（AC-11）

- `projects` 表加一列 `inject_version INTEGER NOT NULL DEFAULT 0`
- 新记忆 promote 成功时 `+1`
- 派工时携带 `注入版本 +1` 的标记 + 只注入「自上次注入以来新增」的条目
- 实现：`ProjectMemoryStore.recall(since=last_injected_at)`

### 5.6 S3 验收

```bash
uv run pytest tests/unit/projects/test_memory_store.py -q
```

- AC-09：派工消息抽样核对含「任务标题 + 描述 + 验收标准 + 相关项目记忆条目」
- AC-11：新增记忆条目 → `inject_version` +1 → 随后派工消息包含该条
- **连接泄漏测试**：连续建/销 100 个项目后，`SELECT count(*) FROM pg_stat_activity` 不增长

**预估**：**4 天**

---

## 6. S4：跨团队房间 + 工具放开

### 6.1 harness 补丁（唯一需要改 harness 的地方）

`octop-harness/src/octop_harness/teams/team_manager.py`

```python
PrepareScope = Callable[[str], set[str] | None]

def bind_peer_scope(self, scope: PrepareScope | None) -> None:
    """Return the caller's allowed peer agent_ids, or None to keep the user_id rule.

    Hosts that model project membership (Octop) bind this so peers resolve by
    project roster instead of agent ownership.
    """
    self._peer_scope = scope
```

在 [`list_peers`](octop-harness/src/octop_harness/teams/team_manager.py:175) 中，**用户过滤之后、`team_peers` 白名单之前**插入：

```python
scope = self._peer_scope(from_agent_id) if (self._peer_scope and from_agent_id) else None
if scope is not None:
    peers = [e for e in peers if e.agent_id in scope]   # 替换，不是叠加
```

补一条 harness 单测锁定：作用域非 None 时可跨 user 解析 peer，且不改 `PEER_IDENTITY_CONFIG_KEYS` 行为。

### 6.2 Octop 侧三处放权（**必须用同一个函数**）

**先建共享服务**：`src/octop/infra/projects/visibility.py`

```python
def visible_agent_ids(user_id: int, *, repos: RepoBundle) -> set[str]:
    """Agents this user may talk to: owned + shared + agents in their projects."""
```

三处消费者：

| # | 位置 | 用途 |
|---|---|---|
| 1 | harness `bind_peer_scope` 绑定处 | 决定 `agent_list` / `ask_agent` 可见范围 |
| 2 | `GET /api/threads`（S0 端点） | 会话列表过滤 |
| 3 | [`teams/service.py:71`](Octop-develop/src/octop/infra/agents/teams/service.py:71) `_user_may_use_member` | 组队时能否把某专家加进团队 |

> ⚠️ **三处必须共用**，否则会出现「能调但看不到」或「看得到但调不了」的权限语义漂移。

### 6.3 团队工具放开

| 方案 | 改动 | 建议 |
|---|---|---|
| 知识库 | `HOST_TOOLS_ALLOWED` 加 `search_knowledge`（[service.py:25](Octop-develop/src/octop/infra/agents/teams/service.py:25)，**1 行**） | ✅ 立即做 |
| 连接器 / ACP | 去掉 `if not team_host` 门禁（[manager.py:3166](Octop-develop/src/octop/infra/agents/manager.py:3166)）+ 去掉清空（[:3331](Octop-develop/src/octop/infra/agents/manager.py:3331)） | ⚠️ **走方案 4**：新增「项目房间 host」角色，单独配白名单 |

**为什么不直接放大全局白名单**：[service.py:24](Octop-develop/src/octop/infra/agents/teams/service.py:24) 注释写明了设计意图 —— *"Hosts only dispatch and keep light memory/time — members do the work."* 简单放大 = 调度者兼执行者，三层防失控边界失效。

### 6.4 S4 验收

- 跨用户专家出现在 `agent_list`，`ask_agent` 可调用且回包落房间
- 原团队成员的 `peer_invoke_mode="sync"` 降级仍然生效
- 团队 host 能 `search_knowledge`，但**不能**用 filesystem / shell 工具

**预估**：**5 天**（含 harness 补丁与其单测）

---

## 7. S5：派单 + 交付物

| 任务 | 说明 | 缺口 |
|---|---|---|
| ACP 派单 | 复用 `acp_runner` 工具（`list/start/message/respond/status/close`） | 无（现成） |
| **commit 回写** | **完全空白，需自研** | 约定 runner 输出格式（建议要求 runner 返回 `git commit` 短 hash + 分支名），写 `artifacts.commit_ref` |
| 资料归档 | 产出写项目 KB + `artifacts` 表回链任务 | KB 写入现成；`artifacts` 表 S1 已建 |
| 时间线回放 | 每次状态变更写 `timeline_events` | 表 S1 已建 |

**预估**：**4 天**

---

## 8. 总工期与里程碑

### 里程碑 M1「项目管理可用」（**建议先交付这一档**）

| 阶段 | 内容 | 预估 | 依赖 |
|---|---|---|---|
| **S1** | 项目域地基（迁移 018 + repo + 权限键 + 空壳路由） | **3 天** | 无 |
| **S2** | 项目 / 成员 / 任务 / 看板 | **6 天** | S1 |
| **S2.5** | 讨论 / 打标 / 需求节点 / Owner 闸门 / 资料归档 | **3 天** | S2 |
| | **M1 小计** | **12 天** | |
| **S0** | 聊天列表改造 | **2.5 天** | 无（可并行，也可 M1 后补） |

> **M1 交付后即可用**：立项 → 拆任务 → 看板 → 派单给专家（同用户）→ 讨论 → 打需求节点 → Owner 在群里拍板 → 产出归档进项目 KB。

### 后续阶段（**建议等上游 `infra/agents` 重构稳定后再开工**）

| 阶段 | 内容 | 预估 | 依赖 |
|---|---|---|---|
| S3 | 项目记忆（档位 A + PG） | 4 天 | M1 |
| S4 | 跨团队房间 + 工具放开 | 5 天 | M1 + harness 补丁 |
| S5 | ACP 派单 + commit 回写 | 4 天 | S4 |
| | 后续小计 | 13 天 | |
| | **全部合计** | **约 27.5 天**（1 人全职） | |

> 对比需求文档原估 12 周：本方案更短，因为**项目记忆走 octop-memory 现成能力**（不重写召回/存储）、**Owner 闸门复用 HITL**（不新建审批）、**房间机制复用团队 room**（不新建群聊）、**讨论线复用 `thread_messages`**（不新建评论系统）。

### 为什么 M1 和后续阶段要分开

| 维度 | M1（S1+S2+S2.5+S0） | 后续（S3+S4+S5） |
|---|---|---|
| 触及高 churn 文件 | **5 个**（全是 i18n JSON + `errors.py`，追加式） | **4 个高 churn 功能文件** + `thread_artifact` 区 |
| 触及 `infra/agents/**` | **完全不碰** ✅ | `manager.py` / `memory_backend.py` / `teams/service.py` |
| 与上游重构撞车风险 | **无** | **高**（上游 09-25 刚重构该目录） |
| 纯新增文件占比 | 高（约 14 个） | 中 |

---

## 9. 风险与前置检查

| # | 风险 | 应对 |
|---|---|---|
| 1 | **fork 分支选错** | **必须基于 `develop`**（`main` 依赖闭源 `orcakit-harness-agent`，改不动 harness） |
| 2 | 两套侧栏并存 | S0 先改 classic（默认布局），minimal 后续跟进 |
| 3 | PG 连接增长 | S3 的 `ProjectMemoryStore` 硬上限 + 显式 close + `pg_stat_activity` 回归测试 |
| 4 | 权限语义漂移 | S4 的 `visible_agent_ids` 三处共用 |
| 5 | i18n 键不一致 | 每次改完跑 `uv run pytest tests/unit/i18n -q` |
| 6 | 迁移号冲突 | 上游若先发 018，本地改成 019 并同步 7 处断言 |
| 7 | `pg_dump` 缺失 | 部署镜像需含 PG 客户端工具，否则 `octop backup` 失败 |

**开工前 5 分钟自检**

```bash
# 1. 确认在 develop 分支
git -C Octop-develop branch --show-current     # 期望 develop

# 2. 确认基线绿
cd Octop-develop && make all

# 3. 确认当前迁移号
ls src/octop/infra/db/migrations/ | tail -3     # 期望最高 017

# 4. 确认前端可构建
cd dashboard && npm ci && npx tsc -b

# 5. 确认 fork 目标
git -C ../octop-harness branch --show-current   # 期望 develop
```

---

## 附录 A：上游同步与冲突评估

### A1. 结论：能更新，冲突可控

| 问题 | 答案 |
|---|---|
| 上游更新后能跟进吗 | **能** —— 标准 `git fetch upstream && git rebase upstream/develop` |
| 每次 rebase 多少冲突 | **3–6 个文件，且多为追加式（git 可自动合并）** |
| 有没有"必冲突"的 | **有 1 处**：迁移号断言（1 行，trivial） |
| 最大冲突源 | **不是注册点，而是 i18n JSON 与 threads/memory 相关文件** |

### A2. 上游改动速率（实测）

| 指标 | 数值 | 来源 |
|---|---|---|
| 版本发布节奏 | **38 个版本；近期约 1 版 / 1–3 天** | `CHANGELOG.md`（09-11/12/13/14/18/22/23） |
| develop 提交速率 | **约 15 commits/天** | GitHub API：09-19→09-25 共 100 条 |

> **高节奏上游。** 攒 3 个月再 rebase = 上千 commits，非常痛苦。**建议每月固定 rebase 一次。**

### A3. 冲突分层（实测数据）

用本地两个快照（`Octop`=1.0.2b2 与 `Octop-develop`=未发布）对**本方案触及的 28 个既有文件**做逐文件哈希比对：

#### 层 1：纯新增文件 → **0 冲突**（约 18 个）

`git` 对新增文件永不冲突：迁移 SQL、`repos/projects.py`、`projects/service.py`、`api/routers/projects.py`、`chat/sessions.py`、`useSessionInbox.ts`、`pages/Projects/**`、全部新测试。

> 这是方案刻意遵守「只加不改」纪律的结果。

#### 层 2：追加式改动 → 低冲突（约 12 个）

import 行、router mount、nav item、i18n key、权限键。只在「同一行附近同时被改」时冲突，通常可自动合并。

#### 层 3：真冲突候选 → **本周期上游已改的 12 个文件**

| 文件 | 上游本周期 | 我要做什么 | 风险 |
|---|---|---|---|
| `src/octop/infra/agents/manager.py` | ✅ | S4 改 host 配置 | **高** |
| `src/octop/infra/agents/memory_backend.py` | ✅ | S3 加项目 namespace | **高** |
| `src/octop/api/common/memory_client.py` | ✅ | S3 参考/扩展 | 中 |
| `src/octop/api/routers/memory_portable.py` | ✅ | S3 文档化 PG 限制 | 低 |
| `src/octop/infra/db/repos/threads.py` | ✅ | S0 加一个方法 | 低（追加） |
| `src/octop/api/routers/chat/history.py` | ✅ | S0 只 import helper | 低 |
| `dashboard/.../hooks/useSessions.ts` | ✅ | S0 只 import `toSession` | 低 |
| **`dashboard/src/locales/{en,zh}.json`** | ✅ | S0/S2 加 key | **高（每周期都改）** |
| **`src/octop/i18n/{en,zh}.json`** | ✅ | S1 加 error key | **高（每周期都改）** |
| `src/octop/infra/errors.py` | ✅ | S1 加 ErrorCode | 中 |

#### 🔍 反直觉发现：那 5 个"rebase 热点"本周期**全都没动**

| 文件 | 上游本周期 |
|---|---|
| `src/octop/api/app.py` | **未改** |
| `src/octop/infra/db/services.py` | **未改** |
| `dashboard/src/routes/index.tsx` | **未改** |
| `dashboard/src/layouts/sidebarNav.tsx` | **未改** |
| `dashboard/src/utils/permissions.ts` | **未改** |

原因：这些文件**只在新增领域时改**，结构稳定（`app.py` 上次改动 09-21，`services.py` 09-08）。而 `manager.py` / `memory_*.py` / i18n **每个版本都在改**。

> **真正要担心的不是"注册点"，而是"功能实现文件"和"i18n"** —— 与常见的 fork 直觉相反。

#### 层 4：必冲突项（1 处，trivial）

`tests/unit/db/test_db_pool.py` 的 **7 处 `assert v == 17`**：

- 我们加 018 → 必须改成 18
- 上游加 018 → 也会改成 18
- **每次上游发迁移，此文件必冲突**（1 行）

另外 [migrate.py](Octop-develop/src/octop/infra/db/migrate.py:56) 的 `_discover` 遇重复版本号直接 `RuntimeError` —— **硬失败而非静默覆盖**，这是好事。

### A4. ⚠️ 顺带修正本方案的一个 Bug

`CHANGELOG.md` 的 `[Unreleased]` 明确写着：

> 会话列表接口 `GET /api/agents/{id}/threads` 的 `limit` 增加 **1–100 边界**……越界请求现在统一拒绝

**本方案 §2.2 写的 `GET /api/threads?limit=200` 会被拒绝。**

（我手上的 develop 快照代码里还没看到该 clamp，但 CHANGELOG 已记录 —— 说明**这正是"正在变动的区域"**，更不该依赖具体上限。）

**修正为服务端聚合**，构造上就有界，不受 limit 争议影响：

```
GET /api/threads/summary
→ [ { agent_id, session_count, has_activity, last_active,
      pinned: [ { thread_id, title, ... } ] } ]      # 每个 agent 一行
```

- 行数 = agent 数 → **天然有界**
- `pinned` 单独封顶（如 20 条）
- 前端用它做分组 + 折叠计数，**不再需要拉全量会话**
- 展开某 agent 时仍走既有 `GET /agents/{id}/threads`（分页不变，零回归）

### A5. 降低冲突的 6 条工程策略

| # | 策略 | 效果 |
|---|---|---|
| 1 | **新代码进新文件**，核心文件只动 1–3 行 | 约 18 个文件永冲突 |
| 2 | **i18n key 用独立命名空间 + 追加到文件末尾**（`projects.*` / `chat.section*`），不插在中间 | i18n 冲突率大幅下降 |
| 3 | **提交粒度**：把「迁移号 + 7 处断言」单独做成一个 commit | rebase 时冲突集中，易解 |
| 4 | **每月固定 rebase 一次**，不要攒 | 上游 ~15 commits/天 |
| 5 | **rebase 前先读 `CHANGELOG` 的 `[Unreleased]`**，对 A3 表里 12 个文件重点核对 | 提前预判冲突 |
| 6 | **迁移号检测脚本**：rebase 后自动比对上游最大号，≥018 则自动重命名 + 改断言 | 机械劳动自动化 |

**策略 6 的脚本**（每次 rebase 后跑一次）：

```bash
#!/usr/bin/env bash
set -euo pipefail
UP=$(ls src/octop/infra/db/migrations/ | grep -oE '^[0-9]{3}' | sort -n | tail -1)
MINE=018
if [ "$UP" -ge "$MINE" ]; then
  NEW=$(printf "%03d" $((10#$UP + 1)))
  echo "上游已到 $UP，本项目迁移需从 $MINE 改为 $NEW"
  git mv "src/octop/infra/db/migrations/${MINE}_projects.sql" \
         "src/octop/infra/db/migrations/${NEW}_projects.sql"
  git mv "src/octop/infra/db/migrations/${MINE}_projects.pg.sql" \
         "src/octop/infra/db/migrations/${NEW}_projects.pg.sql"
  sed -i "s/version = ${MINE#0};/version = $((10#$NEW));/" \
         src/octop/infra/db/migrations/${NEW}_projects*.sql
  sed -i "s/assert v == ${MINE#0}/assert v == $((10#$NEW))/g" tests/unit/db/test_db_pool.py
fi
```

### A6. 量化总结

| 指标 | 数值 |
|---|---|
| 方案触及既有文件 | **22 个** |
| 其中上游本周期已改 | **12 个（55%）** |
| 纯新增文件 | **约 18 个（0 冲突）** |
| **预计每次 rebase 真冲突** | **3–6 个文件** |
| 其中必冲突 | **1 个**（`test_db_pool.py`，1 行） |
| 预计每次 rebase 耗时 | **0.5–1 小时**（含跑 `make all` 验证） |

**总体判断：这是一个可长期维护的 fork 形态** —— 每月 1 小时同步成本，换来不与上游分叉。

> ⚠️ 前提仍然是：**必须基于 `develop` fork，且环境里要先装 Git**（当前环境没有）。
