# Moon Phase Report (月相报告)

## Overview

Generate a lunar influence reading combining the current moon phase with the user's natal chart. This is a concise report — shorter than other report types.

## Input Required

- User's birth data (from SKILL.md)
- Target date (default: today)

## Moon Phase Determination

Run the moon phase script for the target date:
```bash
node scripts/moon-phase.mjs --date "<YYYY-MM-DD>"
```

Map the returned `phaseText` to display:

| phaseText | Chinese | Emoji |
|---|---|---|
| new_moon | 新月 | 🌑 |
| waxing_crescent_moon | 眉月 | 🌒 |
| first_quarter_moon | 上弦月 | 🌓 |
| waxing_gibbous_moon | 盈凸月 | 🌔 |
| full_moon | 满月 | 🌕 |
| waning_gibbous_moon | 亏凸月 | 🌖 |
| last_quarter_moon | 下弦月 | 🌗 |
| waning_crescent_moon | 残月 | 🌘 |

## Retrograde Planet Check

Run the horoscope script for the target date to get retrograde planets:
```bash
node scripts/horoscope.mjs --birthDate "<target date>T12:00:00" --longitude <lng> --latitude <lat>
```

The `retrogradeStars` array in the output contains the currently retrograde planets.

## Output Structure

### Summary (≤40 words)

Prompt pattern (from original):
> 我的星盘是[userStars]，今天的月相是[moonPhase]，生成一个简报，这个报告应该结合月相的影响和我的星盘特点，特别关注于事业、感情、财富等。要求：1.字数控制在40个以内，并且只有一段话 2.只是着重于事业、感情、财富等方向，并不是一定要有相关内容

- Combine moon phase influence with user's natal chart
- Focus on career, love, wealth directions
- ≤40 words, single paragraph
- Only mention these areas if relevant — not all need to be present

### Retrograde Readings

For each currently retrograde planet, generate:

Prompt pattern (from original):
> 我的星盘是[userStars]，我的[planet]是逆行的，生成行星逆行的解读报告。要求：1.生成该行星逆行相对于我的影响报告，字数控制在60个以内

- ≤60 words per planet
- Combine the general retrograde meaning with the user's specific natal placement of that planet
- Single paragraph

## Output Format

```markdown
# 🌙 Moon Phase Report

**Date:** [target date]
**Current Phase:** [Phase Name] [emoji] — [Phase Chinese Name]

## Summary
[≤40 words, single paragraph, combining moon phase + natal chart]

## Planetary Retrogrades

### ☿ Mercury Retrograde
[≤60 words, retrograde impact on user]

### ♄ Saturn Retrograde
[≤60 words, retrograde impact on user]

[...for each retrograde planet]
```

If no planets are currently retrograde, output:

```markdown
## Planetary Retrogrades
No planets currently in retrograde. The energy flows freely today.
```
