# 专家团队模式

主持专家是团队主持人：独立工作区、记忆、通道，负责调度。成员仍是普通专家，可单独聊天、可加入多个团队。过程是群聊上墙，收尾由主持人总结并判断是否收工。

## 已确认决策

### 身份与编制

| # | 决策 |
|---|------|
| 1 | 成员仍是独立专家，可同时加入多个团队 |
| 2 | 创建团队至少 2 个成员（不含主持人） |
| 3 | 成员只能是普通专家，不能套团队 |
| 4 | 可加入：自己的专家 + 分享给自己的专家 |
| 5 | 分享来的专家可以真正派工；产出进对方工作区/聊天，不能改对方配置 |
| 6 | 第一版团队不分享，只有创建者能聊、改成员、绑通道 |
| 7 | 有在途派工时，不能移出该成员、不能删除该专家 |

### 说话与调度

| # | 决策 |
|---|------|
| 8 | 真群聊：成员气泡直接上时间线 |
| 9 | 主持人只调度：寒暄/说明派工可短答；专业工作一律异步派给成员 |
| 10 | `@` 只提示优先，不强制只派给被点名的人 |
| 11 | 成员结束后仍回叫主持人；主持人总结并判断是否收工 |
| 12 | 用户新消息一律先到主持人（即使成员还在说） |
| 13 | 成员可同步 `ask_agent` 问同事，不能再异步往群里拉人 |
| 14 | 主持人一轮可并行 `dispatch` 多人 |
| 15 | 对方没运行则派工失败，主持人权走失败回叫，不自动启动 |
| 16 | 停止只停主持人本轮；成员继续跑完再回叫 |

### 会话、存储、通道、UI

| # | 决策 |
|---|------|
| 17 | 房间 ID = 主持人 `thread_id`；成员 checkpoint = `主thread~成员id`；网关转播 + `speaker_agent_id` |
| 18 | 各写各的工作区；团队准则/团体记忆只在主持人侧，派工时写进任务消息 |
| 19 | 通道只绑主持人 |
| 20 | 两边都能看：团队房间转播；成员侧栏多一条「来自团队 XXX」会话 |
| 21 | 团队出现在现有聊天侧栏，用徽章区分；「我的团队」tab 只做创建和编辑 |
| 22 | 右侧成员条只放成员，不含主持人 |
| 23 | 主持人权能只有成员相关工具：`agent_list` + 异步 `ask_agent` + 记忆/时间；不挂文件系统/浏览器/搜索/MCP/技能/插件；创建编辑无 skill / subagent / 插件 / 人格 |

## 身份模型

团队不是平行实体，而是 `agents.kind = team` 的特殊专家：

| | 专家 (`kind=expert`) | 团队主持人 (`kind=team`) |
|--|--|--|
| 工作区 / checkpoint / 记忆 | 有 | 有（团队记忆根） |
| 系统提示 | 专家模板 | 隐藏调度模板 + 运行时「先消化再改写」约束（用户不可见专家库） |
| 工具 | 干活用的全套 | 轻量 + `agent_list` + 异步 `ask_agent` |
| 可见 peer | 默认同用户其它专家 | 仅 `team_peers` = 团队成员 |
| 通道 | 可绑（1:1） | 可绑（团队入口） |

`team_id` = 主持人 `agent_id`。成员编制只写在主持人工作区 `.octop/manifest.json`（`kind` + `members`）。`agents.kind = team` 只作列表索引。

## 数据

团队主持人仍是普通 `agents` 行（`kind=team`，迁移 `016_agent_teams`）。编制只在工作区清单里：

```json
{
  "kind": "team",
  "members": ["expert-a", "expert-b"]
}
```

`GET /api/teams` / `GET /api/agents` 的 `member_ids` 都从这份清单读。没有成员表。

不拆 `threads.thread_id` 的 UNIQUE。LangGraph checkpoint 仍按专家隔离。

历史归属：fan-in 到主持人对话的消息在 `additional_kwargs.speaker_agent_id`（及 history JSON 的 `agent_id`）上标记说话人。不把多个专家写进同一条 checkpoint。

在途派工：进程内 `TeamJobTracker`，按 inbox `job_id` 幂等记账（`prepare_peer_session` 开始；`record_peer_turn` / `on_reply` 任一路径结束，失败也会释放）。重启后锁消失，可再改编制。

专家互调（非团队）只要带了 `source_thread_id`，会话也走 `peer:{房间}`，不再复用被叫方 1:1 DM。升级后旧 DM 里的 peer 历史不会自动跟过来。

## 运行时

### harness-agent

harness-agent 增加 `peer_invoke_mode: "sync" | "async" | "both"`（默认 `both`，保持旧行为）：

- `sync`：只注入同步 `ask_agent`
- `async`：只注入异步派工（发完即返回）
- `both`：一个工具两个 mode

