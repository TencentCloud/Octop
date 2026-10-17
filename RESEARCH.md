# Octop 调研报告 — 政务智能体底座可行性评估

> 调研日期：2026-10-08 ｜ 代码版本：`main` @ commit `0c5a46ab`，版本 `1.0.2b6`（tag `v1.0.2b6`，2026-10-04）
> 调研档位：**基于它开发 + 完成度评估**（阶段 1→2→3→4→5）
> 调研对象：`C:\Users\Administrator\Documents\code\Octop`（上游 `github.com/TencentCloud/Octop`）
> 目标场景（用户确认）：对内办公助手（体制内人员）；**完全物理隔离内网 + 国产模型**；**信创适配（麒麟/统信 + 鲲鹏/海光）**；二开投入 **整体 fork 深度改造（3–10 人）**

---

## 1. 一句话结论

**能当底座，但你现在拿到的是「控制面 + 门户 + IM 接入」这一半，Agent 运行时那一半在三个独立 MIT 包里（`octop-harness` / `octop-gateway` / `octop-memory`），本仓库改不动；而政务内网最在意的四件事——部门级数据权限、审计防篡改、确定性流程编排、条款级政策检索——现状全部不达标，属于必须自研补齐的部分。**

换个说法：**它的工程成熟度和代码质量高于同类自托管 Agent 平台（144K 行后端 / 182K 行前端 / 481 个测试文件 / Linux+Windows 双平台 CI / `mypy --strict`；我在本机实跑：43 秒装完依赖、12 秒起服务、unit 套件 3554 passed），拿它的分层骨架和工程实践很划算；但把它当成"开箱即用的政务智能体平台"会在合规评审第一关就被卡住，而本机那 39 个测试失败恰好落在你们二开要天天碰的数据库迁移路径上（见 §4.4）。**

---

## 2. 项目画像

| 项 | 结论 |
|---|---|
| **定位** | 自托管、多用户、多 Agent 的 AI 助手平台。单 Python wheel 提供 Web 控制台 + CLI + IM 通道 + 定时任务，数据落在 `~/.octop/`，不依赖外部消息队列和中间件。 |
| **核心特色 1** | **单进程重建式架构**：无 worker、无 Redis/Kafka，重启后全部状态从控制面数据库重建（`docs/architecture.md:26-29`）。运维面极简，但也意味着**横向扩容受限**（见 §6）。 |
| **核心特色 2** | **运行时与产品分层解耦**：LLM 循环、工具、检查点在 `octop-harness`（LangGraph + `deepagents` 之上），IM 归一在 `octop-gateway`。Octop 本体只做编排、权限、UI、渠道装配。 |
| **核心特色 3** | **可插拔工作区后端**：本地磁盘 / Docker 沙箱 / PostgreSQL / COS / S3 统一收口到 `BackendWorkspace`（`docs/agent-backend-file-io.md`），Agent 文件与数据库分离。 |
| **核心特色 4** | 460 个 HTTP 路由全覆盖控制台能力（实测 `grep` 统计），任意门户/系统可程序化驱动；插件 + 技能 + 自定义 MCP 三条外挂路径。 |
| **形态/规模** | 服务 + CLI + SPA。后端 656 个 py 文件 / 144,008 行；前端 933 个 ts/tsx / 181,772 行；外部 `octop-harness` 解开后有 204 个 py / **40,522 行**（我实测拆包，见 §3.3）。 |
| **技术栈** | Python 3.12+ · FastAPI/uvicorn · asyncio · SQLite(WAL) 或 PostgreSQL · React 18 + TS + Vite + AntD · APScheduler · Click |
| **怎么用** | `curl …/install.sh \| bash`（公网 COS）→ `octop init` → `octop run` → 浏览器开 `127.0.0.1:8088`；或 `docker compose up`（`docker/Dockerfile:64` 基础镜像 `python:3.12-slim`）。 |
| **活跃度** | 仓库 **2026-07-08 创建**（约 3 个月），641 commits，近 30 天 225 次；7,812 star / 938 fork / **698 open issues**；最近推送日=今天。版本仍是 **beta（b6）**，两周一个 release 节奏。 |
| **许可证** | MIT（`LICENSE:1`），可闭源改写，须保留版权与许可全文。**仓库无 NOTICE / 第三方许可清单**（尽调要补）。 |

---

## 3. 架构与关键机制

### 3.1 核心数据流（一条链路走读）

一条 dashboard 消息的完整旅程，四段都在本仓库：

1. **入口**：WS `/api/agents/{aid}/chat/ws`，握手用 `?token=` 查询串（`src/octop/api/routers/chat/ws.py:33-48`），会话 key `<aid>:dashboard:<user_id>:dm`（`docs/architecture.md:96-101`）。
2. **鉴权与归属**：JWT HS256 解析 → `current_user`（`api/deps.py:118-140` 滑动续期）→ 载入 agent row 后 `_assert_agent_owner`（`api/common/agent.py:18-23`）。
3. **域编排**：`infra/server.py` 的 `OctopServer.start()` 按依赖序装配单例（`docs/architecture.md:31-60`）：`PathLayout` → `load_config` → `open_database` → `run_migrations` → `SharedServices` → `PluginManager` → `AgentManager`（全局单注册表，按 agent row 懒建 `HarnessAgentRuntime`）→ `Gateway` → `CronManager` → `UserManager`。
4. **下沉到运行时**：`AgentManager` 起 `HarnessAgent`（LangGraph 图），工具执行/审批/脱敏都在 harness 的 middleware 链里（顺序：`pii → media_offload → checkpoint_ts → memory → user middleware → team`，`octop_harness/agent.py:1428-1431`）。回流的 chunk 经 `GlobalProcessor` 做斜杠分发与投影（`infra/gateway/process/processor.py`）。

