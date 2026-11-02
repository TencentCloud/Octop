# Daily Sleep — Sleep Coach Skill

> Morning wake-up routine + evening wind-down — science-backed tips for better sleep and insomnia relief.

[![clawhub](https://img.shields.io/badge/clawhub-daily--sleep-blue)](https://clawhub.ai/skills/daily-sleep)
[![openclaw](https://img.shields.io/badge/openclaw-skill-orange)](https://openclaw.ai)

An [OpenClaw](https://openclaw.ai) skill that acts as your personal sleep coach — a morning wake-up routine to start the day energized, and an evening wind-down program to fall asleep naturally. Covers the largest health pain point: insomnia and poor sleep quality.

---

## Features

- **Morning Wake-Up** — Sleep quality self-review, 5-min activation routine, caffeine cutoff reminder
- **Evening Wind-Down** — Pre-sleep 90-min checklist, 4-7-8 breathing, progressive muscle relaxation
- **Sleep Environment Guide** — Temperature, light, noise, phone tips
- **2-Minute Bedtime Meditation** — Guided mindfulness for falling asleep
- **Daily Sleep Tips** — Circadian rhythm advice by day of week
- **Science-based** — Draws from CBT-I, sleep hygiene research, and mindfulness

---

## Daily Push Schedule

| Push | Time | Content |
|------|------|---------|
| Morning | 07:00 | Wake-up routine + sleep quality review + today's sleep tip |
| Evening | 22:00 | Wind-down program + breathing guide + bedtime meditation |

```bash
node scripts/push-toggle.js on <userId>
node scripts/push-toggle.js on <userId> --morning 07:00 --evening 22:00 --channel telegram
node scripts/push-toggle.js off <userId>
node scripts/push-toggle.js status <userId>
```

Supported channels: `telegram` / `feishu` / `slack` / `discord`

---

## Trigger Words

失眠、睡不好、助眠、睡前放松、入睡困难、睡眠质量、sleep、insomnia、sleep aid、bedtime routine、can't sleep、deep sleep、sleep hygiene、wind down

---

*MIT License · OpenClaw Skill*

## Keywords

sleep · insomnia · sleep aid · bedtime routine · daily sleep · sleep coach · 失眠 · 睡不好 · 助眠 · 睡前放松 · 睡眠质量 · 入睡困难

---

Built for [OpenClaw](https://openclaw.ai) · Published on [clawhub.ai](https://clawhub.ai/skills/daily-sleep)
