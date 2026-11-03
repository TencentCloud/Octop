# Growth Engineering Mastery

> Complete growth system: experimentation engine, viral mechanics, channel playbooks, funnel optimization, retention loops, and scaling frameworks. From zero users to exponential growth.

## 1. Growth Audit — Where Are You Now?

Before experimenting, diagnose. Run this 8-dimension health check:

### Growth Health Scorecard

Rate each 1-5, multiply by weight:

| Dimension | Weight | Score (1-5) | Weighted |
|-----------|--------|-------------|----------|
| Product-Market Fit | 3x | __ | __ |
| Activation Rate | 3x | __ | __ |
| Retention (Week 4) | 3x | __ | __ |
| Referral/Virality | 2x | __ | __ |
| Revenue per User | 2x | __ | __ |
| Channel Diversity | 1x | __ | __ |
| Experiment Velocity | 2x | __ | __ |
| Data Infrastructure | 1x | __ | __ |

**Scoring:** 68-85 = Growth-ready. 50-67 = Fix foundations first. <50 = Stop growth spending, fix product.

### PMF Validation Gate

Do NOT invest in growth until these pass:

```yaml
pmf_gate:
  sean_ellis_test: "≥40% would be 'very disappointed' if product disappeared"
  retention_curve: "Flattens (does not trend to zero) by week 8"
  organic_growth: "≥10% of new users come from referral/word-of-mouth"
  nps: "≥30"
  qualitative: "Users describe product to friends without prompting"
```

**If PMF gate fails:** Stop. Go back to product. Growth without PMF = pouring water into a leaky bucket.

---

## 2. North Star Metric — Pick ONE Number

### Selection Framework

Your North Star Metric (NSM) must pass all 4 tests:

1. **Revenue proxy** — More of this metric = more revenue (eventually)
2. **User value** — Captures the moment users get value
3. **Measurable** — Can track daily/weekly with existing tools
4. **Influenceable** — Team actions can move it within 2-4 weeks

### NSM Examples by Business Type

| Business Type | NSM | Why |
|---------------|-----|-----|
| SaaS (B2B) | Weekly Active Teams | Teams = sticky, revenue follows |
| Marketplace | Weekly Transactions | Both sides getting value |
| Subscription Media | Weekly Reading Time | Engagement predicts retention |
| E-commerce | Weekly Repeat Purchases | Retention > acquisition |
| Social/Community | Daily Active Users posting | Creators drive content loop |
| Dev Tools | Weekly API Calls | Usage = integration depth |
| Fintech | Weekly $ Managed | Trust + engagement |

### Supporting Metrics Tree

```
North Star Metric
├── Input Metric 1: [driver you can directly influence]
├── Input Metric 2: [driver you can directly influence]
├── Input Metric 3: [driver you can directly influence]
└── Guard Metric: [thing that must NOT decrease]
```

Example (SaaS):
```
Weekly Active Teams (NSM)
├── New team activations/week (acquisition input)
├── Features used per team/week (engagement input)
├── Teams inviting 3+ members/week (virality input)
└── Guard: Churn rate must stay <3%/month
```

---

## 3. Experimentation Engine — The Core Growth Loop

### ICE Scoring Framework

Every experiment gets scored before running:

| Dimension | Score 1-10 | Definition |
|-----------|-----------|------------|
| **Impact** | __ | If this works, how much does NSM move? |
| **Confidence** | __ | How sure are we it'll work? (data/analogies/gut) |
| **Ease** | __ | How fast/cheap to test? (days, not weeks) |

**ICE Score** = (Impact + Confidence + Ease) / 3

Run experiments scoring ≥7 first. Kill anything below 5.

### Experiment Log Template

```yaml
experiment:
  id: "GRW-042"
  name: "Add social proof counter to pricing page"
  hypothesis: "Showing '2,847 teams trust us' increases plan selection by 15%"
  north_star_impact: "More paid conversions → more Weekly Active Teams"
  ice_score:
    impact: 7
    confidence: 6
    ease: 9
    total: 7.3
  type: "A/B test"
  audience: "All pricing page visitors"
  sample_size_needed: 2400  # for 95% confidence, 80% power
  duration: "7-14 days"
  primary_metric: "Pricing page → checkout conversion rate"
  secondary_metrics:
    - "Average plan tier selected"
    - "Time on pricing page"
  guard_metrics:
    - "Support tickets about pricing must not increase >10%"
  status: "running"  # proposed | running | won | lost | inconclusive
  result:
    lift: "+18.3%"
    confidence: "97.2%"
    decision: "Ship to 100%"
    learnings: "Social proof most effective on annual plans. Monthly plan conversion unchanged."
    next_experiment: "Test specific customer logos vs generic count"
```

