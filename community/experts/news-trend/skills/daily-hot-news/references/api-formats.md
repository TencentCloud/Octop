# 60s API 响应格式参考

基础 URL：`https://60s.viki.moe/v2`

## 通用参数

- `encoding`：响应格式，可选 `json`（默认）/ `text` / `markdown`
- 部分端点支持额外参数（如 `date`、`query`、`currency`），详见 `sources.md` 对应条目

## 通用响应结构

```json
{
  "code": 200,
  "message": "success",
  "data": { ... }
}
```

## 热榜类响应（微博/知乎/百度/抖音等）

```json
{
  "code": 200,
  "data": [
    { "title": "话题标题", "url": "https://...", "hot": "1234567", "rank": 1 }
  ]
}
```

## 60s 每日新闻

```json
{
  "code": 200,
  "data": {
    "date": "2025年3月13日",
    "news": [
      { "title": "新闻标题", "link": "https://..." }
    ],
    "tip": "每日一言内容"
  }
}
```

## 黄金价格

```json
{
  "code": 200,
  "data": {
    "date": "2025-03-13",
    "metals": [
      { "name": "黄金_9999", "sell_price": "680.50", "today_price": "679.00", "high_price": "682.00", "low_price": "677.00", "unit": "元/克" }
    ],
    "stores": [
      { "brand": "周大福", "product": "足金", "price": "750", "unit": "元/克" }
    ],
    "banks": [
      { "bank": "工商银行", "product": "如意金条", "price": "695.00", "unit": "元/克" }
    ],
    "recycle": [
      { "type": "黄金回收", "price": "670.00", "unit": "元/克", "purity": "Au9999" }
    ]
  }
}
```

## 汇率

```json
{
  "code": 200,
  "data": {
    "base_code": "CNY",
    "updated": "2025-03-13 12:00:00",
    "rates": [
      { "currency": "USD", "rate": 0.1372 },
      { "currency": "EUR", "rate": 0.1265 }
    ]
  }
}
```

## 调用示例

```
# 微博热搜
GET https://60s.viki.moe/v2/weibo

# 每日新闻（指定日期，markdown 格式）
GET https://60s.viki.moe/v2/60s?date=2025-03-13&encoding=markdown

# 黄金价格
GET https://60s.viki.moe/v2/gold-price

# 人民币汇率
GET https://60s.viki.moe/v2/exchange-rate?currency=CNY

# 北京天气
GET https://60s.viki.moe/v2/weather/realtime?query=北京

# Hacker News 热帖
GET https://60s.viki.moe/v2/hacker-news/top
```