**要点**：IM 通道、定时任务、CLI 三条入口最终**汇成同一条处理链**（`docs/architecture.md:104-113`）。这个设计对二开很友好——政务门户只要走 WS/HTTP，就自动继承工具审批、历史投影、记忆写入，不需要重复实现。

### 3.2 官方留的扩展缝（实测清单）

| 缝隙 | 能力 | 天花板 |
|---|---|---|
| **插件** `plugins/` | `plugin.yaml` + `main.py:setup(ctx)`，ctx 只有 3 个挂接面：`tool`（带管理端 `config_fields`）、`skill`、`hook`（LangChain `AgentMiddleware`，`before_model/after_model`）；UI 侧可注册聊天工具结果卡片（`dashboard/src/plugins/toolRenderers/registry.ts`） | **不能**注册斜杠命令（`infra/gateway/slash/dispatcher.py:83-87` 硬编码）、**不能**加新 IM 通道、**不能**加页面/路由、**不能**干预审批流。无沙箱：`install_deps=True` 在服务进程内 import 执行（`infra/agents/plugins/manager.py:631`），`requires` 字段仅展示无校验 |
| **技能** | `SKILL.md` + frontmatter，落 workspace `skills/`；批量下发成熟：`PUT /api/agents/{id}/skills`、`/skill-packages`（`api/routers/skills.py:796,841,554`）、SkillHub/GitHub 导入 | 技能包仅支持 `local_shell/filesystem` 后端（`infra/agents/manager.py:2058-2073`），且写技能要求 agent **处于 running**（`api/common/workspace.py:37-57`）——批量灌几十个领域技能要先起 agent |
| **Connector / MCP** | 接内部 REST 首选零代码：`PUT /api/connectors/custom-mcp`（`api/routers/connectors.py:582`，`streamable_http`/`stdio`）；另有 OAuth PKCE、internal MCP | 内网**字面 IP/RFC1918 放行**（`infra/connectors/custom_mcp.py:147-150`），但内网**域名解析到私网**会被当公网走 HTTPS+SSRF 拒（`infra/utils/ssrf_guard.py:61-70`）→ 政务系统一律用 IP 或 `.internal`。一等公民 connector 要改 657 行硬编码 `_CATALOG`（`infra/connectors/catalog.py:112`） |
| **HTTP API** | 460 路由 / 82 router 文件，OpenAPI 完整，`/api/docs` Scalar | **只有 JWT 鉴权，无 API Key / 服务账号 / 签名机制**（`api/deps.py:12-15`）→ 第三方门户只能"模拟登录换 token"。加自有路由**必须改 `api/app.py:224+` 硬编码挂载表**，`build_app()` 无注入参数 |
| **i18n / 时区** | `src/octop/i18n/{en,zh}.json` 双包 + key 全等测试；服务器时区统一（`config.default_timezone`） | 中文是一等公民（对政务有利），无第三语言抽象 |

### 3.3 设计决策与"为什么"（以及它对你的代价）

- **为什么把运行时抽成 `octop-harness`？** 因为要同时服务 Web/IM/CLI/ACP 四类入口，且要跟着 `deepagents`/LangGraph 生态演进。代价（已实测）：本仓库 **87 个文件、110 处** `import octop_harness`（`grep` 统计），`pyproject.toml:24` 声明 `octop-harness[all]>=1.0.1` **无上界**。**你 fork 了 Octop，也改不到工具执行、审批拦截、脱敏、shell 防护的实际逻辑。** harness 独立仓库 46 star / MIT / 最近推送 2026-10-04。
- **为什么单进程、无队列？** 部署门槛降到最低（一条 `octop run`）。代价：HITL 审批 pending 态在**进程内存**（TTL 30 分钟，`infra/gateway/hitl/store.py:12,33` "process-local, TTL-gc"）→ 重启即丢，且多 worker 不共享。**这对政务"审批不能丢"是硬伤。**
- **为什么不用 pgvector，而用每库一个 sidecar SQLite + 全表暴力余弦？**（`infra/knowledge/index.py:26-134`）省掉扩展依赖，便于迁移。代价：大语料下检索线性退化，且拿不到 ANN/混合检索。
- **为什么 SQLite 与 PostgreSQL 共用一套 schema、双迁移文件编号成对？**（`AGENTS.md` §7 + `infra/db/migrations/00N_*.sql` / `.pg.sql`）让默认部署零依赖。代价：**没有 ORM，全是裸 SQL**，只有 `?`→`%s` 的转换（`infra/db/pool.py:15`）；换国产库要逐个处理 `ON CONFLICT`（`repos/settings.py:23`、`invites.py:216`、`threads.py:184`）、`INSERT…RETURNING`（`repos/_base.py:74`）、SQLite PRAGMA（`infra/backup/snapshot.py:56`）。

