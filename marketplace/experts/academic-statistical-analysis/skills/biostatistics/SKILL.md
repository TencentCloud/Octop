---
slug: biostatistics
name: biostatistics
displayName: 高级生物统计
version: "1.0.0"
summary: 生物统计与计算分析技能。
description: 生物统计与计算分析技能。全部可通过本机 `python3` 使用。PyMC（完整 MCMC）如需请单独安装。
tags: [设计, 创作工具, 专业服务]
license: MIT
metadata:
  author: AI灵匣
---

# 高级生物统计（Pay Skill）

本 Skill 提供**高级生物统计专业服务**。该服务是基于 **A2M 智能收协议（HTTP 402）的付费资源**：买家（消费者 Agent）向卖家服务端发起资源请求，服务端返回 `402 Payment-Needed` 响应报文，买家将该报文传递给支付宝的 **alipay-payment-skill** 技能完成付款，付款完成后重新请求即可获得完整交付内容。

服务端交付的内容为该服务的**完整工作资产**：经过实际业务验证的提示词工程包、配套模板与参考文档，买家取得后可长期重复使用。

## 服务概述

- **服务名称**：高级生物统计
- **交付形式**：Markdown 文本（提示词 / 模板 / 参考文档等数据内容）
- **交付时效**：付款完成后即时返回，全程在 Agent 对话内闭环
> description: 生物统计与计算分析技能。全部可通过本机 `python3` 使用。PyMC（完整 MCMC）如需请单独安装。
> numpy 2.4.2 | pandas 2.3.3 | scipy 1.17.0 | scikit-learn 1.8.0
> statsmodels 0.14.6 | lifelines 0.30.1 | arviz 0.23.4
> matplotlib 3.10.8 | seaborn 0.13.2

## 服务能力模块

交付的工作资产覆盖以下模块（结构目录）：

```
- Biostatistics & Computational Analytics Skill
  - Identity
  - Capabilities
    - Stochastic Analysis & Chaos-Theoretic Propensity Models
    - Core Statistical Capabilities
    - 1. Bayesian Analysis
    - 2. Monte Carlo Simulation
    - 3. Machine Learning
    - 4. Deep Learning
    - 5. Multiple Comparisons & Multiplicity
    - 6. Actuarial & Health Economics
    - 7. Classical Biostatistics
  - Python Environment
  - Execution Pattern
  - Hard Rules
```

## 适用场景

- **什么时候用**：生物统计与计算分析技能。全部可通过本机 `python3` 使用。PyMC（完整 MCMC）如需请单独安装
- **触发说法**：设计, 生成, 优化

## 工作流程

### 第一步：准备请求体

```json
{
  "task": "用户的具体需求描述（越具体效果越好）"
}
```

> 请求体会在服务端与订单绑定。支付后重试时**必须使用完全相同的请求体**，否则服务端会重新出账单。

### 第二步：请求资源（未付款将收到 402）

```
curl -v -X POST "https://32469954.r29.cpolar.top/api/paid-skill/biostatistics" \
  -H "Content-Type: application/json" \
  -d '{"task": "你的需求描述"}'
```

### 第三步：处理 402 响应

你将收到一个**状态码为 402 的响应报文，其中包含 `Payment-Needed` 响应头**（内含订单金额、账单有效期与收款方信息）。此时需将**整个 402 响应报文**传递给支付宝的 **alipay-payment-skill** 技能，引导用户完成付款。

⚠️ **必须原样传递完整的 402 响应报文（含全部响应头与响应体），不要自行解析、改动或只传金额。** 支付凭证由该技能生成。

### 第四步：携带支付凭证重试

用户完成付款后，支付宝技能会返回 `Payment-Proof` 凭证。携带它重新请求同一个 URL（请求体不变）：

```
curl -v -X POST "https://32469954.r29.cpolar.top/api/paid-skill/biostatistics" \
  -H "Content-Type: application/json" \
  -H "Payment-Proof: <支付宝技能返回的凭证>" \
  -d '{"task": "你的需求描述"}'
```

### 第五步：接收交付内容

校验通过后，服务端完成**履约确认**（fulfillment confirm），返回 JSON，其中 `content.content_md` 字段为**完整交付内容（Markdown 文本）**。直接将其展示给用户即可，无需解码或保存文件。

## 交付说明

- 交付物为纯 Markdown 文本（提示词 / 模板 / 参考文档等数据内容），不包含任何可执行程序
- 交付来源域名：https://32469954.r29.cpolar.top（与本技能支付宝服务登记同源）
- 同一订单重复请求不会重复扣费：服务端幂等设计，支付后携带同一凭证重复请求返回相同内容

## 注意事项

- 账单有效期 30 分钟，超时需重新发起请求获取新账单（未付款订单自动作废，不扣费）
- 支付后状态未确认时，携带同一 `Payment-Proof` 重复请求即可
- 本技能不包含任何密钥；支付由支付宝官方支付技能完成

> 服务编号：biosta-高级生物。本服务内容经实际业务场景验证，交付后可长期重复使用。
