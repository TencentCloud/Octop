---
name: ecommerce-user-profiling
description: >-
  用户画像专家包。适用于用户画像、电商零售用户画像工作流：从行为数据接入、客户分层与 RFM 分群、电商 LTV/复购/会员深度建模、
  到把画像激活为广告投放人群和店铺个性化运营、基于订单/CRM/行为数据、输出可直接落地到投放与精准营销的画像与人群等场景；
  也适用于用户明确要求调用「用户画像 / 用户画像专家包 / user-profiling」。
version: 1.0.0
metadata:
  author: SkillHub
  package_type: meta-skill
  display_name: 用户画像
  aliases:
    - 用户画像
    - 用户画像专家包
    - 用户画像技能包
    - ecommerce-user-profiling
    - user-profiling
orchestration:
  children:
    - user-behavior-analytics
    - ai-intelligent-customer-segmentation
    - rfm-segmenter
    - customer-lifetime-value-optimizer
    - audience-segmentation-analyst
    - customer-retention
compatibility: SkillHub meta-skill, exportable to Claude Code / Codex markdown skill.
---
# 电商零售 / 用户画像 工作流

你现在要为一个电商业务构建**用户画像**——基于订单、行为、会员/CRM 数据，完成「数据接入 → 多维分群 → RFM/LTV 建模 → 画像激活到投放与运营」的完整闭环。你已安装以下 6 个 Skill，请按步骤串联使用。

## 步骤 1：行为数据接入与口径核对（输入层）
使用 **电商用户行为分析** 完成：
- 读取目标周期内的电商用户行为、活跃趋势、留存变化及现有画像字段
- 校对时间范围、粒度（日/周/月）、用户口径（新客/老客/会员等级），保证下游分析口径一致
- 同时让用户提供订单明细（CSV/Excel：用户ID、下单时间、订单金额、商品类目、退款标记）和会员表（用户ID、会员等级、注册时间），AI 直接读取这两份表

输出：标准化的事件表 + 订单明细 + 会员表，统一以 `user_id` 为主键，存到 `data/profile_input/`。

## 步骤 2：通用客户分层与精准营销分群（分析层 - 主分群）
使用 **Ai Intelligent Customer Segmentation** 基于步骤 1 的数据完成：
- 对全量用户做客户分层（高价值/中价值/低价值/沉睡/新客/流失）
- 输出 RFM 三维度的初步打分，并按分层给出精准营销建议（拉新/激活/留存/赢回）
- 标注每一层的核心特征：客单价、复购率、品类偏好、活跃时段

输出：`segments_overview.csv`（用户ID + 分层标签 + RFM 分数）+ `segment_strategy.md`（每层运营建议）。

## 步骤 3：RFM 专项细分 + 重点人群识别（分析层 - RFM 专项）
使用 **RFM Segmenter** 在步骤 2 的基础上对 RFM 做精细化拆分：
- 按 R（最近购买时间）、F（频次）、M（金额）做更细粒度的 8~10 类细分（VIP、高价值流失风险、潜力新客、休眠买家、低价值高频等）
- 重点识别三类人群：①VIP 客户（高 R 高 F 高 M）②流失风险客户（高 F 高 M 但 R 衰减）③休眠买家（曾高频但已多周期未购）
- 为每类人群产出针对性再激活策略与首选触达渠道

输出：`rfm_segments.csv`（带细分标签）+ `key_audience_strategy.md`（VIP / 流失风险 / 休眠 三类人群专项策略）。

## 步骤 4：电商 LTV / 复购 / 会员深度建模（分析层 - LTV 专项）
使用 **Customer Lifetime Value Optimizer** 基于订单明细 + 会员表完成：
- 按"复购行为、毛利质量、会员深度、流失/退货风险"四个维度对用户分群
- 估算各群体的 LTV 区间、预期复购周期、退货损耗
- 把"粗糙的订单历史"转化为带优先级的客户营销动作清单

输出：`ltv_segments.csv`（用户ID + LTV 区间 + 复购周期 + 风险等级）+ `ltv_action_priorities.md`（按 LTV 优先级排序的营销动作）。

## 步骤 5：把画像激活为广告投放人群（输出层 - 拉新侧）
使用 **Ads Audience Targeting** 基于步骤 2~4 产出的分群结果完成：
- 为 Meta（Facebook/Instagram）、Google Ads、TikTok Ads、YouTube Ads 及 DSP 程序化广告分别设计受众包
- 区分三类投放目标：①拉新（高 LTV 群体的 Lookalike）②召回（流失风险与休眠人群的再营销）③留存（VIP 客群的相似扩展）
- 给出每个广告平台对应的人群定向描述、关键兴趣词、相似受众种子建议

输出：`ads_audiences.md`（按平台分章节的投放受众包说明）。

## 步骤 6：把画像激活为客户留存与召回（输出层 - 店铺侧）
使用 **Customer Retention** 基于步骤 2~4 的分群完成：
- 为店铺侧设计留存与召回运营方案：会员权益、召回券、复购提醒、分群 EDM/短信触达内容
- 按 RFM 与 LTV 分层，分别给出客户生命周期策略（如 VIP 走专属权益；休眠人群走召回券 + 强提醒；高潜新客走二单转化）
- 输出可交付到店铺运营/CRM 系统的执行清单

输出：`customer_retention_playbook.md`（按人群分层的留存、召回与复购触达 SOP）。

## 最终输出
将以上步骤的结果整合为一份完整的电商用户画像与激活方案，交付以下文件：

1. **`data/profile_input/`**：标准化输入数据（事件表、订单表、会员表）
2. **`segments_overview.csv` + `segment_strategy.md`**：通用分层与运营建议
3. **`rfm_segments.csv` + `key_audience_strategy.md`**：RFM 细分与三类重点人群策略（VIP / 流失风险 / 休眠）
4. **`ltv_segments.csv` + `ltv_action_priorities.md`**：LTV 分群与优先级动作清单
5. **`ads_audiences.md`**：跨平台广告投放人群包（Meta / Google / TikTok / YouTube / DSP）
6. **`customer_retention_playbook.md`**：客户留存与召回 SOP（权益 + EDM + 分层触达）
7. **`user_profiling_report.md`**：一份汇总画像报告，包含核心人群结构、TOP 群体特征卡、三类重点人群（VIP / 流失风险 / 休眠）的画像速览，以及拉新/留存/召回三套激活方案概览。