Octop 普通专家设 `peer_invoke_mode=sync`（单聊：结果回工具）；团队主持人设 `async` 且 `team_peers` = 成员 id（群聊：上墙）。主持人自己的对话请求也会带上 `peer_invoke_mode=async`。在仍默认 `ask_agent mode=sync` 的运行时上，Octop 会把主持人对成员的 `call_peer` 改写成 inbox `submit_peer`，保证发完即返回。异步管道按 inbox / 房间走群聊双写，不按 `kind=team` 决定要不要上墙。

inbox 按 callee 并发：同一成员串行，不同成员并行；主持人回叫按源 `thread_id` 串行。

回叫闭环保持现状：inbox 完成后平台再叫醒主持人（`compose_followup`），不是成员自己调主持人。团队主持人的回叫提示要求判收工、不复述成员已上墙的正文。收口走房间 stream（与成员直播同一条 WS），不再整段 `team_snapshot`。

成员被团队派工时，请求级覆盖 `peer_invoke_mode=sync` 且 `team_peers` 收窄为同事，禁止再异步往群里拉人。成员收到的 Human 是主持人改写后的任务说明书，不是用户原话；群聊记录（用户 / 主持人 / 已上墙成员）只作为 System 背景。成员 checkpoint 仍是 `主thread~成员id`。主持人系统提示会要求先消化再改写，禁止原样转发。

### Octop 主持人装配

`_build_harness_config` 在 `kind=team` 时：

- 不挂 cron / knowledge / mobile / plugin / MCP / 技能包
- 启动时 `init_workspace=False`，不拷贝 harness `_builtin_skills` / 内置 subagent
- `tools_disabled` 只保留 `agent_list` / `ask_agent` / 记忆 / `current_time`（含原本不可关的文件系统与 `task`）
- `team_peers` = 成员
- 种子写入工作区 `SOUL.md`（主持人人格）+ `AGENTS.md`（协调/派工准则）+ `.octop/manifest.json`（`kind=team` 与 `members`）

成员被派工时仍用自己的工作区。对方 `last_state` 非 running 则 harness 调用失败，主持人走失败回叫。

停止：Dashboard 取消只取消主持人当前 stream；inbox 里已排队/在跑的成员任务不取消。

## 房间与转播

```text
conversation_id = 主持人 thread_id
  ├── 主持人 LangGraph thread = conversation_id
  ├── 成员 A checkpoint = conversation_id~A
  └── 成员 B checkpoint = conversation_id~B
```

- 用户始终跟主持人说话；WS 订房间 `conversation_id`
- 房间流式帧带说话人：`agent` 与 `agent_id`（主持人自己的 token 也打主持人 id；主持人 `done` 不带，方便前端结束本轮）
- 成员自己的会话列表多一条 thread（派生 id），标题「来自团队 {name}」；session_key 为 `team:{房间thread}`，不占用成员 1:1 的 `dm` 会话
- `@` 列表在团队聊天里收窄为成员；只作提示，不预调用

房间 WS 逐 token 转播成员回复；fan-in 只在未 live 推送时补一条 snapshot。流式帧用 `agent` / `agent_id` 标识说话人。IM 通道看不到房间 WS：成员收口后会再推一条带说话人姓名的完整消息；主持人收口在 Dashboard 已直播时也会补推到通道。

## HTTP

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/teams` | 当前用户的团队（含成员摘要） |
| POST | `/api/teams` | 创建主持人 + 至少 2 名成员 |
| GET | `/api/teams/{team_id}` | 详情 |
| PATCH | `/api/teams/{team_id}` | 改名称/模型/欢迎语/成员（在途则拒改该成员） |
| DELETE | `/api/teams/{team_id}` | 删除团队主持人 |

`GET /api/agents` 增加 `kind`；团队行带 `member_ids`。`kind=team` 不可 `is_shared`。

错误码：`TEAM_NOT_FOUND`、`TEAM_MEMBERS_TOO_FEW`、`TEAM_MEMBER_INVALID`、`TEAM_MEMBER_BUSY`、`TEAM_NOT_SHAREABLE`。

## 前端

专家页 tab：`我的专家 | 我的团队 | 专家库 | 市场`。

- 我的专家：过滤 `kind !== team`
- 我的团队：卡片/空态指引；创建/编辑只要名称、模型、颜色、欢迎语、成员；通道走现有通道配置（绑在主持人）
- 侧栏：团队带团队徽章
- 团队聊天右侧：成员条（不含主持人）
- 气泡：`speaker_agent_id` 对应专家头像/名称；主持人用自己的头像

## 隐藏模板

`src/octop/infra/agents/teams/template/`，不进 `GET /api/experts`。`template_name = team-host` 仅内部标记。

## 非目标（第一版）

- 团队分享、嵌套团队、自动拉起停用成员
- 多个专家共用同一 `threads.thread_id`
- 成员异步往群里拉人
- 共享团队工作区
- harness inbox 进程外持久化（重启丢在途任务）
