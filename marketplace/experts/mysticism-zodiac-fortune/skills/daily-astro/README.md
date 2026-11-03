# Daily Astro — Western Horoscope Skill

> Daily horoscope for all 12 zodiac signs — love, career, finance scores, lucky elements. Bilingual EN/CN.

[![clawhub](https://img.shields.io/badge/clawhub-daily--astro-blue)](https://clawhub.ai/skills/daily-astro)
[![openclaw](https://img.shields.io/badge/openclaw-skill-orange)](https://openclaw.ai)

An [OpenClaw](https://openclaw.ai) skill that delivers daily Western horoscope readings for all 12 zodiac signs — love, career, and finance scores, lucky color/number/direction, and a daily affirmation. Pairs naturally with [yunshi](https://github.com/jiajiaoy/yunshi) for a complete Chinese + Western astrology experience.

---

## Features

- **12 Zodiac Signs** — Aries through Pisces, all covered daily
- **Three Fortune Scores** — Love 💕 / Career 💼 / Finance 💰 (1–5 stars each)
- **Lucky Elements** — Color, number, direction for today
- **Daily Affirmation** — One guiding sentence per sign
- **Evening Preview** — Tomorrow's top 3 signs + watch-out signs
- **Bilingual** — Chinese and English output

---

## Daily Push Schedule

| Push | Time | Content |
|------|------|---------|
| Morning | 08:00 | Today's horoscope for all 12 signs |
| Evening | 21:00 | Tomorrow's horoscope preview + lucky tips |

```bash
node scripts/push-toggle.js on <userId>
node scripts/push-toggle.js on <userId> --morning 08:00 --evening 21:00 --channel feishu
node scripts/push-toggle.js off <userId>
node scripts/push-toggle.js status <userId>
```

Supported channels: `telegram` / `feishu` / `slack` / `discord`

---

## Trigger Words

星座运势、今日星座、白羊座、金牛座、双子座、巨蟹座、狮子座、处女座、天秤座、天蝎座、射手座、摩羯座、水瓶座、双鱼座、horoscope、zodiac、daily horoscope、astrology、love horoscope

---

*MIT License · OpenClaw Skill*

## Keywords

horoscope · daily horoscope · zodiac · astrology · western astrology · Aries · Taurus · Gemini · Cancer · Leo · Virgo · Libra · Scorpio · Sagittarius · Capricorn · Aquarius · Pisces · 星座运势 · 今日星座 · 每日运势 · 星座

---

Built for [OpenClaw](https://openclaw.ai) · Published on [clawhub.ai](https://clawhub.ai/skills/daily-astro)
