# Octop 对话分组与标签功能 — 技术文档

## 概述

为 Octop 聊天侧边栏增加**文件夹分组**和**标签管理**功能，使用户可以按主题组织对话、快速定位历史对话。

对标产品：Open WebUI（文件夹 + 标签）、LobeChat（分组 + 标签）、ChatGPT（文件夹）。

---

## 设计决策

| 决策项 | 方案 | 理由 |
|--------|------|------|
| 文件夹 | `threads` 表新增 `folder` TEXT 列，nullable，NULL = 未分组 | 最简方案，不需要单独的 folders 表 |
| 标签 | `threads` 表新增 `tags` TEXT 列，存 JSON 数组 `[]` | 一条对话可打多个标签 |
| 层级 | 文件夹为**扁平结构**（不嵌套） | 和 Open WebUI / ChatGPT 保持一致，够用 |
| 作用域 | per-agent + per-user | 不同用户各自组织，互不干扰 |
| 文件夹列表 | 前端从 `DISTINCT folder` 查询结果派生 | 不单独建表，减少复杂度 |

---

## 依赖关系图

```
Step 1 (DB迁移)
  │
  ├─► Step 2 (Repo层) ─► Step 3 (API层) ─► Step 4 (前端类型) ─► Step 5 (Store) ─► Step 6 (UI)
  │
  └─► 每步都可独立运行测试验证，后一步不需要回头改前一步
```

---

## 跨步骤关联标记（重要）

> 以下位置存在跨层依赖，改动时需要保持同步。出现问题时回看此表。

| 关联点 | 涉及步骤 | 说明 |
|--------|----------|------|
| `ThreadRow` ↔ `OctopThread` 接口 | Step 2 ↔ Step 4 | 字段名和类型必须一致：`folder: str\|None` ↔ `folder?: string\|null`，`tags: tuple` ↔ `tags?: string[]` |
| `RenameThreadBody` ↔ `OctopThreadPatch` | Step 3 ↔ Step 4 | PATCH body 字段名必须完全匹配 |
| `GET /threads` 响应格式 ↔ `list()` 客户端 | Step 3 ↔ Step 4 | 新增的 query 参数名 `folder`/`tag` 必须一致 |
| `toSession()` 映射 ↔ `Session` 接口 | Step 4 ↔ Step 5 | `folder`/`tags` 字段名一致 |
| `useSessions` 返回值 ↔ `SessionList` props | Step 5 ↔ Step 6 | 新增的 `folderList`、`setSessionFolder`、`setSessionTags` 需要传入 sidebar |
| i18n key 一致性 | Step 6 + 后端 i18n | 如后端有 `errors.*` 相关 key，需同步 `src/octop/i18n/*.json` |

---

## Step 1：数据库迁移（015）

**目标**：给 `threads` 表加上 `folder` 和 `tags` 列。完成后所有现有数据不受影响（向后兼容）。

### 新增文件

| 文件 | 内容 |
|------|------|
| `src/octop/infra/db/migrations/018_thread_organization.sql` | SQLite 版 |
| `src/octop/infra/db/migrations/018_thread_organization.pg.sql` | PostgreSQL 版 |

### SQL（SQLite `018_thread_organization.sql`）

```sql
-- v18: thread organization (folder + tags)
ALTER TABLE threads ADD COLUMN folder TEXT;
ALTER TABLE threads ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
CREATE INDEX idx_threads_folder ON threads(agent_id, user_id, folder);
```

### SQL（PostgreSQL `018_thread_organization.pg.sql`）

```sql
-- v18: thread organization (folder + tags)
ALTER TABLE threads ADD COLUMN folder TEXT;
ALTER TABLE threads ADD COLUMN tags TEXT NOT NULL DEFAULT '[]';
CREATE INDEX idx_threads_folder ON threads(agent_id, user_id, folder);
```

### 修改文件

| 文件 | 改动 |
|------|------|
| `tests/unit/db/test_db_pool.py` | 两处 `v == 14` → `v == 15` |

### 验证

```bash
uv run pytest tests/unit/db/test_db_pool.py -x -q
```

通过即代表迁移正确执行，schema version 已更新到 15。

---

## Step 2：Repo 层扩展

**目标**：`ThreadRow` 增加 `folder`/`tags` 字段；`ThreadRepo` 增加组织相关方法。完成后所有现有调用无需改动（新字段有默认值）。

### 修改文件

#### ① `src/octop/infra/db/repos/threads.py`

**ThreadRow dataclass 新增字段**（放在已有字段末尾，带默认值）：

```python
folder: str | None = None
tags: tuple[str, ...] = ()
```

**ThreadRepo 新增方法**：

| 方法签名 | 作用 |
|---------|------|
| `set_folder(thread_id: str, folder: str \| None)` | 设置/清除文件夹 |
| `set_tags(thread_id: str, tags: Sequence[str])` | 覆盖整个标签列表（JSON dump 后写入） |
| `list_folders(*, agent_id: str, user_id: int) -> list[str]` | `SELECT DISTINCT folder` 查询该用户所有非空文件夹名 |
| `list_by_folder(*, agent_id: str, user_id: int, folder: str \| None, limit: int = 50) -> list[ThreadRow]` | 按文件夹过滤 |
| `list_by_tag(*, agent_id: str, user_id: int, tag: str, limit: int = 50) -> list[ThreadRow]` | 按标签过滤（JSON 数组 LIKE 匹配或应用层过滤） |

