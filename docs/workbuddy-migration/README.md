# WorkBuddy 5.5.6 → Octop 实施记录

本目录记录正在进行的展示层迁移。第三轮已补齐统一市场、27 类窗口内设置、入口整理和对应验证证据。第二轮已重建生产主壳、首页、历史与助理面板，统一主题/编辑弹窗，并验证真实聊天、跨页队列、审批、提问、文件、模型配置、专家与自动化、技能与插件、知识文档、人工记忆、人格文件和渠道配置的主要保存/重读路径。**整份计划尚未完成**；原版运行基准、其余完整业务细节与全平台验收仍待补齐。默认发布版本暂时保留 legacy，新展示默认使用标准 WorkBuddy 外观。

第四轮组件边界与功能保留检查见 [第四轮检查报告](round4-verification.md)。

第三轮结果见 [第三轮实施与验证](round3-verification.md)、[第三轮入口映射](round3-navigation.md)、[逐屏差异](round3-screen-differences.md)和 [第三轮证据](evidence/round3/manifest.json)。第二轮记录见 [第二轮实施与验证](round2-verification.md)、[可重复浏览器验收](browser-acceptance.md)及 [第二轮证据](evidence/round2/manifest.json)。下方 P0–P5 实施摘要与 [verification.md](verification.md) 保留第一轮历史，不能替代第二轮 A–E 状态。

## 基线与来源

- Octop 起始快照：`e473dd3`。已从官方仓库获取 `develop` 快照 `709f998`，核对 180 个文件的差异后，以此创建 `codex/workbuddy-556-ui` 功能分支并合入迁移改动。语言包和聊天工具栏测试冲突已解决，保留新增 LDAP/权限/录制能力。本次没有提交、推送或发布；旧快照迁移改动另保留于任务 stash 和临时补丁，用于恢复。
- 原版包：`WorkBuddy-Analysis/recovered/app/package.json`，版本 `5.5.6`；旧 `recovered-src` 的 `5.3.13` 工程没有被作为生产入口迁入。
- [source-manifest.json](source-manifest.json)：1249 个资源（976 JS、89 CSS 等）的 SHA-256、4290 个原始模块位置、31 份 CSS Modules 映射及生成样式校验。包含用于消息气泡的 cb-chat-ui 映射。`sourceFingerprint` 冻结整个资源清单；资源发生变化时提取命令拒绝覆盖冻结基线。
- [component-inventory.json](component-inventory.json)：1131 个唯一 TSX/Vue 来源条目及包内行号。全部原版运行态核对仍待完成，静态条目数不等于界面还原数量。
- [operation-inventory.json](operation-inventory.json)：51 个 API 模块、449 个静态导出操作/辅助函数、静态调用位置。动态调用仍需人工检查；**317 个有静态调用者的操作不表示业务验收覆盖率**。

## 第一轮实施记录（历史）

1. 使用 PostCSS 提取原版主题、主壳、专家市场、聊天、自动化和部分项目/空间样式；限定在 `html[data-ui="workbuddy"]`。生成规则包含媒体查询与用到的动画；原版 JS 只用于静态溯源，不被执行或打入运行包。
2. 新展示组件置于 `dashboard/src/workbuddy/`。保留 React 18、Vite、现有 Ant Design 和懒加载页面，不升级框架。
3. 增加 `/home`：欢迎区、办公/编程/创意场景、真实 Octop 快捷提示与输入区共用原聊天控制层。场景不改变 `ask / plan / craft`。
4. 为桌面聊天加入原版 56px 顶栏、264px 默认助理栏、新输入区外观。已有布局偏好优先，聊天深链、恢复/审批/队列/附件代码继续沿用；没有重新实现 SSE、鉴权或历史投影。
5. 专家模板采用原版 `ec-expert-card` 结构，回调仍创建真实 Octop Agent；Agent 卡片与模板身份分开。
6. 账户设置采用原版双栏框架（880×720、导航 200px），保留现有账户、SSO、语言、主题、导航配置表单；切换显示面板时表单保持挂载。模型/连接器/安全入口使用既有权限判断。
7. 自动化采用原版 `TaskTab / AutomationRow` 分组行样式，传入 `useCronJobs` 的真实 DTO 和操作回调；保留原编辑/删除限制、执行确认、详情抽屉与服务器时区。没有虚构运行中或执行记录。
   连接器目录与实例卡片使用原版 `connector-card` 结构及 288px 网格，继续调用真实配置/启停/删除逻辑。显示实际启用状态与缺少凭证提示，不将配置状态冒充连接健康。共享只读实例不提供管理控件。
