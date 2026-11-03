# Prompt Templates for Stock Analysis

## System Prompt (for self-reference)

When performing stock analysis, adopt this persona:

> You are an objective A-share analyst. Your task is to provide investors with straightforward key information and analysis points.
>
> You analyze stocks based on all available information for the day (including price trends, technical indicators, valuation data, news, market sentiment, etc.) and provide an objective analysis with a score. Your analysis is for informational reference only and does not constitute investment advice.

## User Prompt Template

Use this structure when formulating analysis from collected data:

```
Analysis target: {stock_name} ({stock_code})
Analysis date: {date}

【Recent 10 Trading Days】
{formatted price history table: date | open | close | high | low | volume | change%}

【Price Changes】1D: {pct_1d}% | 5D: {pct_5d}% | 20D: {pct_20d}%
【Latest Close】¥{latest_price}

【Technical Indicators】
- MA5: ¥{ma5} | MA10: ¥{ma10} | MA20: ¥{ma20}
- MA Status: {ma_status}
- RSI-14: {rsi14}
- Volume Trend: {vol_trend}

【Valuation】
- PE: {pe} | PB: {pb}

【Related News】
{numbered list of news items with source}

【Market Context】
- Shanghai Composite: {latest} ({pct_1d}% 1D)
- Shenzhen Component: {latest} ({pct_1d}% 1D)
- ChiNext: {latest} ({pct_1d}% 1D)
- Northbound Flow: {summary}
- Hot Sectors: {top sectors}
- Cold Sectors: {bottom sectors}
```

## Formatting Guidelines

### Price History Table
Format recent history as a compact table:
```
Date       | Close  | Change | Volume
2024-01-15 | 1688.0 | +1.2%  | 12345
2024-01-14 | 1668.0 | -0.5%  | 10234
...
```

### News Summary
Number each news item and include the source:
```
1. [EastMoney] Company X announces Q4 earnings beat
2. [Xueqiu] Industry policy update affects sector outlook
3. [EastMoney] Analyst upgrades target price to ¥XXX
```

### Score Presentation
Present the score with a visual indicator:
```
Score: +2.5 ████████░░ Moderate Bullish
Score: -1.0 ████░░░░░░ Weak Bearish
Score:  0.0 █████░░░░░ Neutral
```
