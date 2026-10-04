# 双向覆盖矩阵

状态以真实实施为准：**部分展示**表示尚有原版结构未恢复；**保留业务**表示仍使用既有 Octop 页面；**未接入说明**表示没有对应后端；**待验证**不能计作验收通过。页面打开、API 静态调用或单元测试通过都不是完整功能覆盖证明。

第二轮真实结果及剩余出口见 [round2-verification.md](round2-verification.md)。有限实例路径仍登记为部分浏览器验证，未计作全域/全角色完成。

## 原版视图 → 新入口

| 5.5.6 源视图 | Octop 入口/安排                               | 当前交付状态                                                                                                                                                   |
| ------------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| home         | `/home`                                       | 独立生产主壳、原版首页宽度/推荐避让、场景和真实输入；无常驻助理列，20 组尺寸/主题/语言检查通过；原版运行态待验证                                               |
| chat / task  | `/chat/:agentId/:threadId`                    | 历史主侧栏、固定/浮动助理面板、顶栏、真实输入、用户气泡、工具/审批/提问外层和预览；切页、取消、队列、审批/提问恢复及文件读取真实验证；完整状态与原版比对待验证 |
| conversation | 聊天历史栏                                    | 保留分页/搜索/右键操作；原版列表与菜单待迁移                                                                                                                   |
| projects     | `/projects`                                   | landing/标题/插画/搜索/空状态部分结构；新建和搜索禁用；详情/模板/弹窗待恢复                                                                                    |
| automation   | `/tasks`                                      | 原版分组列表与 520px 居中编辑/详情卡片接入真实操作；完整源字段及执行历史待迁移                                                                                 |
| colleagues   | `/experts` / 团队页签                         | 团队外框统一；成员、生命周期和工具保持业务，完整源结构待迁移                                                                                                   |
| claw         | 聊天 Agent 栏、`/experts`                     | 部分主壳；助理详情/编辑保留业务                                                                                                                                |
| experts      | `/experts` / 专家库                           | 原版模板卡片和文字页签；创建/编辑外框居中并复用表单，完整市场筛选/详情源结构待迁移                                                                             |
| skills       | `/personalization/skills` / `/skill-packages` | 已安装卡片及 640px 居中技能详情、图标/基本信息/预览已恢复，真实创建编辑重读通过；完整市场/安装/技能包逐结构待迁移                                              |
| discover     | `/discover`                                   | 未接入说明；完整源结构待恢复                                                                                                                                   |
| connectors   | `/connectors`                                 | 原版目录/实例卡片与网格、600px 居中配置表单接真实保存/重读与失败反馈；OAuth/MCP 成功授权及完整源字段仍待验证                                                   |
| plugins      | `/personalization/plugins` / `/admin/plugins` | 系统详情使用原版页内结构，Agent 详情/工具配置居中；本地安装、禁用重读和工具配置重读通过，完整外部市场/源结构待迁移                                             |
| inspiration  | `/inspiration`                                | 未接入说明；完整源结构待恢复                                                                                                                                   |
| tencent-docs | `/library/tencent-docs`                       | 未接入说明，不冒充 Octop 知识库                                                                                                                                |
| ima          | `/library/ima`                                | 未接入说明                                                                                                                                                     |
| lexiang      | `/library/lexiang`                            | 未接入说明                                                                                                                                                     |
| my-files     | 聊天文件/右侧预览/工作区                      | 保留已有上传、预览、编辑业务；源结构待迁移                                                                                                                     |
| iframe-menu  | 原版自定义内嵌入口                            | 待盘点和实施，不注册任意外部业务入口                                                                                                                           |
| space        | `/space`                                      | 未接入说明；完整源结构待恢复                                                                                                                                   |
| agent-mail   | `/library/agent-mail`                         | 未接入说明                                                                                                                                                     |
| genie-home   | `/genie`                                      | 未接入说明                                                                                                                                                     |
| genie        | `/genie/*`                                    | 未接入说明；应用运行态待恢复，仅限开发验收样例                                                                                                                 |
| extension    | 原版扩展入口                                  | 待盘点；不迁入 Electron 私有运行链路                                                                                                                           |