### Experiment Velocity Targets

| Stage | Experiments/Week | Focus |
|-------|-----------------|-------|
| Pre-PMF | 5-10 | Product experiments (features, UX, messaging) |
| Early Growth | 3-5 | Activation + retention experiments |
| Scaling | 5-10 | Channel + conversion experiments |
| Mature | 10-20 | Micro-optimizations + new channels |

### Statistical Rigor Rules

- **Minimum sample size:** Calculate BEFORE launching (use: `n = 16 × σ² / δ²` or online calculator)
- **Minimum runtime:** 2 full business cycles (usually 2 weeks)
- **No peeking:** Don't stop tests early on positive results (peeking inflates false positives 3-5x)
- **One change per test:** Isolate variables. Multivariate only with massive traffic
- **Document losses:** Failed experiments are data. Log why the hypothesis was wrong

---

## 4. AARRR Funnel — Stage-by-Stage Playbooks

### 4.1 Acquisition — Getting Users In

#### Channel Evaluation Matrix

Score each channel before investing:

```yaml
channel_evaluation:
  name: "[Channel]"
  scores:
    estimated_volume: 8      # 1-10: How many users can this deliver?
    targeting_precision: 7   # 1-10: Can we reach our ICP specifically?
    cost_per_acquisition: 6  # 1-10: How cheap? (10 = free/organic)
    time_to_results: 4       # 1-10: How fast? (10 = same day)
    scalability: 7           # 1-10: Can we 10x spend and 10x output?
    defensibility: 8         # 1-10: Hard for competitors to copy?
  total: 40  # out of 60
  verdict: "Test with $500 budget over 2 weeks"
```

#### Channel Playbooks (Top 12)

**Organic Channels (low cost, slow build):**

1. **SEO/Content**
   - Target: Bottom-of-funnel keywords first (high intent, lower volume)
   - Playbook: 1 pillar page + 8-12 cluster articles per topic
   - Timeline: 3-6 months to meaningful traffic
   - Experiment: Test 3 content formats (how-to, comparison, listicle) — measure organic signups per article
   - Killer metric: Organic signups/article/month

2. **Community/Forum Marketing**
   - Target: Where your ICP already hangs out (Reddit, HN, Discord servers, Slack groups)
   - Playbook: Provide genuine value for 30 days before any self-promotion. 20:1 value:ask ratio
   - Experiment: Track which communities drive highest-quality signups (activation rate, not just volume)
   - Warning: Getting banned kills the channel permanently. Authenticity is non-negotiable

3. **Referral/Word-of-Mouth**
   - Target: Existing happy users
   - Playbook: See Section 5 (Viral Mechanics) below
   - Killer metric: K-factor (viral coefficient)

4. **Social Media (Organic)**
   - Target: Platform where your ICP consumes content
   - Platform selection: LinkedIn (B2B), Twitter/X (tech/startup), TikTok (consumer/SMB), Instagram (visual/lifestyle)
   - Playbook: Post 5x/week, 80% value + 20% product. Reply to every comment for 90 days
   - Experiment: Test content types (text, carousel, video, thread) — measure profile visits → signups

5. **Partnerships/Integrations**
   - Target: Products your users already use
   - Playbook: Build integration → get listed in partner's marketplace → co-market
   - Experiment: Partner A vs Partner B — which integration drives more activated users?

6. **Product-Led SEO**
   - Target: Create public-facing pages that rank (templates, tools, directories)
   - Examples: Canva templates page, Zapier app directory, Ahrefs free tools
   - Experiment: Build 1 free tool targeting a high-volume keyword — measure signups from tool

**Paid Channels (fast results, requires budget):**

7. **Search Ads (Google/Bing)**
   - Target: High-intent keywords (bottom of funnel)
   - Playbook: Start with exact match branded + competitor terms. Expand to problem-aware keywords
   - Budget rule: Don't spend >$50/day until CAC is profitable
   - Experiment: Ad copy A vs B, then landing page A vs B (sequential, not simultaneous)

8. **Social Ads (Meta/LinkedIn/TikTok)**
   - Target: Lookalike audiences from best customers
   - Playbook: 3 creatives × 3 audiences × 3 copy variants. Kill losers at $50 spend, scale winners
   - LinkedIn: Only for B2B with ACV >$5K (expensive CPMs)
   - Experiment: Audience segmentation — which cohort has lowest CAC AND highest LTV?

9. **Influencer/Creator**
   - Target: Micro-influencers (10K-100K followers) in your niche
   - Playbook: Product-for-post for micro. Paid for 50K+. Always track with UTM + unique codes
   - Experiment: 5 micro-influencers at $500 each. Compare CAC to paid ads

