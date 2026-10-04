# 第三轮导航与功能映射

本轮只改变展示、入口和前端位置状态，继续使用 Octop 的认证、权限、业务 hooks、API、DTO 与通信协议。临时构建开关保留，未进行全局默认切换、提交或发布。

| 工作区入口 | 新位置 | 业务来源与边界 |
|---|---|---|
| 新建任务、助理、历史 | `/home`、既有 `/chat/:agent/:thread` | 现有聊天输入、chatStore、队列与历史 API；深链保留 |
| 专家·技能·连接器 | `/experts`、`/skills`、`/connectors` | 一个市场主壳，三个顶部页签；菜单、页签共用模块权限与导航偏好 |
| 我的专家 | 专家页右上入口 | 真实 Agent、团队及创建/编辑控制器；目录模板仍分别建模 |
| 发现技能、我安装的 | `/skills`、`/skills?tab=installed` | SkillHub 真实目录、分类、排名；明确当前 Agent 安装目标，无 Agent 时只读浏览 |
| 技能详情与编辑 | 市场内容区内返回层级 | 既有文件树、Markdown、编辑器、保存和启停回调 |
| 连接器详情 | `/connectors?detail=<真实 kind>` | 目录原始描述、分类、认证说明；配置再进入既有授权/表单，未将配置等同于连接成功 |
| 自动化 | `/tasks` | 既有 Cron 列表、详情、编辑与执行逻辑 |
| 项目、空间 | 原有独立入口 | 未接入，保留真实状态，无替代 Thread 或伪造数据 |
| 文件、知识库、控制台 | 更多 | 工作区文件、知识库、终端/浏览器、远程桌面/手机按既有权限访问；控制台只有一个一级入口 |
| 账户菜单 | 设置、修改密码、退出 | 用量、外观与管理入口收进设置 |

设置窗口提供 27 个分类，按需加载并保留已访问分类，内容页继续使用既有操作回调。模型、用户、安全的内部页签沿用原模块权限过滤，包含角色、SSO、审计和生成/语音/搜索配置。

| 分组 | 分类及路径尾段 |
|---|---|
| 通用 | `general`、`account`、`appearance`、`shortcuts`、`usage` |
| 功能 | `personalization`、`memory`、`agent`、`channels`、`models`、`tools`、`agent-plugins`、`subagents`、`plugins`、`skill-packages`、`bridge`、`acp` |
| 数据与安全 | `storage`、`backup`、`security`、`https` |
| 系统管理 | `users`、`environments`、`captcha`、`observability` |
| 关于与扩展 | `updates`、`about` |

这些尾段位于 `/settings/<section>/*`。例如角色、SSO 和审计分别位于 `/settings/users?tab=roles`、`/settings/users?tab=oidc`、`/settings/security?tab=audit`。普通分类切换使用各分类保留的位置，保持有效查询参数。市场各页签也单独保留位置，浏览器返回与刷新按 URL 恢复。

旧地址兼容由 `settingsRegistry.tsx` 集中映射。例如：

- `/personalization/skills?kind=custom` → `/skills?kind=custom&tab=installed`。
- `/admin/models?tab=voice` → `/settings/models?tab=voice`。
- `/orca/admin/audit?source=bookmark#retained` → `/settings/security?source=bookmark&tab=audit#retained`。
- `/octop/channels?agent=main` → `/settings/channels?agent=main`。
- 旧会话和定时任务别名也保留查询参数与 hash。

涉及 Agent 的设置明确展示作用对象。切分类不提交表单；切 Agent 后销毁上一对象的未提交面板状态，重新读取新对象，避免把旧草稿写给新 Agent。关闭窗口沿用既有保存或草稿语义，没有加入隐式保存。

市场控制器按已访问页签保留挂载，设置覆盖时工作区仍按背景位置渲染。聊天通信、全局队列和控制台保活逻辑未重写。该机制有生命周期、权限、草稿边界和历史位置测试，隔离实例的聊天/队列保存结果另见验证报告。
