---
name: customer-onboarding
description: Design and execute customer onboarding that drives activation and retention. Use when building onboarding flows for new users, reducing churn in the first 30 days, improving time-to-value, or creating onboarding sequences (email, in-app, or manual). Covers activation metrics, onboarding step design, friction reduction, and measuring onboarding success. Trigger on "customer onboarding", "onboarding flow", "user onboarding", "reduce early churn", "improve activation", "onboarding sequence", "time to value".
---

# Customer Onboarding

## Overview
Onboarding is where you keep or lose customers. The first 7-30 days determine whether they stay or churn. Most solopreneurs focus on acquisition and ignore onboarding — then wonder why churn is high. This playbook builds an onboarding system that gets users to their first win fast, builds confidence, and sets them up for long-term success.

---

## Step 1: Define Your Activation Metric

Onboarding isn't about completing a checklist. It's about getting users to experience value — the "aha moment" where the product clicks.

**Your activation metric is the action that predicts retention.**

Examples:
- **Slack:** Sent 2,000 messages as a team
- **Dropbox:** Uploaded and shared at least one file
- **SaaS analytics tool:** Connected a data source and viewed their first report
- **Project management tool:** Created a project and added 3 tasks

**How to find your activation metric:**
1. Look at retained customers (those who stuck around 90+ days)
2. Identify what they did in their first 7 days that non-retained customers didn't do
3. That action (or set of actions) is your activation metric

**Rule:** Onboarding is successful when a user completes your activation metric. Everything in your onboarding should drive toward this.

---

## Step 2: Map Your Onboarding Journey

Before designing tactics, map the full journey from signup to activation.

**Onboarding journey template:**
```
SIGNUP
  ↓ (What happens immediately after signup?)
SETUP / CONFIGURATION
  ↓ (What do they need to configure? Integrations? Settings? Profile?)
FIRST VALUE MOMENT
  ↓ (What's the simplest, fastest way they can experience value?)
ACTIVATION
  ↓ (They complete the activation metric)
ONGOING ENGAGEMENT
  ↓ (They use the product regularly)
```

**For each stage, ask:**
- What does the user need to do?
- What's blocking them from doing it? (friction, confusion, missing information)
- How can we make this easier or faster?

**Example (SaaS automation tool):**
```
SIGNUP → Email confirmation

SETUP → Connect first data source (e.g., Google Sheets)
  Friction: Don't know which source to start with
  Solution: Pre-select most common source, add "why start here?" tooltip

FIRST VALUE MOMENT → See automated workflow run successfully
  Friction: Don't know what workflow to build
  Solution: Provide 3 templates, one-click to activate

ACTIVATION → Run 10 workflows successfully
  Friction: Forget to check back after first success
  Solution: Email reminder after 24 hours with progress + next step

ONGOING ENGAGEMENT → Use weekly, add more workflows
```

---

## Step 3: Reduce Friction at Every Step

Friction = anything that slows down or confuses the user. Every friction point increases the chance they abandon.

**Common friction points and fixes:**

| Friction | Impact | Fix |
|---|---|---|
| **Too many fields on signup** | Users abandon mid-signup | Collect only email + password. Get everything else later. |
| **Unclear next step** | Users sign up, then stare at a blank screen | Show a clear "Start here" CTA immediately after signup |
| **Complex setup** | Users get overwhelmed and leave | Break setup into 3-5 small steps with progress bar. Let them skip non-essential steps. |
| **Jargon or unclear labels** | Users don't understand what to do | Use plain language. Replace "Configure API endpoint" with "Connect your account" |
| **Long time-to-value** | Takes 30+ min to see results | Create a fast "quick win" path — even if it's a simplified version of the full value |

**Rule:** Every step in onboarding should take < 2 minutes. If it takes longer, break it into smaller steps or defer it until later.

---

## Step 4: Build Your Onboarding Sequence

Onboarding is not just in-app. It's a multi-channel experience: in-app guidance + email + (optionally) human touch.

### In-App Onboarding
**Tactics:**
- **Welcome modal:** Appears immediately after signup. "Welcome! Here's how to get started in 3 steps."
- **Tooltips/hotspots:** Highlight key features as users explore ("This is where you create a new project")
- **Checklist:** Show progress toward activation ("2 of 5 steps complete — you're almost there!")
- **Empty states:** When a user sees a blank page, show helpful prompts ("No projects yet? Start your first one here.")

**Tools:** Intercom, Appcues, Userflow, or custom-built with plain JavaScript.

**Rule:** Don't overwhelm. Show 1-2 tips at a time, not 10.

