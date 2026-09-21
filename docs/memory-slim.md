# 手动在线整理 memory.sqlite

## 用户命令与表现

升级本次 Octop 和 harness-memory 0.9.11 或更新版本，重启 Octop 一次加载控制入口。之后每次整理无需停服：

```bash
octop memory list             # 只看可整理的智能体名称和 ID，不触发维护
octop memory slim             # 使用已设定的默认智能体；没有默认时按编号选择
octop memory slim --agent ID  # 已知 ID 时直接指定
octop memory slim --all       # 顺序整理列表中所有符合条件的智能体
```

不需要记住 agent 名称或 ID；没有默认智能体时会列出运行中、使用兼容 SQLite 记忆库的智能体，
输入编号即可。重名时可用同时显示的 ID 区分，Ctrl+C 可退出选择，不会触发整理。
已用 `octop agent use` 选择默认智能体时会沿用该选择，执行前打印目标 ID。
本地源码也可从 harness-memory 目录执行：

```bash
./scripts/memory-slim --online       # 同样支持默认智能体或编号选择
./scripts/memory-slim --online ID    # 指定 ID
./scripts/memory-slim --online --all # 顺序整理所有符合条件的智能体
```

`--all` 在启动时获取一次 `memory list` 的候选列表，范围是当前 OCTOP_HOME 内所有用户的
运行中、使用兼容 SQLite 记忆库的智能体；不启动已停止的 agent，也不扫描其他目录中的离线库。
忽略已保存的默认智能体，但不能与显式 `--agent`（含根命令参数）或 `OCTOP_AGENT` 同时使用。
终端显示 `[1/3] 名称 [ID]` 及该智能体的阶段、耗时和扫描数；每个完成并恢复后才开始下一个。
每个库分别备份、分别显示前后大小。遇到失败或连接中断立即停止批次，报告已完成数和未执行数，
不自动重试。关闭终端后当前已启动的作业仍由宿主完成，后续尚未提交的项目不会继续执行。
`octop --json memory slim --all` 的进度带 `agent_id`、`index`、`total_agents`，批次终态为
`batch_done` 或 `batch_failed`。`memory list` 可用于提前查看范围，它本身不执行瘦身。

上述终端命令直接触发维护，不是预览。它连接运行中的同一个 OCTOP_HOME 实例，不会启动第二份 Octop；
不指定数据库路径，服务使用该智能体实际打开的 SQLite 文件。
原 `harness-memory db slim FILE` / `scripts/memory-slim FILE` 仍然是离线预览入口。

终端和聊天页面显示：等待当前任务结束 → 备份 → 去重历史上下文 → 压缩 → 恢复。
等待期间不强行中断当前对话；120 秒内找不到空闲窗口时失败退出，不迁移。
进入维护后，新 stream/call/HITL resume 在现有 invocation gate 等待；页面两秒轮询状态，
显示经过时间，暂停发送。终端每秒刷新当前阶段及已用时间，去重时显示已扫描/总条数；
输出到文件/管道时，阶段或扫描数变化立即追加一行，其余每五秒追加心跳，方便日志查看。
备份/VACUUM 不提供虚假的百分比或剩余时间；耗时增加仅表示服务连接仍有响应，不代表完成比例。
记忆面板的 RPC 在维护期间返回 `AGENT_BUSY`，避免同步 SQLite 锁等待阻塞状态轮询；完成后可重试。
成功或失败后释放 gate，发送按钮恢复。其他独立数据库的智能体仍可使用。

备份位于原文件旁，名字为 `memory.sqlite.before-slim.<随机ID>.bak`，不会自动删除或覆盖。
命令结束显示主文件大小变化及备份路径；`octop --json memory slim --agent main` 输出逐行 JSON 进度。
JSON 进度包含 `elapsed_seconds`。`octop --json memory list` 返回可选列表；JSON 模式无默认智能体且
未指定 `--agent` 时输出列表后以非零状态退出，不自动选择或等待交互。
关闭终端不会取消已经开始的数据库作业。若服务连接中断，先看页面/日志状态再重试，
不要恢复旧备份覆盖期间新增的数据。

## PostgreSQL 提示与维护边界

单个 PostgreSQL 智能体返回独立提示：PG 也可能存在重复数据或空间膨胀，但本命令目前尚未支持
PG 瘦身，只支持 SQLite；本次未执行整理，可以继续聊天。空候选提示同样说明 SQLite 范围和
PG 尚未接入，避免把“命令不支持”误解成“数据库无需维护”。中英文同步。