**修改已有方法**：

- `insert()` — 新参数 `folder=None`, `tags=()`，INSERT SQL 增加这两列
- `get()` / `list_by_agent()` / `list_by_agent_user()` — row 映射补充 `folder` 和 `parse_thread_tags(tags)` 解析

**新增辅助函数**：

```python
def parse_thread_tags(raw: str | None) -> tuple[str, ...]:
    """安全解析 JSON 数组字符串为 tuple，失败返回空 tuple。"""
```

#### ② 新增测试 `tests/unit/db/test_thread_organization.py`

测试用例：
- insert 带 folder/tags → get 能正确返回
- set_folder 设置、清除（设为 None）
- set_tags 添加、替换、清空
- list_folders 返回去重列表，不包含 NULL 和空字符串
- list_by_folder 过滤正确（含 folder=None 查未分组）
- list_by_tag 过滤正确
- 旧数据兼容（folder=NULL, tags='[]'）

### 验证

```bash
uv run pytest tests/unit/db/test_thread_organization.py -x -q
uv run pytest tests/unit/db/ -x -q          # 确保不破坏其他 DB 测试
```

---

## Step 3：API 层扩展

**目标**：新增组织相关 HTTP 端点，扩展已有的 list/patch 端点。完成后 `curl` 即可验证。

### 修改文件

#### ① `src/octop/api/routers/chat/models.py`

修改：

| 模型 | 改动 |
|------|------|
| `RenameThreadBody` | 增加 `folder: str \| None = None`, `tags: list[str] \| None = None` |

新增：

```python
class OrganizeThreadBody(BaseModel):
    folder: str | None = None
    tags: list[str] = Field(default_factory=list)
```

#### ② `src/octop/api/routers/chat/history.py`

**修改端点**：

| 端点 | 改动 |
|------|------|
| `GET /agents/{agent_id}/threads?limit=&folder=&tag=` | 新增可选 query 参数 `folder: str \| None = None` 和 `tag: str \| None = None`，有值时调用对应 repo 方法过滤 |
| `PATCH /agents/{agent_id}/threads/{thread_id}` | 在已有字段处理逻辑后追加：如果 body.folder 不为 sentinel 则 set_folder，如果 body.tags 不为 None 则 set_tags |
| `GET /threads` 响应 | 每条 thread dict 增加 `"folder"` 和 `"tags"` 字段 |

**新增端点**：

```python
@router.get("/agents/{agent_id}/thread-folders")
async def list_thread_folders(agent_id: str, ...) -> dict:
    """返回 {"folders": ["工作", "学习", ...]}"""
```

#### ③ `src/octop/infra/gateway/threads.py`（ThreadRegistry）

新增方法（代理到 repo）：

- `set_folder(thread_id: str, folder: str | None)`
- `set_tags(thread_id: str, tags: Sequence[str])`
- `list_folders(*, agent_id: str, user_id: int) -> list[str]`

#### ④ 新增测试 `tests/unit/api/test_thread_organization_api.py`

测试用例：
- GET /threads 响应包含 folder/tags 字段（向后兼容）
- GET /threads?folder=工作 只返回该文件夹下的对话
- GET /threads?tag=重要 只返回带该标签的对话
- PATCH /threads/{id} body 含 folder → 成功设置
- PATCH /threads/{id} body 含 tags → 成功设置
- GET /thread-folders 返回正确去重列表

### 验证

```bash
uv run pytest tests/unit/api/test_thread_organization_api.py -x -q
uv run pytest tests/unit/api/ -x -q
```

---

## Step 4：前端类型 + API 客户端

**目标**：TypeScript 类型和 API 客户端同步后端改动。完成后 `npx tsc --noEmit` 通过。

### 修改文件

#### ① `dashboard/src/api/modules/octopThreads.ts`

**OctopThread 接口新增**：

```typescript
folder?: string | null;
tags?: string[];
```

**OctopThreadPatch 接口新增**：

```typescript
folder?: string | null;
tags?: string[];
```

**新增 API 方法**（挂在 `octopThreadsApi` 上）：

```typescript
listFolders(agentId: string): Promise<{ folders: string[] }>
// GET /agents/{agentId}/thread-folders

list(agentId: string, limit?: number, options?: { folder?: string; tag?: string }): Promise<OctopThread[]>
// 修改已有 list 方法，增加可选 folder/tag query 参数
```

### 验证

```bash
cd dashboard && npx tsc --noEmit
```

---

## Step 5：前端 Session Store 扩展

**目标**：`useSessions` hook 支持 folder/tags 操作和筛选。完成后逻辑层可用，UI 层还没渲染但不报错。

### 修改文件

#### ① `dashboard/src/pages/Chat/hooks/useSessions.ts`

