---
name: subscription-setup
description: 学习订阅任务创建与启用。医生完成 5 项登记后，按用户选择创建订阅任务（每日指南连续学习/专业指南更新提醒/地区医保政策变化学习）。平台 cronjob_create 自动绑定当前会话通道投递，无需微信绑定门禁。先查重再创建，回执如实写已启用。
---

# 学习订阅任务创建

## 前置条件

- 5 项登记已完成（称谓、地区、医院、科室、职称），`clinical_profile.py register` 返回 ok: true。
- 未登记时先走 `doctor-registration` skill，不得跳过登记直接创建订阅。

## 可选任务

向用户列出可选任务，让其选择开启哪些（可全选或只选部分）：

1. **每日指南连续学习**：每天 07:30，通用 cron + 弱投递防重规程（无通道回执）。
2. **专业指南更新提醒**：每 3 天一次，按科室、亚专业、职称深度和基层场景检索权威来源更新。
3. **地区医保政策变化学习**：每周二、周五 09:00，摘要登记地区的医保正式文件变化与本地确认提示。

用户回复"全部开启/都开启"→开启 1、2、3；只点名一个或多个→只开点名的；"暂不开启/先不推送"→只保留登记，不创建任务。

## 创建流程

1. **查重**：创建前先 `cronjob_list(include_disabled=true)` 检查已有任务，不得重复创建。
2. **创建**：对每个用户明确选择的任务调用 `cronjob_create`。
   - **平台自动路由**：`cronjob_create` 自动绑定当前会话 `session_key`，并按该会话通道（微信/QQ/dashboard/CLI 等）投递。**不要要求微信绑定、不要以"非微信会话"为由拒绝、不要反问用户是否在微信里**。
   - 直接创建，不需要 `:weixin:` 会话标识，不要求 `allow_dashboard` 之类的门禁。
3. **核对**：创建后调用 `cronjob_list` 核对，回执如实写"已启用，推送至当前会话通道"。
4. **回执**：按 `references/output-templates.md` 的"登记启用回执"模板输出，列出已启用任务（注明推送至当前会话通道）和未启用任务。

任务排程参数（trigger / task_type / prompt）使用 `references/cron-presets.json` 的预设：

- 每日指南学习：`cron:30 7 * * *`，`task_type=agent`，`fresh_thread=true`，prompt 用弱投递防重模板（见下）。
- 专业指南更新提醒：`cron:0 9 */3 * *`，`task_type=agent`。
- 地区医保政策变化学习：`cron:0 9 * * 2,5`，`task_type=agent`。

## 每日指南学习弱投递防重规程

每日指南学习的 cron prompt 必须使用 `references/cron-presets.json` 中"每日指南连续学习"预设的弱投递防重模板，严格按顺序：

1. `delivery-check` 按逻辑日期查重——已记录则当天停发；
2. `learning-next-lesson` 读取下一固定单元——无已启用轨道或无下一单元时如实说明并停止，不得编造内容；
3. 按 `references/daily-learning-template.md` 生成单元（3 个编号要点 + 下一单元预告 + 来源行），用 `scripts/validate_output.py --module daily_guideline_learning` 校验；
4. 校验通过后 `delivery-record` 记账，再输出正文。

该账本只防重复、**不代表送达回执**——不得对用户宣称"已确认送达"。在用户选定权威指南轨道前，cron 运行会如实报告"暂无已启用轨道"并停止，不随机推送。等具备通道回执的平台适配器上线后，每日指南学习应迁移到强回执投递。

## 禁止项

- 未被用户明确选择的任务不得调用 `cronjob_create`，回执中不得写已启用。
- 不得调用 `cronjob_run`、`cronjob_trigger` 或任何手动执行能力进行"首推"。
- 创建订阅不得顺带手动首推或推进学习状态（不得调用 `guideline-advance`）。
- 工具不可用或创建失败时，不得宣称任务已启用；如实说明失败原因并保留登记档案，**不要以"未绑定微信通道"作为回执**。
- 不得宣称弱投递已"确认送达"。

## 边界

本技能只管订阅任务的创建/查重/核对/回执，不负责医生登记（见 `doctor-registration`）、不生成学习内容（见各医学 skill）、不做信源核验。任务是否真正存在以 `cronjob_list` 为准，不以 USER.md 的订阅备注字段判断。
