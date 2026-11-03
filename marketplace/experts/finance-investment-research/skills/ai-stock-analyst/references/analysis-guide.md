# A-Share Stock Analysis Guide

## Scoring System

Score range: **-5.00 to +5.00** (0 = neutral)

The score represents the AI's comprehensive judgment on a stock's likely performance over the next 2-4 weeks. Positive scores indicate bullish outlook; negative scores indicate bearish outlook. Two decimal places are supported.

### Score Anchors

| Score Range | Signal Strength | Typical Triggers |
|-------------|----------------|-----------------|
| ±4.0 to ±5.0 | Strong | Major technical breakout/breakdown, significant policy changes, critical corporate events, fundamental business logic shifts |
| ±2.0 to ±3.9 | Moderate | Policy tailwinds/headwinds, sector rotation signals, concentrated capital flows, fundamental trend changes, significant company events |
| ±0.5 to ±1.9 | Weak | Sentiment shifts, valuation deviations, volume changes, uncertain signals |
| 0.0 to ±0.4 | Neutral | Insufficient information or no clear directional signal |

## Analysis Dimensions

### 1. Technical Analysis
- **K-line patterns**: Recent candlestick formations, support/resistance levels
- **Moving average system**: MA5/MA10/MA20 alignment (bullish: short above long; bearish: short below long)
- **RSI-14**: <30 oversold, >70 overbought, 40-60 neutral
- **Volume trend**: Increased volume (>1.3x avg) on price rise = bullish confirmation; decreased volume on price drop = selling pressure easing

### 2. Fundamental Analysis
- **PE ratio**: Compare to industry average. Low PE may indicate undervaluation or poor growth prospects
- **PB ratio**: <1 may indicate undervaluation for asset-heavy industries
- **Industry position**: Market share, competitive advantages, growth runway

### 3. Information/News Analysis
- **Company announcements**: Earnings, management changes, major contracts
- **Industry policy**: Regulatory changes, government support/restrictions
- **Market sentiment**: Analyst ratings, social media buzz, institutional positioning

### 4. Capital Flow Analysis
- **Northbound flow**: Net inflows from Hong Kong investors often signal institutional confidence
- **Sector rotation**: Money flowing into/out of related sectors
- **Turnover changes**: Sudden spikes may indicate pending catalysts

## Conflict Resolution

When dimensions give contradicting signals:
1. State the conflict explicitly in the analysis
2. Weight more recent data higher (last 5 days > last 20 days)
3. Give fundamental signals more weight for longer-term outlook
4. Give technical signals more weight for shorter-term outlook
5. Adjust score toward 0 (neutral) when conflicts are severe

## Special Cases

### Suspended Stocks
- Score: 0.0
- Note suspension status and expected resume date if known

### ST / *ST Stocks
- Add prominent risk warning at the top of the report
- Note delisting risk if applicable
- Apply higher skepticism to positive signals

### New IPOs (< 30 Trading Days)
- Score should trend toward 0 (insufficient data)
- Note limited historical data
- Focus more on fundamental analysis and industry context

### Data Unavailability
- If historical data fetch fails: note missing data, rely on available dimensions
- If news fetch fails: note limited information, focus on technical and fundamental data
- Never fabricate data or pretend data exists when it does not

## Output JSON Format

When generating raw analysis data (not the final report), use this format:

```json
{
  "score": 2.5,
  "summary": "Objective analysis within 150 characters covering bullish factors, bearish factors, risks, and key data points"
}
```

## Report Template

```markdown
## {Stock Name} ({Stock Code}) Analysis Report
Date: {YYYY-MM-DD}

**Score: {score}** ({signal strength description})

### Key Findings
- Bullish: [factors]
- Bearish: [factors]
- Risks: [factors]

### Technical Analysis
- Latest close: ¥{price}
- MA status: {MA5/MA10/MA20 positions}
- RSI-14: {value} ({interpretation})
- Volume: {trend description}
- Price change: 1D {pct}% | 5D {pct}% | 20D {pct}%

### Fundamental Analysis
- PE: {value} (vs industry avg {value})
- PB: {value}
- Industry context: {brief description}

### News & Sentiment
- {Key news item 1 and its implication}
- {Key news item 2 and its implication}

### Conclusion
{2-3 sentence balanced summary}

> Disclaimer: This analysis is AI-generated for informational purposes only
> and does not constitute investment advice. Always conduct your own research
> before making investment decisions.
```