---

## 4. 完成度核验（README 逐条对代码）

**原则：README 会过时。下表每个状态都落到具体行。**

| README 声称的能力 | 状态 | 证据 | 说明 |
|---|---|---|---|
| 多用户 JWT 认证 + 管理员角色 | ✅ 完整 | `infra/users/identity.py:9-21`、`infra/db/repos/user_roles.py:77-116`、`api/deps.py:168-197` | admin/user 模板 + 自定义角色表（ULID）+ 模块级权限目录 `permissions.py:50-234` |
| LDAP / SSO 登录 | ✅ 成熟 | `infra/auth/ldap/service.py:194-203`、`ldap/config.py:169-176`；OIDC 走 PKCE+nonce+JWKS | LDAP 支持组白名单准入、`admin_groups` 映射角色、强制 StartTLS。**坑：OIDC 只落默认 `user` 模板，不按 claim 映射角色（`infra/users/manager.py:253-259`），与 LDAP 不对称** |
| 密码策略 / 失败锁定 | ⚠️ 部分 | `infra/users/password.py:48-70`（Argon2id）、`config.py:130-131`（5 次/900s） | 无强制有效期/历史；口令策略偏弱（无大小写/符号） |
| 工具审批（human-in-the-loop） | 🙈 **已实现但默认关闭** | `infra/agents/security/policy_store.py:21` `data["hitl"]["enabled"] = False`；harness 侧 `security/models.py:119,165` 默认亦 False | 按**工具调用粒度**审批（`gateway/hitl/coordinator.py:91`），IM `/approve` 双通道送达。缺：不能按角色强制；会话级 `allow_all` 旁路持久化在 DB |
| Shell 命令防护 | ⚠️ 已实现但默认**只告警** | `policy_store.py:22` `{"enabled": True, "mode": "warn"}`；规则 `octop_harness/security/tool_guard/rules/dangerous_shell_commands.yaml`（31 条，含 `\brm\b`/`\bmv\b`） | 引擎是 YAML 正则黑名单，规则目录可通过 `~/.octop/security/tool_guard/` 外部覆盖（`rule_guardian.py:93-160`）→ **扩展性尚可，但默认不拦，且是黑名单不是白名单** |
| 敏感信息脱敏 | ✅ **存在且默认开启**（子代理初判为"没有"，我复核纠正） | `octop_harness/middleware/pii.py:95-132` 覆盖 openai/anthropic/AWS/GCP/HF 密钥 + **中国大陆手机号**（`:124-127`，支持 +86）+ **身份证号**（`:132`）；`config/__init__.py:655` `pii_enabled: bool = True` | 但它是**正则式密钥/PII 掩码**，不是政务要的"数据分级分类 + 字段级脱敏策略"；出口只覆盖对话链路，未见审计日志/IM 落库前脱敏 |
| 数据/文件隔离 | ⚠️ 弱 | `api/routers/workspace.py:132,185,479,514`（owner_only）；`infra/utils/host_dirs.py:83-93` | OS 级牢笼**只在 Linux + bubblewrap 才成立**，否则 `root_dir` 只约束工具路径，agent 进程仍持服务账号全盘 FS 权限；**任意认证用户可浏览宿主机根目录**（`api/routers/filesystem.py:10`） |
| 跨用户共享 | ⚠️ 粗 | `infra/db/repos/agents.py:213`、`knowledge.py:174-181` | `is_shared=1` / `shared=1` 即**对全部用户可见可用**，无按人/按部门授权。**共享 agent 的 workspace 读/下载非 owner 也可访问**（`workspace.py:166,346,380`） |
| 审计留痕 | ⚠️ 部分 | `audit_log(ts,actor,action,target,payload)` 覆盖约 51 处；查询需 `admin_console`（`api/routers/admin.py:51-76`）；面板 `dashboard/src/pages/Settings/Security/AuditLogPanel.tsx` | **纯追加表，无哈希链/签名**（有 DB 写权限即可篡改）；`delete_before` 无调用者→**无保留期策略**；对话内容与 workspace 读/下载**无审计调用** |
| 用量统计 | ⚠️ 部分 | `usage_log`（`migrations/001_initial.sql:181-196`）、`api/routers/usage.py`（含 xlsx 导出） | 只有 token，**无单价/成本核算** |
| 知识库 RAG | ⚠️ 可用但不达政务要求 | 解析 `knowledge/parse.py:34-71`（pdf/docx/pptx/xlsx/csv/图片，OCR 可选）；分块 `chunk.py:6-21` **固定 800 字符滑窗 overlap 120**；检索 `index.py:40-100` 纯向量**全表暴力余弦**；配额 `service.py:29-30`（**每人 20 库、每库 100 篇**） | **无 BM25/混合检索、全库 rerank 0 命中**；引用回填只到**文件级** HTML 注释 marker（`citations.py:101-150`）→ **给不了"《XX 办法》第十二条"** |
| AgentTeams 多智能体协作 | ⚠️ Beta，代码真实 | `infra/agents/teams/team_manager.py`（1,750 行），`api/routers/teams.py` 仅 6 个 CRUD 端点；主实现在**外部** `octop_harness/teams/`（`docs/agent-interop-mailbox.md:3`） | README 自己也标 Beta / In progress（`README.md:53,165`） |
| **确定性流程编排（DAG/workflow）** | ❌ 没有 | 全库 `workflow\|dag\|pipeline` 只命中专家提示词文本（`infra/agents/experts/manifest_generator.py:26`） | 只有 APScheduler 定时 + 工具级 HITL 单点审批。**政务审批流的节点/会签/退回/时限必须自建** |
| MFA / 双因素 | ❌ 没有 | 全库无 totp/mfa；登录 captcha 仅反爬（`api/routers/auth.py:185-191`） | 等保三级/密评会问 |
| 令牌吊销 | ❌ 没有 | HS256 无状态、无 jti（`infra/auth/tokens.py:17-45`）；logout 明确不吊销服务端 token（`api/routers/auth.py:212`） | 只能靠改密/禁用用户/轮换全局密钥（`docs/configuration.md:241` 无零停机方案） |
| **JWT 密钥存放** | ❌ 文档与实现不一致 | 文档称在 `~/.octop/secrets/jwt_secret`（`docs/configuration.md:16/235`），实际存 **DB `secrets` 表**（`infra/server.py:676-678`），且与密文同库、`os.urandom(32)` 无独立保护 | 合规评审的典型问题点 |
| 三员管理（系统/安全/审计管理员） | ❌ 没有 | 权限是**模块级平铺表**（`infra/users/permissions.py:50-234`），无职责分离 | 政务硬指标 |
| 限流 / 并发配额 | ❌ 基本没有 | 仅 LDAP 绑定、邀请、setup、远程桌面有 throttle；**无按用户/接口 QPS、无 agent turn 并发上限** | token 总额配额有（`users/resource_policy.py:182,196`） |
| Prompt injection 防护 | ❌ 没有 | 全库无对应机制 | Agent 能执行 shell + 读网页，风险面真实存在 |
| SSRF 防护 | ✅ 质量好 | `infra/utils/ssrf_guard.py:143-221`：强制 https、拒私网/保留 IP、**DNS 解析后 IP 锁定防 rebinding** | 本仓库可控部分里最扎实的一处 |
| 凭据加密 | ✅ | `infra/connectors/crypto.py:8-28` Fernet，密钥 `get_or_create` 存 `secrets` 表 | 与 JWT 同库，密钥未独立保护 |
| 自托管 / 无外部服务 | ✅ | `docker/Dockerfile:64` `python:3.12-slim`，仅 `EXPOSE 8088`；`config.py:126` 默认 `bind_host=127.0.0.1`；API docs/CORS 默认关（`config.py:126,135`）；前端零 CDN（`dashboard/index.html` 仅本地 favicon/manifest，字体在 `src/assets/fonts`）；**遥测 0 命中**（grep telemetry/sentry/posthog），版本检查仅手动触发（`api/routers/update.py:205`） | 但 **Docker 全程无 `USER` 指令 → 以 root 运行**（`docker/Dockerfile`、`fnos/docker/Dockerfile`） |
| 移动端 / 桌面端 / 飞牛 NAS | ✅ 存在但画像不符 | `desktop/` 是 Wails v3 桌面壳，`fnos/` 是飞牛 NAS `.fpk` | **面向个人 NAS / 家庭共享的产品画像**，不是政务交付形态 |

