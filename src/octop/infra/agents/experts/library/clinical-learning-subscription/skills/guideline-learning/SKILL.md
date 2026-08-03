---
name: guideline-learning
description: 为医生组织教育用途的版本化指南学习轨道、章节单元、学习预览和受回执保护的正式投递。不得生成诊疗方案、疾病 SOP、急诊行动卡、个体患者建议或药物剂量说明。
---

# 指南学习轨道与每日单元

## 必读边界

起草内容前，必须阅读并遵守：

- ../../USER.md
- ../../references/compliance-boundary.md
- ../../references/source-policy.yaml
- ../../references/department-queues.md
- ../../references/output-templates.md
- ../../references/daily-learning-template.md
- ../../references/learning-track-template.md

## 先判断请求类型

本 skill 处理指南学习轨道、固定章节单元、下一单元预览和正式订阅课程。

- 用户要求评估掌握情况、做教育性小测、建立学习地图，或学习指南中的诊断标准/鉴别框架时，使用 guideline-learning-diagnosis skill。
- 用户要求展开某一章节、细看原文、或把指南整理成学习顺序/路径时，使用 guideline-section-expansion skill。
- 用户说明备考或岗位目标、要求按考试推荐教材时，使用 exam-material-recommendation skill。
- 用户说看看效果、预览、测试推送、展开本章或给我学习地图时，属于只读预览；不得创建投递账本或推进状态。
- 用户要保存长期计划时，先得到明确确认，再保存学习目标、轨道和章节单元。
- 用户要正式订阅时，除用户确认外还需要有具备真实通道回执的发送适配器。当前普通 agent cron 没有该回执能力，不能假称正式送达或自动推进。

## 读取状态

USER.md 只是自动生成的只读摘要。任何保存、领取、发送或状态判断都先调用：

    python ../../scripts/clinical_profile.py get

不要把第几天、聊天摘要或旧的 current_guideline 当作真实进度。读取 learning.tracks、learning.goals 和 delivery_ledger 的状态；只向用户展示轨道、版本、下一单元和可理解的进度，不展示账本 ID、令牌、哈希或通道会话信息。

个性化学习目标和轨道可以在用户确认后保存，不必强制完成 5 项医生登记。只有按科室、地区、职称定制或开启地区/微信订阅时，才按 doctor-registration 要求获取必要档案与同意。

## 创建一个可持续学习轨道

先核验权威文件的完整名称、发布机构、版本、来源链接和来源修订标识。没有原文时只给候选学习地图，不能建成可正式投递的轨道。

### 1. 保存学习目标（可选但推荐）

先复述将保存的目标、每日可投入时间、目标日期和用途；用户明确确认后才调用：

    python ../../scripts/clinical_profile.py learning-goal-save \
      --label <学习目标> --kind <exam|work_review|update_tracking|teaching|custom> \
      --daily-minutes <5-240> --target-date <YYYY-MM-DD，可省略> \
      --priority <0-100> --goal-id <稳定slug，可省略> --confirm true

### 2. 创建已核验来源的草稿轨道

用户确认选择该指南后才调用：

    python ../../scripts/clinical_profile.py learning-track-create \
      --label <指南完整名称> --publisher <发布机构> --version <版本/年份> \
      --source-url <权威原文URL> --source-revision <版本或发布日期> \
      --goal-id <已保存目标ID，可重复> --track-id <稳定slug，可省略> \
      --confirm true

创建轨道不等于立即推送，也不等于已启用。

### 3. 保存固定章节单元

把已核验的章节拆为连续编号的单元。每个单元必须有：ordinal、title、source_anchor、至少一个 objectives、可选 topic_tags、estimated_minutes。只保存课程结构和来源锚点，不复制指南全文。

调用 learning-track-lessons-replace 前，先向用户展示候选章节顺序并取得确认。该命令会保留已确认送达的单元，不能改写发送中、状态不明或已送达单元。

    python ../../scripts/clinical_profile.py learning-track-lessons-replace \
      --track-id <轨道ID> --replace-pending true --confirm true \
      --lesson-json '{"id":"<单元ID>","ordinal":1,"title":"<章节主题>","source_anchor":{"section":"<章节>","locator":"<小节>"},"objectives":["<学习目标>"],"topic_tags":["<主题>"],"estimated_minutes":10}'

为每个单元重复追加一个 --lesson-json。编号必须从 1 连续，且同一轨道内不能重复章节单元。

### 4. 启用轨道

用户确认计划和节奏后调用：

    python ../../scripts/clinical_profile.py learning-track-activate --track-id <轨道ID> --confirm true

如果用户有多条活跃轨道，先让其选择；不要用默认猜测抢占另一条轨道。

用户明确要求暂停或归档时，保留历史并调用：

    python ../../scripts/clinical_profile.py learning-track-set-status \
      --track-id <轨道ID> --status <paused|archived> --confirm true

## 预览与正式投递

### 预览

读取下一单元但不写状态：

    python ../../scripts/clinical_profile.py learning-next-lesson --track-id <轨道ID>

