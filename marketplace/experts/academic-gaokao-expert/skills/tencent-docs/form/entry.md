# 收集表（form）品类操作指引

本目录面向腾讯文档**个人版**收集表：报名/信息登记、问卷、投票、文件收集、打卡和接龙。结构化创建、题目/设置编辑与提交结果查询均使用独立的 `form-mcp`；SaaS 暂不支持此服务。具体字段和返回状态见 [FormMCP API 参考](./api/mcp-api.md)。

## 服务信息

| 项目 | 说明 |
|---|---|
| 服务 | `form-mcp`，与主服务 `tencent-docs` 平级 |
| 地址 | `https://docs.qq.com/api/v6/form/mcp`（仅个人版） |
| 工具名 | `form_*`，如 `form_get_context`；不是 `form.*` |
| 凭据 | 使用个人版 `setup.sh` 注册的 MCP Token，与其他个人版服务共用；首次使用参见 [鉴权说明](../references/auth.md) |
| 工具发现 | `mcporter list form-mcp`；**传参以实时返回的工具 Schema 为准** |

`manage.create_file` 只适合用户明确需要空白收集表文件，不代替 `form_create_*` 的题目/原生主体创建；FormMCP 创建失败或结果未知时不得静默改用它重建。文件列表/重命名等仍走 `tencent-docs` 主服务。

## 工具速查

| 场景 | 工具 |
|---|---|
| 查看模板、按模板复制 | `form_get_template`、`form_create_by_template` |
| 查看现有表结构、品类、版本和可编辑能力 | `form_get_context` |
| 新建普通表/打卡/接龙/投票/问卷/文件收集 | `form_create_normal`、`form_create_checkin`、`form_create_following`、`form_create_vote`、`form_create_questionnaire`、`form_create_file_collection` |
| 编辑标题、说明、题目 | `form_update_content` |
| 打卡、接龙、定时和重复设置 | `form_get_checkin_config` / `form_update_checkin_config`、`form_get_following_config` / `form_update_following_config`、`form_get_periodic_config` / `form_update_periodic_config` |
| 提交概览、单题统计、筛选记录 | `form_get_result_overview`、`form_get_question_stats`、`form_query_records` |
| 附件统计、整表提交名单、交叉分析 | `form_attachment_summary`、`form_submission_checklist`、`form_get_cross_analysis` |

## 选择目标与安全边界

1. 优先沿用用户给出的收集表 URL 或真实 `file_id`；已有当前收集表时，含糊的“帮我做一个报名表”先按**完善当前表**理解。只有明确“新建一份/另建”或确无现有目标时才创建。`form_get_context` 需要 `file_id` 或 `file_url`，不要发空对象探测，也不要把分享链接中的一段猜作 ID；需要 ID 的设置工具可从 `form_get_context.meta.file_id` 取得。
2. 编辑前读取 `form_get_context`，核对 `meta.form_type_known`、`meta.init_state`、`form_capabilities`、逐题 `capabilities` 和 `unsupported_questions`；未知品类、未就绪或不支持的题目只能按返回能力处理，**不能按普通表假设可编辑**。不能把已有表转换为另一品类，不能用创建新表冒充转换。
3. 任何创建或写入先展示标题、题目/选项、必填和设置影响的用户可读预览，获得明确确认后再调用写工具；删除、改题型或改附件限制需特别说明影响。交互方式遵循当前宿主能力，不假设存在某个特定问询工具。不得向用户泄露 Token、原始答案或不必要的内部 ID。
4. 写后回读 `form_get_context` 及相应设置读取工具，核对已确认内容；仅交付工具返回/回读的访问链接，不自行拼接。修改保存到编辑页/草稿态不代表已发布，提醒用户**需在编辑页手动发布**才能让填写人看到本次变更。

## 权限与能力边界

- **`form_get_context` 仅表主（owner）和管理员可用。** 它是编辑前读取结构与版本的入口，打卡/接龙设置读取（`form_get_checkin_config`、`form_get_following_config`）遵循同一规则；编辑题目、查看提交结果同样要求表主或管理员。普通协作者或仅有填写权限的用户会被拒绝。
- 遇到无权限错误时，如实告诉用户“只有这张收集表的表主或管理员才能查看和修改其结构，请联系表主或管理员操作或授权”。**不要**换用其他工具、改传链接或凭经验猜测结构来绕过，也不要在没有读取结果的情况下继续写入。
- **FormMCP 不支持将收集表结果关联（同步）到在线表格。** 用户提出“结果自动汇总到某个表格”“把表格和收集表关联”时，明确说明当前不支持，不要声称已建立关联或自动同步，也不要用其他工具拼凑出看似关联的效果。可询问是否改为一次性导出当前数据快照，见文末「导出收集表数据」。

## 按场景工作流

### 从官方模板创建

1. 确认用户本轮确实要求按模板新建；用真实 `template_id` 调 `form_get_template`，根据返回的题目、品类和可继承设置展示预览。模板题目 ID **不能**用于编辑新表。
2. 用户确认后调 `form_create_by_template`。仅 `state=TEMPLATE_CREATE_STATE_READY` 时才继续回读新表并定制；`CREATED_NOT_READY` 或请求超时可能已创建文件，保留已返回链接并核对最近文档，**不自动再次创建**。`READY` 不保证设置复制已完成，定制后仍需回读。

