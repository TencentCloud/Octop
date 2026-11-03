---
name: tarot-reading
description: "Tarot reading skill. This skill should be used when the user wants to: draw tarot cards, do a tarot reading, ask about tarot spreads or card meanings; ask yes/no questions (can I, will it, should I); find lost items; seek advice or reminders. This skill uses Python's secrets module for cryptographically secure random card draws (TRNG-level, not AI probability sampling). Supports both Chinese and English. Supports multiple languages: call the script with 'en' as the third argument for English output, or use English question types directly (Yes/No, Find, Advice, Reminder)."
---

# Tarot Reading Skill

## Overview

This skill provides complete readings for the 78-card Rider-Waite-Smith tarot deck, supporting 4 question types and 7 spreads, with cryptographically secure random card draws using Python's `secrets` module.

**Dual Language Support**: Works with both Chinese and English users. Language is auto-detected from question type keywords or the `lang` parameter.

## Core Principles

1. **Randomness**: All card draws use Python's `secrets` module (system-level cryptographic entropy) — not AI probability sampling
2. **Deck**: Standard Rider-Waite-Smith 78-card deck — 22 Major Arcana + 56 Minor Arcana
3. **Respect Privacy**: User holds the question in their mind; never ask for specifics
4. **Card Meanings**: Based on traditional Rider-Waite-Smith symbolism and interpretation
5. **Entertainment**: Tarot readings are for entertainment only and do not constitute actual decision-making advice

## Question Types

| Type | Description | Trigger Phrases |
|------|-------------|-----------------|
| **Yes/No** | Quick binary answer | can I, will it, should I, is it, does, will |
| **Find** | Locate lost items | where is, lost, missing, can't find |
| **Advice** | Seek guidance on what to do | what should I do, how to, advice, guidance |
| **Reminder** | Alerts and things to watch for | watch out, remind me, be careful, notice |

## Supported Spreads

### 1. Single Card (1 card)
- **Best for**: Yes/No, Find
- **Interpretation**: Direct answer or item location clue

### 2. Past-Present-Future (3 cards)
- **Best for**: Advice, Reminder, Yes/No upgrade
- **Interpretation**: Reveals the timeline of events

### 3. Situation-Advice-Outcome (3 cards)
- **Best for**: Advice, Reminder
- **Interpretation**: Objective analysis → action guidance → expected outcome

### 4. Self-Others-Relationship (3 cards)
- **Best for**: Advice, Reminder (interpersonal focus)
- **Interpretation**: Analyzes both parties' positions in a relationship

### 5. Four Elements (4 cards)
- **Best for**: Advice, Reminder
- **Interpretation**: Analyzes from Fire/Water/Air/Earth perspectives

### 6. Horseshoe (7 cards)
- **Best for**: Advice, Reminder
- **Interpretation**: U-shaped spread analyzing obstacles and how to overcome them

### 7. Celtic Cross (10 cards)
- **Best for**: Advice, Reminder (most comprehensive)
- **Interpretation**: In-depth analysis with 10 positions including core, obstacle, foundation, past, possible future, above, self, surroundings, hope/fear, and outcome

### 8. Finding (3 cards)
- **Best for**: Find
- **Interpretation**: Item status → obstacle → search guidance

### 9. Finding Extended (5 cards)
- **Best for**: Find
- **Interpretation**: Detailed location, condition, barrier, time, and action guidance

## Usage Flow

### Step 1: Understand the User's Question

Map the user's question to one of the 4 types:
- **Yes/No**: Asks "can/will/is" → **Yes/No**
- **Advice**: Asks "what to do/how to/which to choose" → **Advice**
- **Reminder**: Asks "what to watch/be careful about" → **Reminder**
- **Find**: Asks "where is/lost/missing" → **Find**

### Step 2: Determine the Spread

- User specifies a spread → use specified spread
- User doesn't specify → use the default for that question type
- Ask if they want to upgrade (e.g., "Would you like to upgrade this Yes/No to a 3-card Past-Present-Future?")

### Step 3: Execute the Draw Script

Call `scripts/draw_tarot.py` to perform the draw:

```
python <skill_dir>/scripts/draw_tarot.py [question_type] [spread_name] [lang]
```

**Parameters**:
- `question_type`: `Yes/No`, `Find`, `Advice`, `Reminder` (or Chinese equivalents)
- `spread_name`: `Single Card`, `Past-Present-Future`, `Situation-Advice-Outcome`, `Self-Others-Relationship`, `Four Elements`, `Horseshoe`, `Celtic Cross`, `Finding`, `Finding Extended`
- `lang`: `cn` (default) or `en` — auto-detected if English question type is used

### Step 4: Interpret the Result

The script outputs two parts:
1. **JSON structured data**: timestamp, spread, question type, card details
2. **Formatted readable text**: interpreted reading content

**Interpretation Style Requirements**:
- Concise and natural, no fluff
- Connect card meanings to the user's actual question context
- Explain why each card is relevant to the question
- Stay faithful to card meanings, no over-interpretation
- End with "Tarot readings are for entertainment only"

### Step 5: Follow-up Options (if applicable)

After the reading:
- Ask if user wants to try a different spread for more depth
- Offer to interpret a specific card in more detail
- For Yes/No questions, ask if they'd like to upgrade to a 3-card spread

## Yes/No Judgment Logic

Single card Yes/No answers are determined by:

| Category | Upright | Reversed |
|----------|---------|----------|
| Major Arcana (positive cards) | YES | NO |
| Major Arcana (negative cards) | NO | YES |
| Major Arcana (neutral cards) | YES | NO |
| Wands/Cups/Pentacles (Minor) | YES | NO |
| Swords (Minor) | NO | YES |

**Positive Major Arcana** (favor YES): Fool 0, Magician 1, Empress 3, Lovers 6, Strength 8, Hermit 9, Wheel of Fortune 10, Justice 11, Temperance 14, Star 17, Sun 19, Judgement 20, World 21

**Negative Major Arcana** (favor NO): Hierophant 5, Chariot 7, Hanged Man 12, Death 13, Devil 15, Tower 16, Moon 18

## Output Format Template

```
[*] [Tarot Reading · <Spread Name>]

<Interpretation of each card>

---
<Summary based on question type>
---

[!] Tarot readings are for entertainment only and do not constitute actual decision-making advice.
```

## Common Issues

**Q: User didn't specify a spread?**
A: Use the default spread for that question type and explain your choice.

**Q: Same card drawn twice?**
A: If the exact same card (same number and orientation) appears twice, note that the probability is ~1/6084. This may carry deeper meaning — interpret it accordingly.

**Q: User's question is very personal and they don't want to share details?**
A: That's perfectly fine. Respect their privacy — they only need to hold the question in their mind.
