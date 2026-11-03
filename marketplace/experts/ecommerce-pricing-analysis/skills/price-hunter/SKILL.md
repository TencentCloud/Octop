---
name: price-hunter
description: Global price comparison tool with international platform support. Compare prices across Amazon, eBay, AliExpress, Temu (international) AND JD, Taobao, Tmall, Pinduoduo (China). Best for cross-border shopping, finding the cheapest option globally, or checking if buying abroad is cheaper than domestic. Triggers on "比价XXX", "where is XXX cheapest globally", "compare Amazon vs JD", "海外比价", "XXX国内买还是国外买".
---

# Price Hunter

Find the best price for any product across multiple e-commerce platforms.

## Quick Start

**Input:** Product name, model number, or product URL

**Output:** Structured price comparison table with:
- Platform name
- Price (normalized to user's currency)
- Seller rating (when available)
- Shipping cost estimate
- Direct link

## Workflow

### Step 1: Clarify the Product

Before searching, confirm:
- Exact product name/model (e.g., "Sony WH-1000XM5" not just "Sony headphones")
- Preferred currency (default: USD)
- Region preference (default: global)
- Any specific requirements (new/used, prime shipping, etc.)

If the user provides a URL, extract the product identity first.

### Step 2: Multi-Platform Search

Search these platforms based on relevance:

**International:**
- Amazon (amazon.com, regional sites)
- eBay
- AliExpress
- Temu
- Walmart

**China:**
- JD.com (京东) - 京东自营价格较准
- Taobao (淘宝) - 搜索 `"{商品名}" site:taobao.com 价格`
- Tmall (天猫) - 官方旗舰店，搜索 `"{商品名}" site:tmall.com`
- Pinduoduo (拼多多) - 搜索 `"{商品名}" 拼多多 价格` 或 `百亿补贴`

**Platform notes:**
- **拼多多**: 
  - ⚠️ 无法提供直接商品链接（网页版需登录，搜索引擎无法抓取）
  - 价格来源：第三方聚合站（值值值、什么值得买等）
  - 输出格式：提供价格 + 建议用户在拼多多APP内搜索
  - 示例：`拼多多 - ¥329 - *请在APP内搜索"Keychron K3 Pro"*`
- **淘宝/天猫**: 部分页面需要登录，优先用搜索结果的摘要信息
- **京东**: 价格相对透明，容易抓取

**Region-specific (ask if needed):**
- Rakuten (Japan)
- Coupang (Korea)
- Shopee (Southeast Asia)

Use `web_search` with queries like:
- `"{product name}" price Amazon`
- `"{product name}" site:ebay.com`
- `"{商品名}" 京东 价格`
- `"{商品名}" 拼多多 百亿补贴`

### Step 3: Extract Price Data

For each promising result:
1. Use `web_fetch` to get the product page
2. Extract: price, seller, rating, shipping info
3. Note any coupons or discounts mentioned

**Price extraction tips:**
- Look for `¥`, `$`, `€`, `£` symbols
- Check for "from" prices (indicates multiple variants)
- Note if price includes tax/shipping

### Step 4: Normalize and Compare

**IMPORTANT: Output format depends on platform:**

**For Discord/WhatsApp (no tables):**
Use bullet list with inline links:
```
**🏆 最划算**
• **Amazon** - $279 - Amazon官方 - 4.8★ - [购买](https://amazon.com/...)
• **eBay** - $265 - topSeller99 - 4.9★ - [购买](https://ebay.com/...)
• **AliExpress** - $198 - Official Store - 4.7★ - [购买](https://aliexpress.com/...)
```

**For other platforms (support tables):**
| Platform | Price | Seller | Rating | Shipping | Link |
|----------|-------|--------|--------|----------|------|
| Amazon | $279 | Amazon | 4.8★ | Free | [购买](url) |

**Link requirements:**
- Every result MUST include a direct clickable link when available
- Use markdown format: `[购买](URL)` or `[Buy](URL)`
- **Exceptions:**
  - **拼多多**: Cannot provide direct links. Output format: `拼多多 - ¥329 - *请在APP内搜索"商品名"*`
  - **淘宝/天猫**: Use search result links when product pages require login
- If multiple sellers exist, link to the best-priced one
- Verify links are accessible (not blocked by login wall)

**Currency conversion:** Use approximate rates if needed (no need for API)

### Step 5: Recommendation

Provide a clear recommendation:
- **Best value:** [Platform] at [Price] - [Why]
- **Fastest delivery:** [Platform] - [Shipping time]
- **Most reliable:** [Platform] - [Seller reputation]

## Tips

- For electronics, check if the price is for the correct region/version
- For clothing, note size availability
- For used items, clearly mark condition
- If no results found, try alternative product names or model numbers

## Limitations

- Cannot complete purchases (informational only)
- Prices may change between search and purchase
- Some platforms (Taobao, JD) may require translation for non-Chinese users
- Real-time inventory not guaranteed
