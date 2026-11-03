---
name: discount-marketing-strategy
description: When the user wants to plan, implement, or optimize discount and promotional pricing strategy. Also use when the user mentions "discount strategy," "promo code," "coupon," "redeem code," "lifetime deal," "LTD," "AppSumo," "Black Friday," "Cyber Monday," "BFCM," "seasonal sale," or "promotional pricing." For pricing page, use pricing-page-generator.
metadata:
  version: 1.1.1
---

# Strategies: Discount Marketing

Guides discount and promotional pricing strategy for SaaS, e-commerce, and tools. Covers discount structures, lifetime deals (LTD), redeem codes, Black Friday / Cyber Monday, and campaign design. Aligns with **pricing-strategy** (base price structure); discounts apply on top of base pricing.

**When invoking**: On **first use**, if helpful, open with 1–2 sentences on what this skill covers and why it matters, then provide the main output. On **subsequent use** or when the user asks to skip, go directly to the main output.

## Initial Assessment

**Check for project context first:** If `.claude/project-context.md` or `.cursor/project-context.md` exists, read it for product, pricing, and goals.

Identify:
1. **Product type**: SaaS, e-commerce, tool
2. **Goal**: Acquisition, retention, cash flow, annual plan promotion
3. **Discount type**: One-time, recurring, LTD, campaign
4. **Constraints**: LTV:CAC, margin, support capacity

## Discount Structures (SaaS)

| Type | Typical Range | Use |
|------|---------------|-----|
| **Annual commitment** | 15–25% | Improve cash flow, reduce churn; Slack, Zoom, HubSpot |
| **Volume-based** | 10–40% | Enterprise; scale by seat/volume; Atlassian, Salesforce |
| **First-time / new customer** | 15–30% | Overcome hesitation; 3–12 months; below 15% rarely moves behavior; above 30% attracts price-sensitive, higher churn |
| **Lifetime deal (LTD)** | One-time; heavily discounted | Cold start, AppSumo; fast cash upfront; see LTD section below |

**Financial guardrails**: Ensure LTV:CAC supports discount; set qualification criteria (timeline, use case, contract length).

## Lifetime Deal (LTD) / AppSumo

LTD = one-time payment for lifelong access instead of recurring subscription. Common for cold start and deal platforms.

### Benefits

| Benefit | Notes |
|---------|-------|
| **Immediate cash flow** | Upfront lump sum; reinvest in product |
| **Cost-effective acquisition** | Community-driven; word-of-mouth; lower CAC |
| **User feedback** | LTD buyers are engaged; direct feedback for roadmap |
| **Audience access** | AppSumo: 500K+ users, 2K+ affiliates |

### Challenges

| Risk | Mitigation |
|-----|------------|
| **Revenue cannibalization** | Tiered LTD; upsell to premium; limit scope |
| **Resource strain** | Support, infra, dev capacity; plan for surge |
| **Commission** | AppSumo takes cut; factor into pricing |
| **Pricing perception** | May undervalue vs subscription; position clearly |

### When to Use

- **Cold start**: Zero traction; need fast revenue; see **cold-start-strategy**
- **Validation**: Test product-market fit; price-sensitive early adopters
- **Platform**: AppSumo, similar deal platforms; top 1% acceptance

**Cold start**: LTD is one channel in cold-start-strategy. Use **cold-start-strategy** for full launch planning; use **discount-marketing-strategy** for LTD structure, pricing, and trade-offs.

## Redeem Code / Coupon

### Types

| Type | Use |
|------|-----|
| **Percentage** | % off; feels more valuable for higher-priced items |
| **Fixed amount** | $ off; better for lower cart values |
| **Product-specific** | Clear inventory; promote collections |
| **BOGO / buy X get Y** | Increase cart size |
| **Free shipping** | With or without minimum order |

### Goals

