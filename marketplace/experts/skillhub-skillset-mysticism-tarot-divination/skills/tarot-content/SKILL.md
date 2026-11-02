---
name: tarot-content
description: Generate tarot × astrology content for social media — weekly horoscope scripts, tarot spreads, video scripts, and cover art. Use when asked to "create tarot content", "weekly horoscope", "tarot reading script", "zodiac video", "astrology content calendar", "tarot spread design", or "horoscope video script". Supports 12-sign weekly readings, event-driven specials (retrogrades, eclipses, conjunctions), and multi-platform formatting (YouTube Shorts, TikTok, Instagram, blog).
---

# Tarot Content Generator

Create professional tarot × astrology content for social media at scale.

## Capabilities

1. **Weekly 12-Sign Readings** — Scripted horoscope videos with tarot card pulls
2. **Event-Driven Specials** — Content for major transits (retrogrades, eclipses, conjunctions)
3. **Tarot Spreads** — Custom spread designs with interpretation frameworks
4. **Video Scripts** — TTS-ready scripts with screen text cues
5. **Cover Art** — Pillow-generated thumbnails optimized for mobile
6. **Content Calendar** — Automated scheduling based on astrological events

## Quick Start

### Weekly 12-Sign Reading

```
Generate a weekly tarot reading for all 12 signs.
Date range: {start} to {end}
Style: conversational, no jargon
Format: video script with screen text cues
```

The agent will:
1. Pull real ephemeris data (planetary positions, aspects)
2. Map transits to each sign's house system
3. Pull tarot cards (Challenge / Guidance / Blessing spread)
4. Write scripts in a natural, engaging voice

### Event-Driven Special

```
Create a special video about {transit/event}.
Example: Saturn conjunct Neptune in Aries
Include: what it means, historical context, 12-sign breakdown
```

## Content Framework

### The 3-Card Spread (Challenge / Guidance / Blessing)

A proven framework for weekly readings:

| Position | Meaning | Tone |
|----------|---------|------|
| Challenge | What to watch out for | Honest, not scary |
| Guidance | What to focus on | Actionable advice |
| Blessing | What's coming | Hopeful, encouraging |

### Script Structure (per sign, 60-90 seconds)

```
1. Opening hook (5s) — "Hey {Sign}, this week is about..."
2. Transit context (10s) — What planets are doing in their house
3. Card 1: Challenge (15s) — The obstacle + real-life scenario
4. Card 2: Guidance (15s) — Practical advice
5. Card 3: Blessing (10s) — The reward / positive outcome
6. CTA (5s) — "Follow for your sign's weekly reading"
```

### Writing Style Guidelines

- **Say it like a friend, not a fortune teller** — "You might feel stuck" not "The cards reveal stagnation"
- **Use scenarios** — "That coworker drama? Time to set boundaries" not "Conflict in relationships"
- **Numbers in words** — "twenty twenty-six" not "2026" (TTS-friendly)
- **Avoid fear-mongering** — Even tough cards get a constructive spin
- **No clichés** — Ban "the universe has a plan", "trust the process", "everything happens for a reason"

## Ephemeris Data

### Using pyswisseph (recommended)

```python
import swisseph as swe
from datetime import datetime

def get_planet_position(planet_id, dt):
    """Get planet longitude in zodiac."""
    jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute/60)
    pos = swe.calc_ut(jd, planet_id)[0]
    longitude = pos[0]
    sign_num = int(longitude / 30)
    degree = longitude % 30
    signs = ['Aries','Taurus','Gemini','Cancer','Leo','Virgo',
             'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces']
    return signs[sign_num], degree

# Planet IDs: SUN=0, MOON=1, MERCURY=2, VENUS=3, MARS=4,
#             JUPITER=5, SATURN=6, URANUS=7, NEPTUNE=8, PLUTO=9
```

### Install
```bash
pip install pyswisseph
```

## Cover Art Generation

### Pillow-based covers (no AI text artifacts)

```python
from PIL import Image, ImageDraw, ImageFont
import os

def generate_cover(sign, hook_text, date_range, colors, output_path):
    """Generate a 1080x1920 Shorts cover."""
    W, H = 1080, 1920
    img = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)

    # Gradient background
    for y in range(H):
        r = int(colors[0][0] + (colors[1][0]-colors[0][0]) * y/H)
        g = int(colors[0][1] + (colors[1][1]-colors[0][1]) * y/H)
        b = int(colors[0][2] + (colors[1][2]-colors[0][2]) * y/H)
        draw.line([(0,y),(W,y)], fill=(r,g,b))

    # Load fonts (adjust paths for your system)
    font_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    font_md = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 56)
    font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 40)

    # Sign name (large, centered)
    draw.text((W//2, H*0.35), sign.upper(), font=font_lg, fill='white', anchor='mm')

    # Date range
    draw.text((W//2, H*0.48), date_range, font=font_md, fill=(255,215,0), anchor='mm')

    # Hook text
    draw.text((W//2, H*0.62), hook_text, font=font_md, fill='white', anchor='mm')

    # Brand
    draw.text((W//2, H*0.78), "WEEKLY TAROT", font=font_sm, fill=(200,200,200), anchor='mm')

    img.save(output_path, quality=95)

# Color schemes per sign
SIGN_COLORS = {
    'aries':       [(220,50,30),  (120,20,60)],
    'taurus':      [(30,120,50),  (15,60,30)],
    'gemini':      [(230,200,40), (180,120,20)],
    'cancer':      [(150,180,220),(60,80,140)],
    'leo':         [(240,170,30), (200,100,10)],
    'virgo':       [(80,140,80),  (40,80,50)],
    'libra':       [(200,160,200),(120,80,150)],
    'scorpio':     [(140,20,40),  (60,10,40)],
    'sagittarius': [(160,80,180), (100,40,120)],
    'capricorn':   [(80,60,50),   (30,25,20)],
    'aquarius':    [(40,100,220), (20,50,140)],
    'pisces':      [(160,130,200),(80,60,130)],
}
```

### Cover Rules
- ⚠️ **Never use Unicode zodiac symbols** (♈♉ etc.) — most fonts render them as ☒
- Use English sign names in large text instead
- Text must be readable at thumbnail size (phone screen)
- Keep important elements away from bottom 15% (YouTube UI overlay)

## Content Calendar

### Weekly Cycle
| Day | Content | Platform |
|-----|---------|----------|
| Mon | 12 sign readings (video) | YouTube Shorts, TikTok |
| Wed | Mid-week energy check | Instagram Reel |
| Fri | Weekend tarot pull | TikTok, Shorts |

### Event-Driven (auto-detect from ephemeris)
- Mercury Retrograde → "Survival guide" series
- Full/New Moon → Moon ritual + tarot spread
- Eclipse season → "Eclipse portal" specials
- Major conjunctions → Deep-dive explainer + 12-sign impact

## Sensitive Content Notes

Platform content policies vary. Avoid:
- Health/medical claims ("this card says you'll recover")
- Financial advice ("invest now, Jupiter says so")
- Fear-inducing predictions ("danger ahead", "death card means...")
- Always frame readings as reflection tools, not predictions
