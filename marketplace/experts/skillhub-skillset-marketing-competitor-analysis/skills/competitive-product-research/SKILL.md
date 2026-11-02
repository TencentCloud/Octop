---
name: competitive-product-research
slug: competitive-product-research
version: 1.4.8
displayName: 竞品调研 · CPR
description: >-
  Dual-track competitive research: experience benchmarking (8 UX dimensions) + strategic diagnostics (SWOT/Five Forces/PESTLE), source-traceable HTML or Markdown report.
  Use when competitive analysis, benchmarking, differentiation strategy, or when the user says「竞品调研」「对标分析」「和 XX 比差在哪」.
---

# 竞品调研 · Competitive Product Research

> **EN** Dual-track benchmarking + strategy → source-traceable HTML / Markdown (`SRC-xxx`).  
> **中文** 体验对标 + 战略诊断 → 证据可溯源 HTML / Markdown 报告。

**When / 何时用：** 对标 · 差异化 · SWOT/五力/PESTLE · 评审前材料  
**Not / 不用：** 拍脑袋市场规模 · 纯概念战略 · 违规采集 · 替用户拍板

```text
Our app post conversion is 3% — benchmark Xiaohongshu vs Instagram, first-post funnel.
我们 App 发帖转化率 3%，对标小红书与 Instagram 分析首链路。
```

也可「帮我做 XX 和 YY 竞品调研」/ "benchmark X against Y" — 先清单，再报告。

## 可直接触发的说法

以下口语输入都应触发本技能，不要求用户先按模板填写：

- 帮我拉一版 XX 和 YY 的竞品对标。
- 我们这个功能和小红书/抖音比差在哪？
- 对标一下竞品的首单/发布/开户/投顾链路。
- 我只有几张截图，先帮我做一版体验差异分析。
- 这个 PRD 评审前需要一份竞品材料。
- 帮我判断这个赛道里我们该学谁、不该学谁。
- 竞品最近这么做背后的策略是什么？
- 给我一份能给老板看的竞品 HTML 报告。

## 最小可用输入

**最低可启动**：调研目标 + 至少 1 个明确竞品。若只有 1 个竞品，先询问是否需要补第 2 个；用户不补时，可用“我方方案/行业常见做法”作为对照，并在报告中标注对照口径。

**推荐输入**：调研目标、对标对象、我方现状、核心场景、报告用途、输出格式、可用材料（链接/截图/PRD/数据）。

**可兼容输入**：

- 一句话需求：先提炼目标、对象、场景，再给采集清单。
- 截图/链接/碎片材料：先建证据索引，缺口标 `SRC-GAP`。
- 中英混合或口语输入：保持用户原意，统一为调研参数。
- 用户说“直接生成”：只跳过业务信息追问，用保守假设继续，并在报告首屏标注假设；**不视为跳过输出格式确认**。

## 工作流

```text
1) 提交调研需求  2) 信息采集清单  3) 问题对齐 + 证据建库
4) 双轨分析（体验八维 + 战略四件套）  5) 按用户选择生成 HTML / Markdown 报告
```

### 信息采集清单（第 2 步）

预填 +「待补充」；可说「跳过，直接生成」。

```text
1️⃣ 调研目标  2️⃣ 对标对象（至少 1 个，推荐 ≥2）  3️⃣ 我方现状  4️⃣ 核心场景  5️⃣ 行业
6️⃣ 补充材料  7️⃣ 战略模块（格局/SWOT/五力/PESTLE）  8️⃣ 报告用途（内部/对外脱敏）
9️⃣ 输出格式（HTML / Markdown）  🔟 约束条件
```

**采集交互（优先使用可操作表单）**：