10. **Cold Outreach (Email/LinkedIn)**
    - Target: Named accounts (ABM)
    - Playbook: 5-touch sequence over 14 days. Personalized first line. Clear CTA
    - Volume: 50-100/day per domain (warm up first). Separate domain from main
    - Experiment: Subject line tests (5 variants, 200 sends each)

**Leverage Channels (unconventional):**

11. **PR/Media**
    - Target: Industry publications, podcasts, newsletters
    - Playbook: Newsjack trending topics. Offer original data/research. Be a source, not an ad
    - Experiment: 10 podcast appearances — measure signups per appearance

12. **Platform Piggyback**
    - Target: Launch on Product Hunt, HN Show, AppSumo, marketplaces
    - Playbook: Coordinate launch day (Tuesday-Thursday). Mobilize existing users to upvote. Respond to every comment
    - Timeline: 1 day of effort, potentially thousands of signups
    - Experiment: Which platform delivers highest-LTV users?

#### Channel Prioritization Rule

**The "Bull's Eye" Framework:**
1. Brainstorm all 12+ channels
2. Rank by ICE score
3. Test top 3 with minimum viable spend ($500-1K each, 2 weeks)
4. Double down on the ONE winner
5. Don't diversify until that channel is saturated (CAC rising >30% month-over-month)

### 4.2 Activation — The "Aha Moment"

#### Define Your Aha Moment

```yaml
aha_moment:
  description: "The specific action where users first experience core value"
  examples:
    slack: "Sent 2,000 team messages"
    dropbox: "Put 1 file in Dropbox folder"
    facebook: "Added 7 friends in 10 days"
    hubspot: "Imported contacts and sent first email"
  your_product:
    action: "[specific action]"
    threshold: "[quantity/frequency]"
    timeframe: "[within X days of signup]"
  validation: "Users who reach aha moment retain at 2x+ rate of those who don't"
```

#### Activation Funnel Map

```
Signup → [Step 1] → [Step 2] → ... → Aha Moment → Retained User
  |         |          |                  |
  v         v          v                  v
Drop-off  Drop-off  Drop-off          Success
 rate %    rate %    rate %             rate %
```

Map EVERY step. Measure EVERY drop-off. Fix the BIGGEST leak first.

#### Activation Tactics (by drop-off point)

**Signup → First Session:**
- Reduce signup friction (social login, no credit card, fewer fields)
- Welcome email within 5 minutes with ONE clear next step
- In-app checklist showing progress to aha moment
- Experiment: Remove 1 signup field → measure completion rate

**First Session → Key Action:**
- Interactive onboarding tour (max 4 steps)
- Pre-populate with sample data so product feels alive
- Contextual tooltips on first encounter (not all at once)
- Experiment: Guided tour vs self-serve vs video walkthrough

**Key Action → Aha Moment:**
- Trigger celebration/reward when they complete key action
- Show value immediately (dashboard, report, insight)
- Prompt sharing/inviting while enthusiasm is high
- Experiment: Time-to-value — can you deliver aha moment in <5 minutes?

#### Activation Scorecard

```yaml
activation_metrics:
  signup_to_first_session: "Target: >80% within 24h"
  first_session_to_key_action: "Target: >60% within session 1"
  key_action_to_aha: "Target: >40% within 7 days"
  overall_activation_rate: "Target: >30% (signup → aha within 14 days)"
  benchmark_comparison: "[industry average is X%, we're at Y%]"
```

### 4.3 Retention — The Only Metric That Matters

#### Cohort Analysis Template

Track weekly cohorts (by signup week):

```
         Week 0  Week 1  Week 2  Week 3  Week 4  Week 8  Week 12
Cohort A  100%    45%     32%     28%     25%     22%     20%
Cohort B  100%    52%     38%     33%     30%     27%     25%
Cohort C  100%    48%     35%     30%     27%     24%     22%
```

**What to look for:**
- Does the curve flatten? (Good — you have a retention floor)
- Is each cohort better than the last? (Good — product is improving)
- Where's the biggest week-over-week drop? (Fix that transition)

#### Retention Curve Benchmarks

| Product Type | Good Week-4 | Great Week-4 | Week-12 Floor |
|-------------|-------------|--------------|---------------|
| SaaS (B2B) | 30% | 50%+ | 20%+ |
| Consumer App | 15% | 25%+ | 10%+ |
| Marketplace | 20% | 35%+ | 15%+ |
| Gaming | 10% | 20%+ | 5%+ |