### 4.1 未完成信号扫描

- `TODO` / `FIXME` / `NotImplemented`（src 全量 py）：**仅 10 处**，分布在 144K 行里 → 密度极低，没有"占位式实现"的迹象。
- 测试：**481 个 `test_*.py`**，分 `tests/unit`（db/cron/gateway/agents/api/cli/i18n）与 `tests/integration`，带 `live` marker 隔离真实 LLM 调用。
- CI：`.github/workflows/ci.yml` 跑 **ubuntu-latest（:15-16）+ windows-latest（:46）**，另有 CodeQL（`codeql.yml`）、docker-publish、desktop、fnos 构建。**Windows 也进 CI**——这点很重要，说明它没假设只有 Linux。
- 契约测试即"改造阻力"：`tests/unit/db/test_db_pool.py:102,184,323,348,383` **写死 `assert v == 20`**（迁移版本）；i18n 要求 en/zh key 全等 + 前后端 `apiErrors` 同步。

### 4.2 运行环境核验（本次未实跑，如实标注）

| 项 | 核验结果 |
|---|---|
| **本机实跑** | ✅ **已实跑**（2026-10-08，Windows + Python 3.12.10 + uv，PyPI 走腾讯镜像）。结论：**装得上、起得来，但 `make all` 的 ship bar 在本机 Windows 上不成立**（详见 §4.4）。此前"未实跑"的保留意见已用实测替换。 |
| OS 绑定 | 跨平台（Linux/Windows/macOS 均支持），**不是** macOS-only。但两处 POSIX 依赖：① 文件牢笼靠 bubblewrap（`host_dirs.py:24,150` 的 denylist **Windows 下为空**）② systemd 服务安装（`infra/setup/service.py:1`） |
| 外部服务依赖 | 必需：**仅 1 个 LLM 端点**（任意 OpenAI 兼容，`db/repos/providers.py:84`，`api/routers/providers.py:330` 走标准 `GET /models`）。可选且默认不触发：IM 平台、SkillHub、edge-tts、tavily/brave 搜索、reCAPTCHA、COS/S3、Langfuse。**注意：这些默认不触发但会在内网报错刷屏**（`infra/connectors/catalog.py`、`infra/skills/skills_hub.py:1350,1466`、`infra/voice/adapters.py:259`、`infra/utils/search_probe.py`、`infra/auth/captcha/providers.py`） |
| 必需密钥 | LLM API Key（或本地 vLLM/Ollama 端点，`infra/utils/` 有 Ollama 支持且下载目录可配）；JWT/加密密钥**自动生成无需人工**；IM 通道凭据按需 |
| 安装链路 | ⚠️ **默认全走公网**：`scripts/install.sh:193` 从 astral.sh 取 uv、`:360` 调 sh.rustup.rs、`:18` 从 GitHub 取源码；`install.ps1:68/112` 同理；README 直链是腾讯云 COS（`README.md:192/198`）。有 `--mirror`（`install.sh:88`）可换内网 PyPI，但**没有"纯离线 wheel 目录"入口**。可直接复用的现成机制：`desktop/portable/vendor-wheels.sh:40`（`uv pip download` 打全量 wheels + standalone Python 离线 zip，飞牛 native 版即 ~200MB 自带依赖） |
| 断网启动 | ✅ 默认可断网启动（`bind_host=127.0.0.1`、无遥测、前端零 CDN、SQLite 零依赖） |