- **必须复用** [assets/intake-form.html](assets/intake-form.html)，不得临时重写表单 UI。
- 将上下文预填为 `prefill` URL 参数（URI 编码 JSON）；推断值不得伪装成用户确认值，输出格式保持未选。
- 宿主支持内嵌 HTML 时直接展示；否则复制该资产到当前输出目录并用浏览器打开。提交后读取宿主回传或用户粘贴的结构化参数。回传统一使用 `{schema_version:"1.0", skill, action, data}`；优先 `window.codex.submitForm`，兼容 `window.openai.sendFollowUpMessage`，最后复制 JSON。
- 仅当宿主无法展示或打开 HTML 时退回文本清单；格式未确认不得生成，用户明确委托默认时使用 HTML。

## 方法概要

双轨四层法详规 → [research-playbook.md](references/research-playbook.md)

- **体验轨（八维）**：竞品怎么做、我方差在哪 → D1–D8，先拆最小操作节点
- **战略轨（可选）**：赛道为何如此、我方怎么打 → 格局 · SWOT · 五力 · PESTLE
- **证据**：每条关键结论挂 `SRC-xxx`（U 用户 / P 公开 / H 经验须标验证）

## 输出

按采集表确认的格式生成：HTML 严格使用 [report-template-pro.html](references/report-template-pro.html)；Markdown 使用同一分区结构。格式锁、事实边界、文风、自检 → [research-playbook.md](references/research-playbook.md)。

必含：对标表 · Key Findings · 路线图（Owner/优先级）· Source Index · 免责声明。对外分享须脱敏。

HTML 报告中的公开来源证据标签必须可点击并直接打开对应 URL；同一单元格有多个来源时，每个 `SRC-xxx` 分别生成链接，禁止合并成一个不可点击的标签。无 URL 的用户材料、行业推断和证据缺口链接到 Source Index 内对应条目，并明确标注其类型。

## 硬约束

- **信息优先**：禁止编造；缺失标注；推断透明；清单追问优于脑补
- **证据**：关键结论至少一个 `SRC-xxx`；HTML 的公开来源 `SRC-xxx` 必须直接链接来源 URL；体验轨与策略轨不重复
- **输出**：具名、具数、具动作；必有执行建议
- **优先级**：信息优先 > 格式锁 > playbook > 文风护栏

**Rigid**（不可跳过）：
- SRC-xxx 证据标注 · 信息采集清单先行（用户说「跳过」才可省略）· 报告必含对标表 + Key Findings + 路线图 + Source Index + 免责声明

**Flexible**（可按场景调整）：
- 战略模块选择（格局/SWOT/五力/PESTLE 按需求 N/A）· 体验八维可合并相近维度 · 报告格式外的补充附录

## 验收与失败路径

- **清单追问**：≤3 轮未响应 → 标注缺失信息，以保守假设继续
- **对标对象不足**：只有 1 个竞品 → 先询问补充；用户跳过则用我方/行业常见做法作参照并标注限制
- **公开证据不足**：记录 `SRC-GAP`，不写具体数字，给下一步补证动作
- **输入很碎**：先整理为调研参数和证据索引，再分析；不可因格式不标准拒绝
- **完成标准**：报告含 Rigid 必含项 + ≥1 个 SRC-xxx/关键结论 + 路线图有 Owner/优先级
- **失败判定**：无调研目标、无对标对象、也无法从上下文推断，且用户拒绝补充 → 明确告知无法出具有效报告

## 运行时说明

调研工作流由 LLM 执行。修改采集表后运行 `python tests/test_intake_form_contracts.py` 做全表单契约与渲染回归；竞品表单的深度交互回归仍可运行 `python competitive-product-research/scripts/test_intake_form.py`，需本地 Chrome 与 Python 包 `websocket-client`。

## 参考文件

| 文件 | 内容 |
|------|------|
| [references/research-playbook.md](references/research-playbook.md) | 双轨四层法详规 · 事实边界 · 格式锁 · 自检 |
| [references/report-template-pro.html](references/report-template-pro.html) | HTML 报告模板 |
| [assets/intake-form.html](assets/intake-form.html) | 跨 Agent 可复用采集表 UI |
| [scripts/test_intake_form.py](scripts/test_intake_form.py) | 本地 Chrome 表单回归测试 |