#### Retention Improvement Playbook

**Week 1 drop-off (activation problem):**
- Improve onboarding (see 4.2)
- Add "quick win" in first session
- Re-engagement email at 24h, 72h, 7 days

**Week 2-4 drop-off (habit problem):**
- Build triggers: notifications, emails, in-app prompts at optimal times
- Create recurring use case (weekly report, daily digest, scheduled task)
- Social hooks: team features, sharing, collaboration

**Week 4+ decline (value problem):**
- Feature depth: are power users hitting ceiling?
- New use cases: expand the "jobs to be done"
- Community: forums, events, user groups create switching cost

#### Engagement Loops

Design self-reinforcing loops:

```
User takes action → Gets value → Triggers notification/reminder → User returns → Takes deeper action
```

**Types of engagement loops:**
1. **Content loop:** User creates content → others consume → creator gets feedback → creates more
2. **Social loop:** User invites friend → friend joins → both get value → invite more
3. **Data loop:** User adds data → product gets smarter → better recommendations → user adds more
4. **Habit loop:** Trigger (email/notification) → Action (check dashboard) → Reward (insight) → Investment (customize)

### 4.4 Revenue — Monetization That Doesn't Kill Growth

#### Pricing-Growth Alignment

| Pricing Model | Growth Impact | Best For |
|---------------|--------------|----------|
| Freemium | High viral potential, low conversion (2-5%) | Network effects, large TAM |
| Free trial | Higher conversion (10-25%), time pressure | Clear aha moment within trial |
| Usage-based | Natural expansion, low barrier | API/infrastructure, measurable value |
| Flat rate | Simple, predictable, easy to sell | Simple product, single persona |
| Per-seat | Expansion revenue, team adoption incentive | Collaboration tools |

#### Revenue Experiments

- **Pricing page layout:** Test 2-tier vs 3-tier vs slider
- **Anchor pricing:** Test showing enterprise tier first vs starter first
- **Trial length:** 7-day vs 14-day vs 30-day (shorter often converts better)
- **Feature gating:** Which free feature, if paywalled, would drive most upgrades?
- **Annual discount:** Test 10%, 17%, 20%, 25% annual discount — optimize for LTV not just conversion

#### Unit Economics Health Check

```yaml
unit_economics:
  cac: "$[X]"                    # Total sales+marketing / new customers
  ltv: "$[X]"                    # Average revenue × average lifetime
  ltv_cac_ratio: "[X]:1"        # Target: >3:1. Below 1 = losing money
  payback_months: "[X]"          # Target: <12 months (SaaS), <3 months (consumer)
  gross_margin: "[X]%"           # Target: >70% (SaaS), >40% (marketplace)
  expansion_revenue: "[X]%"      # % of revenue from existing customers expanding
  ndr: "[X]%"                    # Net Dollar Retention. Target: >100% (ideally >120%)
```

### 4.5 Referral — Turning Users Into a Growth Channel

See Section 5 (Viral Mechanics) for complete referral system design.

---

## 5. Viral Mechanics — Engineering Word-of-Mouth

### Viral Coefficient (K-Factor)

```
K = invites_sent_per_user × conversion_rate_of_invites

K > 1 = exponential growth (every user brings >1 new user)
K = 0.5 = good amplifier (50% more users from virality)
K < 0.3 = not meaningfully viral
```

### Viral Cycle Time

K-factor alone isn't enough. Speed matters:

```
Viral Cycle Time = time from user signup → their invite → invitee signup

Shorter cycle = faster growth (even with K < 1)
```

**Goal:** Reduce viral cycle time to <48 hours.

### Types of Virality (Design for ALL of them)

#### 1. Inherent Virality (product requires sharing)
- Example: Zoom (you invite people to join meetings), Figma (collaborate on designs)
- Design: Core use case involves other people
- Strongest form. Build this into the product if possible

#### 2. Collaboration Virality (better with more people)
- Example: Slack (more teammates = more valuable), Notion (shared workspace)
- Design: Features that work better with team/network
- Trigger: Prompt team invites during high-value moments

#### 3. Word-of-Mouth Virality (users talk about it)
- Example: ChatGPT (people share outputs), Canva (people share designs)
- Design: Create shareable outputs with subtle branding
- Trigger: Make outputs beautiful/impressive enough that users WANT to show them off

#### 4. Incentivized Virality (rewards for sharing)
- Example: Dropbox (250MB per referral), Uber ($10 credit per referral)
- Design: Two-sided reward (referrer AND referee both get something)
- Warning: Attracts low-quality users if reward is too generous. Gate the reward behind activation