登录、设置、弹窗、菜单及组件级清单另见 `component-inventory.json`，不能由上述 23 行代替逐状态验收。

## Octop 功能 → 新展示及验收责任

| 功能操作域                                           | 入口                                               | 权限/状态来源                               | 现有 API/控制层                          | 当前证据与缺口                                                                                                                              |
| ---------------------------------------------------- | -------------------------------------------------- | ------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 初始化、登录、验证码、邀请、密码帮助、SSO/LDAP       | `/setup`、`/login`、`/invite`、OIDC 回调及目录登录 | develop 认证及 AuthGuard                    | auth、wizardClient、ssoPopup             | 独立实例真实 SQLite/管理员初始化通过；普通登录/验证码/SSO/LDAP 与完整源视觉待验证                                                           |
| 首页、Agent 选择、新任务、草稿                       | `/home`、`/chat`                                   | 原 AgentContext/所有权                      | useChatNavigation、chatStore、ChatInput  | 生产主壳/首页/输入共用组件；真实发送、欢迎配置保存重读和跨页恢复已验证；草稿/模型/Agent 组合及原版运行比对待验证                            |
| 会话分页/搜索/重命名/置顶/删除/分叉/已读             | 聊天历史栏、消息操作                               | 原用户与 Agent 范围                         | threads、useSessions                     | 既有单测复用；新页面真实持久化/重开待验证                                                                                                   |
| 模型、推理、执行模式、技能/文件/知识提及、语音、队列 | 真实 ChatInput                                     | 原 DTO/配置与模式语义                       | providers、voice、skills、chat hooks     | 既有单测；弹层原版结构和真实任务闭环待验证                                                                                                  |
| 流式、思考、工具、多智能体、审批、提问、轨迹         | 消息与过程面板                                     | chatStore/后端事件                          | chat、hitl、teams、history               | 协议复用；切页/刷新、取消、队列、审批批准/拒绝及提问提交真实验证；断网、多智能体和全部轨迹状态待验证                                        |
| 文件、图片、PDF、Office、音视频、工作区编辑          | 文件侧栏与预览                                     | 原附件鉴权/Agent workspace                  | workspace、uploads、预览组件             | 更多/聊天工作区入口接入原 API；审批生成 Markdown 后真实重读/预览已验证；远程存储、附件与全部格式待验证                                      |
| 专家库、Agent 生命周期、共享专家、团队、发布         | `/experts`                                         | 现有权限/模板与实例区分                     | agents、experts、publishedExperts、teams | 原版模板卡片、中心文字页签及居中编辑表单接原回调；专家标题语保存刷新重读已验证；团队/共享/发布全路径待验证                                  |
| Cron 创建/编辑/启停/删除/立即执行/历史               | `/tasks`                                           | activeAgent.is_owner、原启用限制            | octopCronApi、useCronJobs、服务器时区    | 独立实例创建/编辑/刷新/启停/启用限制通过；立即执行、删除、共享权限及完整源编辑结构待验证                                                    |
| 技能包/安装/启停/导入/市场                           | `/skill-packages`、`/personalization/skills`       | 原资源写权限                                | skillPackages、skills                    | 卡片/640px 详情恢复，真实创建与编辑后刷新重读通过；取消/只读/稳定名称组件测试通过；市场安装和技能包全路径待验证                             |
| 插件、Agent 工具与配置                               | `/personalization/plugins`、`/admin/plugins`       | 原模块权限                                  | plugins、tool renderer registry          | 卡片更新 force 参数、错误禁用、卸载确认单测；本地 echo-tool 安装、禁用重读及 Agent 工具配置保存重读已验证；全部外部市场/错误卸载/角色待验证 |
| 连接器、OAuth、MCP                                   | `/connectors`、设置链接                            | navAllowed + 原授权状态                     | connectors、mcp                          | 卡片配置回调、只读共享、启停/刷新、新旧标题提示等单测；本地配置保存刷新重读与真实探测失败已验证；成功授权/OAuth/MCP 全路径待验证            |
| 渠道配置/绑定/测试/状态                              | `/personalization/channels`                        | 原 channels 权限                            | channels                                 | 统一资源卡片与 600px 配置；真实停用 MQTT 配置保存/刷新重读及连接拒绝验证；端口整数契约修正。实际平台绑定、连接和消息收发待验收。            |
| 知识库/文档/引用                                     | `/knowledge-bases`、输入提及                       | 原模块/写权限                               | knowledgeBases                           | 520px 基础/功能设置与 880px 文档编辑；私有 Markdown 创建/编辑/索引就绪/刷新预览验证。共享权限、检索、OCR、引用及其他格式待完整验收。        |
| 记忆/人格/主动关怀/导入导出                          | `/personalization/*`                               | 原 Agent scope                              | memory、persona、proactiveCare           | 记忆详情与编辑确认统一，人工记忆创建/替换/刷新重读及专家 SOUL 文件保存/重读验证；自动记忆、MBTI、主动关怀、导入导出待完整验收。             |
| 终端、浏览器/回放、远程桌面、手机、Shell             | `/workbench/*`、`/remote-desktop/*`                | pathPermissionKeys                          | 原 keep-alive 页面与相关 API             | 统一主壳且不更改保活逻辑；实际终端标记输出在切页后保留；浏览器启动/录制、远程控制、手机与桌面壳待验证                                       |
| ACP、Bridge                                          | `/acp`、`/bridge`                                  | 原 admin/Bridge 规则                        | acp、bridge                              | 保留业务；统一展示及真实控制待验证                                                                                                          |
| Provider、生成/语音/搜索、本地模型、用量             | `/admin/models`、`/token-usage`                    | 原 models/use permissions                   | providers、models、voice、usage          | 账户管理入口按模块权限；本地受控 Provider 配置/连接测试/保存重读已验证；其他生成/语音/搜索/本地下载全路径与源细节待验证                     |
| 用户/角色/SSO/存储/安全/审计/备份/HTTPS/更新等       | `/admin/*`                                         | 原权限路由及模块权限                        | 既有 51 个 API 模块中的管理模块          | 统一 56px 顶栏与内容区域、保留全部原入口；逐页适配及隔离副作用 E2E 待验证                                                                   |
| 账户/语言/主题/导航偏好                              | 头像设置                                           | 当前用户及原偏好                            | AvatarDropdown 原表单                    | 独立标准/自定义外观与面板偏好映射；设置权限/草稿单测、真实名称保存、明暗及主动配色切换通过；所有角色及偏好组合待验证                        |
| 尚无后端的原版能力                                   | 新导航的“未接入”入口                               | unsupported，与 unconfigured/forbidden 分开 | 不发业务请求                             | 明确状态单测；完整原版样例结构待恢复                                                                                                        |

## 验收登记方式

`operation-inventory.json` 中少数已执行的真实浏览器路径登记为 `partial-browser-verified`，其余保持 `pending`。有限路径不表示该操作整体验收通过。人工确认是否属于用户操作后，在 `acceptance` 中补上：入口、权限角色、配置前提、具体输入、预期后端结果、重读/刷新结果、自动化用例、日志/截图以及最后验证快照。缺少任一关键结果不能计入“100% 已验收”。

视觉基准分开保存：原版实际渲染、Octop 已适配回归截图。当前 `evidence/` 包含 **Octop 开发样例及独立真实实例的 JPEG 展示截图**，尚没有原版基准，因此尺寸相符不能推导为静态截图差异小于 1%。
