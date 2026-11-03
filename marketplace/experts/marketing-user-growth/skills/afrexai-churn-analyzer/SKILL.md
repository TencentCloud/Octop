# Churn Risk Analyzer

Identify customers most likely to churn before they leave. Uses behavioral signals, usage patterns, and engagement data to score accounts and recommend retention actions.

## When to Use
- Customer success reviews
- Quarterly retention planning
- When usage data or support ticket logs are available
- Proactive outreach prioritization

## How It Works

### 1. Gather Data
Ask the user for available data sources:
- **Usage metrics** (logins, feature adoption, API calls)
- **Support tickets** (frequency, sentiment, resolution time)
- **Billing history** (downgrades, late payments, discount requests)
- **Engagement signals** (email opens, meeting attendance, NPS scores)

If no structured data, work from what the user describes qualitatively.

### 2. Score Each Account
Apply this risk framework:

| Signal | Weight | High Risk Indicator |
|--------|--------|-------------------|
| Usage decline (30d) | 25% | >30% drop |
| Support ticket spike | 20% | 2x+ above baseline |
| Champion departure | 20% | Key contact left |
| Contract timing | 15% | <90 days to renewal |
| Payment behavior | 10% | Late/disputed invoices |
| Engagement drop | 10% | No response to last 3 outreach |

**Score**: 0-100 (higher = more likely to churn)

### 3. Categorize
- **🔴 Critical (75-100)**: Immediate intervention needed
- **🟡 At Risk (50-74)**: Schedule check-in this week
- **🟢 Healthy (25-49)**: Monitor monthly
- **💚 Thriving (0-24)**: Expansion opportunity

### 4. Recommend Actions
For each at-risk account, suggest specific retention plays:
- Executive sponsor call
- Custom success plan
- Feature training session
- Pricing review / loyalty offer
- Roadmap preview (show upcoming value)

### 5. Output
Generate a retention report with:
- Ranked list of accounts by churn risk
- Top 3 actions per critical account
- Estimated revenue at risk
- 30/60/90 day retention calendar

## Integration Notes
- Works with CSV exports, CRM data, or manual input
- Pair with the [AfrexAI Context Packs](https://afrexai-cto.github.io/context-packs/) for industry-specific retention strategies ($47/pack)
- For a full AI-powered retention system built for your business, try the [AI Revenue Calculator](https://afrexai-cto.github.io/ai-revenue-calculator/) to see what you're leaving on the table
