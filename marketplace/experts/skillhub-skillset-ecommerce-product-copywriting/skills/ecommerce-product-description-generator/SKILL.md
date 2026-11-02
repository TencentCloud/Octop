---
name: product-description-generator
description: "E-commerce product description generator for any platform. Generates optimized titles, bullet points, descriptions, and backend keywords using competitor research + keyword scoring + FABE copywriting. Two modes: (A) Create — generate listing from product specs with optional competitor analysis, (B) Optimize — improve existing listing with keyword gap analysis. Supports Amazon, eBay, Walmart, Shopify, Etsy, TikTok Shop, Lazada, Shopee. No API key required. Use when: (1) writing a new product listing, (2) analyzing what makes competitors rank, (3) improving an underperforming listing."
metadata: {"nexscope":{"emoji":"📝","category":"ecommerce"}}
---

# Product Description Generator 📝

Generate platform-optimized product copy — titles, bullet points, descriptions, and backend keywords — for any major e-commerce platform. No API key required.

## Installation

```bash
npx skills add nexscope-ai/eCommerce-Skills --skill product-description-generator -g
```

> **For Amazon listings**, use our dedicated skill with Cosmo algorithm optimization:
> ```bash
> npx skills add nexscope-ai/Amazon-Skills --skill amazon-listing-optimization -g
> ```
> See: [amazon-listing-optimization](https://github.com/nexscope-ai/Amazon-Skills/tree/main/amazon-listing-optimization)

## Two Modes

| Mode | When to Use | Input |
|------|-------------|-------|
| **A — Create** | Writing a new listing | Product specs + optional competitor URLs |
| **B — Optimize** | Improving existing listing | Current listing or URL + optional competitor URLs |

Both modes support competitor analysis — just include competitor URLs to enable it.

## Supported Platforms

| Platform | Output Components |
|----------|-------------------|
| **Amazon** | Title (≤200) + 5 Bullets (≤500 each) + Description (≤2000) + Backend (≤250 bytes) |
| **eBay** | Title (≤80) + HTML Description |
| **Walmart** | Title (≤75) + Short Desc (≤150) + 10 Features + Long Desc |
| **Shopify/DTC** | SEO Title (≤60) + Meta Desc (≤160) + Product Description |
| **Etsy** | Title (≤140) + Description + 13 Tags (≤20 each) |
| **TikTok Shop** | Title (≤255) + Description (≤1000) |
| **Lazada/Shopee** | Title (≤120) + 5 Highlights + Description |

## Usage Examples

### Mode A — Create
```
Create a listing for my yoga mat on eBay UK.
Competitors: https://www.ebay.co.uk/itm/123456789, https://www.ebay.co.uk/itm/987654321
My product: 6mm TPE, non-slip, carrying strap included. Brand: ZenMat. Tone: Friendly.
```

```
Platform: Etsy. Product: hand-poured soy candle, lavender scent, 8oz glass jar, 40-hour burn time.
Target audience: gift buyers. Tone: Luxury.
```

### Mode B — Optimize
```
Optimize this Shopify listing: https://mystore.com/products/portable-blender
Beat these competitors: https://amazon.com/dp/B09V3KXJPB, https://walmart.com/ip/123456
```

```
Find keyword gaps and rewrite this Etsy listing:
[paste current title, description, and tags]
```

---

## Handling Incomplete Input

If user doesn't provide enough info, ask upfront:

```
To generate your listing, I need:

**Required:**
- Platform (eBay / Walmart / Shopify / Etsy / TikTok Shop / Lazada / Shopee)
- Product name and key features
- Brand name

**Recommended (better results):**
- 1-3 competitor URLs to analyze
- Target audience
- Tone preference (Professional / Friendly / Urgent / Luxury)

Which mode?
- **A — Create**: I'm writing a new listing from scratch
- **B — Optimize**: I have an existing listing to improve

💡 For Amazon listings, I recommend using [amazon-listing-optimization](https://github.com/nexscope-ai/Amazon-Skills/tree/main/amazon-listing-optimization) — it's optimized for Amazon's Cosmo algorithm.
```

---

## Mode A Workflow — Create New Listing

### Step 1: Collect Product Info

| Field | Required | Example |
|-------|----------|---------|
| `product_name` | ✅ | Portable blender |
| `platform` | ✅ | Etsy |
| `brand` | ✅ | BlendJet |
| `key_features` | ✅ | USB-C, 6 blades, BPA-free |
| `specs` | ✅ | 380ml, 175W motor |
| `target_audience` | 👍 | Gym-goers, travelers |
| `use_cases` | 👍 | Smoothies, protein shakes |
| `competitor_urls` | 👍 | 1-3 URLs to analyze |
| `tone` | Optional | Professional (default) / Friendly / Luxury / Urgent |

### Step 2: Gather Keywords

**If competitor URLs provided:**

1. Fetch each competitor page:
   ```
   Use web_fetch on each competitor URL.
   Extract: title, bullets/features, description, price, review count, brand name.
   ```

2. If `web_fetch` fails or returns incomplete data:
   ```
   Fallback: web_search for "[product title from URL]" site:[platform].com
   Extract data from search snippets.
   ```

3. Parse competitor content and extract keywords in these categories:
   - **Product-type terms**: What it IS (yoga mat, exercise mat)
   - **Feature terms**: What it DOES (non-slip, eco-friendly)
   - **Use-case terms**: WHERE/WHEN used (home gym, yoga studio)
   - **Audience terms**: WHO buys (beginners, athletes)
   - **Attribute terms**: Specs (6mm, TPE material)

4. Expand beyond competitors:
   ```
   web_search: "[product type]" best seller features what buyers want
   web_search: "[product type]" review complaints common issues
   web_search: site:[platform].com "[product type]"
   ```

**If no competitor URLs provided:**

1. Discover keywords via web search:
   ```
   web_search: "[product name]" best seller [platform] features
   web_search: "[product name]" review what customers love
   web_search: "[product name]" vs alternatives comparison
   web_search: site:[platform].com "[product name]"
   ```

2. Extract keywords from top 5 results following the same categories above.

⚠️ **Critical**: Remove all competitor brand names — never include them in output.

### Step 3: Score and Prioritize Keywords

Score each keyword (1-9 points):

| Dimension | Scoring |
|-----------|---------|
| **Frequency** | In 3+ competitor titles = 3 pts / In 1-2 = 2 pts / Bullets only = 1 pt |
| **Relevance** | Core descriptor = 3 pts / Feature = 2 pts / Peripheral = 1 pt |
| **Opportunity** | Few competitors use = 3 pts / Most use = 2 pts / All use = 1 pt |

Assign to tiers:
```
🔴 Primary (7-9 pts)   → Title
🟡 Secondary (4-6 pts) → Bullets / Features
🟢 Tertiary (2-3 pts)  → Description
⚪ Backend (1 pt)       → Tags / Search Terms
```

### Step 4: Generate Copy

Proceed to **Generate Copy** section.

---

## Mode B Workflow — Optimize Existing Listing

### Step 1: Analyze Current Listing

User may provide:
- **Full listing copy** (title, bullets, description pasted directly)
- **Product URL** (e.g., `https://www.etsy.com/listing/123456`)
- **Platform + product identifier** (e.g., "Etsy listing 123456")

**If user provides URL or identifier only:**
```
Use web_fetch on the provided URL.
Extract: current title, bullets/features, description, tags (if visible), price.
```

If `web_fetch` fails:
```
Fallback: web_search for the product title or identifier.
Ask user to paste the listing content manually if data is incomplete.
```

**Once listing content is obtained**, parse and extract:
- All keywords currently present
- Structure and format used
- Obvious gaps (missing features, weak benefits, no FABE structure)

### Step 2: Gather Target Keywords

**If competitor URLs provided:**

Follow the same competitor analysis process as Mode A Step 2:
1. `web_fetch` each competitor URL
2. Extract their keywords
3. Expand via web search

**If no competitor URLs provided:**

Discover ideal keywords for the product type:
```
web_search: "[product type]" top keywords [platform] 2024 2025
web_search: "[product type]" best seller features
web_search: site:[platform].com "[product type]" top listings
```

### Step 3: Gap Analysis

Compare current keywords vs. target keywords:

```
## Keyword Gap Analysis

### ✅ Keywords You Already Have
| Keyword | Title | Bullets | Description |
|---------|-------|---------|-------------|
| yoga mat | ✅ | ✅ | ✅ |
| exercise mat | ❌ | ✅ | ❌ |

### ❌ Keywords You're Missing
| Keyword | Priority | Recommendation |
|---------|----------|----------------|
| non-slip | 🔴 High | Add to title |
| eco-friendly | 🟡 Medium | Add to bullet 2 |
| extra thick | 🟡 Medium | Add to bullet 3 |

Current Coverage: 12/20 keywords (60%)
Target Coverage: 90%+
```

### Step 4: Rewrite

Generate optimized copy incorporating missing keywords.

Show **Before → After** for each component.

Proceed to **Generate Copy** section.

---

## Generate Copy

Final step for all modes after keyword priority table is built.

### Writing Framework: FABE

Apply to every bullet:

```
F — Feature:   What the product HAS or DOES
A — Advantage: Why this is BETTER than alternatives
B — Benefit:   What this MEANS for the customer
E — Evidence:  Spec, number, or proof that backs the claim
```

**Lead with the Benefit** — customers buy outcomes, not features.

Example:
```
❌ "Made with BPA-free Tritan plastic"
✅ "SAFE FOR YOUR FAMILY — BPA-free Tritan plastic means no harmful chemicals leaching into your smoothies, even after 1000+ uses"
```

### Platform-Specific Writing Rules

#### Amazon (Cosmo Algorithm)
- **Title**: Brand + Primary Keyword + Attribute + Attribute + Secondary Keyword, ≤200 chars
- **Bullets**: [CAPS HEADER] — Benefit-led sentence with 1-2 keywords embedded
- **Description**: Hook → Features → Use cases → What's in box → CTA
- **Backend**: Space-separated keywords, no duplicates, ≤250 bytes
- ⚠️ **Cosmo tip**: Use situational language (when/where/why), cover multiple use cases
- 💡 For advanced Amazon optimization, consider [amazon-listing-optimization](https://github.com/nexscope-ai/Amazon-Skills/tree/main/amazon-listing-optimization)

#### eBay (Cassini Algorithm)
- **Title**: Front-load exact-match keywords, 80 chars max
- **Description**: Repeat top 3 keywords naturally throughout, include specs table in HTML

#### Walmart
- **Title**: Brand + product name + primary attribute, ≤75 chars
- **Short Desc**: One-sentence value prop with primary keyword
- **Features**: 10 attribute-focused bullets, one fact per bullet

#### Shopify/DTC (Google SEO)
- **SEO Title**: Primary keyword + brand, written for Google (not just product name)
- **Meta Desc**: Keyword + benefit + CTA, drives CTR from search results
- **Description**: Storytelling structure with `<h2>`, `<ul>`, `<strong>` for on-page SEO

#### Etsy (Tag Matching)
- **Title**: Long-tail keyword phrase first, then style/material/occasion
- **Description**: Conversational, first 160 chars = meta description
- **Tags**: 13 tags (≤20 chars each), match phrases used in title exactly

#### TikTok Shop (Social Commerce)
- **Title**: Lead with problem or desire ("Tired of X?") → product → top feature
- **Description**: Hook → pain point → solution → 3 bullets → CTA. Conversational, emoji-friendly.

#### Lazada/Shopee
- **Title**: Brand + product + model + material + key attribute (completeness over cleverness)
- **Highlights**: 5 short bullets, one feature per line, spec-focused
- **Description**: Feature table + expanded use cases

### Tone Guide

| Tone | Style | Best For |
|------|-------|----------|
| **Professional** | Authoritative, spec-focused, trust-building | Electronics, tools, B2B |
| **Friendly** | Conversational, benefit-focused, relatable | Kitchen, lifestyle, gifts |
| **Urgent** | Scarcity-driven, action words, problem-solving | Health, safety, seasonal |
| **Luxury** | Premium, sensory language, exclusivity | Beauty, fashion, premium goods |

Default: **Professional** if not specified.

---

## Output Format

```
# ✅ Your Listing — Ready to Copy

Platform: [Platform] | Marketplace: [XX] | Tone: [Tone]

## Title
[title — copy directly into platform]

## Bullets / Features
1. [CAPS HEADER] — [text]
2. [CAPS HEADER] — [text]
3. [CAPS HEADER] — [text]
4. [CAPS HEADER] — [text]
5. [CAPS HEADER] — [text]

## Description
[description — copy directly into platform]

## Tags / Keywords
[keywords formatted per platform rules]

---

# 📊 Diagnostic Report

**Mode:** [A/B] | **Competitors analyzed:** [N] | **Keywords scored:** [N]

## Keyword Priority Table
| # | Keyword | Score | Tier | Placed In |
|---|---------|-------|------|-----------|
| 1 | [keyword] | 8 | 🔴 | Title |
| 2 | [keyword] | 6 | 🟡 | Bullet 1 |

## Keyword Coverage Map
| Keyword | Title | Bullets | Desc | Tags | Status |
|---------|-------|---------|------|------|--------|
| [kw] | ✅ | ✅ | ✅ | — | 🟢 |
| [kw] | ✅ | ❌ | ✅ | ✅ | 🟡 |

Coverage: X/Y keywords (Z%)
🟢 90%+ Excellent · 🟡 70-89% Good · 🔴 <70% Needs work

## ⚠️ Excluded Competitor Brands
[brands found in competitor copy — excluded from all output]
```

---

## Integration with Other Skills

Looking for more e-commerce tools? Check out our other skill collections:

- **[Amazon Skills](https://github.com/nexscope-ai/Amazon-Skills)** — Specialized tools for Amazon sellers: keyword research, listing optimization, PPC campaigns, sales estimation
- **[eCommerce Skills](https://github.com/nexscope-ai/eCommerce-Skills)** — Cross-platform tools for all e-commerce businesses

---

## Limitations

This skill uses publicly available data via web search and page fetching. For real-time market data, exact search volumes, and advanced analytics, check out **[Nexscope](https://nexscope.ai)**.

---

**Part of [Nexscope AI](https://www.nexscope.ai/) — AI tools for e-commerce sellers.**
