# Horoscope Prediction Report (运势预测报告)

## Overview

Generate a daily horoscope prediction combining the user's natal chart with current planetary transits for a specific date.

## Input Required

- Birth data (from SKILL.md)
- Target date (default: today)

## Astrology Calculation

Run the horoscope script twice to compute both charts:
```bash
# User's natal chart
node scripts/horoscope.mjs --birthDate "<birth ISO date>" --longitude <lng> --latitude <lat>
# Transit chart for target date
node scripts/horoscope.mjs --birthDate "<target date>T12:00:00" --longitude <lng> --latitude <lat>
```

Based on both charts' `decimalDegrees` data, analyze:
- Aspects between transiting and natal planets (conjunctions, oppositions, trines, squares, sextiles — use standard orbs)
- House activations (transiting planets entering natal houses)
- Significant transits (Saturn return, Jupiter transit, etc.)

## Topics

Default topics: Career (事业), Love (感情), Wealth (财富), Creativity (创造力), Health (健康)

The user may request specific topics only.

## Report Generation Workflow (Two-Layer)

Follow the Two-Layer strategy defined in SKILL.md.

### Layer 1: Overview

1. Calculate natal chart + transit chart for target date
2. Generate title + summary (Steven Forrest style)
3. For each topic, generate a score (40-100) and one-sentence overview
4. Output as overview table, then prompt user to select a topic or "全部"

### Layer 2: Detail

When the user selects a specific topic → generate that topic's 4 detail sections (Overview, Planetary Influence, Strengths, Challenges).

When the user says "全部" → generate all topics in batches:
- **Batch 1:** Career + Love
- **Batch 2:** Wealth + Creativity
- **Batch 3:** Health
- After each batch: self-check word limits, Sue Tompkins style consistency, no repeated phrasing

## Output Structure

### Title (≤10 characters)

Prompt pattern (from original):
> 请结合我的本命星盘和今日星盘为我生成这一天的星座运势摘要标题。要求：1.不提及您的依据 2.格言的形式 3.不提及任何日期 4.不超过10个字

- Motto/aphorism style (格言形式)
- ≤10 characters
- Do NOT mention your basis for derivation
- Do NOT mention any date
- Example: "破茧成蝶" / "Seeds Bloom"

### Summary (≤140 words)

Prompt pattern (from original):
> 请你用斯蒂芬·福里斯特(Steven Forrest)的语言告诉我我在这一天的运势。要求：1.不要提及你的依据 2.字数不超过140字 3.不要提及任何日期 4.最后一句话提出一下我今天会遇到什么挑战 5.以"今天"开头

- **Style: Steven Forrest** (evolutionary astrology — poetic, soul-centered, growth-oriented)
- Start with "Today" / "今天"
- ≤140 words
- Do NOT mention your basis for derivation
- Do NOT mention any specific date
- Last sentence: hint at the day's challenge

### Per-Topic Sections

For each topic, generate 4 parts + a score:

#### Score (40–100)
Generate using the random score script with a deterministic seed:
```bash
node scripts/random-score.mjs --seed "<birthDate>:<targetDate>:<topic>" --with-category
```
Example: `node scripts/random-score.mjs --seed "1990-06-15:2026-03-12:career" --with-category`

#### Section 1: Overview (≤140 words)

Prompt pattern (from original):
> 请告诉我我当天关于[topic]的星座运势。要求：1.把字数控制在140字左右 2.不要提及一天中的任何具体时间 3.提到一些占星术的基础 4.不要以"今天是xxx日"开头

- ≤140 words
- Reference basic astrological principles
- Do NOT mention specific times of day
- Do NOT start with "Today is [date]..." / "今天是xxx日..."

#### Section 2: Planetary Position Analysis (≤140 words)

Prompt pattern (from original):
> 请你用苏·汤普金斯(Sue Tompkins)的语言告诉我我关于[topic]的行星在这一天所在的宫位，并描述它的象征。要求：1.找到和[topic]关联的行星并说明它的位置 2.不超过140字 3.不要以'根据xxx'开头 4.不要提及具体的日期 5.只使用一段话输出结果

- **Style: Sue Tompkins** (practical aspect interpretation, clear symbolism)
- Identify the planet most associated with this topic
- Describe its current transit house position
- Explain the symbolic meaning
- ≤140 words, single paragraph
- Do NOT start with "According to..." / "根据xxx..."
- Do NOT mention specific dates

#### Section 3: Strengths (≤200 words)

Prompt pattern (from original):
> 请你用苏·汤普金斯的语言告诉我我在这一天在[topic]这个方面有什么优势。要求：1.200字以内 2.提出至少三个有利方面 3.不要以'根据xxx'开头 4.不要提及具体时间 5.直接说优势点，不要以"你在xxx有以下优势"开头 6.只用一段话输出

- **Style: Sue Tompkins**
- ≤200 words, single paragraph
- List at least 3 favorable aspects
- Do NOT start with "According to..." / "根据xxx..."
- Do NOT start with "You have the following advantages in..." / "你在xxx有以下优势..."
- Do NOT mention specific times
- Jump straight into the strengths

#### Section 4: Challenges (≤200 words)

Prompt pattern (from original):
> 请你用苏·汤普金斯的语言告诉我我在这一天在[topic]这个方面有什么挑战。要求：1.200字以内 2.不要以'根据xxx'开头 3.不要提及具体时间 4.结尾说一下解决办法 5.只用一段话输出

- **Style: Sue Tompkins**
- ≤200 words, single paragraph
- Do NOT start with "According to..." / "根据xxx..."
- Do NOT mention specific times
- End with a suggested approach to overcome the challenge

## Topic → Planet Mapping Reference

| Topic | Primary Planet | Secondary |
|---|---|---|
| Career (事业) | Saturn, Jupiter | Sun, Mars |
| Love (感情) | Venus | Moon, Mars |
| Wealth (财富) | Jupiter | Venus, 2nd House ruler |
| Creativity (创造力) | Neptune | Venus, 5th House ruler |
| Health (健康) | Mars | Sun, 6th House ruler |

## Output Format

### Layer 1: Overview

```markdown
# [Title — ≤10 chars, motto style]

> [Summary — Steven Forrest style, ≤140 words, starts with "Today"/"今天"]

| Topic | Score | Overview |
|-------|-------|----------|
| 💼 Career | [N]/100 | [one-sentence overview] |
| ❤️ Love | [N]/100 | [one-sentence overview] |
| 💰 Wealth | [N]/100 | [one-sentence overview] |
| 🎨 Creativity | [N]/100 | [one-sentence overview] |
| 🏥 Health | [N]/100 | [one-sentence overview] |

> Enter a topic name for detailed reading, or "all" for the full report.
```

### Layer 2: Single Topic Detail

```markdown
## 💼 Career — Score: [N]/100

### Overview
[≤140 words]

### Planetary Influence
[≤140 words, Sue Tompkins style, single paragraph]

### Strengths
[≤200 words, Sue Tompkins style, ≥3 points, single paragraph]

### Challenges
[≤200 words, Sue Tompkins style, ends with solution, single paragraph]
```

### Layer 2: Full Report ("全部")

Title + Summary + all 5 topics in batch order, separated by `---`.
