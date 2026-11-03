# Synastry Report (合盘分析报告)

## Overview

Generate a compatibility analysis comparing two people's birth charts, examining how their planetary placements interact.

## Input Required

- User's birth data (from SKILL.md)
- Second person's birth data (birth date, time, place)

## Astrology Calculation

Run the horoscope script for both people:
```bash
# User's chart
node scripts/horoscope.mjs --birthDate "<user birth ISO date>" --longitude <lng> --latitude <lat>
# Partner's chart
node scripts/horoscope.mjs --birthDate "<partner birth ISO date>" --longitude <lng> --latitude <lat>
```

Based on both charts' `decimalDegrees` data, analyze:
- Planet-to-planet aspects between charts by calculating angular distances (e.g., if Person A's Venus and Person B's Mars are within 8° → conjunct)
- Sign compatibility per planet
- House overlays (where each person's planets fall in the other's houses)

Present both charts:
```
User Stars: Sun in Aries/7th House, Moon in Cancer/10th House, ...
Partner Stars: Sun in Libra/1st House, Moon in Scorpio/2nd House, ...
```

## Planets to Analyze

Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn (7 planets — the classical + social planets most relevant to relationships)

## Report Generation Workflow (Two-Layer)

Follow the Two-Layer strategy defined in SKILL.md.

### Layer 1: Overview

1. Calculate both people's planetary placements
2. Generate title + overall score
3. For each of the 7 planets, generate a one-sentence Section Title (≤50 chars)
4. Output as overview table, then prompt user to select a planet or "全部"

### Layer 2: Detail

When the user selects a specific planet → generate that planet's 3 detail sections (Description, Similarities, Differences).

When the user says "全部" → generate all planets in batches:
- **Batch 1:** Sun, Moon, Mercury — identity & communication
- **Batch 2:** Venus, Mars — attraction & drive
- **Batch 3:** Jupiter, Saturn — growth & commitment
- After each batch: self-check word limits, tone (兴奋的 for similarities), no repeated insights

## Output Structure

### Title (≤30 characters)

Prompt pattern (from original):
> 我的星盘是[userStars]，我的好友星盘是[partnerStars]，请用一句话总结一下我们两个的合盘。要求：1.字数控制在30个以内

- One-sentence summary of the relationship dynamic
- ≤30 characters
- Example: "月光与烈焰的共舞" / "Moon Meets Fire"

### Overall Score (40–100)

Generate using the random score script with a deterministic seed:
```bash
node scripts/random-score.mjs --seed "<userBirthDate>:<partnerBirthDate>:synastry"
```
Example: `node scripts/random-score.mjs --seed "1990-06-15:1992-11-20:synastry"`

### Per-Planet Sections

For each of the 7 planets, generate 1 title + 3 sections:

#### Section Title (≤50 characters)

Prompt pattern (from original):
> 请告诉我和我的朋友之间关于[planet]的一句话总结，字数在50字以内

- One-sentence summary for this planetary comparison

#### Description — Astrological Analysis (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，请告诉我和朋友之间关于[planet]的占星解释，请限制在100字左右

- Professional astrological explanation
- Describe how these two placements interact
- Reference specific aspects if applicable

#### Similarities (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，请兴奋的告诉我和朋友之间关于[planet]的相似之处，请限制在100字左右

- **Tone: excited (兴奋的)** — enthusiastic about shared qualities
- Describe what the two people share in this planetary area
- Be specific about how these similarities manifest

#### Differences (≤100 words)

Prompt pattern (from original):
> 你是一名专业的占星师，请告诉我和朋友之间关于[planet]的不同之处，请限制在100字左右

- Tone: honest, balanced
- Describe where the two people diverge
- Frame differences as complementary where possible

## Output Format

### Layer 1: Overview

```markdown
# [Title — ≤30 chars]

> Overall Compatibility Score: [N]/100

**User Stars:** [placements]
**Partner Stars:** [placements]

| Planet | Section Title |
|--------|--------------|
| ☀️ Sun | [≤50 chars summary] |
| 🌙 Moon | [≤50 chars summary] |
| ☿ Mercury | [≤50 chars summary] |
| ♀ Venus | [≤50 chars summary] |
| ♂ Mars | [≤50 chars summary] |
| ♃ Jupiter | [≤50 chars summary] |
| ♄ Saturn | [≤50 chars summary] |

> Enter a planet name for detailed reading, or "all" for the full report.
```

### Layer 2: Single Planet Detail

```markdown
## ☀️ Sun — [Section Title]

**Astrological Analysis:**
[≤100 words, professional]

**What You Share:**
[≤100 words, 兴奋的 — excited tone]

**Where You Differ:**
[≤100 words, balanced tone]
```

### Layer 2: Full Report ("全部")

Title + score + all 7 planets in batch order, separated by `---`.