#### 5. Artificial Scarcity/FOMO
- Example: Clubhouse (invite-only), Gmail (invite-only launch)
- Design: Limited access creates desire. Waitlists with position number
- Timing: Only effective at launch or for new features. Wears off fast

### Referral Program Design Template

```yaml
referral_program:
  name: "[Program name]"
  mechanics:
    referrer_reward: "[What they get]"
    referee_reward: "[What invitee gets]"
    reward_trigger: "Referee must [complete activation action] before rewards unlock"
    reward_type: "product_credit"  # cash | product_credit | feature_unlock | status
    cap: "10 referrals/month"      # Prevent gaming
  distribution:
    share_methods:
      - "Unique referral link (primary)"
      - "Email invite from product"
      - "Social share buttons (Twitter, LinkedIn)"
      - "QR code for in-person"
    placement:
      - "Post-aha-moment celebration screen"
      - "Settings/account page"
      - "Monthly usage summary email"
      - "In-app prompt after positive action (e.g., saved money, closed deal)"
  tracking:
    metrics:
      - "Share rate: % of users who share referral link"
      - "Click-through rate: % of link viewers who click"
      - "Conversion rate: % of clickers who sign up"
      - "Activation rate: % of referred signups who activate"
      - "K-factor: shares × CTR × signup × activation"
    cohort_quality: "Compare referred users vs non-referred on Day 30 retention + LTV"
  optimization_experiments:
    - "Test reward amount ($5 vs $10 vs $20)"
    - "Test reward type (credit vs cash vs feature)"
    - "Test referral prompt timing (post-signup vs post-aha vs post-payment)"
    - "Test share copy (3 variants)"
```

### Viral Content Strategies

For products where output sharing drives growth:

1. **Branded outputs:** Add subtle watermark/badge ("Made with [Product]") to exports, reports, shares
2. **Public profiles/pages:** User-created content that's publicly accessible (SEO + social sharing)
3. **Embed widgets:** Let users embed product functionality on their sites
4. **Template marketplace:** User-created templates others can discover and use
5. **Leaderboards/badges:** Shareable achievements that demonstrate status

---

## 6. Growth Loops — Self-Reinforcing Systems

### Why Loops > Funnels

Funnels are linear (top → bottom, then done). Loops are circular — output becomes input.

### Loop Architecture

```
[New User] → [Takes Action] → [Creates Value] → [Attracts New User] → repeat
```

### 6 Growth Loop Templates

#### 1. User-Generated Content Loop
```
User creates content → Content gets indexed/shared → New user discovers content → Signs up to create own → Creates content
```
- Examples: Medium, GitHub, Canva templates
- Key metric: Content pieces created/week
- Leverage point: Make content creation effortless + discoverable

#### 2. Paid Marketing Loop
```
Revenue → Reinvest in ads → Acquire users → Users generate revenue → Reinvest more
```
- Key metric: LTV:CAC ratio (must be >3:1)
- Leverage point: Increase LTV (expansion revenue, retention) → can afford higher CAC

#### 3. Sales Loop
```
Close deal → Case study/testimonial → Use in sales materials → Close next deal faster
```
- Key metric: Win rate improvement per quarter
- Leverage point: Systematize case study collection (ask at Month 3 of every account)

#### 4. Data Network Effect Loop
```
Users use product → Product collects data → Product improves (AI/ML/recommendations) → More valuable for all users → More users join
```
- Examples: Waze, Netflix recommendations, Google Search
- Key metric: Improvement in core metric per doubling of data
- Leverage point: Show users how product gets better with more usage

#### 5. Marketplace/Platform Loop
```
Supply joins → Attracts demand → Demand attracts more supply → More selection attracts more demand
```
- Key metric: Liquidity (% of listings that transact)
- Leverage point: Solve chicken-and-egg: seed supply first, constrain geography to build density

#### 6. Community Loop
```
Expert users help newbies → Newbies become power users → Power users help next wave → Community grows
```
- Examples: Stack Overflow, Reddit, Discord servers
- Key metric: Weekly active contributors
- Leverage point: Gamification (reputation, badges, privileges for top contributors)

---

## 7. Funnel Optimization — CRO Playbook

### Conversion Rate Benchmarks

| Funnel Step | Median | Good | Excellent |
|-------------|--------|------|-----------|
| Landing page → Signup | 2-3% | 5-8% | 10%+ |
| Signup → Activation | 20-30% | 40-50% | 60%+ |
| Free → Paid | 2-3% | 5-7% | 10%+ |
| Trial → Paid | 10-15% | 20-30% | 40%+ |
| Annual → Renewal | 70-80% | 85-90% | 92%+ |

### Landing Page Optimization Checklist