**Session 接口新增**：

```typescript
folder?: string | null;
tags?: string[];
```

**`toSession()` 映射新增字段**：

```typescript
folder: row.folder ?? null,
tags: row.tags ?? [],
```

**新增操作函数**（导出在 hook 返回值中）：

| 函数 | 作用 |
|------|------|
| `setSessionFolder(id: string, folder: string \| null)` | 乐观更新本地 Session.folder → 调用 `octopThreadsApi.patch` |
| `setSessionTags(id: string, tags: string[])` | 乐观更新本地 Session.tags → 调用 `octopThreadsApi.patch` |
| `folders` 状态 | `string[]`，当前用户的所有文件夹 |
| `fetchFolders()` | 调用 `octopThreadsApi.listFolders` 更新 folders 状态 |

**修改 `sortSessions()`**：保持现有排序逻辑（pinned 优先 → 时间倒序），文件夹分组展示逻辑放在 UI 层（Step 6）处理。

### 验证

```bash
cd dashboard && npx tsc --noEmit
```

---

## Step 6：前端 Sidebar UI

**目标**：在聊天侧边栏中增加文件夹分组展示 + 标签筛选。这是用户能看到的变化。

### 修改文件

#### ① `dashboard/src/pages/Chat/components/SessionList.tsx`

**改动内容**：

- 在搜索栏下方新增**标签筛选条**：横向滚动的标签 chip 列表，从所有 session 的 tags 中收集去重
- 在 session 列表区域按 folder 分组渲染：每个文件夹一个可折叠 section，"未分组"在最后
- 每个文件夹 section header 显示：文件夹图标 + 名称 + 对话数量 + 折叠箭头
- 点击标签 chip 时过滤只显示带该标签的对话（可与文件夹筛选叠加）

#### ② `SessionItem` 右键菜单扩展

新增菜单项：
- **"移至文件夹"** → 弹出输入框/选择器（可新建或选择已有文件夹）
- **"添加标签"** → 弹出标签输入器（支持新建标签、选择已有标签）
- **"移除标签"** → 子菜单列出当前标签，点击移除

#### ③ 新增组件 `FolderSection.tsx`（可内联在 SessionList.tsx 中）

- 可折叠的文件夹 section
- Header：文件夹图标 + 名称 + 计数 + 折叠箭头
- 内部渲染该文件夹下的 `SessionItem` 列表
- 折叠状态持久化到 localStorage（key: `octop:chat-folders-collapsed`）

#### ④ i18n 字符串

`dashboard/src/locales/en.json` 新增：

```json
{
  "chat": {
    "folders": {
      "title": "Folders",
      "ungrouped": "Ungrouped",
      "newFolder": "New Folder",
      "moveTo": "Move to Folder",
      "rename": "Rename Folder",
      "delete": "Delete Folder"
    },
    "tags": {
      "title": "Tags",
      "addTag": "Add Tag",
      "removeTag": "Remove Tag",
      "filterByTag": "Filter by Tag",
      "noTags": "No tags"
    }
  }
}
```

`dashboard/src/locales/zh.json` 新增：

```json
{
  "chat": {
    "folders": {
      "title": "文件夹",
      "ungrouped": "未分组",
      "newFolder": "新建文件夹",
      "moveTo": "移至文件夹",
      "rename": "重命名文件夹",
      "delete": "删除文件夹"
    },
    "tags": {
      "title": "标签",
      "addTag": "添加标签",
      "removeTag": "移除标签",
      "filterByTag": "按标签筛选",
      "noTags": "暂无标签"
    }
  }
}
```

### 验证

```bash
cd dashboard && npx tsc --noEmit
```

手动验证清单：
1. 右键对话 → 移至文件夹 → 选择/新建 → 对话出现在对应分组下
2. 右键对话 → 添加标签 → 标签出现在筛选条中
3. 点击标签筛选 → 只显示带该标签的对话
4. 折叠/展开文件夹 → 状态正确，刷新后持久化
5. 搜索 + 文件夹 + 标签筛选可叠加
6. "未分组"对话显示在最底部 section
7. 删除文件夹中的对话 → 文件夹计数更新
8. MinimalAgentSessionNav 模式不受影响（不显示分组）

---

## 实施顺序总结

```
Step 1 ──► Step 2 ──► Step 3 ──► Step 4 ──► Step 5 ──► Step 6
 迁移       Repo       API       TS类型     Store      UI
(~30min)  (~1h)      (~1h)     (~30min)   (~1h)     (~2-3h)
```

每步完成后跑对应的验证命令，确认绿灯后再进入下一步。

---

## 故障排查指引

遇到问题时：
1. **先回看本文档**对应步骤，确认改动是否遗漏
2. **查看跨步骤关联表**，确认上下游字段名/类型是否一致
3. 如果类型不匹配，检查 Step 2 的 `ThreadRow` 和 Step 4 的 `OctopThread` 是否同步
4. 如果 API 报错，先用 `curl` 测试 Step 3 的端点，排除前端问题
5. 如果测试失败，先跑该步骤的验证命令，再跑全量测试