### 按品类创建

- 普通报名/登记选 `form_create_normal`；问卷选 `form_create_questionnaire`；投票选 `form_create_vote`（原生投票主体仅一题）；文件收集选 `form_create_file_collection`（先用一道默认文件题创建，读取新表后再按能力调整限制和补题）。题目需符合实际 Schema，新增 `question_id` 留空，不写原始 `qdata`。
- 打卡选 `form_create_checkin`，接龙选 `form_create_following`：两者均有产品原生主体，**不接受普通题目模拟打卡/接龙**。打卡方式及昵称/位置/图片走打卡配置，接龙预设备注走接龙配置；定时/重复走独立周期配置。
- **打卡的 `initial_config` 必须同时传 `update_fields`**：只写 `update_fields` 中列出的项，缺失时配置不生效，且服务端会返回 `510005`（已创建但未全部完成），并留下标题为空的半成品表。遇到 `510005` 时用返回的链接定位该表并回读，不要重新创建。
- 创建成功后使用返回的 `file_id` 调 `form_get_context` 核对标题、品类、题目及 `meta.init_state`；若未就绪或与预览不一致，说明现状并停止，不宣称完成、不盲目重建。

### 修改已有表

1. 调 `form_get_context` 取得最新结构与 `base_version`；确认当前品类和字段/题目可编辑。更新正文时，`form_update_content` 只传预览中明确同意的 `form_patch` / `operations`，版本必须原样来自刚回读的上下文。
2. 打卡/接龙设置先读对应 `form_get_*_config`，向用户预览后使用读取结果的版本写入；周期设置先读 `form_get_periodic_config`，**完整保留未改字段后替换 `config`，请求不带 `base_version`**。仅普通、问卷、文件收集、打卡支持周期设置。
3. 版本冲突或调用超时后先回读确认真实状态；方案或版本变化时重新展示并确认，不重放可能已成功的写入。写入后回读核对、附访问链接及手动发布提醒。

### 查询与分析结果

- 整体提交量、填写人数、趋势用 `form_get_result_overview`；单题选项分布用 `form_get_question_stats`；只有需要筛选特定记录/答案时才用 `form_query_records` 的最小 `return_questions` 白名单及分页。不可通过自动翻页拼出所谓全量统计。
- 附件题的 `form_attachment_summary` 给**提交次数**、缺交次数及有权限时的容量，不是去重人数或文件数量，也不给谁缺交；整表“谁交了/没交”另用 `form_submission_checklist`，未提交名单需要应交人群基线、匿名表可能只返回人数。只按用户需要展示姓名，不自动发送催交消息。
- 交叉分析先不传行列，调用 `form_get_cross_analysis` 发现可分析字段，再由用户确认行/列后查询；矩阵/表格需指定子行/列 ID。发现模式 `total_records=0` 不能断定无人提交。
- 优先判断 `limit`、`data_complete`、`unavailable_reason` 和 `names_available`；计算中、超限或超时都不能把空结果/零值当真实数据。超时不自动重试，建议缩小范围（如限定时间或字段）后再查；报告中区分事实与推断。

## 导出收集表数据

**收集表本身不支持导出下载**，不要对收集表调用 `manage.export_file` / `manage.export_progress`，也不要向用户承诺能生成导出文件链接。用户想要“导出/下载/存成 Excel 或 CSV”时，改为“先用 form-mcp 取得提交数据，再由你写入本地文件”，并先说明这是一次提交数据**快照**：

1. **确认需求**：向用户确认要导出的题目（默认仅必要字段）、时间范围、文件格式（建议 CSV，UTF-8 带 BOM 以便 Excel 打开）和保存路径。导出内容含个人提交数据，仅写入用户指定的本地路径，不在对话中整表回显，也不上传到其他位置。
2. **核对权限与规模**：用 `form_get_context` 取得题目清单（仅表主/管理员可用，无权限则按上文处理并停止）；用 `form_get_result_overview` 查看 `filled_submissions` 与 `limit`，`limit.over_limit` 为真时说明当前无法完整导出并停止。提交量很大时先告知预计分页请求次数并取得用户确认。
3. **分页拉取**：用 `form_query_records` 按 `page.page_size`（最大 100）与 `page.cursor` 逐页拉取，`return_questions` 每次最多 20 题；题目超过 20 个时用相同 `scope` 分批取列，以记录的 `seq` 对齐合并。只取用户确认的列，直至 `has_more=false`。这是用户明确要求导出时的受控分页，与“不要为统计自动翻页”的规则不冲突。
4. **写入本地文件**：使用当前环境的本地文件写入能力（或 Python 标准库 `csv`）写入，不要把数据拼进命令行参数；表头使用题目标题（同名时追加序号）。若当前环境无法写本地文件，如实告知，不改用其他方式假装已导出。
5. **核对并说明口径**：写完核对行数（`page.total_is_known` 为真时对照 `page.total`），汇报文件路径、行数、列和导出时间。必须同时说明：答案为摘要口径，长文本可能被截断（`is_truncated`），附件仅为计数摘要、不含文件内容、文件名或下载链接；`limit.is_truncated`、行数与总数不一致或任一页失败时，标明导出不完整，不要说“已完整导出”。若用户还想把结果放进在线表格，说明只能另行把该本地文件作为新文件上传，**不会**与收集表保持关联或同步。