- [ ] Hero headline matches ad/source copy (message match)
- [ ] Clear value proposition in ≤10 words
- [ ] Social proof above the fold (logos, numbers, testimonials)
- [ ] ONE primary CTA (not 3 competing buttons)
- [ ] CTA button text is action-specific ("Start free trial" not "Submit")
- [ ] Mobile-first design (60%+ of traffic is mobile)
- [ ] Page loads in <3 seconds (every second = 7% conversion drop)
- [ ] Remove navigation (landing page ≠ homepage)
- [ ] Include objection handling (FAQ, guarantee, security badges)
- [ ] Exit-intent popup with alternate offer

### High-Impact CRO Experiments (ordered by typical lift)

1. **Headline copy** (10-30% lift potential) — Test problem-focused vs benefit-focused vs social-proof
2. **CTA button** (5-20% lift) — Test color, copy, size, position
3. **Social proof type** (5-15% lift) — Test logos vs testimonials vs numbers vs case studies
4. **Form length** (10-25% lift) — Test fewer fields, progressive profiling
5. **Page layout** (5-15% lift) — Test long-form vs short-form, video vs text
6. **Pricing display** (10-30% lift) — Test anchoring, default selection, feature comparison
7. **Trust signals** (3-10% lift) — Test guarantees, security badges, review scores

---

## 8. Retention & Re-engagement — Keeping Users

### Lifecycle Email Sequences

#### Welcome Sequence (Days 0-14)

```yaml
welcome_sequence:
  - day: 0
    trigger: "Signup"
    subject: "Welcome — here's your quick win"
    content: "One specific action to get value in <5 minutes"
    cta: "Do [aha action] now"
  - day: 1
    trigger: "Has NOT completed aha action"
    subject: "[First name], you're 1 step away"
    content: "Show what they'll get once they complete the action"
    cta: "Complete setup"
  - day: 3
    trigger: "Still not activated"
    subject: "How [similar company] uses [Product]"
    content: "Case study / use case matching their profile"
    cta: "Try this approach"
  - day: 7
    trigger: "Not activated"
    subject: "Need help? Reply to this email"
    content: "Personal note from founder. Offer 1:1 call"
    cta: "Reply or book call"
  - day: 14
    trigger: "Still not activated"
    subject: "Last chance: your [Product] account"
    content: "We'll archive your account in 7 days. Here's what you're missing"
    cta: "Reactivate"
```

#### Re-engagement Sequence (for churned/dormant users)

```yaml
reengagement:
  - trigger: "14 days inactive"
    subject: "We miss you — here's what's new"
    content: "Top 3 new features/improvements since they left"
  - trigger: "30 days inactive"
    subject: "[First name], [specific value they got] is waiting"
    content: "Reference their actual usage data. Show what they've built"
  - trigger: "60 days inactive"
    subject: "Should we close your account?"
    content: "FOMO trigger. Offer win-back discount (20-30% off)"
  - trigger: "90 days inactive"
    subject: "Feedback request (we'll shut up after this)"
    content: "Why did you leave? 3-question survey. Offer incentive"
```

### Push Notification Strategy

**Rules:**
- Max 3-5/week (more = uninstall)
- Only send when you can show value (not "We miss you!")
- Personalize: "Your report is ready" > "Check out new features"
- A/B test timing: morning vs evening, weekday vs weekend
- Let users choose notification categories

### Churn Prediction Signals

Build an early warning system. Track these leading indicators:

| Signal | Timeframe | Risk Level |
|--------|-----------|------------|
| Login frequency drops 50%+ | Week over week | 🟡 Medium |
| Key feature usage stops | 7 days | 🟡 Medium |
| Support ticket unresolved >48h | Rolling | 🟡 Medium |
| No logins for 14+ days | Rolling | 🔴 High |
| Billing failure (payment method expired) | Event | 🔴 High |
| Export/download of all data | Event | 🔴 Critical |
| Admin user leaves company | Event | 🔴 Critical |

**Response playbook:** Trigger automated outreach at 🟡, human outreach at 🔴.

---

## 9. Scaling — From Working to 10x

### When to Scale a Channel

```yaml
scale_criteria:
  channel: "[name]"
  ready_when:
    - "CAC is <1/3 of LTV"
    - "Conversion rates are stable for 4+ weeks"
    - "Process is documented and repeatable"
    - "Can increase spend 50% without CAC rising >20%"
  warning_signs:
    - "CAC rising >20% month-over-month"
    - "Conversion rates declining"
    - "Quality of leads/users dropping (lower activation rate)"
    - "Creative fatigue (CTR declining)"
```

### Scaling Playbook