底层 harness-memory 已有 PG 普通 VACUUM / VACUUM FULL 运维能力，但不是当前对话命令的后端。
普通 VACUUM 主要供库内复用空间；FULL 重写表且阻塞读写。PG checkpoint 表在同一 database 内
可能由多个 agent/用户共享，不能仅暂停当前 agent 就调用 FULL。后续宜先做不阻塞聊天的只读诊断，
再按实际收益和共享范围提供管理员维护操作。本轮只做只读评估和提示修正，没有开启 PG 整理。

2026-09-18 文案回归：memory/slash memory/i18n 117 passed、2 deselected，Ruff/format 和
strict mypy 499 files 通过。未重启正在运行的 Octop；新提示需加载更新后的代码才生效。

## 实现与一致性边界

### 从对话触发

登录后的 Octop 网页聊天框或本地 CLI 对话支持以下命令，无需知道 agent 名称：

```text
/memory slim                       查看作用、影响和当前智能体目标
/memory slim --all                 查看自己的全部在线候选和批量整理影响
/memory slim --confirm             确认现在整理当前智能体
/memory slim --all --confirm       确认现在逐个整理自己的全部在线候选
/memory status                     查看最近一次整理的阶段、耗时、扫描条数及结果
```

这是注册的 slash 命令，不经过模型判断执行；`/memory` 或错误参数只返回用法。
不带 `--confirm` 时只展示用途、保留历史、额外备份空间、暂停发送和无法预估耗时的说明，以及
候选名称/ID 和确认命令；不会创建维护任务、备份或预约，不影响聊天。这里是操作说明和范围预览，
不扫描 checkpoint，也不计算预期缩减量。确认执行时重新计算当前符合条件的候选并重新验证权限。
带 `--confirm` 后立即返回受理回执，宿主持有后台作业，网页沿用维护提示和发送暂停/恢复逻辑。
对话的 `--all` 与本地管理 CLI 范围不同：只选当前用户自己的 agent，不包含其他用户或共享 agent。
一个宿主同时只允许一个维护任务，整个对话批次期间也互斥；任务执行前及状态读取时重新验证所有权。
每个候选分别备份，依次处理，失败停止并将其余项标为未执行。关闭页面不会取消已受理的后台批次；
服务关闭会等待正在执行的 SQLite 作业结束，不再启动后续候选。状态仅驻留内存，新任务会替换旧状态。
维护期间当前聊天输入框被暂停时可看页面提示，恢复后用 `/memory status` 查看结果。
维护提示明确覆盖该智能体的所有会话，可切换到其他未维护的智能体。经过 60 秒后补充大库/磁盘
耗时说明；没有虚假的剩余时间。轮询失败时标记当前状态可能过时并持续重试，不把失败视为恢复发送。
API 保留手动维护的 done/failed/skipped 终态（`kind=memory_slim`），页面明确展示恢复使用或未执行，
停止转圈和计时，用户可点击“知道了”关闭结果提示；下一次维护会重新显示提示。

IM 暂不开放：现有 IM `user_id` 是用于会话存储的 agent owner，不是发送者的可验证维护身份。
飞书/微信等 IM 输入 `/memory` 会提示转到网页或本地 CLI，不启动维护；普通聊天、模型回复不会触发。
网页版命令目录和 `/help` 会自动展示新命令，不需要额外前端 hardcode。

命令目录通过 `persist_checkpoint=False` 声明维护回执只保存到聊天展示记录，不写入正在整理的 LangGraph checkpointer，以免回执等待 SQLite 锁。
已就绪的控制面历史投影仍保存命令和回复；尚未完成历史迁移的会话只保证当前回执可见，刷新后可能不保留。
这不删除既有历史，也不改变普通聊天的 capture/recall 流程。失败细节写入服务日志，聊天只提示失败，
完成结果显示备份文件名，完整备份路径仍可从本地 CLI 查看。

### 协调与存储

- `cli/commands/memory.py` → `infra/agents/memory_slim_control.py` 的本机 loopback 通道。
  控制端口随机，仅绑定 127.0.0.1；`OCTOP_HOME/memory-slim-control.json` 包含私有 token，
  通过权限为 0600 的临时文件原子发布（Windows 依赖用户目录 ACL）。权限语义沿用本机 CLI 的文件系统信任。
  不提供无认证的远程 HTTP 管理入口。该文件随正常退出删除，旧 token 不能调用新进程。
- `launch.py` 启动/关闭控制 listener；`AgentManager.memory_slim` 持有任务协调器，Manager shutdown 先等待维护结束再关闭 Agent。
  关闭 listener 后不再接受新作业，服务关闭会等正在执行的 SQLite worker 完成再关闭运行时。
