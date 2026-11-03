# 腾讯文档 Form MCP 工具参考

本文件提供了腾讯文档 Form MCP 工具的通用 API 说明。
调用前用 `mcporter list form-mcp` 查看实时工具 Schema，字段、枚举及必填项以服务端为准。工作流和确认要求见 [收集表品类入口](../entry.md)。

## 公共约定

- 文件定位：大多数结构/结果工具支持 `file_id`、`file_url` 二选一，**具体以本节各工具为准**；专属设置读取/更新只接受 `file_id`。有分享链接时直接传 `file_url`，不要截取链接片段充当 ID。附件统计、名单和交叉分析要求 `file_id` 为真实的全局 ID（形如 `300000000$xxx`）；可先调用 `form_get_context` 获取 `meta.file_id`。
- 版本：`FormVersion` 是 `{ "base_revision": <整数>, "base_pos": <整数> }`。`form_update_content` 用 `form_get_context.base_version`，打卡/接龙配置更新用对应读取工具的 `base_version`；必须原样传回，不能自造。**`form_update_periodic_config` 不含版本字段**，而是完整替换读到的配置。
- 题目：`Question` 的 `type` 使用完整 `QUESTION_TYPE_*` 枚举名；创建/新增时 `question_id` 留空，更新和删除时使用 `form_get_context` 返回的 ID。题型配置在 `question.config` 下按类型选 `text`、`choice`、`temporal`、`attachment`、`range`、`cascader`、`matrix`、`table` 或 `rating`，不能传裸 `qdata`。表格题的列在 `question.config.table.columns`，不可嵌套表格。
- 用户权限由服务端按目标表检查；可列出工具**不等于**有权读取结果或编辑。写入前先预览并取得用户明确确认，写后回读；版本冲突/超时不盲目重试。不展示内部版本、题目 ID、Token、原始提交答案或附件下载链接。
- 统计可靠性：概览/题目统计/记录查询查看顶层 `limit`（题目还要查每项 `stats[].limit`）；附件与交叉分析只有 `data_complete=true` 时计数/矩阵才有效，名单须检查 `names_available`、`unavailable_reason`。`limit.is_truncated` 是部分结果而非完整统计，`limit.over_limit` / 不可用状态不能按 0 解读。

## 模板与现有表

### `form_get_template`

- 请求：`template_id`（必填，长度 1–128）。仅传官方模板 ID；若入口给出模板链接，可取 `/mall/detail/` 后的模板 ID，不传完整链接。
- 返回：`title`、`subtitle`、`form_type`、`questions`、`sections`、`unsupported_questions`、`settings`（仅可继承的设置）。返回题目 ID 属于**源模板**，不能作为新建表的编辑目标。

### `form_create_by_template`

- 请求：`template_id`（必填）；复制前先 `form_get_template` 并展示预览、取得确认。
- 返回：`file_id`、`file_url`、`state`、`message`。`TEMPLATE_CREATE_STATE_READY` 表示文件和正文就绪但**不保证设置复制完成**；`TEMPLATE_CREATE_STATE_CREATED_NOT_READY` 表示文件已知但尚未完成，不能直接编辑或重复创建。超时先核对是否已创建。

### `form_get_context`

- 请求：`file_id` 或 `file_url` 二选一，不传空对象；提供分享链接时使用原始 `file_url`。**权限：仅表主（owner）和管理员可调用**，普通协作者或填写者会被拒绝，此时停止并如实告知，不绕过。
- 返回：`meta`（含 `file_id`、`file_url`、`form_type`、`form_type_known`、`init_state`、`published`）、`questions`、`sections`、`base_version`、`capabilities`（每题可改字段/删除/换题型）、`form_capabilities`、`unsupported_questions`。未知品类、未就绪或不支持题目不能按普通表猜测可写。

只读调用示意（ID 须来自用户提供的真实标识或已有工具返回）：

```bash
mcporter call "form-mcp" "form_get_context" --args '{"file_id":"<真实 file_id>"}'
```

## 按品类创建（六个工具）