### 4.3 信创适配结论（针对你选的鲲鹏/海光）

| 目标 | 把握 | 依据 |
|---|---|---|
| **海光（x86_64）** | 高 | 常规 wheel 全覆盖 |
| **鲲鹏/飞腾（aarch64）** | 中高 | `uv.lock` 实测 cryptography / argon2-cffi-bindings / playwright / pillow / onnxruntime / numpy / aiohttp **均有 aarch64 wheel** |
| **龙芯 loongarch64** | ❌ 低 | `uv.lock` 中 loongarch64 **命中 0**，需全量源码编译（Rust + gcc），且 install.sh 的 glibc<2.28 兜底（`:332/534-545`）本身要联网 |
| **麒麟/统信自带 Python** | ⚠️ 必须自带解释器 | 这些系统常带 3.7–3.9，而 `pyproject.toml:11` 要求 `>=3.12` → 用 vendor-wheels + standalone Python 方案 |
| **国产 OS 反而加分** | ✅ | 麒麟/统信是 Linux → bubblewrap 文件牢笼可用，比 Windows 部署的隔离强度更好 |
| **达梦** | ❌ 大改 | 需重写 `RETURNING` / `ON CONFLICT` / `AUTOINCREMENT` / 大小写语义 |
| **人大金仓 / GaussDB** | ⚠️ 中改 | PG 内核，改动小；新增一个 Pool 即可（`db/pool.py:15` 已有 `?`→`%s` 转换） |
| **商标/品牌** | ⚠️ 要清 | MIT 不授权 "Octop / TencentCloud" 名称与 logo：`dashboard/src/assets/mascot.ts`、`Dockerfile:69` 的 `image.source=github.com/TencentCloud/orca` 等要替换 |

### 4.4 实测记录（Windows 11 / Python 3.12.10 / 2026-10-08）

命令链：`pip install uv` → `uv sync --extra dev` → `uv run octop --help` → `uv run octop init --admin-username admin --admin-password ***` → `uv run octop run --port 18088` → curl 探测 → `uv run pytest tests/unit -q -n 4`。`OCTOP_HOME` 全程指向临时目录，未触碰真实 `~/.octop`（该目录此前不存在）。

| 步骤 | 结果 |
|---|---|
| 依赖安装 `uv sync` | ✅ **43 秒**（腾讯 PyPI 镜像），含 playwright / onnxruntime / numpy / psycopg-binary / `octop-harness[all]` → **内网 mirror 场景的装机成本非常低** |
| `octop --help` | ✅ CLI 正常，子命令全部注册可用 |
| `octop init` | ⚠️ **半成功**：`config.json` / `octop.db` / `plugins` 已建出来，但向导崩在 `prompt_toolkit` → `NoConsoleScreenBufferError: Found xterm-256color, while expecting a Windows console`。**非 TTY / Git Bash / SSH / CI 场景下 `octop init` 不能用**（即使已传 `--admin-username` / `--admin-password` 仍会走到交互）。政务静默批量部署要绕开它——容器路径（`docker/docker-entrypoint.sh:58-62`，Linux）不受影响 |
| `octop run` 启动 | ✅ **12 秒**内 HTTP 端口就绪，启动过程无外网请求 |
| API 可达性 | ⚠️ 服务在跑，但 `POST /api/auth/login` 返回 `{"setup_required":true}` —— 首启向导未完成时 `api/middleware/` 会锁死业务路由；`/api/openapi.json` 在未登录且 `enable_api_docs=false`（默认）时取不到路由清单。**因此"完整对话链路"本次仍未验证**（还差一个可用模型端点） |
| unit 测试 | ❌ **39 failed / 3554 passed / 126 skipped（4 分 15 秒）** |

失败归类（均可本机复现，非猜测）：