- 对话复用已有的 `SlashCtx.agent_manager`，由 `handlers/memory.py` 调用其 `memory_slim` →
  `MemorySlimCoordinator.start_chat/chat_status`；批次复用同一 `_run`、空闲预约和 SQLite worker。
  后端 catalog 同时供 `/help` 和网页命令菜单使用；不新增远程管理 HTTP 端点。
- `MemorySlimCoordinator` 复用 `AgentManager.try_begin_history_backfill/end_history_backfill` 的
  空闲预约，与既有历史回填互斥；它们已覆盖 stream/call/resume 的 admission。
  同一宿主同时只整理一个库。没有自动阈值触发或周期性全量压缩。
- 仅接受正在运行、具备 `CompactSqliteSaver` 和独立连接 decoder 的 SQLite agent。
  配套 harness-memory 必须提供 `application.checkpoint_maintenance.slim_live_checkpoints`；
  版本不匹配、关闭记忆、PostgreSQL 或未运行的 agent 都会在改写之前失败。
- 在线库采用 WAL。迁移每批先 `BEGIN IMMEDIATE` 再读/改行，防止把并发写入覆盖回旧值。
  本轮扫描固定 rowid 上界，不无限追逐新增行。内容与引用同事务提交，历史 ID、metadata、
  parent、writes 和业务记忆不删除。在线路径不执行历史裁剪、逆向展开或孤立 blob GC。
- 保留兼容读连接/缓存，已有 SQLite 读快照继续读取一致内容；后台 capture/提取写入由 SQLite
  写锁串行协调，不通过关闭连接或跳过 capture 来制造“空闲”。完整备份与校验在改写之前执行。
- VACUUM 可能等待其他事务。长读事务仍占用 WAL 时，会报告“去重完成但空间回收未完成”；
  释放聊天预约，保留可读的混合格式和备份，不伪报全部压缩完成，也不自动回滚。
- 此模式针对一个运行中的 Octop 管理的库。它不能升级独立运行的旧 reader，不能保证其他进程
  使用旧格式 reader 或自定义写库脚本时兼容；部署前需统一升级。共享同库的其他写入仍受 SQLite 锁影响。

## 验证

2026-09-18 不可整理原因诊断修复：单个 agent 的预览先验证归属，再诊断运行时，明确区分
未运行、未启用记忆、非 SQLite backend（例如 PostgreSQL）以及配套在线整理接口缺失。
修复了“已运行的 PostgreSQL agent 被过滤后只显示没有候选”的误导提示；候选列表也检查
`slim_live_checkpoints` 能力，避免旧安装包被误报为可在线整理。未自动切换 backend 或更新运行环境。
memory/slash memory/i18n 定向回归 117 passed、2 deselected（本轮排除已有 socket 用例）；
strict mypy 499 files、Ruff/format 通过。这里只验证 PostgreSQL 拒绝提示，没有新增 PG 瘦身能力。

2026-09-18 确认与维护提示改造：两个仓库从各自当前 HEAD 签出 `feature/memory-slim-tool`，保留
全部未提交改动。Octop 原分支为 `feature/harness-agent-bump`，harness-memory 原分支为 `main`。

- 上述对话/维护回归加 `tests/integration/test_memory_api.py`：201 passed，覆盖预览无任务/无改写、
  确认后执行、权限和接口终态；`uv run --no-sync mypy --strict src/octop`：499 files 通过。
- `npm test -- src/pages/Chat/hooks/useMemoryMaintenance.test.ts src/pages/Chat/components/MemoryMaintenanceBanner.test.tsx`：
  9 passed，覆盖长耗时解释、断连重试、完成/失败恢复发送和可关闭结果；`npm run build` 通过。
- 本轮不改库内迁移实现、不重复完整门禁；此前全量门禁限制见下。未提交、部署或执行真实库维护。

2026-09-18 对话入口补充：

```bash
PYTHONPATH=../harness-memory/src:src uv run --no-sync pytest tests/unit/agents/test_memory_slim.py tests/unit/gateway/test_slash*.py tests/unit/gateway/test_message_keys.py tests/unit/gateway/test_gateway.py tests/unit/gateway/test_history_projection.py tests/unit/i18n -q
```

