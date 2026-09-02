---
name: guideline-learning
description: 指南学习流程约束。判断请求类型→读取状态→按流程创建轨道/预览/投递/排查迁移；操作命令与细则见 references/learning-operations.md。选题用权威信源，输出前经 output-format 校验。不生成诊疗/处方/急诊SOP/个体患者建议。
---

# 指南学习流程

## 必读

- ../../USER.md
- ../../references/source-policy.yaml
- ../../references/output-templates.md
- ../../references/daily-learning-template.md

执行轨道创建/预览投递/重复漏发排查/新版本迁移时，再读 `../../references/learning-operations.md`（操作命令与细则，非每次必读）。

## 请求分流

- 评估掌握/教育性小测/学习地图/诊断标准学习 → `guideline-learning-diagnosis`
- 展开章节/学习顺序/路径图 → `guideline-section-expansion`
- 备考选材 → `exam-material-recommendation`
- 学习轨道/预览/投递/重复漏发/新版本迁移 → 本 skill，按 learning-operations.md 对应流程执行

## 读取状态

任何保存/领取/发送/状态判断先调用：

    python ../../scripts/clinical_profile.py get

不把第几天、聊天摘要或旧的 current_guideline 当真实进度。读取 learning.tracks、learning.goals、delivery_ledger；只向用户展示轨道/版本/下一单元/可理解进度，不展示账本 ID/令牌/哈希/通道会话信息。个性化目标轨道可确认后保存，不必强制登记；只有按科室/地区/职称定制或开启订阅才登记。

## 流程约束

1. **创建轨道**：先核验指南完整名称/机构/版本/来源链接/来源修订；用户确认后才保存目标→草稿轨道→固定章节单元→启用。命令与细则见 learning-operations.md。
2. **预览**：读下一单元不写状态；响应必须直接以【格式预览｜不计入学习进度】开头，该标记前不得添加任何文字；不调用投递领取/手动触发/guideline-advance。
3. **正式投递**：弱投递防重协议（delivery-check 查重→读取单元→校验→delivery-record 记账→输出）；账本只防重复不代表送达，不得宣称已确认送达。强回执状态机为迁移目标。细则见 learning-operations.md。
4. **重复/漏发/迁移**：先读真实状态再处理，不凭印象补发；新版本先给迁移方案，确认前不覆盖旧轨道。细则见 learning-operations.md。

## 选题与来源边界

选题优先级：本科室常见高频基层需要 > 高风险识别与转诊知识（只作学习内容，不写行动卡）> 检查/报告/质控/慢病/规范 > 经核验近期更新。

最终依据只用 source-policy.yaml 允许的权威信源；用户明确指定国际指南或国内无覆盖时，按 `international-guideline-source-routes.yaml` 使用国际 A 级正式指南，不得静默覆盖国内现行规范。学习内容必须含至少一个权威原文链接 `来源：名称：[链接](URL)`；A/B 均找不到时可按 `source-verify` 规则披露一次 C 级全网转述，但只能作为待核验背景，不能据此创建正式指南轨道、展开原文或生成精确推荐。允许讲适用范围/学习目标/核心概念/风险意识/质控/报告随访的学习性说明；禁止个体诊疗/药物剂量/急诊行动卡/疾病 SOP/医院流程/HIS。

## 输出语言与校验

**输出语言与格式**：全程使用简体中文；只输出最终正文，不输出思考、推理、检索或执行过程（禁止出现 I'll、Let me、Now running、Validation passed、Here is the answer.、搜索过程、检索日志等过程语句）。执行检索、读 skill、跑脚本和校验时静默；需要向用户确认选项时，也只用简体中文提问，问完即停，不要夹带工具过程句。

发送或提供正式草稿前运行 `python ../../scripts/validate_output.py --module daily_guideline_learning`，失败先修正，不得绕过。校验结果仅供内部控制；通过后直接输出正文，不得向用户输出“校验通过”“为您推送预览内容”等过程说明。四条硬格式与校验流程见 `output-format` skill。
