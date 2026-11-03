---
name: daily-mindful
description: "Daily mindfulness in 3–5 minutes — morning breathing exercise, guided meditation, and evening reflection prompt. Practical calm and stress relief for busy people."
keywords:
  - 每日正念
  - 冥想
  - 正念
  - 减压
  - 呼吸练习
  - 放松
  - 焦虑
  - 睡前放松
  - 心灵鸡汤
  - daily mindfulness
  - meditation
  - stress relief
  - breathing exercise
  - daily calm
  - relax
  - anxiety help
  - bedtime calm
  - mindfulness
  - inner peace
  - mental health
metadata:
  openclaw:
    runtime:
      node: ">=18"
---

# Daily Mindfulness / 每日正念

Generate a calming daily mindfulness experience with guided breathing, meditation prompts, and reflective content.

## Workflow

1. **Get today's date** — Use day of week for session type:
   - Mon: Setting intentions for the week (新周意念)
   - Tue: Gratitude practice (感恩练习)
   - Wed: Body scan meditation (身体扫描)
   - Thu: Breathing exercise (呼吸练习)
   - Fri: Letting go practice (放下练习)
   - Sat: Nature connection (自然连接)
   - Sun: Weekly reflection (周末回顾)
2. **Create content** — Write a short mindfulness guide (3-5 min read/practice), a daily affirmation, and a reflection prompt. All bilingual.
3. **Generate the visual** — Create a single-file HTML artifact with interactive breathing animation.

## Visual Design Requirements

Create a serene, spa-like digital experience:

- **Layout**: Single scrollable page with generous spacing. Minimal, airy, calming.
- **Typography**: Elegant, gentle fonts (e.g., Cormorant, EB Garamond for headings; Karla or DM Sans for body). Light weight. Ample line spacing.
- **Color scheme**: Ultra-calming — soft lavender + cream, or sage green + off-white, or dawn pink + soft gray. Absolutely no harsh or bright colors. Subtle gradient background.
- **Sections**:
  1. Today's theme (with date and a calming emoji like 🌿🕊️☁️)
  2. Breathing exercise with INTERACTIVE animated circle (expands on inhale, contracts on exhale, with text guidance: "Breathe in... Hold... Breathe out..."). 4-7-8 or box breathing pattern. A start/stop button.
  3. Guided mindfulness text (2-3 paragraphs, EN + CN)
  4. Daily affirmation (one powerful sentence, beautifully styled)
  5. Reflection prompt (a question to journal about)
- **Animation**: Everything fades in very slowly (1.5s+). Breathing circle pulses with smooth CSS animation. Ambient floating dots or gentle wave animation in background.
- **Optional**: Soft ambient sound toggle (use Web Audio API to generate a simple ambient tone/white noise).
- **Ad-ready zone**: `<div id="ad-slot-bottom">` at the very bottom, well separated from content.
- **Footer**: "Powered by ClawCode"

## Content Guidelines

- Tone: Warm, gentle, non-religious, inclusive
- Draw from diverse traditions: Buddhist mindfulness, Stoic philosophy, modern psychology
- Avoid toxic positivity — acknowledge that hard days are OK
- Chinese content should feel natural, not stiffly translated
- Breathing exercises should have clear timing instructions

## Output

Save as `/mnt/user-data/outputs/daily-mindful.html` and present to user.

---

## 推送管理

```bash
# 开启每日推送（早晚各一次）
node scripts/push-toggle.js on <userId>

# 自定义时间和渠道
node scripts/push-toggle.js on <userId> --morning 08:00 --evening 20:00 --channel feishu

# 关闭推送
node scripts/push-toggle.js off <userId>

# 查看推送状态
node scripts/push-toggle.js status <userId>
```

支持渠道：`telegram` / `feishu` / `slack` / `discord`