| 工具 | 请求字段 | 关键约束与返回 |
|---|---|---|
| `form_create_normal` | 必填 `title`；可选 `subtitle`、`questions` | 普通表，允许空题目；`questions` 最多 200 项。返回 `file_id`、`file_url`。 |
| `form_create_checkin` | 必填 `title`；可选 `subtitle`、`initial_config` | 原生打卡主体，不传普通题目。`initial_config` 仅写 `update_fields` 指定项；返回 `file_id`、`file_url`。 |
| `form_create_following` | 必填 `title`；可选 `subtitle` | 原生接龙主体，不传普通题目；返回 `file_id`、`file_url`。 |
| `form_create_vote` | 必填 `title`、`questions`；可选 `subtitle` | 至少一题投票题；当前产品仅一项原生投票主体，不擅自创建多题。返回 `file_id`、`file_url`。 |
| `form_create_questionnaire` | 必填 `title`；可选 `subtitle`、`questions` | 问卷允许空题目；返回 `file_id`、`file_url`。 |
| `form_create_file_collection` | 必填 `title`、`questions`；可选 `subtitle` | 至少一道文件题；建议先创建一题并保留模板默认附件配置，再回读并按能力补齐限制/题目。返回 `file_id`、`file_url`。 |

标题最长 128 字符，说明最长 5000 字符；题目字段和约束依实时 Schema。普通收集表示例（**写操作须先得到本轮明确确认**）：

```json
{
  "title": "活动报名",
  "questions": [
    {
      "type": "QUESTION_TYPE_SIMPLE",
      "title": "姓名",
      "required": true,
      "config": {"text": {"data_type": "DATA_TYPE_TEXT"}}
    }
  ]
}
```

普通题 `config.choice.options` 至少含有效选项；多选限制仅多选题支持；附件 `config.attachment` 有文件数、分类、大小和命名规则；日期题通过 `config.temporal.mode` 区分日期、时间、时长。投票用投票题及其选项，打卡/接龙不拿普通题代替原生主体；不要用底层枚举数字代替 MCP 的字符串枚举。

### 枚举值速查（取值是完整枚举名）

> Schema 描述里的中文（如「满意度」「评星」）只是展示名，**不能直接作为值传入**。

**日期/时间题 `config.temporal.mode`**：只支持下列 5 种，其他取值（如 `TEMPORAL_MODE_DATETIME`、`_DATE_RANGE`、`_YEAR_MONTH`、`_WEEK`）会被拒绝，注意是 `DATE_TIME` 而不是 `DATETIME`。

| 用户说法 | 取值 |
|---|---|
| 日期 | `TEMPORAL_MODE_DATE` |
| 时间 | `TEMPORAL_MODE_TIME` |
| 日期 + 时间 | `TEMPORAL_MODE_DATE_TIME` |
| 时长 | `TEMPORAL_MODE_DURATION` |
| 月份 | `TEMPORAL_MODE_MONTH` |

用户要的是上表之外的格式（如日期范围、周、年月）时，如实告知暂不支持，不要自行换成其他取值。

**评分题 `config.rating`**（不传时默认 `RATING_DEGREE_SATISFACTION` + `RATING_ICON_STARS`）：

| 字段 | 展示名 | 取值 |
|---|---|---|
| `degree` | 满意度 | `RATING_DEGREE_SATISFACTION` |
| `degree` | 推荐度 | `RATING_DEGREE_RECOMMENDATION` |
| `degree` | 符合度 | `RATING_DEGREE_CONFORMITY` |
| `degree` | 认同度 | `RATING_DEGREE_IDENTIFICATION` |
| `degree` | 可能性 | `RATING_DEGREE_POSSIBILITY` |
| `degree` | 意愿度 | `RATING_DEGREE_WILLINGNESS` |
| `degree` | 重要度 | `RATING_DEGREE_IMPORTANCE` |
| `icon` | 评星 | `RATING_ICON_STARS` |
| `icon` | 点赞 | `RATING_ICON_LIKES` |
| `icon` | 表情 | `RATING_ICON_EMOJIS` |

组合约束（实测）：`RATING_ICON_STARS`、`RATING_ICON_LIKES` 可搭配任意 `degree`；**`RATING_ICON_EMOJIS` 只能搭配 `RATING_DEGREE_SATISFACTION`**，与其他程度文案组合会返回 `11607`。用户要「表情 + 非满意度」时，如实说明限制并改用评星或点赞。

## 编辑与设置（七个工具）

### `form_update_content`