1. **Automate first** — Before hiring, automate everything possible (email sequences, ad management, content scheduling)
2. **Document SOPs** — Every process needs a playbook before delegation
3. **Hire specialists, not generalists** — At scale, you need a paid ads person, not a "growth person"
4. **Build dashboards before scaling** — If you can't measure it in real-time, you can't scale it safely
5. **10% rule** — Increase budget/volume by max 10-20%/week. Sudden jumps break things

### International Expansion Checklist

- [ ] Localize landing pages (not just translate — adapt)
- [ ] Research local competitors and positioning
- [ ] Adjust pricing for purchasing power (PPP)
- [ ] Local payment methods (not just Stripe)
- [ ] Support in local timezone and language
- [ ] Comply with local regulations (GDPR, data residency)
- [ ] Test demand before committing (run ads in target language first)

---

## 10. Growth Team Structure

### Solo/Small Team (1-3 people)

```
Growth Lead (you)
├── Runs experiments (2-3/week)
├── Manages 1-2 channels
├── Analyzes data weekly
└── Writes copy/creates content
```

**Focus:** Find ONE channel that works. Don't spread thin.

### Growth Team (4-10 people)

```
Head of Growth
├── Acquisition Lead → paid, SEO, partnerships
├── Product/Growth Engineer → experiments, features, A/B tests
├── Lifecycle/CRM → emails, notifications, retention
└── Data Analyst → metrics, cohorts, experiment analysis
```

### Growth Meeting Cadence

| Meeting | Frequency | Duration | Purpose |
|---------|-----------|----------|---------|
| Experiment standup | 2x/week | 15 min | Status of running experiments |
| Metrics review | Weekly | 30 min | NSM, funnel metrics, cohort review |
| Experiment planning | Weekly | 45 min | Prioritize next week's experiments (ICE scoring) |
| Growth strategy | Monthly | 90 min | Channel performance, resource allocation, quarterly goals |

---

## 11. Growth Toolkit — Technical Setup

### Analytics Stack (Minimum Viable)

```yaml
analytics_stack:
  product_analytics: "Mixpanel or Amplitude or PostHog (free tier)"
  web_analytics: "Google Analytics 4 + Google Tag Manager"
  attribution: "UTM parameters (mandatory on ALL links)"
  ab_testing: "PostHog or GrowthBook (free) or Optimizely (paid)"
  email: "Customer.io or Resend or SendGrid"
  crm: "HubSpot (free) or Pipedrive"
  session_recording: "Hotjar or FullStory (free tier)"
  surveys: "Typeform or native in-app"
```

### UTM Convention

```
utm_source: [platform] — google, linkedin, twitter, email, partner-name
utm_medium: [type] — cpc, social, email, referral, organic
utm_campaign: [campaign-name] — q1-launch, black-friday, webinar-series
utm_content: [variant] — hero-cta, sidebar-banner, email-v2
utm_term: [keyword] — only for paid search
```

**Rule:** Every external link gets UTMs. No exceptions. Untracked traffic = wasted budget.

### Event Tracking Plan

Track these events minimum:

```yaml
required_events:
  acquisition:
    - "page_view (with UTM params)"
    - "signup_started"
    - "signup_completed"
  activation:
    - "onboarding_step_completed (step_number)"
    - "first_key_action"
    - "aha_moment_reached"
  engagement:
    - "feature_used (feature_name)"
    - "session_started"
    - "session_duration"
  revenue:
    - "plan_selected (plan_name, price)"
    - "payment_completed (amount, plan)"
    - "upgrade (from_plan, to_plan)"
    - "churn (reason)"
  referral:
    - "referral_link_shared (method)"
    - "referral_link_clicked"
    - "referred_signup"
    - "referred_activated"
```

---

## 12. Anti-Patterns & Common Mistakes

### The 10 Growth Killers

1. **Scaling before PMF** — Spending on acquisition when retention is broken = burning money
2. **Vanity metrics addiction** — Signups, downloads, pageviews mean nothing without activation + retention
3. **Copying without context** — "Dropbox did referrals" doesn't mean you should. Understand WHY it worked for THEM
4. **Too many channels too soon** — Master ONE before adding another. Spread thin = learn nothing
5. **Peeking at A/B tests** — Stopping tests early inflates false positives 3-5x. Run to completion
6. **Optimizing pennies** — CRO on a page getting 100 visits/month is pointless. Get traffic first
7. **Ignoring retention** — Acquiring users you can't keep is literally the most expensive thing you can do
8. **Over-automating before understanding** — Automate processes you've done manually 50+ times. Not before
9. **Growth hacks without strategy** — One-off tactics without a system = random acts of marketing
10. **Not documenting experiments** — If you don't log it, you'll repeat failures and forget successes

