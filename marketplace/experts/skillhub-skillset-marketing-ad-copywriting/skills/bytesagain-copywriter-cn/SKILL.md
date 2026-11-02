---
description: "Generate Chinese and English marketing copy using AIDA and A/B frameworks. Use when writing ad copy, drafting product descriptions, creating email campaigns, or generating brand slogans."
author: BytesAgain
homepage: https://bytesagain.com
source: https://github.com/bytesagain/ai-skills
---
# bytesagain-copywriter-cn

中英文广告文案生成工具，支持AIDA框架、A/B变体、产品描述、邮件营销和品牌口号。Generate Chinese and English marketing copy for ads, products, emails, and brand slogans.

## Usage

```
bytesagain-copywriter-cn ad <product> <audience>
bytesagain-copywriter-cn product <name> <features>
bytesagain-copywriter-cn email <topic> <goal>
bytesagain-copywriter-cn aida <product>
bytesagain-copywriter-cn ab <product>
bytesagain-copywriter-cn slogan <brand> <values>
```

## Commands

- `ad` — Generate 4 ad copy variants (pain-point, result, social proof, urgency)
- `product` — Create short/standard/detailed product descriptions
- `email` — Email subject lines + body framework with CTA guidance
- `aida` — Full AIDA framework (Attention/Interest/Desire/Action) for any product
- `ab` — Generate A/B test variants across hooks, CTAs, and pricing presentation
- `slogan` — Brand slogan ideas using formula-based generation

## Examples

```bash
bytesagain-copywriter-cn ad "AI写作工具" "内容创作者"
bytesagain-copywriter-cn product "智能日历" "自动排期,冲突检测,团队协同"
bytesagain-copywriter-cn email "季度促销" "购买转化"
bytesagain-copywriter-cn aida "效率管理App"
bytesagain-copywriter-cn ab "SaaS工具"
bytesagain-copywriter-cn slogan "BytesAgain" "效率,简单,专业"
```

## Requirements

- bash
- python3

## When to Use

Use when writing marketing copy, product descriptions, email campaigns, or brand messaging in Chinese or English. Generates structured frameworks you can fill in and customize.