| 失败簇 | 规模 | 根因 | 对政务二开的含义 |
|---|---|---|---|
| `tests/unit/db/test_db_pool.py` 迁移 / schema repair 重建（`test_v7_sqlite_sql_upgrades_legacy_text_pks`、`test_schema_v10_without_projection_tables_is_repaired`、`test_pre_squash_schema_version_clamped_and_knowledge_tables_filled` 等） | ~15 | 复现时伴随 `PytestUnhandledThreadExceptionWarning`，属 Windows 下 SQLite 连接池线程 / rebuild 路径的行为差异 | ⚠️ **最需要警惕的一簇**——它们恰好是你二开加字段、写迁移、适配国产库时**每天要碰的路径**。信创机器上跑测试要预留排障成本 |
| `tests/unit/knowledge/*` + `api/test_knowledge_bases.py`（embedding provider / capability gate） | ~11 | `infra/agents/providers/onnx_service.py:357` 处**解释器直接崩溃**（Fatal Python error + native 栈回溯，调用经 `infra/knowledge/gate.py:76`）→ 本机 onnxruntime 一加载就炸，疑缺 VC++ 运行库 | 本地 ONNX embedding 路线在目标环境**必须单独验**。建议优先走"远程 OpenAI 兼容 embedding"（国产模型服务一般自带 embedding），绕开这个雷 |
| `tests/unit/test_vendor_wheels_argv.py`（4 个平台参数化） | 4 | 纯 Windows-only 测试缺陷；**上游当天已开分支修**：`test/posix-only-vendor-wheels-argv`（2026-10-08 05:51） | 双面信号：他们清楚跨平台测试有洞并在系统性补（`AGENTS.md` §7 整套规则即为此），但也说明 **Windows 侧测试基线当下是脏的** |

**推断与推论**：上游 `test-windows` job 跑的是 `make install`（= 纯 `uv sync`，`Makefile:306`，**不含 `local-embedding` / `knowledge-ocr` extra**）+ `make test`（`ci.yml:46-66`），环境与本机基本一致，却出现了本机 39 失败 → 要么 GitHub runner 与真实 Windows 桌面/服务器行为不同，要么 `main` 当下就是脏的。**对你们的行动项：拿到代码后第一件事是在目标信创机器上重跑 `make test` 并以此为准，不要假设"CI 绿 = 我的机器绿"。**

**意外发现（对内网私服很有用，也是 fork 陷阱）**：设了 `UV_DEFAULT_INDEX=<内网镜像>` 之后，`uv sync` **会就地重写 `uv.lock`**——3004 行变更，把所有 `source registry` 与 sdist/wheel URL 从 `pypi.org` / `files.pythonhosted.org` 换成镜像域名，同时把 `revision = 3` 抬到 `5` 并丢掉 `size` / `upload-time` 字段（我用 `git checkout -- uv.lock` 复原了）。两个含义：① 好消息——**换内网 PyPI 不需要手工改锁文件**，一条环境变量就能产出可离线解析的 lock；② 坏消息——**你们必须提前定下提交策略**（建议：跟踪上游时永不提交被内网镜像重写的 lock，改用 `--default-index` 加 `--frozen` 安装，或维护一份独立的 `uv.lock.internal`），否则每次同步都会产生几千行噪声 diff，把 code review 和上游合并彻底搞乱。

---

## 5. 落地路径（按投入从低到高）

你选了"整体 fork 深度改造（3–10 人）"，但我建议**不要一上来就 fork 运行时**——理由和路线如下。

| 方式 | 投入 | 你能得到什么 | 前置条件 / 风险 |
|---|---|---|---|
| **0. 内网离线 PoC** | 1–2 周 / 1 人 | 证明"断网装得上、起得来、能对话"。产出内网离线包 + 部署手册，这是后续所有路线的地基 | 拿 `desktop/portable/vendor-wheels.sh` 打全量 wheel + standalone Python；一个国产模型的 OpenAI 兼容端点。**已实测部分**：Windows 上 `uv sync` 43 秒装完（含 `octop-harness[all]`/playwright/onnxruntime），`octop run` 12 秒起服务且无外网请求。**未验证**：真断网环境、国产模型下的完整对话与工具调用链路、`octop init` 在无 TTY 时的替代部署路径（实测它在非 TTY 下会崩，见 §4.4） |
| **1. 不改架构，只做「硬化 + 外挂」** | 1–2 月 / 2–3 人 | 能上小范围试点的对内办公助手。清单：`hitl.enabled=True`、`tool_guard.mode` 从 warn 改强制、YAML 规则换成你们的白名单、关掉全部外网 catalog、把 edge-tts 从核心依赖剔除、LDAP/AD 对接、前面挂 nginx 做 IP 白名单 + QPS 限流（**Octop 自身没有**）、容器加非 root `USER`、审计导出报表 | 几乎不动核心代码，政务定制走**插件（tool/skill/hook）+ 自定义 MCP（内网系统一律用 IP 或 `.internal`）+ 460 路由 HTTP**。这是投入产出比最高的一档 |
| **2. Fork 主干，改 5 个文件面 + 自建编排** | 3–6 月 / 3–6 人 | 真正的"政务底座 1.0"：部门/分级数据权限、门户直连鉴权、条款级政策检索 | 核心改动集中在这几处：`api/app.py`（自有路由挂载，`build_app` 无注入参数）、`api/middleware/`（新增 API Key/服务账号/签名）、`infra/users/permissions.py`（模块级 → 部门/分级 ACL）、`infra/knowledge/{chunk,index,citations}.py`（结构化条款分块 + ANN/混合检索 + 条款级引用）、`infra/connectors/catalog.py`（政务系统目录）。**流程编排建议做成独立服务**（状态机在你们侧，Octop 只当"一次对话 + 一个工具"），因为 Octop 完全没有 DAG |
| **3. 连 `octop-harness` / `octop-gateway` 一起 fork 并 vendor** | 6 月+ / 6–10 人 | 运行时级管控：工具白名单在引擎侧强制、租户级配额、内容审核插在模型调用前、新 IM 通道（政务微信/钉钉专有版）、去掉 `deepagents`/langgraph 依赖的可能 | **代价：你永久承接 40K+ 行运行时和上游三个包的合并**。本仓库 87 文件 110 处 import harness，版本要求 `>=1.0.1` 无上界（`pyproject.toml:24`）。只有当合规要求必须做到"引擎级不可绕过"时才值得 |

