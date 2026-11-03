---
slug: cross-border-ecommerce-product-analysis
name: 跨境电商选品分析
description: 自动爬取跨境电商平台榜单、智能计算利润、排查侵权风险、分析竞品与市场机会，一键生成专业完整的选品决策报告
version: 1.0.0
author: 张峰
tags:
- 跨境电商
- 选品分析
- 榜单分析
- 利润计算
- 侵权查询
- 竞品分析
- 选品报告
skill:
  inputs:
  - label: 目标电商平台
    key: platform
    type: select
    required: true
    options:
    - 亚马逊
    - Temu
    - TikTok Shop
    - 速卖通
    - SHEIN
  - label: 类目或关键词
    key: keyword
    type: string
    required: true
  - label: 目标国家
    key: country
    type: string
    required: true
  - label: 采购成本（元）
    key: cost
    type: number
    required: false
  - label: 物流方式
    key: logistics
    type: select
    required: false
    options:
    - FBA
    - 自发货
    - 虚拟海外仓
  prompt: 你是资深跨境电商选品分析师，根据用户提供的平台、关键词、国家、采购成本与物流方式，完成全流程专业选品分析：1.榜单分析：自动抓取热销榜、新品榜、飙升榜，统计价格、销量、评分、评论数、竞争程度与市场趋势；2.利润计算：结合平台佣金、物流、广告、售后、采购成本，精确核算毛利率、净利率、ROI、回本周期与盈亏平衡点；3.侵权风险排查：对商标、专利、版权进行检索判断，划分风险等级并给出规避建议；4.竞品分析：分析头部卖家占有率、用户差评痛点、差异化机会与改良空间；5.输出完整报告：包含市场数据、利润明细、风险评估、竞争分析、运营建议与最终推荐结论，内容专业清晰、结构完整、可直接用于运营决策。
---