- Convert hesitant shoppers; reduce cart abandonment (~70% abandonment)
- Track by channel; unique codes per campaign
- Segment customers; targeted discounts
- Retention; loyalty programs

### Implementation

- **Conditions**: Valid codes; minimum order; product eligibility
- **Validation**: Automated at checkout
- **Tracking**: Redemption data; attribution
- **Placement**: Top banner (30–50% redemption lift when used well); popup; email; see **top-banner-generator**, **popup-generator**

## Black Friday / Cyber Monday (BFCM)

### Timing

- **Launch**: Early November (e.g. Nov 7); lower promo volume post-election
- **Peak**: Monday before Thanksgiving; 40%+ of email campaigns contain discounts by then
- **Planning**: Start October

### Strategy

| Approach | Notes |
|----------|-------|
| **Strategic pricing** | 10–25% often outperforms deep cuts; quality and loyalty over rock-bottom |
| **Price anchoring** | Multiple options: e.g. $1 first month OR 50% off annual |
| **Psychological triggers** | Countdown; "cancel anytime"; % discount prominent |
| **Multi-channel** | Email, website, paid; personalized; peak send 9–10am ET Black Friday |
| **Post-holiday** | Retarget; segment; shift messaging |

## Campaign Types

| Campaign | Use | Related |
|----------|-----|---------|
| **BFCM** | Seasonal; Nov | See BFCM section above |
| **LTD** | Cold start; AppSumo | See LTD section |
| **Referral reward** | Discount/credits for referrer and referee | **referral-program** |
| **Contest / giveaway** | Prize = product, discount, cash | **contest-page-generator** |
| **Startups / education** | Special pricing for segment | **education-program**, **startups-page-generator** |
| **Forum / community** | Discount codes in niche forums | **community-forum** |
| **Affiliate** | Coupon sites; affiliate-specific codes | **affiliate-marketing** |

## Promotional Materials

| Type | Use |
|------|-----|
| **Banner / poster** | Website, events; attract attention |
| **Brochure** | Handout; company overview |
| **Logo stickers** | Brand exposure |
| **Website prep** | Promo landing page; banner for BFCM, seasonal; see **top-banner-generator** |
| **Media kit** | For press, partners; see **media-kit-page-generator** |

**Corporate materials**: Company overview, annual report, product info—for investor/partner meetings; printable for events.

## Implementation Best Practices

- **Clear objectives**: Define goals (e.g. +20% trial signups, -5% churn)
- **ICP alignment**: Tailor to segment; startups vs enterprise differ
- **Genuine scarcity**: Time-bound; avoid perpetual "limited time"
- **LTV:CAC**: Ensure discount economics work
- **Channel tracking**: UTM; unique codes per channel

## Output Format

- **Discount type** and structure
- **Campaign** (if applicable: BFCM, LTD, etc.)
- **Redeem code** approach (if applicable)
- **Financial** guardrails
- **Related** page/component skills (pricing-page, top-banner, contest-page)

## Related Skills

- **pricing-strategy**: Base price structure; pricing-strategy defines when discounts fit; discount-marketing-strategy defines how to execute
- **pricing-page-generator**: Pricing page display; anchoring, annual discount presentation
- **cold-start-strategy**: LTD as cold-start channel; full launch planning
- **indie-hacker-strategy**: Indie hacker LTD use; monetize day one; cold start revenue
- **referral-program**: Referral rewards (discounts, credits); 10–30% of price
- **contest-page-generator**: Giveaway/contest; prize = discount
- **education-program**: Student/education discount channel; verification, placement, discount structure
- **startups-page-generator**: Startups/education program page; when standalone page needed
- **top-banner-generator**: Promo banner; discount code display; 30–50% redemption lift
- **community-forum**: Forum promotion; discount codes in industry forums
- **affiliate-marketing**: Coupon sites; affiliate-specific codes
- **landing-page-generator**: Promo landing pages
- **directory-submission**: Promo code field for Product Hunt, deal platforms
