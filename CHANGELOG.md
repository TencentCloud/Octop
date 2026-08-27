# Changelog

本文件记录项目的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本号遵循 [语义化版本规范](https://semver.org/spec/v2.0.0.html)。

## [Unreleased]

### 新增

- 自定义 MCP 连接器支持 OAuth：从 MCP URL 自动发现授权端点，统一 `POST /connectors/oauth/start` 启动授权；保存后可探测、一键授权，Bearer 注入 harness spec；Custom Connectors UI 支持启用与「对话默认选中」分离、保存后可选探测

### 变更

- Docker / FnOS 镜像对外统一为 `ghcr.io/tencentcloud/octop`（仍同步推送 Docker Hub；移除 vanilla 镜像标签）
- FnOS FPK 在 Release 成功后自动构建：复用 GHCR 镜像与 Release wheel，不再重复编镜像
- 正式发版时 Auto Tag 同步触发桌面客户端打包，产物挂到同一 `v*` GitHub Release（不再对任意分支 push 跑六平台矩阵）
- 修复 Auto Tag → `workflow_dispatch` 时 Docker 镜像可能只有 `:latest`、缺少 `:{version}` 的问题（显式从 tag 解析版本）

### 修复

- 合并冲突的双份 schema v10 迁移：投影表不再被 `010_kb_max_documents` 抢先抬版本而跳过；启动时幂等补建 `thread_messages` / `thread_history_projection`
- Windows CI：`test_create_keeps_user_workspace_dir` 等真实 Harness 单测关闭 memory，避免 GC 线程与 `close()` 争用 SQLite 触发 access violation
- 更新腾讯云通用 Token Plan 的七个规范模型，新增企业版（中国站）与 Hy Token Plan 预设，并让企业版 DeepSeek 沿用嵌套 thinking effort 适配

## [0.9.29] - 2026-08-27

### 修复

- 长会话卡死：聊天历史改为独立投影分页加载，并支持后台迁移旧会话（不再同步扫 checkpoint）

### 变更

- 依赖：`orcakit-harness-agent[all]>=0.9.27`、`harness-memory>=0.9.7`、`harness-browser>=0.7.6`（自动 full VACUUM 关闭，空闲维护只走 lifecycle GC + incremental `nudge_vacuum`）

## [0.9.28] - 2026-08-26

### 修复

- 无更新权限时隐藏检查更新入口
- `/compact` 兼容 `.octop/conversation_history/` 卸载路径
- FnOS 镜像改为 Docker Hub `jubaoliang/octop`

### 新增

- 基层医生学习助手增加普通医学问答快路径、国内专业学会/专科分会与国际指南精确路由，并完善受控信源降级和检索预算。

## [0.9.27] - 2026-08-26

### 新增

- 内置插件随包装分发（默认关闭，卸载后升级不重建）
- 可配置上传上限（`max_upload_mb` / `OCTOP_MAX_UPLOAD_MB`，默认 100MB）
- Dashboard 推送通知（定时任务与主动关怀 toast）
- 聊天音视频附件预览播放，并扩展 inbound 附件 MIME
- 火山方舟 Seedream / Seedance 生成模型配置、测试与结果展示
- 连接器：Ardot、滴答清单；远程 MCP OAuth 改为 catalog 驱动
- 单工具开关热更新与插件工具目录
- ACP 内置 Runner：Kimi Code、Cursor CLI、Pi
- 知识库文件夹重命名
- ONNX 模型下载竞速 Hugging Face 与 hf-mirror
- 远程手机 ADB shell（旋转与分屏布局）
- FnOS NAS 应用打包（Docker / native `.fpk`）
- 专家模板扩充（通用、Karpathy、临床来源策略）
- 中文子智能体约 49 个（HR / 法务 / 供应链）
- Dashboard 剪贴板回退与聊天 UI 打磨

### 修复

- 知识库文件夹操作按钮误开文件夹
- 工具预期失败不再误报为 `stream_error`
- 连接器 OAuth 公网回调 / HTTPS / 自动保存；npm 不可写时回退用户级 prefix
- SSO ID token issuer 校验
- Dashboard：SW 激活后再 reload、Firefox 无限刷新、选择器 popover、文案全球化
- 浏览器 runtime 目录在 Windows 上可写探测

### 变更

- FnOS 打包拆分为 `docker/` 与 `native/`

## [0.9.26] - 2026-08-23

### 新增

- 远程手机（实验性）：安装时探测主机移动能力（`capabilities.mobile`，物理机 / Redroid / KVM）；能力开启后开放 `GET /api/settings/capabilities` 与 `/api/mobile/*`。控制台「远程手机」支持 adb H.264/JPEG 推流、触控、画质预设、设备信息与 AI 助手面板；智能体移动工具绑定当前远程手机会话
- 控制台布局支持经典 / 极简模式，聊天记录统一承载；用户可选填邮箱（邀请 / 登录）；知识库支持应用内编辑 markdown / txt；远程桌面与远程手机合并为统一控制入口

### 修复

- 邀请链接统一为 `/invite?code=`，修复邀请页居中与移动端在 overflow-hidden 壳下的滚动；启动前显示 logo 加载动画；设置页邮箱输入图标对齐；移除聊天坞中的远程手机入口
- 加固 dashboard 鉴权与请求层（setup 锁定 503、401 刷新）、登录页与 AuthGuard 体验；按服务器能力门控移动端功能；远程控制中枢页签文案缩短为「服务器 / 手机」

## [0.9.25] - 2026-08-21

### 新增

- Token 计量新增缓存命中支持：按模型调用累计未缓存输入、缓存读取、缓存写入、推理 Token 与模型调用次数；用量页和消息气泡展示缓存命中数据。
- 编辑专家抽屉可修改标题语（欢迎语），与创建时同一字段，写入智能体实例而非仅页面配置
- 专家支持上传自定义头像，写入工作区 `.octop/avatar.png`（或 jpg/webp/gif）并通过 `agents.icon_url` 展示；发布快照会带上头像，安装后自动绑定。未设置时仍用配色 + Lucide 图标
- 实例化专家的欢迎语改为单一 `welcome_message` 字段（用户自填，不再分中英）；专家模板仍保留双语欢迎词
- 智能体状态接口返回 `memory_maintenance`（queued / pruning / compacting）。聊天页显示阶段进度条，整理本库时暂停发送；专家卡片显示「整理记忆」标签。
- 聊天页：文件工具卡片显示「编辑了 N 个文件」（不含截图）；文件面板标题改为「文件变更」。会话 `artifacts` 由 Octop 工具中间件在写文件 / 发文件 / 桌面截图成功后写入，切换会话后仍可在文件变更中查看。路径优先取工具 args，仅在 args 没有 path 时才扫结果文本。专家选择器「共享」标记与名称同一行。右侧增加工作区入口；工作区目录树支持将文件拖到其他文件夹。
- 知识库、技能包、已发布专家改为整数自增 `id` + 对外字符串 ID（`knowledge_base_id` / `skill_package_id` / `published_expert_id`；文档用 `kb_id` 关联）。`agents` 仍用字符串引用技能包与已发布专家。知识库文档支持文件夹路径；分片大小等仍存实例 `settings`。删除未使用的 `knowledge_base_members`。上述库变更与专家资料列、会话 artifacts、实例欢迎语单字段一并作为 schema v7。
- 对话检索结果附带知识库引用标记；聊天页在回答下方展示可点击的来源文档（跳转知识库页）

### 修复

- 技能：修复编辑已导入技能并保存后，技能内其余文件与文件夹（README.md、references/ 等）被整体清除的问题——内容编辑（仅 SKILL.md）现原地覆盖清单文件、保留全部同级文件；携带完整 `files` 载荷的更新仍整目录替换（与覆盖重装语义一致）
- Harness usage 事件按稳定调用 ID 去重，避免流重放重复计费；上下文环保留路由模型的真实窗口上限，并将构成拆分明确显示为近似估算。
- Admin 环境变量未进入正在运行的 Agent：本地 shell 默认不继承进程 env，Docker exec 也不传 env，工作区 `.env` 只落盘不注入。现本地 shell 每次 execute 继承当前进程环境（含 `~/.octop/env`）并 overlay 工作区 `.env`；Docker 热读全局文件 + 工作区 `.env` + 最小 PATH（不含完整宿主机环境）。保存 Admin 列表会从进程环境删除已去掉的键；仅搜索类 key 变化时后台 reload Agent。MCP stdio 只注入 SDK 安全子集 + 全局/连接器 env，不再灌入整份 `os.environ`。
- Token 用量账本每轮只记下最后一次模型调用，工具循环中前面若干次调用被丢弃，页面合计会远低于聊天里看到的用量；现按该轮全部 AI 调用的 `usage_metadata` 累加，以 `state_snapshot` 为权威终值（snapshot 之后的增量不再相加），畸形 usage 字段跳过以免打断对话
- 插件工具使用中文等非 ASCII 名称时 LLM 调用失败：主流 API 要求工具名匹配 `^[a-zA-Z0-9_-]{1,64}$`，现自动将非法名称转写为合法拼音名（`pypinyin` 缺失时退回下划线替换），冲突追加 `_2`/`_3` 后缀，并在工具描述前缀 `[原名: …]` 保留原名映射；`config_json.plugins` 配置键与插件内部仍使用原始名称，路由不受影响
- 修复聊天页在"生成中"时于输入框持续打字导致消息列表上下轻微抖动的问题：输入框高度测量改为在离屏克隆节点上进行，不再瞬态改变页面布局
- 工作区读写在 harness 后台重建窗口（DB 仍为 running）回退到 `workspace_for_agent`，避免误报 `AGENT_NOT_RUNNING`
- 聊天页上下文占用环：旧会话没有分段快照时，从消息上已有的 `usage_metadata` / `response_metadata.token_usage` 回填已用量；相对 1M 级窗口不再把真实占用四舍五入成 0%
- 专家抽屉保存页面配置时合并写入 `manifest.json`：保留其它字段与另一语言欢迎语；加载未完成或未改动时不写文件
- 修复个性化「通道」面板在页面放大后不出现纵向滚动条、被挤出的通道卡片无法查看的问题：工具栏固定、卡片网格改为内部滚动区（与技能面板一致），移动端仍整页滚动

## [0.9.24] - 2026-08-15

### 新增
- 知识库：新增知识库与对话检索，支持本地 ONNX 向量嵌入模型运行
- 认证：新增 OpenID Connect（OIDC）单点登录
- 权限：新增按用户模块权限（RBAC）及管理员绕过
- 专家：支持将工作区快照发布为可安装模板（专家市场）
- 智能体：支持将智能体共享给其他用户
- 技能：新增对话式技能管理器（SkillHub），并兼容 Windows
- 备份：新增自动定时系统备份
- 频道：新增 final-only 仅终稿回复模式
- 线程：支持从 AI 回复处分叉会话（fork）
- 体验：HITL 工具选择器、运行时按需安装、KB/技能 UX 优化；对话与镜像等界面打磨；知识嵌入初始化流程加固

### 修复
- 媒体/预览白名单补充音频 MIME 类型
- 修正 ONNX 下载检测在未安装 fastembed 时的误判
- 加固更新状态缓存与存储处理
- 预提交门控：修复 staged 变更检测，避免 testmon 门控误报为绿

### 变更
- 升级 harness-browser 依赖至 0.7.5
- 数据库 schema 收敛为 v5
- 备份恢复面板图标更新为 CalendarClock；对话/镜像等界面打磨

## [0.9.23] - 2026-08-13

### 修复
- 取消首次引导时删除 `octop-login.txt` 引导密码文件的逻辑，避免引导密码意外丢失
- 修复安装脚本版本显示问题，并将安装输出调整为英文

### 新增

- Octop-owned built-in `skill-manager` for conversational Skill lifecycle
  management from uploaded files, archives, Git/GitHub or web URLs, and
  SkillHub. It is seeded into every agent instance without modifying
  harness-agent and installs user Skills only under that agent's `skills/`.

## [0.9.22] - 2026-08-11

### 新增
- 专家工作区支持 `.docx` 在线编辑：以 Markdown 在 Monaco 中打开/保存，保存时转回 docx 覆盖原文件（标题/加粗/斜体/列表/表格保留，复杂格式简化）；工作区新建的 `.docx` 即初始化为合法文档包，预览/编辑立即可用。基于可扩展注册表，新增可编辑后缀只需注册一个后端转换器类 + 前端注册表一行

### 变更
- 依赖新增 `python-docx==1.2.0`（含 `lxml`），用于工作区 `.docx` 的 Markdown 往返转换

### 修复
- 仪表盘发版后或长时间未打开时白屏：Service Worker 不再 Cache-First 钉死旧 `index.html`；hashed 资源改为 CacheFirst；入口脚本失败时清除 SW 缓存并自动刷新一次 (#236)

### 安全
- 仪表盘 SPA 静态回退路由加固：在拼接路径前显式拒绝绝对路径与 `..` 父目录引用，并保留最终 `relative_to` 校验，杜绝路径穿越读取 dashboard 目录之外的文件（修复 CodeQL 标记的 Uncontrolled data used in path expression）

## [0.9.21] - 2026-08-11

### 新增
- 插件管理页支持从本地 ZIP 上传安装插件，可选覆盖已安装的同名插件，无需先把插件托管到 HTTP 直链
- Docker 沙箱 backend（agent `config.backend.type=docker` 或存储 `kind=docker`）；Admin Docker 卡片、本机 Docker 探测/安装；详见 [docs/agent-backend-file-io.md](docs/agent-backend-file-io.md) §13
- 强制密码策略并优化账户与子代理（subagent）使用体验
- 浏览器 HITL 流式交互与网关抢占能力
- 新增每用户模型与推理（reasoning）偏好设置

### 变更
- 依赖 `orcakit-harness-agent[all]>=0.9.20`；FilesystemGuard / ModelSettings 由 harness 自动挂载（Octop 仅保留 BinaryReadGuard 与 runtime_limits）
- 专家 `workspace_dir`：创建时写入 `config_json.workspace_dir`（默认 `{OCTOP_HOME}/agents/<id>/`），所有 backend 共用；Docker 在容器内镜像同名路径为专家工作区，宿主同路径放 sessions/memory/checkpoints
- Docker：`sandbox_scope`（agent/user/fixed）+ `sandbox_prefix`（默认 `octop_sandbox`）；删专家不删容器；专家工作区在 running 时可预览；Admin 存储 `previewable` 仅控制浏览（默认仅 fixed）；探测用 test 沙箱做真实读写
- 删除被专家 `named` 引用的存储后端时返回 `STORAGE_BACKEND_REFERENCED` 并列出引用专家
- 将 IM 频道定时任务从 ACE 迁移至 Octop cron

### 修复
- 超大图片不再降级为附件路径提示：超过视觉嵌入上限（2 MB）的图片由 Pillow 压缩缩放至最长边 1568px 后仍以内联图片嵌入请求（保留 EXIF 方向与透明通道，仅当压缩失败时才回退为路径提示），视觉模型自动升级随之生效 (#219)
- 保留技能 ZIP 导入时的空目录与根级技能的子文件夹
- 修复移动端个人设置抽屉，并恢复玫瑰色主题配色

## [0.9.20] - 2026-08-09

### 新增
- QQ 频道二维码扫码绑定，支持群聊上下文（仪表盘频道抽屉 + `octop channel` CLI）(#160)
- 语音接入小米 MiMo STT / TTS 供应商（`mimo-v2.5-asr` / `mimo-v2.5-tts`），设置页可选择计费端点与 9 种预置音色，TTS 标注限免 (#186)
- 仪表盘自定义品牌配色：8 套调色板（玫瑰 / 科技 / 靛蓝 / 青绿 / 紫罗兰 / 翠绿 / 琥珀 / 石墨），与浅色 / 深色模式正交且本地持久化

### 修复
- Windows 下新建 agent 时，本地后端 `root_dir:"/"` 被解析为当前盘根目录，导致读取工作区（通常位于另一盘符）时抛 `Path ... outside root directory`；现在后端规格解析会在 Windows 上将主机根 `/` 的 `root_dir` 改写为工作区路径（保留原 `type` 等字段）
- 删除专家时同步清理 `~/.octop/agents/<id>/` 工作区目录（rmtree 移出事件循环执行）；清理失败不阻断数据库删除；仪表盘与 CLI 删除确认提示工作区将永久删除且不可恢复
- 乐享连接器 MCP URL 补充 `preset=meta` 参数并简化快捷授权链接 (#213)
- 专家卡片的编辑 / 删除按钮默认可见，不再仅在悬停时显示 (#187, #193)
- 登录页滑动验证通过后，提示文案居中显示在滑块左侧的可见区域 (#185)

### 变更
- 企业微信客户群二维码与文档有效期更新至 2026-08-16

## [0.9.19] - 2026-08-05

### 新增
- 登录页滑动验证控件；侧栏与 Agent 资料抽屉 UI 优化 (#170)
- 聊天历史 API 返回 `turn_active`，重连客户端可 re-subscribe WebSocket 恢复流式输出 (#168, #157)
- Workbench 与聊天 Dock 共用同一 terminal 会话；旧式硬切会话标题迁移为带省略号的裁剪标题 (#157)
- 局部 `root_dir` 下 Linux bubblewrap execute jail（`POST /api/filesystem/ensure-bwrap`、仪表盘 root 目录树 mkdir/rename）(#167)
- 虚拟工作区路径 I/O：host 绝对路径经 `file://` 与 `BackendWorkspace` failback 对齐 (#167)
- 高级设置「更新」页提供按安装方式升级说明与一键检查升级双栏布局；HTTPS 页优化签发状态与预检展示 (#143)

### 修复
- 401 会话过期时通过 React Router 跳转登录，避免整页 reload 导致 lazy chunk 白屏 (#169)

### 变更
- `make all` 先执行前后端 `format-all`（Ruff + Prettier）；pre-commit 在 format 后回写已暂存文件并构建 dashboard (#143)
- harness runtime 诊断日志写入 `~/.octop/logs`（与 `octop.log` 并排），不再落到各 agent workspace 的 `logs/`；行内带 `[agent=…]`
- 依赖 `orcakit-harness-agent>=0.9.19`、`harness-gateway>=0.9.1`（scoped root execute jail）
- 企业微信客户群二维码与文档有效期更新至 2026-08-08 (#149)

## [0.9.18] - 2026-08-02

### 新增
- 聊天 Dock 支持可关闭的文件列表 / 预览 / 浏览器标签页，以及 PR 风格路径树与路径去重；账户气泡与侧栏交互打磨 (#130)
- 内置示例插件（greeting / toolkit / turn-logger）与中英文插件说明文档
- 搜索设置页显性展示当前搜索源：未配置第三方服务时提示内置搜索，配置后展示实际服务 (#109)

### 修复
- 已停止或禁用的专家统一返回 `AGENT_NOT_RUNNING`（不再误报未找到）；管理员 Token Usage 支持按用户筛选；聊天会话频道图标与创建用户角色选择优化 (#137)
- 强化插件安装错误诊断与自定义 MCP 校验；网关流式错误支持本地化
- 聊天流式错误在界面可见；Token Usage / Memory 图表与空状态展示优化；弹层 Dock 几何与全屏行为修正

### 变更
- 设置、连接器、插件管理与管理用户等页面统一到共用仪表盘布局语言
- Docker / 安装文档中的国内加速镜像示例改为腾讯云镜像 (#116)
- 依赖抬升：`orcakit-harness-agent` ≥0.9.18、`harness-memory` ≥0.9.5；对齐 Python 3.12 目标与依赖刷新 (#118)

## [0.9.17] - 2026-07-31

### 新增
- 全局技能包：实例级可复用技能集合，支持挂载到专家、从 SkillHub 导入技能集，以及本地 ZIP / URL 导入技能
- 个性化页整合技能 / 子专家 / 频道 / MBTI / 记忆；技能包管理页支持移动端列表详情切换
- 搜索设置页显性展示当前搜索源：未配置第三方服务时提示使用内置搜索（免 API Key，不保证稳定），配置后展示实际使用的服务 (#109)

### 变更
- 技能相关域逻辑迁至 `infra/skills/`；数据库迁移合并为 schema v2（cron MCP + skill_packages 含图标）(#108)
- 备份/恢复纳入 `skill-packages/` 目录，恢复前清空避免残留 (#108)
- 统一聊天生成中 / 滚动辅助逻辑；antd message 经 App.useApp 绑定，支持主题感知 toast (#119)

### 修复
- Memory 原始事件列表的时间戳按服务器时区展示，与其余 Memory 页保持一致 (#110)

### 修复
- 记忆提取 / 提升等 harness 内部辅助 LLM 默认跟随全局偏好模型（此前切换全局模型后仍回退到首个可用模型）(#110)

## [0.9.16] - 2026-07-29

### 新增
- 统一自定义 / 预设 / 配置提供商弹窗的模型编辑流程，支持拉取 OpenAI 兼容远程模型列表，并仅在显式保存时落库 (#91)
- 支持从 LightClaw 迁移导入（备份快照与系统归档兼容，含外键约束处理）(#58)

### 修复
- 修复自定义提供商弹窗 TypeScript 错误（未使用导入 / 可选 `input`），恢复 release 构建
- 从 GitHub URL 导入技能时保留完整技能目录（含引用文件与脚本），并加固归档下载的分支名、文件数与体积限制 (#92)
- 浏览器配置不再对系统路径执行 chmod，改为使用共享目录 `~/.octop/browser-profiles` (#87)
- 部署后静态资源哈希不匹配导致白屏时，自动软刷新一次并防止重载死循环 (#88)
- 修正网易邮箱 IMAP 主机解析，并在登录前发送 IMAP ID；同时加固 QQ / 网易 / Gmail 邮件主机预设与探测 (#89)

### 变更
- 最低依赖 `orcakit-harness-agent` 提升至 ≥0.9.16
- README 补充中长期 Roadmap / 规划说明
- 新增可选 `.githooks` 提交前检查（`make install-hooks`）

## [0.9.15] - 2026-07-27

### 修复
- 加固聊天导航：切换专家时避免残留旧会话 URL，并稳定流式 Markdown 渲染
- 优化 Memory / Token Usage 页面布局，消除嵌套滚动并改善信息密度
- 补充企业微信客户群二维码相关文档说明

## [0.9.14] - 2026-07-25

### 新增
- 控制平面支持 PostgreSQL 双后端（统一 DatabasePool、并行 PG 迁移、安装向导选择/绑定、pg_dump 备份；PostgreSQL 下记忆默认复用控制平面 DSN）(#60)
- SkillHub 改为走 HTTP API，支持来源中立的技能包安装与搜索 (#55)
- 远程浏览器/桌面支持真实拖拽（转发 CDP 指针事件），并共享推流连接中指示 (#50)
- 聊天界面布局与交互打磨：历史侧栏、消息队列、自动滚动与欢迎页等体验优化 (#66, #69, #70)

### 修复
- 修复 macOS/Linux 上 Agent 上下文历史写入主机根目录的问题：依赖 harness-agent≥0.9.12 将 deepagents artifacts 落到 Agent 工作区 (#57)
- Provider catalog 的 `context_window` 映射为 harness `max_input_tokens`，修复 Auto/摘要阈值与 UI 上下文环按错误上限计算的问题
- 元宝扫码绑定后保存官方 API 与 WebSocket 地址，并升级网关至 0.8.7 以支持完整媒体收发 (#56)
- ChatGPT/Codex OAuth 改为 device code 流程，修复非 localhost 部署下授权失败 (#54)
- 技能 CLI 安装不再根据用户输入的 slug 推导路径，避免装错包 (#63)
- 删除会话时同步清理 harness checkpoint，避免「删除」后消息历史仍残留 (#60)
- 修正 PostgreSQL 记忆可移植导出的误导性 pg_dump 提示（共享 schema 下按 namespace 隔离，不可整库导出单 agent）(#60)
- 技能启用/禁用与 SkillHub 安装不再触发整机 Agent rebuild，避免切到技能列表时短暂「未找到 Agent」
- 修复聊天向上滚动加载更早消息失效，并在列表未溢出时提供可点击回退
- 工作区路径语义澄清（`from_workspace`），并加固 Windows 下 file URL / 主机路径校验

### 变更
- `/compact` 改为在当前话题强制触发一次 Summarization（总结较早消息并 offload 到 `conversation_history/`），不再新建线程；新建空话题请用 `/new`
- `/compact` 成功提示明确：聊天界面仍保留完整历史，压缩的是下一轮模型可见上下文
- 文档与发布流程改为 develop 日常集成、先合入 main 再打 tag (#48)

## [0.9.13] - 2026-07-23

### 新增
- SkillHub 改为走 HTTP API，支持来源中立的技能包安装与搜索 (#55)
- 远程浏览器/桌面支持真实拖拽（转发 CDP 指针事件），并共享推流连接中指示 (#50)

### 修复
- 修复 macOS/Linux 上 Agent 上下文历史写入主机根目录的问题：依赖 harness-agent≥0.9.12 将 deepagents artifacts 落到 Agent 工作区 (#49, #57)
- Provider catalog 的 `context_window` 映射为 harness `max_input_tokens`，修复 Auto/摘要阈值与 UI 上下文环按错误上限（如 128k）计算的问题
- 修复取消聊天任务后再次提问会一直停留在思考状态的问题 (#42, #43)
- 技能启用/禁用与 SkillHub 安装不再触发整机 Agent rebuild，避免切到技能列表时短暂「未找到 Agent」
- 内置专家卡片标题与图标水平对齐
- SkillHub / 专家市场在 Python SSL 失败时给出可操作提示，并修正技能市场错误态「Retry」未本地化为「刷新」(#44, #46)
- 元宝扫码绑定后保存官方 API 与 WebSocket 地址，并升级网关至 0.8.7 以支持完整媒体收发 (#56)
- ChatGPT/Codex OAuth 改为 device code 流程，修复非 localhost 部署下授权失败 (#54)
- 远程桌面安装拒绝不支持的 EL10 环境 (#41)
- 聊天上下文占用图例在空会话时对齐 (#40)
- 修复聊天向上滚动加载更早消息失效，并在列表未溢出时提供可点击回退
- 工作区路径语义澄清（`from_workspace`），并加固 Windows 下 file URL / 主机路径校验

### 变更
- `/compact` 改为在当前话题强制触发一次 Summarization（总结较早消息并 offload 到 `conversation_history/`），不再新建线程；新建空话题请用 `/new`
- `/compact` 成功提示明确：聊天界面仍保留完整历史，压缩的是下一轮模型可见上下文
- 文档与发布流程改为 develop 日常集成、先合入 main 再打 tag (#48)

## [0.9.12] - 2026-07-21

### 新增
- 备份恢复后可在进程内同步 providers 并重载 agent；提供商变更后仅重载受影响的 agent
- 新增服务端时区 API（`default_timezone` / `GET /api/settings/timezone`），控制台时间展示对齐服务端时区
- 记忆提炼支持为每个 agent 单独指定提取模型，并在整理记录中展示每次 extract_run 结果

### 修复
- 修复记忆提取模型无法 fallback 导致提炼失效的问题
- 修复语音输入 STT 回退处理
- 修复内部 MCP gateway 在事件循环上阻塞的问题
- 修复高级搜索探测接口缺失、表格分页卡在 10 条、新建会话图标提示，并加固安装脚本
- 改进 Notion OAuth HTTPS 错误提示

### 变更
- Memory 页签「全部」更名为「记忆沉淀」

## [0.9.11] - 2026-07-19

### 新增
- 新增 SkillHub 专家市场：支持浏览、安装与管理专家，并完善安装安全校验与欢迎页快捷卡片体验
- 新增自定义 MCP 连接器管理，支持探测、工具缓存与连接器配置

## [0.9.10] - 2026-07-18

### 新增
- 新增工作区文件预览与浏览器工作区支持，并完善相关工具链
- 新增聊天面板停靠式文件预览、HTML 预览与历史下拉刷新

### 修复
- 修复连接器 Notion OAuth 弹窗阻塞的问题 (#19)

### 变更
- 重构聊天界面，将浏览器面板与文件面板统一为 ChatDock
- 调整工作区路径透传逻辑，不再重写 BackendWorkspace 路径
- 将上下文使用统计委托给 harness-agent 0.9.10

### 移除
- 移除内置的临床医生专家 (#20)

## [0.9.9] - 2026-07-16

### 新增
- 新增远程桌面安装与连接器探测能力增强 (#16)

## [0.9.8] - 2026-07-15

### 新增
- 远程浏览器/远程桌面安装日志面板新增「复制日志」按钮，并在安装失败时提示可将日志交给 Octop 协助排查
- 新增前端 `copyText` 工具，在非安全上下文（如 plain-http 管理页）下通过临时 textarea + execCommand 回退，保证剪贴板复制可用
- 桌面安装脚本新增 `A-F4`（关闭窗口）与 `C-A-D`（显示桌面）openbox 快捷键，对应桌面快捷键

### 修复
- 修复桌面安装脚本的 Python 构建依赖检测：改用 venv Python（而非系统 `python3`）解析 `pythonX.Y-dev`，避免 evdev 编译时找不到 `Python.h`；`setup.py` 安装构建依赖时显式传入 `--python` 指向当前 venv Python
- 修复连接器类型漂移导致聊天弹窗 logo 解析失败的问题

### 变更
- Docker 构建与 `make build-frontend` 的 `NODE_OPTIONS --max-old-space-size` 由 4096 调低为 2048，降低构建内存占用
- 新增 `docker-publish.yml` 工作流，构建并推送镜像到 Docker Hub
- 移除 `release.yml` 中多余的 `id-token: write` 权限
- 删除已与现行 Docker Hub 发版流程脱节的离线部署脚本 `docker_deploy.sh`，并清理 `docker/README.md`、`README_CN.md` 中的相关章节
- 修正 `docker/README.md` 标题笔误（`ODocker` → `Octop`）

## [0.9.7] - 2026-07-14

### 新增
- 新增多款连接器网关适配器：百度地图、携程问道、飞猪、美团旅游助手、QQ 音乐、元典 (#14)
- 重构连接器网关目录与注册机制，支持更灵活的连接器安装 (#14)

### 修复
- 修复 Linux 远程桌面安装脚本在 EL7（TigerVNC 1.8）下的兼容性，避免 xfdesktop 阻塞安装

## [0.9.6] - 2026-07-13

### 新增
- 新增远程桌面（Remote Desktop）功能，支持跨 Linux、Windows、macOS 的桌面串流 (#7)

### 修复
- 从 .dockerignore 中移除 uv.lock，修正 Docker 构建无法 COPY 锁文件的问题 (#9)
- 修复远程桌面、浏览器、终端及安装向导的本地化（i18n）问题 (#11)

## [0.9.5] - 2026-07-12

### 新增
- 新增 Linux、Windows、macOS 三端的远程桌面串流能力
- 完善远程桌面的安装/卸载交互，并打包 Linux 端安装脚本

### 修复
- 修复 Windows 与 Linux CI 下桌面配置/捕获/输入相关单测与 mypy 报错
- 修复 Mac 端远程桌面安装时误导性的提示文案
- 加固桌面安装 SSE 流式推送并清理 dashboard 端 lint 问题

## [0.9.4] - 2026-07-11

### 新增
- 新增 agent backend 的主机 root_dir 浏览器与权限探测能力
- 改进聊天流式滚动行为与思考计时器

### 修复
- 修复 Windows 下 sqlite 路径测试、媒体路径与 POSIX 专属测试导致的 CI 失败
- 修复 Windows 测试收集问题（惰性导入 pwd 模块）
- 修复 harness-memory Bridge 导入路径
- 修复 CI 流水线并让测试套件通过，项目重命名为 Octop

### 变更
- Windows 兼容：默认 agent backend 限定到 workspace，并集中 POSIX 专属 stdlib 调用以适配 Windows mypy CI

## [0.9.1] - 2026-07-08

### 新增
- 远程浏览器控制页面与浏览器 AI 面板，支持远程浏览器自动化操作
- 附件下载的 `Content-Disposition` 头（RFC 5987，兼容非 ASCII 文件名）
- 前端 UI 语言偏好持久化（自动检测浏览器语言并记忆）
- 专家目录欢迎语（默认欢迎内容 / 工作区清单读取 / 专家目录播种）
- 附件相关国际化域（`i18n/domains/attachment.py`）
- 聊天欢迎语支持

### 变更
- 重构聊天附件与上传处理链路，精简接口与实现
- 重构网关媒体层：附件提示、入站存储、工具媒体展示重写
- 重构 harness 请求构造与消息处理器
- 调整上下文拆分、专家目录、provider 存储与 agent 管理器
- 重构前端聊天界面：输入框、消息气泡、工具媒体条、上下文窗口环等组件大量更新
- 更新登录、初始化向导、终端 AI 面板等前端页面

### 修复
- 修复附件路径解析与内容分发相关问题

### 移除
- 移除模型配置提示弹窗、旧聊天流模块、slash 上下文与附件签名测试