### When Growth Stalls

Diagnostic checklist:
- [ ] Has the channel saturated? (CAC up >30% in 3 months)
- [ ] Has the product changed? (New features breaking existing flows)
- [ ] Has the market shifted? (New competitor, regulation, trend change)
- [ ] Has the team burned out? (Experiment velocity dropped)
- [ ] Is it seasonal? (Compare to same period last year)
- [ ] Are you measuring the right thing? (NSM still reflects actual value?)

---

## 13. Edge Cases & Special Situations

### B2B vs B2C Growth Differences

| Dimension | B2B | B2C |
|-----------|-----|-----|
| Sales cycle | Weeks-months | Minutes-days |
| Decision makers | 3-7 people | 1 person |
| Channels | LinkedIn, content, events, outbound | Social, SEO, paid, viral |
| Pricing | Value-based, negotiated | Fixed, transparent |
| Retention driver | Switching cost, integration depth | Habit, engagement |
| Referral mechanics | Case studies, introductions | In-product, social sharing |

### Two-Sided Marketplace Growth

Chicken-and-egg solution order:
1. Seed supply manually (scrape, import, do it yourself)
2. Constrain geography (one city/niche first)
3. Offer supply-side tools for free (even without demand)
4. Build just enough demand to show supply it works
5. Let organic flywheel take over before expanding geography

### PLG (Product-Led Growth) Specifics

```yaml
plg_metrics:
  free_to_paid: "Target: 3-5% (freemium) or 15-25% (free trial)"
  time_to_value: "Target: <5 minutes"
  expansion_rate: "Target: >120% NDR"
  self_serve_ratio: "Target: >80% of revenue from self-serve"
  pql_rate: "Target: 20-40% of active free users qualify"
```

**Product Qualified Lead (PQL) definition:** User who has reached activation AND shows buying signals (hits usage limit, views pricing page, invites team members).

### Growth with Zero Budget

1. Build in public (Twitter/LinkedIn) — share metrics, learnings, behind-the-scenes
2. Launch on 5 platforms: Product Hunt, HN, Reddit, Indie Hackers, relevant Discords
3. Write 1 SEO article/week targeting long-tail keywords
4. Offer free tool that solves a related problem → funnel to main product
5. Cold DM 10 potential users/day — ask for feedback, not sales
6. Partner with complementary products for cross-promotion
7. Answer questions on Quora/Reddit/forums where your ICP hangs out

---

## 14. Weekly Growth Review Template

```yaml
weekly_review:
  period: "Week of [DATE]"
  north_star_metric:
    current: "[X]"
    target: "[X]"
    trend: "up|down|flat"
    wow_change: "+X%"
  funnel_metrics:
    acquisition: "[visitors/signups]"
    activation: "[activated/total signups] = X%"
    retention: "[week 1 retention] = X%"
    revenue: "[$MRR] | [new paying] | [churned]"
    referral: "[K-factor] | [referral signups]"
  experiments:
    completed:
      - name: "[experiment]"
        result: "won|lost|inconclusive"
        impact: "[metric change]"
        next_step: "[ship|iterate|kill]"
    running:
      - name: "[experiment]"
        progress: "[X/Y days complete]"
        early_signal: "[trending positive|neutral|negative]"
    launching_next_week:
      - name: "[experiment]"
        ice_score: "[X]"
        hypothesis: "[statement]"
  channels:
    - name: "[channel]"
      spend: "$[X]"
      cac: "$[X]"
      volume: "[X] new users"
      quality: "[activation rate of users from this channel]"
  top_learning: "[Single most important thing learned this week]"
  biggest_risk: "[What could derail growth next month?]"
  focus_next_week: "[1-2 priorities]"
```

---

## 15. Natural Language Commands

Use these to activate specific workflows:

| Command | Action |
|---------|--------|
| "Run growth audit" | Execute 8-dimension health scorecard |
| "Define north star" | Walk through NSM selection framework |
| "Score this experiment" | ICE scoring + experiment template |
| "Analyze my funnel" | Map funnel stages with conversion rates |
| "Design referral program" | Complete referral program template |
| "Evaluate this channel" | Channel scoring matrix |
| "Build growth loop" | Design self-reinforcing growth loop |
| "Optimize this page" | Landing page CRO checklist |
| "Plan retention emails" | Generate lifecycle email sequences |
| "Weekly growth review" | Fill in weekly review template |
| "Diagnose growth stall" | Run diagnostic checklist |
| "Scale this channel" | Scaling readiness assessment |