**推荐**：**0 → 1 → 2，把 3 作为按需触发的分支**。判断依据：460 个 HTTP 路由 + 自定义 MCP + 插件 hook 已经足够把政务业务包在外面，而 harness 依赖的 `deepagents`/LangGraph 恰是演进最快的一层（harness 3 个月内 30+ commits 且刚升 1.0.1），fork 它等于把每次模型侧升级都变成自己的维护负债。真正"必须在引擎侧做"的只有两件事：工具白名单强制、内容审核前置——前者可通过把 `mode` 改 enforce + 外部规则目录（`rule_guardian.py:93-160` 支持）缓解，后者可试 `hook`（`before_model`/`after_model`，`plugins/demo-turn-logger/main.py:34-59`）——**先验证 hook 够不够，再决定要不要 fork harness。**

**跟上游的工程约定**（fork 前必须建好）：锁 tag（当前 `v1.0.2b6`）+ patch 队列（`git format-patch`）+ `octop-harness`/`octop-gateway`/`octop-memory` **全部 pin 精确版本**并镜像到内网 PyPI；`make all`（format-all + lint + `mypy --strict` + pytest）与 pre-commit 闸门（`Makefile:201,222-224,241`）照抄；迁移版本断言（`v == 20`）和 i18n key 全等测试纳入你们自己的 CI。

---

## 6. 风险与边界（容易被想当然的地方）

1. **"Octop 是 Agent 框架"——不是。** 它是控制面 + 门户 + IM 接入；LLM 循环、工具执行、审批拦截、脱敏、shell 防护**全在外部包 `octop-harness`**（我拆包实测 204 py / 40,522 行，含 `security/tool_guard/`、`teams/`、`mcp.py`、`middleware/pii.py`）。改 Octop 改不到 Agent 行为本身。
2. **"开源 = 能直接私有化交付"——不是。** 装机链路默认打 astral.sh / rustup / GitHub / 腾讯云 COS，没有纯离线 wheel 入口；离线包要你们自己用现成的 vendor-wheels 机制做。
3. **"README 说的安全能力开箱即用"——不是。** 审批默认关（`policy_store.py:21`）、命令防护默认只告警（`:22`）。默认状态下 Agent 可直接执行含 `rm`/`mv` 的命令而不被拦。
4. **"多用户 = 部门隔离"——不是。** 共享是**全局布尔位**（`agents.is_shared` / `knowledge.shared`），且共享 agent 的 workspace 读/下载非 owner 也能访问；权限表是模块级平铺，没有部门/职级/数据分级维度。这是对内政务场景**最需要重做的一块**。
5. **"知识库能答政策文件"——现状不能达政务标准。** 800 字符定窗滑切 + 全表暴力余弦 + **无 BM25/无 rerank** + 引用只到文件级 + 硬配额 20 库/100 篇。政策条款问答会出"引用不到第几条"的合规问题。
6. **"有 AgentTeams 就能编排审批流"——不能。** 它是 LLM 自主调度，官方自己标 Beta；**全库没有任何 DAG/状态机/会签**实现。
7. **审批态在进程内存**（`infra/gateway/hitl/store.py:12,33`，TTL 30 min、process-local）→ 重启丢 pending、不能多 worker 横向扩。加上"单进程无队列"的架构设定，**政务要支撑几千公务员并发，扩容方案得自己设计**。
8. **无 MFA、无令牌吊销、JWT 密钥与密文同库存放且文档描述与代码不符**（`docs/configuration.md:16/235` vs `infra/server.py:676-678`）→ 等保/密评典型扣分点。
9. **无 API Key / 服务账号鉴权**，第三方门户只能"模拟登录"；WS 还把 token 放在 **query string**（`chat/ws.py:33-48`）→ 会进 nginx 访问日志。另有 `internal_mcp` 同样走 query token（`internal_mcp.py:55,63`）、`connectors/builder.py:75` 对内网 MCP 用了 **`verify=False`**（密评要改）。
10. **"装了 Docker 就隔离了"——看人。** 官方镜像**全程 root 无 `USER` 指令**；Docker 沙箱的隔离强度取决于 harness 的 `sandbox_scope`/`sandbox_prefix`（`docs/agent-backend-file-io.md` §13），不是本仓库保证的。
11. **版本仍是 beta（`1.0.2b6`）、仓库只有 3 个月、698 个 open issue、主贡献者 1 人占 340/641 commits**，`SECURITY.md` 的联络方式是**个人 gmail**、older releases 只 "best effort"，无 CLA / 无 NOTICE / 无漏洞 SLA。**政府采购尽调与长期维护承诺这块会被问住。**
12. **许可证不是纯风险但有尾巴**：MIT 允许闭源改写但须保留版权全文；`edge-tts` 是**核心依赖**（`pyproject.toml:30`，上游认知为 GPL-3.0 且调用微软服务 → 内网必失效），`ldap3` LGPL；`uv.lock` 不带 license 字段，**必须在内网逐包核实后出一份第三方许可清单**。
13. **实跑已做，但只跑到"起服务"这一步**（见 §4.4）：安装、启动、API 端口就绪均已实测通过；**含工具调用的完整对话链路未验证**（缺可用模型端点 + 首启向导在非 TTY 下走不完）。另外本机 unit 套件 **39 failed / 3554 passed**，说明"上游 CI 绿"不等于"你的机器绿"。