- 请求：`file_id` / `file_url` 二选一；`base_version` **必填**（刚读取的 `form_get_context` 返回值）；可选 `form_patch`（`title`、`subtitle` 和对应的 `update_fields`）、`operations`（最多 200 项，按顺序执行）。
- `operations[]` 的 oneof：`add_question`（`question`、可选 `insert_after_question_id`）、`update_question`（`question_id`、`question`、**必填** `update_fields`）、`change_question_kind`（`question_id`、完整 `target`）、`delete_question`（`question_id`）。可编辑字段以 `capabilities[].allowed_update_fields` 为准；不能编辑 `unsupported_questions`。删除前说明影响并取得确认。
- 返回：`affected_question_ids`、新 `version`、`impacts`。换题型会生成新题目 ID，历史答卷仍关联旧 ID；下次写入前重新 `form_get_context`。

### `form_get_checkin_config` / `form_update_checkin_config`

- 读取请求：`file_id`；返回 `config`（`mode`、`options`、`require_nickname`、`require_image`、`require_location`、`allow_repeat`）和 `base_version`。`allow_repeat` 是重复**打卡**设置，不是周期收集。
- 更新请求：`file_id`、`base_version`、`patch`。`patch.update_fields` 只允许上列配置字段；切换打卡方式用 `CHECKIN_MODE_ONE_TAP` / `CHECKIN_MODE_OPTIONS` 完整枚举，选项模式至少两项有效选项。返回回读的 `config` 和 `version`。

### `form_get_following_config` / `form_update_following_config`

- 读取请求：`file_id`；返回 `config.example_remark`（接龙“填写备注”预设文案，不是用户已提交内容）及 `base_version`。
- 更新请求：`file_id`、从读取结果原样回传的 `base_version`、完整 `config`（`example_remark` 可设为空以清除预设）。返回回读的 `config`、新 `version`。

### `form_get_periodic_config` / `form_update_periodic_config`

- 读取请求：`file_id`；返回当前 `config`，`enabled=false` 表示未启用。
- 更新请求：`file_id`、**完整替换**的 `config`，**不传** `base_version`；先读再预览并保留用户未要求改变的字段。`config.enabled=true` 时需设置 `pattern`（日/周/月）、`days`（每日留空，周日=0 至周六=6，月为 1–31）、`allowed_start_seconds`、`allowed_end_seconds`（当日秒数）、`reminder`；可选 `start_time_unix_seconds`、`end_time_unix_seconds`，提前提醒时设置 `reminder_before_minutes`。返回回读的 `config`。
- 仅普通表、问卷、文件收集、打卡支持；投票、接龙不支持。周期设置与打卡方式分属不同工具。
- 枚举取值（必须是完整枚举名，经实测）：

| 字段 | 展示含义 | 取值 |
|---|---|---|
| `pattern` | 每天 | `PERIODIC_PATTERN_DAILY`（`days` 留空） |
| `pattern` | 每周 | `PERIODIC_PATTERN_WEEKLY`（`days` 为 0–6，周日=0） |
| `pattern` | 每月 | `PERIODIC_PATTERN_MONTHLY`（`days` 为 1–31） |
| `reminder` | 不提醒 | `PERIODIC_REMINDER_NONE` |
| `reminder` | 开始时提醒 | `PERIODIC_REMINDER_AT_START` |
| `reminder` | 提前提醒 | `PERIODIC_REMINDER_BEFORE`，同时填 `reminder_before_minutes`（10、15 或 30） |

- `enabled=true` 时 `pattern`、`reminder` 均必填；`reminder` 只能是 `NONE`、`AT_START`、`BEFORE` 三者之一，其他取值（如 `BEFORE_START`、`AT_END`）会被拒绝。`enabled=false` 即关闭周期，其他字段可省略。
- 每天允许填写时段用秒数表示（距当天 00:00），`allowed_end_seconds` 必须大于 `allowed_start_seconds`；周/月周期的 `days` 不能为空。

## 提交与统计（六个工具）

### `form_get_result_overview`

- 请求：`file_id` 或 `file_url`；可选 `scope`（`time_range` 或 `cycle_collect_time`，默认全量；文本/题目筛选不影响概览）。
- 返回：`meta`、`filled_submissions`（有效提交份数）、`filled_users`（去重人数）、`deleted_submissions`、`unfilled_users`、`recycle_trends`、来源/设备分布、`analyzable_fields`、`collection_status`、`effective_scope`、`limit`；仅在 `attachment_storage_size_available=true` 时使用 `attachment_storage_size_bytes`。`total_submissions` 是有效份数兼容字段，不是填写人数。

