# Octop `develop` 更新日志整理

> 数据来源：仓库 `CHANGELOG.md` 的 `[Unreleased]` 段 + `main`↔`develop` 逐文件哈希比对 + GitHub commits atom feed
> 快照时间：develop HEAD 约 2026-09-25

---

## 一、develop 与 main 的关系

| | main | develop |
|---|---|---|
| 版本 | **1.0.2b2**（2026-09-23） | 1.0.2b2 + `[Unreleased]` |
| 运行时依赖 | `orcakit-harness-agent` / `harness-*` | **`octop-harness` / `octop-memory` / `octop-gateway` / `octop-browser` 1.0.0** |
| 定位 | 生产版 | 日常集成分支 |

**规模差异（实测）**：main 3057 个文件 → develop 3061 个文件

| 类型 | 数量 |
|---|---|
| 修改 | **282** |
| 新增 | **4** |
| 删除 | 0 |

> ⚠️ **282 个修改里绝大多数是 `octop-*` 改名**（import 路径 + 文档 + UI 文案），不是新功能。

---

## 二、改动集中在哪（实测分布）

### 按目录

| 目录 | 修改文件数 | 说明 |
|---|---|---|
| `src/octop/infra` | **105** | 后端核心 |
| `tests` | **87** | 测试同步 |
| `src/octop/api` | **22** | HTTP 层 |
| `dashboard/src/pages/Chat` | **20** | 聊天前端 |
| `docs` | 13 | 文档 |
| `plugins` | 6 | 示例插件 |
| `src/octop/i18n` | 3 | 后端文案 |
| `dashboard/src/locales` | 2 | 前端文案 |

### `src/octop/infra` 细分（105 个）

| 子包 | 数量 | 备注 |
|---|---|---|
| `infra/agents` | **54** | 其中 **~24 是 bundled 插件 `main.py` 的 import 改名** |
| `infra/gateway` | **30** | IM/slash/media 全链路改名 |
| `infra/backend` | 5 | |
| `infra/db` | 3 | `repos/agents.py`、`repos/sessions.py`、`repos/threads.py` |
| 其余 | 13 | errors / backup / browser / users / utils … |

### 4 个新增文件

| 文件 | 归属 |
|---|---|
| `src/octop/infra/agents/thread_artifact.py` | **团队产物**（新功能） |
| `src/octop/infra/utils/thread_artifact.py` | 同上（叶子类型） |
| `dashboard/src/components/TokenCountInput.tsx` | Token 输入 UX（新功能） |
| `dashboard/src/components/TokenCountInput.module.less` | 同上 |

---

## 三、`CHANGELOG [Unreleased]` 全文整理

### 变更（1 条 —— 但是影响面最大的一条）

| # | 内容 |
|---|---|
| 1 | **运行时依赖改名**：`octop-harness[all]` / `octop-gateway` / `octop-memory` / `octop-browser` **1.0.0**（原 `orcakit-harness-agent` / `harness-*`）；文档、UI 文案与生成路径同步改为 `octop-*`（`~/.harness-browser` 仅作迁移/拒绝源） |

### 修复（10 条）

| # | 模块 | 修复内容 | 编号 |
|---|---|---|---|
| 1 | 知识库 | 文档数达上限时错误文案答非所问：单库 `max_documents` 可配置后，超限仍按字面量「at most 100」匹配，只有上限恰好=100 的库才报对；现两条报错按各自措辞区分，超限一律返回 `KNOWLEDGE_DOC_LIMIT` | |
| 2 | 知识库 | 文档重命名保留存储键后缀：去掉 `.pdf` 后原文下载/预览 404、删除留孤儿文件；现补回原后缀 | #1107 |
| 3 | 会话列表 | `GET /api/agents/{id}/threads` 的 `limit` 增加 **1–200** 边界（与消息分页同一上限）：此前负数被 SQLite 解释成「不限制」而返回全部会话，`limit=0` 返回空列表；越界请求统一拒绝 | |
| 4 | MCP / OAuth | IPv6 字面量地址无法连通：固定 IP 时 URL 被重建为 httpx 无法解析的形式（`InvalidURL`）且丢弃路径参数；现原样保留 | |
| 5 | HITL | 会话级「跳过审批」不再按进程缓存：多 worker 或 CLI 并发时，另一进程撤销的跳过仍持续放行、新授予的可能不生效；改为每次判定读 `threads.hitl_policy` | |
| 6 | 用户 | 角色与禁用/删除状态改为按请求读库：多 worker 或 CLI 离线改写时，另一进程里被降级/禁用/删除的用户立即失效 | #1102 |
| 7 | 备份 | 导入工作区 zip 时跳过 Octop 自有的 `_builtin_skills/` 条目：该前缀不允许删除或移动，归档里的同名文件会留下无法移除的技能 | |
| 8 | 工作区 | 写入接口补 `_builtin_skills` 保护：`PUT /workspace/file` 与 `POST /workspace/upload` 此前可往内置技能目录写文件，而删除/移动对该前缀一律 403，导致再也清不掉 | |
| 9 | 插件（安全） | `wiki_summary` 的 `lang` 不再被拼进请求主机名：此前传 `evil.com#` 会真的向 `https://evil.com` 发请求并把摘要回显进聊天；现只接受 `zh`/`en`/`zh-classical` 这类裸子域标签 | |
| 10 | 认证（安全） | 验证码 `OCTOP_CAPTCHA_V3_MIN_SCORE` 只按 `float()` 解析：填 `nan` 时 `score < nan` 恒为 `False`，分数门槛被静默关闭（机器分 0.0 也能登录），负数同样放行，`inf` 则锁死所有登录；现只接受 `[0,1]` 内有限值 | |