---

## 7. 值得直接搬走的工程实践

不管你最终 fork 与否，这六条建议照搬到政务底座项目：

1. **`AGENTS.md` 式的模块边界契约**（§5 的 "May import / Must NOT import" 表 + 硬禁清单）。怎么搬：把"业务层不得 import 传输层""repos 不得 import 非 DB 包"写成你们团队的同格式文件，并把边界做成可测的 import 检查。
2. **双迁移对 + 版本断言**（`00N_*.sql` / `00N_*.pg.sql` + `test_db_pool.py` 断言 `v == 20`）。怎么搬：这是支持"SQLite 开发 / 国产库生产"的最小可行办法；换成 `00N_*.pg.sql` + `00N_*.dm.sql`，断言测试保留——**它把"忘了写国产库迁移"变成 CI 失败，而不是上线事故**。
3. **i18n key 全等测试**（`tests/unit/i18n/` 要求后端 en/zh 树一致 + 前端 `apiErrors` 同步）。怎么搬：政务多语言不是刚需，但**"文案不许硬编码在代码里"这条纪律**用它这种机器化方式落地，比约定有效。
4. **契约测试前置到 pre-commit（`make all` = format + lint + `mypy --strict` + pytest）**。怎么搬：政务项目交付前要有闸口，mypy --strict + 双平台 CI 这个组合的实际成本远低于收益。
5. **`BackendWorkspace` 抽象**（本地/Docker/PG/COS/S3 统一收口，业务层不感知 backend 类型）。怎么搬：政务"文件到底放本地盘、NAS 还是对象存储"一定变，这层抽象值得原样复用；对应的 AGENTS.md 硬规"不得用 `Path.write_text` 绕过 workspace"值得抄。
6. **每库一个 sidecar SQLite 向量索引 + 纯 stdlib 余弦**（`knowledge/index.py`）。**思路**值得学：在不引入 pgvector/向量数据库的前提下把向量检索跑起来，非常适合信创环境；**实现**要换掉（暴力扫描 + 定窗分块过不了你们的数据量与引用粒度要求）。

同类对比（一句话）：与 Dify/FastGPT/最大 AI 类低代码平台相比，Octop 的差异点是**"自托管单进程 + 多用户多 Agent + IM/桌面/CLI 全覆盖"的产品化程度**，而不是编排能力——编排和合规恰好是政务侧需要自己补的。

---

## 8. 建议下一轮单独开题的问题

1. **信创实机验证（下一件事）**：Windows 侧的"装得上、起得来"我已实测通过（§4.4），剩下要验的是 **麒麟/统信 + 鲲鹏/海光 + 离线包** 这条真实交付路径，以及 `make test` 在目标机上的失败面——本机已暴露的 39 个失败里，**迁移/repair 那一簇（~15 个）正好落在你们二开要天天碰的路径上**，必须优先定位是 Windows 平台问题还是代码问题。
2. **国产模型的 function-calling 兼容性**：Octop 的工具体系依赖模型侧 tool calling 质量；国产模型（DeepSeek/Qwen/文心私有版）与 `deepagents` 提示模板的适配度需要实测，**这是 Agent 成败的地基，比任何架构问题都优先**。
3. **harness 的 `hook`（`before_model`/`after_model`）能否承载"内容安全审核"和"字段级脱敏"** —— 决定你们要不要走方式 3（fork 运行时）。
4. **多实例分片方案**：单进程 + 进程内审批态，几千公务员并发怎么切（按部门多实例？改造成 Redis 态？）需要一次专项设计。
5. **第三方许可与供应链尽调**：在内网 PyPI 镜像上逐包生成许可证清单（重点 `edge-tts`、`ldap3`、`lark-oapi`、各云 SDK），并评估 `deepagents`/LangGraph 的上游约束。
6. **上游治理风险**：3 个月、1.0.x beta、单主维护者 + 个人 gmail 安全联系人——需要决定是否要求"源码托管/共建协议"，或直接按永久 fork 做预算。