### `form_get_question_stats`

- 请求：`file_id` 或 `file_url`，`questions[]`（必填 1–10 项，`question_id`，矩阵/表格子题另传 `sub_question_id`），可选 `scope`、`top_n`（不超过 50）。
- 返回：`stats[]` 中的 `submitted`、`missing`、`options[]`（`count` 和范围 0–1 的 `rate`）、单题 `limit`；顶层还有整体 `limit`。截断时可展示已返回项并标明“仅前 N 项”，不可宣称完整分布；不支持的题型按 `unsupported_reason` 说明。

### `form_query_records`

- 请求：`file_id` 或 `file_url`；可选 `scope`（时间/周期、搜索词、`question_filters`）、`return_questions[]`（最多 20 项；不传仅返回记录元信息）、`page`（`page_size` 最大 100，下一页传 `page.cursor`）。
- 返回：`records[]`（提交者/时间以及白名单内答案**摘要**）、`page.has_more`、`page.next_cursor`、`page.total_is_known`、`limit`。仅在 `total_is_known=true` 时使用 `page.total`；附件/长文本可能截断。不要为做概览自动翻页拉取全量个人答案。

### `form_attachment_summary`

- 请求：真实全局 `file_id` 或完整 `file_url`；可选 `question_ids[]`（最多 50，空为全部附件题）。
- 返回：`data_complete`、`unavailable_reason`、`total_submission_count`、`questions[]`（`submitted_count`、`missing_count`）、`ignored_question_ids`、`storage_size_available` / `storage_size_bytes`。仅 `data_complete=true` 时使用计数；这是**提交次数**，不是去重人数或文件个数，不返回谁缺交附件。容量只在 `storage_size_available=true` 时使用。

### `form_submission_checklist`

- 请求：真实全局 `file_id` 或完整 `file_url`；必填 `scope`（`SUBMISSION_SCOPE_SUBMITTED` / `SUBMISSION_SCOPE_UNSUBMITTED`）和 `page_size`（1–200；分页只对已提交名单生效），可选 `cursor`（下一页传上次 `next_cursor`）。
- 返回：`names_available`、`unavailable_reason`、`members[]`（最小化姓名和提交时间）、`total_count`、`has_more`、`next_cursor`。已提交 `total_count` 为**去重人数**，未提交为未交人数；未交名单依赖应交人群基线，仅个人版支持；匿名表 `names_available=false` 时不展示姓名。**这是整表名单，不是单道附件题缺交名单**。

### `form_get_cross_analysis`

- 请求：真实全局 `file_id` 或完整 `file_url`；`row_fields[]`、`col_fields[]` 同时留空为发现模式，选定后每侧最多 5 个字段。`CrossField` 含 `question_id`，矩阵/表格选择列须带 `sub_id`。
- 返回：`analyzable_fields`、`data_complete`、`unavailable_reason`、`total_records`、`tables[]`（只有 `data_complete=true` 时有效）、`limit_detail`、`unsupported_fields`。发现模式不聚合，`total_records=0` **不能断言无人提交**。只支持离散选项；超限先看 `limit_detail`，必要时减少字段或选更低基数的选项。交叉格 `cells[].count` 是提交记录次数，不是去重人数。

只读发现模式示意：

```bash
mcporter call "form-mcp" "form_get_cross_analysis" --args '{"file_id":"<真实全局 file_id>"}'
```

## 不可用状态与输出

- `limit.over_limit`、`limit.unsupported_reason` 非空：不推断统计为零；`limit.is_truncated`：只陈述已返回的部分，不推断完整分布。
- 附件和交叉分析 `data_complete=false`：依据 `unavailable_reason` 区分计算中、环境不支持、字段不支持、超限、超时等；不输出默认计数或空矩阵。
- 名单 `names_available=false`：不输出姓名；没有应交人群基线、匿名、超时或服务异常按 `unavailable_reason` 如实说明，不凭空编造名单。超时不自动重试或改用别的工具拼全量结果。
- 回答时区分“提交份数/人次”“去重填写人数”“附件文件数（本接口不提供）”，仅使用回答所需的最少个人信息；引用收集表链接只能使用工具返回值。