正文首行写【格式预览｜不计入学习进度】。预览不调用投递领取、定时任务手动触发、送达确认或旧的 guideline-advance。

### 正式投递协议（弱投递模式）

当前用通用 agent cron 投递，**必须严格按以下顺序执行，任何一步失败即停止且不输出正文**：

1. 取今天日期（Asia/Shanghai，YYYY-MM-DD），运行 `python3 scripts/clinical_profile.py delivery-check --logical-date <今天>`。`already_sent` 为 true 时回复"今日学习内容已推送"并停止——**不得重复生成**，这是防重复推送的闸门。
2. 运行 `python3 scripts/clinical_profile.py learning-next-lesson` 读取下一固定单元。无已启用轨道或无下一单元时如实说明并停止，不得编造内容。
3. 按 `../../references/daily-learning-template.md` 生成该单元（恰好 3 个编号要点、下一单元预告、来源行 `来源：名称：[链接](URL)`），再运行 `python3 scripts/validate_output.py --module daily_guideline_learning` 校验；不通过先修正再校验一次，仍不通过则停止并说明原因。
4. 校验通过后运行 `python3 scripts/clinical_profile.py delivery-record --logical-date <今天> --confirm true` 记账（同时把该单元标记为已投、推进到下一单元），然后输出正文。正文首行 `【每日指南学习｜{主题}】（第 {ordinal}/{total} 单元）`。

**诚实口径**：这个账本只防重复，不代表微信真的受理了——不得对用户说"已确认送达"。用户反馈漏发时如实说明这是弱投递（以 cron 执行为准），可为其补发当日单元；反馈重复时先读账本核对。

创建任务时使用 `../../references/cron-presets.json` 中"每日指南连续学习"预设的 prompt（已内嵌以上规程）。等具备通道回执的平台投递适配器上线后，应迁移到强回执协议（领取→生成→校验→发送→回执→确认解锁）。

## 选题、来源和内容边界

选题优先级：

1. 本科室常见、高频、基层真实需要复习的主题。
2. 高风险识别和转诊知识，但只能作为学习内容，不写成行动卡。
3. 检查、报告、质控、慢病管理、专业规范等适合学习订阅的内容。
4. 经权威信源核验的近期专业更新。

最终依据只能使用 source-policy.yaml 中允许的权威信源。正常学习内容必须包含至少一个权威原文页面或正式附件链接，格式为：来源：文件或页面名称：[链接](URL)。找不到权威原文时明确待人工复核，不得编造来源。

允许讲解适用范围、学习目标、核心概念、风险意识、质控指标、报告/随访要求的学习性说明、流程概念和信源追溯。禁止输出个体患者诊断或治疗建议、任何药物剂量、急诊行动卡、疾病 SOP、医院流程改造或 HIS 配置建议。

## 内容重复与漏发的排查口径

用户反馈「每天推的内容重复」或「今天没收到」时，先读取真实状态再回答，不要凭印象解释，也不要立刻补发。

### 内容重复

重复的根因几乎总是**没有按固定单元推进**，而是重新生成了内容。处理顺序：

1. 运行 `python ../../scripts/clinical_profile.py get`，读取该轨道的单元列表、每个单元的 ordinal 与状态。
2. 核对是否存在 ordinal 重复、同一 source_anchor 被拆成多个单元、或多条活跃轨道绑定了同一份指南。
3. 向用户说明当前进度（第几单元 / 共几单元）和已完成单元，指出重复出现在哪里。
4. 需要调整时，用 `learning-track-lessons-replace` 修正**未送达**单元，并保留已确认送达的单元。不得改写发送中、状态不明或已送达单元。

绝不能用「换一个单元补发」来掩盖重复：那会同时打乱顺序并产生新的跳段。同一单元在未确认送达前也不得被当作新内容重发。

### 漏发

当前每日指南学习是**弱投递**（通用 cron 执行即视为已投，无通道回执）。用户反馈漏发时：

- 先运行 `python3 scripts/clinical_profile.py delivery-check --logical-date <当天>` 核对账本：有记录而用户没收到，说明 cron 执行了但通道未送达——如实说明这是弱投递限制；无记录则说明当天未执行。
- 可以为用户**补发当日单元**：在当前对话按模板生成当天单元（此时账本已有记录，不要再调 delivery-record 重复记账；补发正文首行标注【每日学习补发】）。
- 不要归因为「已发送但用户没看到」，也不要调用 guideline-advance 推进。
- 反复漏发时如实告知：等具备通道回执的平台投递适配器上线后才能保证送达。

## 输出与校验

使用 daily-learning-template.md：

- 正好 3 个编号要点。
- 包含下一单元预告。
- 标明轨道、已固定的指南版本、学习单元序号/总数、章节和关联目标。
- 不设置自测题，也不提示之后公布答案。
- 默认 600-900 字，最多 1000 字。
- 内容必须是学习拆解，而不是临床处置建议。

发送或提供正式草稿前运行：

    python ../../scripts/validate_output.py --module daily_guideline_learning

校验失败时先修正；不得绕过。