### 主线方向（从修复列表反推）

1. **多 worker（`octop run --workers N`）正确性** —— 第 5、6 条都是"进程内缓存 → 改为按请求读库"
2. **`_builtin_skills` 边界保护** —— 第 7、8 条成对出现
3. **Web 安全** —— 第 9、10 条都是注入/校验类
4. **知识库错误语义** —— 第 1、2 条

---

## 四、⚠️ `CHANGELOG [Unreleased]` **没有覆盖**的改动

从 commit 历史看，以下改动**未写进 CHANGELOG**（`[Unreleased]` 段不完整）：

| 日期 | commit | 影响 |
|---|---|---|
| 09-25 | `feat(chat): team artifacts, fan-in tool trail, and host wrap-up context` | **新增 `thread_artifact.py` ×2** —— 团队产物归属 |
| 09-25 | `fix: team chat/IM UX, ACP sandbox, channel thinking, and related polish` | 团队/IM/ACP |
| 09-25 | `fix(plugins): offload oversized octop_ui payloads to ToolMessage.artifacts` | 插件 |
| 09-25 | `refactor(infra): group agents modules and clarify package ownership` | **目录重构**（改名+移动） |
| 09-25 | `feat(connectors): 恢复企查查一键 OAuth，保留 internal HTTP 工具加载` | #1106 |
| 09-24 | `feat: admin user batch policies, token UX, default FS root, and media…` | **新增 `TokenCountInput`** |
| 09-24 | `fix: connectors empty layout and restore prior control-plane behaviors` | 连接器 |
| 09-24 | `docs: point README at TencentCloud octop-harness repos` | 文档 |

> **结论：跟进上游时必须以 commit 为准，不能只读 CHANGELOG。**

---

## 五、最近 4 个正式版本（看方向）

| 版本 | 日期 | 新增要点 |
|---|---|---|
| **1.0.2b2** | 09-23 | **Teams 主持人改写派工，成员回复同步 IM**；企查查、OpenAlex 连接器 |
| **1.0.2b1** | 09-22 | 极验行为验 v4；**对话默认折叠思考与工具过程**；**可隐藏不常用共享专家**；Ask/Plan/Craft 模式；生成模型多厂商；插件市场；**专家团队宿主**；Discord 渠道 |
| **1.0.1** | 09-18 | 飞书/钉钉/企微 OAuth SSO；登录验证码；容器工作区；模型列表搜索；ACP 纳入个性化 |
| **1.0.0** | 09-14 | GA 发布 |

**方向判断**：上游近期在**团队协作（Teams）** 上连续投入 —— 1.0.2b1 上"专家团队宿主"，1.0.2b2 上"主持人改写派工 + 成员回复同步 IM"，develop 上"团队产物 + 工具轨迹 fan-in + host 收口"。

> **这既是好消息也是风险**：好消息是我们的"跨团队房间"方向与上游一致；风险是**这块正在被上游快速迭代**，我们的 S4 会持续撞车。

---

## 六、对我们改造方案的 5 点影响

### 影响 1（最重要）：上游已有「thread artifact」体系，`artifacts` 表设计必须对齐

develop 新增的 [`thread_artifact.py`](Octop-develop/src/octop/infra/agents/thread_artifact.py) 已实现一套产物采集：