178 passed，覆盖真实临时 SQLite 的对话触发、历史保留、用户隔离、批次串行/互斥、所有权变更、
失败和关机停止后续项、IM owner fallback 禁止授权、禁用用户、进度/结果、gateway 注入、
维护回执不访问 checkpointer。strict mypy 499 files、Ruff/format 通过。
随后补充“等待活跃对话结束期间 owner 变更”的检查：取得维护预约后再次验证 owner，6 个 chat
协调器用例定向复跑通过（含新增用例），strict mypy 再次通过；未获授权时不创建备份或改写库。
没有更改前端源文件或库内存储实现；未重复全量门禁，其既有环境限制见下。未部署、重启或整理真实库。

临时数据库验证 reader snapshot、批次间并发替换/新增、迁移故障、备份可读和历史保留。
协调器测试覆盖等待活跃调用、维护期间新调用等待、成功/失败释放、取消时先等待 worker 完成，
本机控制认证/进度及 CLI 中文输出。前端测试覆盖每个阻塞阶段与成功/失败后的发送恢复。

```bash
# 从 Octop 仓库运行，加载配套 harness-memory 源码。
PYTHONPATH=../harness-memory/src:src uv run --no-sync pytest tests/unit/agents/test_memory_slim.py tests/unit/i18n -q
cd dashboard
npm test -- src/pages/Chat/hooks/useMemoryMaintenance.test.ts
npm run build
```

本轮只在临时库测试，未更新正在运行的生产进程、未对用户真实库执行瘦身。

2026-09-18 选择与持续进度补充验证：coordinator/CLI/控制通道/i18n 共 81 passed，覆盖编号选择、
错误编号重新输入、重名识别、空列表、只读发现、JSON 禁止自动选择，以及备份阶段无状态变化时
仍持续发送耗时心跳。strict mypy 498 files 通过；本地脚本 `--online --help` 和 shell 语法检查通过。
本轮未改动存储迁移/前端代码，未重复全量测试；完整门禁的既有环境限制见下。

2026-09-18 `--all` 补充验证：上述定向测试更新为 88 passed，新增串行执行、默认项不干扰、
批次及单项进度、人类可读/JSON 输出、失败/断连停止、参数冲突和空列表覆盖。
strict mypy 498 files、Ruff/format、wrapper `--online --all --help` 通过。没有执行真实库整理。

2026-09-18 验证结果：

- harness-memory checkpoint compaction：37 passed（含长 reader 与并发写入）。
- Octop 协调器/本机控制/CLI/记忆面板保护 + 原 memory API 集成 + i18n：90 passed。
  本机 socket 测试因默认 sandbox 不允许 bind，放行仅此临时测试后通过；没有使用真实用户库。
- 更广的 agent manager、启动及 CLI registry 回归：153 passed、1 skipped；唯一初次失败为
  上述 socket bind 权限，已在后续放行的测试中通过。
- Ruff/format、strict mypy（Octop 498 files、harness-memory 107 files）通过；
  前端 2 个阶段恢复测试、TypeScript 编译与生产构建通过。
- 两仓完整门禁均未全绿：harness-memory 的 24 个既有测试访问不可写的默认用户目录失败；
  Octop 全量在旧 captcha 测试绑定端口时报 PermissionError，确认环境原因后中止全量运行，
  复跑该文件定位为 2 passed / 1 error。未把中止结果或 PostgreSQL skip 当成通过。
- 多 GiB 库/完整生产 IM 端到端/长期磁盘增长未测；本轮没有提交、部署或重启真实 Octop。

## 2026-09-20 提交前验证与依赖收敛

- 维护对象由 `AgentManager.memory_slim` 持有，shutdown 等待维护完成后关闭 Agent；
  Gateway、SlashCtx、OctopServer 不再增加专用传递字段。CLI 控制入口按请求获取当前 runtime，
  支持首次配置完成后加载 AgentManager。
- `/memory` 在 catalog 声明 `persist_checkpoint=False`；processor 统一读取保存策略，
  普通命令及别名继续写入 checkpoint 和已就绪的聊天展示记录。
- `UV_CACHE_DIR=/tmp/octop-uv-cache PYTHONPATH=../harness-memory/src:src make all RUN='uv run --no-sync' PYTEST_JOBS=4`：
  3361 passed、18 skipped；Ruff/format 和 mypy（499 source files）通过。
- `cd dashboard && npm test -- src/pages/Chat/components/MemoryMaintenanceBanner.test.tsx src/pages/Chat/hooks/useMemoryMaintenance.test.ts`：
  9 passed。提交钩子另执行 change-aware 检查和 `npm run build`（包含 `tsc -b`）。
- 未执行真实记忆库瘦身或 PostgreSQL 维护；在线能力仍明确限定为兼容 SQLite。
