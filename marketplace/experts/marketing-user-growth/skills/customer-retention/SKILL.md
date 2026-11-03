---
name: customer-retention
description: Build and execute customer retention strategies for a solopreneur business. Use when reducing churn, improving customer lifetime value, building loyalty programs, re-engaging inactive users, or creating retention-focused product and communication strategies. Covers churn analysis, retention cohorts, lifecycle marketing, win-back campaigns, and loyalty mechanics. Trigger on "customer retention", "reduce churn", "keep customers", "improve retention", "churn rate", "customer loyalty", "win-back campaign".
---

# Customer Retention

## Overview
Retention is the foundation of sustainable growth. It costs 5-7x more to acquire a new customer than to keep an existing one. For solopreneurs, improving retention by even 5% can dramatically increase lifetime value and profitability. This playbook shows you how to measure, understand, and improve retention systematically.

---

## Step 1: Measure Your Retention

You can't improve what you don't measure. Start by calculating your retention and churn rates.

**Key metrics:**

**Churn Rate (monthly):**
```
Churn Rate = (Customers Lost in Month / Customers at Start of Month) × 100
```
Example: Started month with 100 customers, lost 5 → 5% churn rate

**Retention Rate (monthly):**
```
Retention Rate = 100% - Churn Rate
```
Example: 5% churn = 95% retention

**Cohort Retention:**
Track what % of customers stick around after 1 month, 3 months, 6 months, 12 months.

Example:
```
Jan Cohort (100 customers signed up in Jan):
  Month 1: 90 still active (90% retention)
  Month 3: 75 still active (75% retention)
  Month 6: 65 still active (65% retention)
  Month 12: 55 still active (55% retention)
```

**Benchmarks (SaaS):**
- **Healthy:** Monthly churn < 5%, 12-month retention > 70%
- **Needs work:** Monthly churn 5-10%, 12-month retention 50-70%
- **Critical:** Monthly churn > 10%, 12-month retention < 50%

**Where to track:** Your payment processor (Stripe, Paddle), CRM, or manual spreadsheet for small customer counts.

---

## Step 2: Understand WHY Customers Churn

Churn has patterns. Identify the top reasons so you can address them systematically.

**How to find out why:**

### Method 1: Cancellation survey
When someone cancels, ask them why (1-2 questions max):
```
"We're sorry to see you go. What's the main reason you're canceling?"
  - Not using it enough
  - Too expensive
  - Missing a feature I need
  - Found a better alternative
  - Product didn't deliver expected value
  - Other: [text field]
```

### Method 2: Exit interviews (for high-value customers)
If a customer paying $100+/month cancels, reach out personally:
```
"Hey [Name], saw you canceled. Totally understand if the timing isn't right.
Would you be open to a 10-min call? I'd love to understand what wasn't working
so we can improve for future customers."
```

### Method 3: Churn cohort analysis
Look at customers who churned vs. those who stayed. What's different?
- Did churned customers have lower usage in their first 30 days?
- Did they skip onboarding steps?
- Did they have a specific profile (industry, company size, use case)?

**Common churn reasons and what they tell you:**
- "Not using it enough" → Onboarding problem or product didn't fit their workflow
- "Too expensive" → Pricing/value mismatch or they didn't see ROI
- "Missing a feature" → Product gap (track which features are requested most)
- "Found a better alternative" → Competitive positioning issue
- "Didn't deliver expected value" → Product-market fit problem or messaging mismatch

---

## Step 3: Retention Strategy by Customer Lifecycle Stage

Different stages require different retention tactics.

### Stage 1: First 7 Days (Onboarding)
**Goal:** Get them to activation (see customer-onboarding skill)

**Tactics:**
- Welcome email sequence (see email-marketing skill)
- In-app onboarding flow (tooltips, checklists)
- Quick win template or tutorial
- Proactive check-in (automated or manual): "How's it going? Need help?"

**Why this matters:** Most churn happens in the first 30 days. Fix onboarding, fix half your churn.

### Stage 2: Days 8-90 (Habit Formation)
**Goal:** Turn them into regular users

**Tactics:**
- Usage-triggered emails: "You haven't logged in in 7 days — here's what you're missing"
- Feature discovery emails: "Did you know you can [do X]?"
- Weekly/monthly usage reports: "Here's what you accomplished this month"
- Engagement loops: In-app notifications for new content, features, or milestones

**Metric to track:** Weekly Active Users (WAU) or Monthly Active Users (MAU). Engaged users don't churn.

### Stage 3: Month 4+ (Ongoing Value)
**Goal:** Keep delivering value, prevent complacency