| 能力 | 实现 |
|---|---|
| 产物类型 | `ThreadArtifact{path, agent_id}` —— **工作区文件路径** |
| 存储 | `threads.artifacts` **JSON 列**（迁移 007 已有），非独立表 |
| 自动采集 | 从工具调用提取，白名单 `ARTIFACT_TOOL_BASES = {write_file, edit_file, send_file, send_file_to_user, desktop_screenshot, mobile_screenshot}` |
| 上限 | `MAX_THREAD_ARTIFACTS = 200`（超出保留最后 200 条） |
| API 载荷 | `thread_artifacts_payload()` → `{artifacts:[path], artifact_refs:[{path,agent_id}]}` |
| **develop 新增** | **`agent_id` 戳记** —— 让团队成员的产物可归属 |

**与我们的 `project.artifacts` 表的关系**：

| | 上游 `threads.artifacts` | 我们的 `project.artifacts` |
|---|---|---|
| 语义 | **文件级线索**（哪个文件被写过） | **业务级交付物**（PRD / 代码提交 / 文档） |
| 粒度 | 路径 | 带 `kind` / `commit_ref` / `kb_document_id` |
| 来源 | 自动从工具调用提取 | 任务完成时归集 |

✅ **两者不冲突，但实现方式要改**：

- ❌ **不要**重新扫描工作区来填 `project.artifacts`
- ✅ **应该**引用上游已有的 thread artifact（存 `path` + `agent_id` + `thread_id`），再补业务字段
- ✅ 展示层直接复用 `thread_artifacts_payload()`

> 好消息：本方案 S0 的规格里已经正确引用了 `thread_artifacts_payload`，与上游一致，无需返工。

### 影响 2：S5 的「commit 回写」有了现成扩展点

上游的 `ARTIFACT_TOOL_BASES` + `extract_artifact_paths()` 就是"从工具调用提取产物"的标准做法。**我们的 `git commit` 提取器应该做成同一模式**（加一类 tool base / 加一个 commit_ref 提取器），而不是另起一套。

⚠️ 但注意：`thread_artifact.py` 两个文件都是 **develop 新增**（main 没有）→ **上游还在快速迭代这个区域**，扩展它冲突概率高。建议我们的 commit 提取器**放独立新文件**，只 import 上游的 `ThreadArtifact`。

### 影响 3：S0 的会话列表端点要重新考虑 limit

CHANGELOG 说 `limit` 加了 **1–200** 边界。

⚠️ **但我在 develop 快照代码里没找到对应实现** —— 全仓只有消息分页的 `HISTORY_MAX_LIMIT = 200`（[serialize.py:54](Octop-develop/src/octop/api/routers/chat/serialize.py:54)）+ `_clamp_history_limit`，而 threads 端点（[history.py:99-111](Octop-develop/src/octop/api/routers/chat/history.py:99)）仍是 `limit: int = 50` 直通 SQL，**没有 clamp**。

**这意味着文档与代码在这个区域未完全同步**（也可能是我拿到的快照与 HEAD 有偏差）。

→ **设计结论不变且更强**：**不要依赖 limit 语义**，S0 改用服务端聚合：

```
GET /api/threads/summary
→ [ { agent_id, session_count, has_activity, last_active, pinned: [...] } ]
```
行数 = agent 数，构造上就有界。

### 影响 4：改名已由上游完成，我们不用再管

`develop` 已全切 `octop-*`，且 `main` 的 README 里"harness-* 筹备开源中"的说明也已同步更新。**fork `develop` 即直接拿到开源栈**，无需自己做 rename。

### 影响 5：上游正在重构目录

`refactor(infra): group agents modules and clarify package ownership`（09-25）说明 **`infra/agents/` 的模块组织正在变动**。我们的 S3/S4 要改 `infra/agents/manager.py`、`memory_backend.py`、`teams/service.py` —— **建议等这次重构稳定后再动这几个文件**，否则 rebase 成本翻倍。

---

## 七、跟进建议

| # | 建议 |
|---|---|
| 1 | **每次 rebase 前读 commit feed**（不是只读 CHANGELOG，`[Unreleased]` 不完整） |
| 2 | **重点盯 Teams / thread_artifact / infra/agents 目录** —— 上游正快速迭代，也是我们要改的地方 |
| 3 | **S4（跨团队房间）建议推迟到 `infra/agents` 重构稳定后** |
| 4 | **S5 的 commit 回写放独立新文件**，只 import 上游 `ThreadArtifact` |
| 5 | **S0 用服务端聚合**，不依赖 limit 边界 |
