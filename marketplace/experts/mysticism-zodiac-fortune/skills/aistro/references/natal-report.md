# Natal Chart Report (本命盘报告)

## Overview

Generate a comprehensive birth chart analysis examining each planet's placement in the user's chart. This report is the most detailed — it covers 10 planets, each with 1 title + 3 detail sections.

## Input Required

- Birth date, birth time, birth place (collected by SKILL.md)

## Astrology Calculation

Run the horoscope script to compute the user's chart:
```bash
node scripts/horoscope.mjs --birthDate "<ISO date>" --longitude <lng> --latitude <lat>
```

From the output, extract each planet's sign and house placement. Present the full star chart summary before the detailed sections:
```
Stars: Sun in Aries/7th House, Moon in Cancer/10th House, Mercury in Pisces/6th House, ...
```

## Report Generation Workflow (Two-Layer)

Follow the Two-Layer strategy defined in SKILL.md.

### Layer 1: Overview

1. Calculate the user's planetary placements in signs and houses
2. Generate a report title (motto-style)
3. For each of the 10 planets, generate a one-sentence Section Title (≤100 words)
4. Output as overview table, then prompt user to select a planet or "全部"

### Layer 2: Detail

When the user selects a specific planet → generate that planet's 3 detail sections (Strengths, Opportunities, Challenges).

When the user says "全部" → generate all planets in batches:
- **Batch 1:** Sun, Moon, Mercury — personality core
- **Batch 2:** Venus, Mars, Jupiter — social expression
- **Batch 3:** Saturn, Uranus — structure & change
- **Batch 4:** Neptune, Pluto — deep transformation
- After each batch: self-check word limits, tone correctness, no repeated metaphors

## Output Structure

### Title

Prompt pattern (from original):
> 你是一名专业的占星师。我的生日是[birthDate]，我的星盘是[stars]，现在请你用格言式的语言总结一下我的本命盘，不要超过50个字符。

Requirements:
- Motto/aphorism style (格言式)
- ≤50 characters
- Summarize the overall natal chart theme
- Example: "心怀星海，脚踏实地的探索者" / "A Dreamer with Roots in Reality"

### Section Title — Per-Planet Summary (Layer 1)

Prompt pattern (from original):
> 你是一名专业的占星师，我的星盘是[stars]，请描述关于我[planet in sign/house]的解读，请限制在100字左右。

- Tone: professional astrologer (专业占星师)
- ≤100 words per planet
- Focus on the specific meaning of this planet's placement
- Used in the overview table

### Per-Planet Detail Sections (Layer 2)

When expanding a specific planet, generate 3 parts:

#### 1. Strengths — 优势 (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，我的星盘是[stars]，气势磅礴得告诉我[planet in sign/house]的优势，请限制在100字左右。

- **Tone: bold and magnificent (气势磅礴)** — this is a dramatic, empowering tone
- Describe the advantages and powers this placement grants
- Be specific, not generic

#### 2. Opportunities — 机遇 (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，我的星盘是[stars]，喜出望外得告诉我[planet in sign/house]的机遇，请限制在100字左右。

- **Tone: pleasantly surprised and delighted (喜出望外)** — convey exciting discoveries
- Focus on growth potential and fortunate aspects
- Highlight unexpected gifts this placement brings

#### 3. Challenges — 挑战 (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，我的星盘是[stars]，慷慨激昂得告诉我[planet in sign/house]的挑战，请限制在100字左右。

- **Tone: passionate and inspiring (慷慨激昂)** — acknowledge difficulty with rallying energy
- Be honest about challenges while remaining supportive
- Frame challenges as opportunities for growth

## Planet Order

☀️ Sun → 🌙 Moon → ☿ Mercury → ♀ Venus → ♂ Mars → ♃ Jupiter → ♄ Saturn → ♅ Uranus → ♆ Neptune → ♇ Pluto

## Output Format

### Layer 1: Overview

```markdown
# [Title — motto style, ≤50 chars]

**Stars:** Sun in [Sign]/[House], Moon in [Sign]/[House], ...

| Planet | Placement | Summary |
|--------|-----------|---------|
| ☀️ Sun | [Sign] / [House] | [≤100 words interpretation] |
| 🌙 Moon | [Sign] / [House] | [≤100 words interpretation] |
| ☿ Mercury | [Sign] / [House] | [≤100 words interpretation] |
| ♀ Venus | [Sign] / [House] | [≤100 words interpretation] |
| ♂ Mars | [Sign] / [House] | [≤100 words interpretation] |
| ♃ Jupiter | [Sign] / [House] | [≤100 words interpretation] |
| ♄ Saturn | [Sign] / [House] | [≤100 words interpretation] |
| ♅ Uranus | [Sign] / [House] | [≤100 words interpretation] |
| ♆ Neptune | [Sign] / [House] | [≤100 words interpretation] |
| ♇ Pluto | [Sign] / [House] | [≤100 words interpretation] |

> Enter a planet name for detailed reading, or "all" for the full report.
```

### Layer 2: Single Planet Detail

```markdown
## ☀️ Sun in [Sign] / [House]

### Strengths
[≤100 words, 气势磅礴 — bold and magnificent]

### Opportunities
[≤100 words, 喜出望外 — delighted and surprised]

### Challenges
[≤100 words, 慷慨激昂 — passionate and inspiring]
```

### Layer 2: Full Report ("全部")

Same as single planet detail, repeated for all 10 planets in batch order, separated by `---`.