### Email Onboarding
**Email sequence (5-7 emails over 14 days):**

```
EMAIL 1 (Day 0, immediately after signup):
  Subject: "Welcome to [Product]! Let's get you started."
  Body: Confirm signup, set expectations, link to first step or template

EMAIL 2 (Day 1, if activation metric not hit):
  Subject: "Quick question — stuck on anything?"
  Body: Address common blockers, offer help, link to docs or support

EMAIL 3 (Day 3, if activation metric not hit):
  Subject: "Here's the fastest way to see results"
  Body: Share a quick-win template or walkthrough video

EMAIL 4 (Day 5, if activation metric HIT):
  Subject: "Nice work! Here's what to do next"
  Body: Celebrate their first win, suggest next feature or use case

EMAIL 5 (Day 7, if activation metric not hit):
  Subject: "Need a hand? Let's jump on a quick call"
  Body: Offer a personal onboarding call (manual touch for high-value prospects)

EMAIL 6 (Day 10):
  Subject: "3 pro tips from our best users"
  Body: Share advanced tips or lesser-known features

EMAIL 7 (Day 14):
  Subject: "How's it going? We'd love your feedback"
  Body: Ask how onboarding went, request feedback, link to survey
```

**Personalization triggers:** Send different emails based on behavior:
- If they completed activation → send "here's what to do next" content
- If they didn't complete activation → send troubleshooting or offer help

### Human Touch (Optional, for High-Value Customers)
For high-ticket SaaS or service businesses, add a human layer:
- **Onboarding call:** Schedule a 15-30 min call to walk them through setup
- **Check-in emails:** Personal email (not automated) asking how it's going
- **Slack/community access:** Invite them to a private Slack or Circle community for direct support

**When to use:** When LTV > $500 or when the product is complex.

---

## Step 5: Measure Onboarding Performance

Track these metrics to know if onboarding is working:

| Metric | What It Means | Healthy Benchmark |
|---|---|---|
| **Activation rate** | % of signups who hit activation metric | 30-60% (varies by product) |
| **Time to activation** | Median days/hours from signup to activation | Under 24 hours is ideal |
| **Day 7 retention** | % of signups still active after 7 days | 40-60% |
| **Day 30 retention** | % of signups still active after 30 days | 25-40% |
| **Onboarding email open/click rates** | Engagement with onboarding emails | Opens: 40-60%, Clicks: 10-20% |

**Where to track:** Use your analytics tool (Mixpanel, Amplitude, or simple event tracking in Google Analytics) + email tool (ConvertKit, Mailchimp).

**Diagnose issues:**
- **Low activation rate?** Too much friction in setup, or unclear value prop. Simplify first steps.
- **Long time to activation?** Too many steps or too complex. Create a faster "quick win" path.
- **High activation but low Day 30 retention?** They got initial value but didn't build a habit. Improve ongoing engagement (notifications, email reminders, new features).

---

## Step 6: Iterate on Onboarding

Onboarding is never "done." Continuously improve based on data and feedback.

**Monthly onboarding review:**
1. Check activation rate — is it improving?
2. Review user feedback from surveys or support tickets — where are people getting stuck?
3. Watch 2-3 user session recordings (tools: Hotjar, FullStory) — what confuses people?
4. Test one improvement per month (e.g., simplify signup, add a tooltip, rewrite an email)

**A/B testing ideas:**
- Different welcome email subject lines
- Checklist vs no checklist in-app
- Video walkthrough vs text instructions
- Length of signup form (fewer fields vs more upfront info)

**Rule:** Focus on the biggest drop-off point first. If 50% of users abandon during setup, fixing that is 10x more valuable than optimizing a later step.

---

## Onboarding Mistakes to Avoid
- **Dumping everything on Day 1.** Don't explain every feature upfront. Guide them to one quick win, then introduce more over time.
- **No clear next step after signup.** A blank screen or "Welcome!" with no guidance kills activation. Always show a clear "Do this first" CTA.
- **Ignoring non-activated users.** If someone signs up and doesn't activate, don't give up. Re-engage them with helpful emails or a manual outreach.
- **Making setup mandatory when it's optional.** Let users skip non-essential steps. Forcing them to fill out a profile or connect integrations before they see value creates friction.
- **No human touch for high-value customers.** If your LTV is $1,000+, a 15-minute onboarding call is worth it. Don't over-automate at the high end.
- **Not measuring time to activation.** If it takes 2 weeks for users to see value, you'll lose most of them. Aim for value in < 24 hours.