**Tactics:**
- Product updates and new features (show you're actively improving)
- Customer success check-ins: Quarterly email or call for high-value customers
- Exclusive content or community access (make them feel special)
- Cross-sell or upsell: "Based on how you're using X, you might benefit from Y"

**Metric to track:** NPS (Net Promoter Score) — are they likely to recommend you?

### Stage 4: At-Risk (Low engagement or cancellation intent)
**Goal:** Win them back before they churn

**Tactics:**
- Re-engagement email campaign (see Step 4)
- Personal outreach (if high-value): "Noticed you haven't been active — everything okay?"
- Special offer or discount (last resort): "We'd love to keep you — here's 30% off next month"

**Trigger:** User hasn't logged in for 30 days, or usage dropped 50%+ from baseline.

---

## Step 4: Build a Re-Engagement Campaign

For users who've gone inactive but haven't canceled yet, a re-engagement campaign can bring them back.

**Re-engagement email sequence (3-5 emails over 14 days):**

```
EMAIL 1 (Day 0): "We miss you!"
  Subject: "Still getting value from [Product]?"
  Body: Acknowledge they've been away. Ask if something's blocking them. Offer help.

EMAIL 2 (Day 3): "Here's what you're missing"
  Subject: "3 things you can do with [Product] this week"
  Body: Share quick wins or new features. Reframe the value.

EMAIL 3 (Day 7): "One-click back in"
  Subject: "Your account is ready — pick up where you left off"
  Body: Direct link to their account or a specific feature. Remove friction to re-engage.

EMAIL 4 (Day 10): "Can we help?"
  Subject: "What's one thing we could do better?"
  Body: Ask for feedback. Make them feel heard. Offer a call or direct message.

EMAIL 5 (Day 14): "Last call"
  Subject: "We don't want to see you go"
  Body: Mention upcoming cancellation (if auto-renewing). Offer a discount or pause option.
```

**Response rate:** 5-15% of inactive users will re-engage from a well-designed campaign.

---

## Step 5: Build Customer Loyalty

Loyal customers stay longer, spend more, and refer others. Build loyalty proactively.

**Loyalty tactics:**

| Tactic | How | When to Use |
|---|---|---|
| **Loyalty program** | Points or rewards for usage, referrals, or tenure | B2C or high-volume B2B |
| **VIP tier** | Exclusive access to features, content, or community | When you have 100+ customers |
| **Annual discounts** | 20-30% off for committing to annual vs monthly | SaaS, subscriptions |
| **Customer advisory board** | Invite top customers to give feedback and shape the roadmap | B2B, high-touch |
| **Surprise and delight** | Send unexpected value (free month, gift, handwritten note) | High-value customers |

**What builds loyalty most:** Delivering consistent value + listening to feedback + treating them like partners, not transactions.

---

## Step 6: Retention Experiments to Run

Test these to see what moves the retention needle for your business:

**Experiment 1: Onboarding call for new customers**
- Hypothesis: Personal touch in first week increases activation and retention
- Test: Offer 15-min onboarding call to 50% of new signups
- Measure: 30-day retention rate (call group vs no-call group)

**Experiment 2: Usage milestone celebrations**
- Hypothesis: Celebrating progress builds emotional investment
- Test: Send automated email when user hits milestones ("You've completed 10 projects!")
- Measure: Do users with milestone emails have higher 90-day retention?

**Experiment 3: Pause option instead of cancel**
- Hypothesis: Offering a pause (1-3 months) instead of cancel reduces churn
- Test: Add "Pause my account" button on cancellation page
- Measure: How many choose pause vs cancel? Do paused users return?

**Experiment 4: Quarterly check-in for high-value customers**
- Hypothesis: Proactive check-ins catch issues before churn
- Test: Email or call top 20% of customers quarterly to ask how it's going
- Measure: Churn rate of check-in group vs no-check-in group

---

## Step 7: Track Retention Over Time

Monthly retention review (15 min):
- [ ] Churn rate this month vs last month (trending up or down?)
- [ ] Cohort retention (are recent cohorts retaining better or worse?)
- [ ] Top 3 churn reasons this month
- [ ] Which retention experiments are running? Any results yet?
- [ ] One action to improve retention this month

**Leading indicators (predict future churn):**
- Declining usage (logins, actions per session)
- Support tickets with frustrated tone
- Not opening emails (disengaging from communication)
- Failed payment attempts (passive churn)

If you see these signals, intervene before they cancel.

---

## Customer Retention Mistakes to Avoid
- **Only focusing on acquisition.** New customers don't matter if they all churn in 3 months. Retention > acquisition for sustainable growth.
- **Not measuring churn by cohort.** Overall churn rate hides patterns. Cohort analysis reveals whether you're getting better or worse over time.
- **Waiting until they cancel to act.** By then it's too late. Catch at-risk users while they're still customers.
- **Ignoring low-engagement users.** Low engagement = future churn. Re-engage them proactively.
- **Not asking why people churn.** If you don't know why, you can't fix it. Always run exit surveys or interviews.
- **Treating all customers the same.** High-value customers deserve more attention (personal check-ins, dedicated support). Don't over-automate at the high end.
