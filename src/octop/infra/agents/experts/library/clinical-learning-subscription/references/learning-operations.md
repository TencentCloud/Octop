# 指南学习操作细则

本文件承载学习轨道创建、预览投递、重复漏发排查与新版本迁移的脚本命令与约束。流程入口与分流见 `skills/guideline-learning/SKILL.md`。

## 轨道创建

先核验权威文件完整名称、发布机构、版本、来源链接和来源修订标识。没有原文时只给候选学习地图，不能建成可正式投递的轨道。

### 1. 保存学习目标（可选）

先复述目标、每日可投入时间、目标日期和用途；用户确认后调用：

    python ../../scripts/clinical_profile.py learning-goal-save \
      --label <学习目标> --kind <exam|work_review|update_tracking|teaching|custom> \
      --daily-minutes <5-240> --target-date <YYYY-MM-DD，可省略> \
      --priority <0-100> --goal-id <稳定slug，可省略> --confirm true

### 2. 创建草稿轨道

用户确认选择该指南后调用：

    python ../../scripts/clinical_profile.py learning-track-create \
      --label <指南完整名称> --publisher <发布机构> --version <版本/年份> \
      --source-url <权威原文URL> --source-revision <版本或发布日期> \
      --goal-id <已保存目标ID，可重复> --track-id <稳定slug，可省略> --confirm true

创建轨道不等于立即推送，也不等于已启用。

### 3. 保存固定章节单元

把已核验的章节拆为连续编号单元。每个单元必须有：ordinal、title、source_anchor、至少一个 objectives、可选 topic_tags、estimated_minutes。只保存课程结构和来源锚点，不复制指南全文。

调用 learning-track-lessons-replace 前先向用户展示候选章节顺序并取得确认。该命令保留已确认送达单元，不能改写发送中/状态不明/已送达单元。

    python ../../scripts/clinical_profile.py learning-track-lessons-replace \
      --track-id <轨道ID> --replace-pending true --confirm true \
      --lesson-json '{"id":"<单元ID>","ordinal":1,"title":"<章节主题>","source_anchor":{"section":"<章节>","locator":"<小节>"},"objectives":["<学习目标>"],"topic_tags":["<主题>"],"estimated_minutes":10}'

为每个单元重复追加一个 --lesson-json。编号从 1 连续，同一轨道内不能重复章节单元。

### 4. 启用/暂停

用户确认计划和节奏后启用：

    python ../../scripts/clinical_profile.py learning-track-activate --track-id <轨道ID> --confirm true

多条活跃轨道先让用户选择，不用默认猜测抢占。暂停/归档保留历史：

    python ../../scripts/clinical_profile.py learning-track-set-status --track-id <轨道ID> --status <paused|archived> --confirm true

## 预览与投递

### 预览（不计进度）

读取下一单元但不写状态：

    python ../../scripts/clinical_profile.py learning-next-lesson --track-id <轨道ID>

正文首行写【格式预览｜不计入学习进度】。预览不调用投递领取、定时任务手动触发、送达确认或 guideline-advance。

### 正式投递（弱投递防重协议）

当前用通用 agent cron 投递，必须严格按顺序，任何一步失败即停止且不输出正文：

1. 取今天日期（Asia/Shanghai，YYYY-MM-DD），运行 `python3 scripts/clinical_profile.py delivery-check --logical-date <今天>`。`already_sent` 为 true 时回复"今日学习内容已推送"并停止，不得重复生成。
2. 运行 `python3 scripts/clinical_profile.py learning-next-lesson` 读取下一固定单元。无已启用轨道或无下一单元时如实说明并停止，不得编造内容。
3. 按 daily-learning-template.md 生成该单元（恰好 3 个编号要点、下一单元预告、来源行），再运行 `python3 scripts/validate_output.py --module daily_guideline_learning` 校验；不通过先修正再校验一次，仍不通过则停止并说明原因。
4. 校验通过后运行 `python3 scripts/clinical_profile.py delivery-record --logical-date <今天> --confirm true` 记账（同时标记该单元已投、推进到下一单元），然后输出正文。正文首行 `【每日指南学习｜{主题}】（第 {ordinal}/{total} 单元）`。

诚实口径：账本只防重复，不代表通道真的受理——不得对用户说"已确认送达"。创建任务时用 cron-presets.json 中"每日指南连续学习"预设的 prompt（已内嵌以上规程）。

### 强回执状态机（迁移目标）

具备真实通道回执的平台投递适配器上线后，正式投递必须遵守状态机：读取轨道 → 原子领取下一单元 → 生成并安全校验 → 通道实际发送 → 收到通道回执 → 确认送达并解锁下一单元。

- 平台投递服务必须原子领取固定单元，按任务标识/逻辑日期/目标通道去重；模型不能提供或伪造这些输入。
- 只有具备真实通道回执的发送适配器才能把投递标为已受理并解锁下一单元；专家包工作区不保存可信送达账本，也不向模型暴露投递生命周期命令。
- 不得由模型/普通 cron/内容已生成自行确认送达；不得再调用 guideline-advance。
- 发送失败可记录为可重试；发送中断或回执不明必须标 unknown 并先对账，不能盲目重发或跳过。
- 已确认送达只表示内容被通道受理，不表示用户已阅读/掌握/具备临床胜任力。

当前弱投递模式只防重复、不代表送达回执，是强回执上线前的过渡方案。

## 重复/漏发排查与新版本迁移

### 内容重复

重复根因几乎总是没有按固定单元推进，而是重新生成了内容。处理顺序：

1. 运行 `python ../../scripts/clinical_profile.py get`，读取该轨道单元列表、每个单元 ordinal 与状态。
2. 核对是否存在 ordinal 重复、同一 source_anchor 被拆成多个单元、或多条活跃轨道绑定同一份指南。
3. 向用户说明当前进度（第几单元/共几单元）和已完成单元，指出重复出现在哪里。
4. 需要调整时用 learning-track-lessons-replace 修正未送达单元，保留已确认送达单元；不得改写发送中/状态不明/已送达单元。

绝不能用"换一个单元补发"掩盖重复。同一单元未确认送达前不得当新内容重发。

### 漏发

当前每日指南学习是弱投递（通用 cron 执行即视为已投，无通道回执）。用户反馈漏发时：

- 先运行 `python3 scripts/clinical_profile.py delivery-check --logical-date <当天>` 核对账本：有记录而用户没收到，说明 cron 执行了但通道未送达——如实说明这是弱投递限制；无记录则说明当天未执行。
- 可为用户补发当日单元：在当前对话按模板生成当天单元（账本已有记录，不要再调 delivery-record 重复记账；补发正文首行标注【每日学习补发】）。
- 不要归因为"已发送但用户没看到"，也不要调用 guideline-advance 推进。
- 反复漏发时如实告知：等具备通道回执的平台投递适配器上线后才能保证送达。

### 新版本指南迁移

发现新版本指南时，不得静默覆盖旧轨道、旧学习单元或既有投递账本。先给出旧/新版本、已送达单元、受影响章节和新增规划需求；用户确认后创建新的草稿轨道，保留旧轨道历史，再重新核验和规划新单元。