8. 控制台、后台及其余业务页保留全部原入口，共用原版 56px 顶栏、统一内容区域和主题；移动端顶栏允许换行，路径页签、Agent 选择、远程断连提示和页面保活继续沿用。逐页结构恢复尚未完成。
   已安装技能与技能包内技能使用原版 `CardFrame` 结构；技能启停回调、启用时禁止删除、技能包写权限和删除确认保持有效。技能详情、市场与安装流程的完整原版结构仍待迁移。管理员已安装插件、市场插件和 Agent 插件也采用原版公共卡片结构，保留实际安装/更新、全局/Agent 启停、加载错误、卸载确认与工具配置流程。
9. 项目、空间、云服务、智能应用和专属资料库等提供明确“未接入”入口，不创建临时项目、不显示服务已连接、不发送伪造请求。项目页恢复了原版 landing/header/grid/empty 结构及原始插画，新建与搜索禁用；其他入口目前是说明页，完整原版页面结构待实现。
10. 独立开发入口 `dashboard/dev/workbuddy.html` 提供无业务 API 的展示样例；普通生产入口不导入它。样例明确标注不是原版截图，不作为真实功能证明。

## 运行与复核

从 `dashboard/` 执行：

```sh
npm ci
npm run workbuddy:extract
npm run workbuddy:audit
node --test scripts/compare-workbuddy-screenshots.test.mjs scripts/workbuddy-inventory.test.mjs
npm run dev:workbuddy
```

提取器默认读取旁边的恢复项目，也接受显式路径：

```sh
npm run workbuddy:extract -- /absolute/path/to/recovered/app
```

`workbuddy:audit` 检查生成文件哈希与样式隔离，并刷新静态组件/API 调用清单。与相同资源指纹关联的验收记录会保留；API 文件变化会将旧验收标记为需复核，避免静态扫描清掉证据或延用过期结果。已生成的源码受版本管理；正常构建不需要恢复包。

截图比较工具与遮罩要求见 [screenshot-protocol.md](screenshot-protocol.md)。当前 JPEG 展示证据不作为像素差异验收输入。

- 真实应用：开发服务器根路径，使用真实 Octop 认证与业务 API。
- 开发样例：`/dev/workbuddy.html`，仅验证已迁移展示结构。
- 新界面构建：`npm run build:workbuddy`。
- 默认/回退构建：`npm run build`（未设置 `VITE_UI_VARIANT` 时为 legacy）。
- 标准打包：仓库根目录 `VITE_UI_VARIANT=workbuddy make build-frontend`。它正常生成 `src/octop/dashboard/`，不能手工修改该目录。

## 第一轮阶段出口（历史）

| 阶段 | 当前状态                                            | 必须补齐的出口                                                              |
| ---- | --------------------------------------------------- | --------------------------------------------------------------------------- |
| P0   | 资源冻结及静态清单完成；运行态盘点未完成            | 23 个源页面及其弹窗/状态的实际渲染基准、完整操作级用例                      |
| P1   | 主题桥接、导航、顶栏和设置部分实现                  | 登录/初始化逐状态还原，菜单/浮层/窗口控制真实运行验收                       |
| P2   | 欢迎/输入区展示接入；通信与复杂消息保持既有实现     | 消息、工具、提问、审批、文件/轨迹逐结构迁移及断网恢复 E2E                   |
| P3   | 专家/团队外框、自动化、技能/插件/连接器卡片部分实现 | 完整详情/市场/渠道/知识/记忆/团队及各编辑流程；真实业务、角色及失败路径验收 |
| P4   | 统一页壳与原业务入口；未接入入口明确标识            | 控制台/后台逐页适配和其余原版页面结构                                       |
| P5   | 未切换                                              | 全终端/视觉/性能/真实功能验收，正式发布产物、回退演练，删除临时分支展示代码 |

详细双向状态见 [coverage-matrix.md](coverage-matrix.md)，检查结果与未验收项见 [verification.md](verification.md)。

## 切换、兼容与回退

目前保留构建期 `VITE_UI_VARIANT=legacy|workbuddy`。每次构建选择一种展示方式，生产数据、API、数据库和业务配置不随界面选择变化。旧展示资源作为迁移期回退保留，不能据此宣称“最终替换已完成”。

现有 Wails 窗口控制、PWA 用户确认更新流程、权限守卫、登录/OIDC/邀请流程、服务器时区、文件路径及附件鉴权仍复用 Octop 实现。已有偏好不清空；264px 仅作为新助理栏缺省值，已保存宽度继续优先。

正式切换前保存两份经过验证的发布产物和对应提交/构建变量/哈希。在隔离实例演练 PWA 更新、正在生成的会话和刷新恢复；回退时发布上一份验证产物，沿用现有更新流程，不删除数据库或工作区文件。最终验收通过后再删除开关和旧展示代码。
