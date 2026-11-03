---
name: daily-sleep
description: "Sleep better tonight — personalized wind-down routine, breathing exercises, bedtime stories, and sleep hygiene tips. Daily evening push for better rest."
keywords:
  - 失眠
  - 睡不好
  - 助眠
  - 睡眠
  - 睡前放松
  - 入睡困难
  - 睡眠质量
  - 帮我睡觉
  - 睡眠问题
  - 深度睡眠
  - 睡前仪式
  - 睡眠卫生
  - 午睡
  - 亚健康
  - 睡眠不足
  - 早睡早起
  - 睡眠改善
  - sleep
  - insomnia
  - sleep aid
  - bedtime routine
  - sleep quality
  - can't sleep
  - deep sleep
  - sleep hygiene
  - sleep coach
  - wind down
  - relaxation
  - sleep tips
  - better sleep
  - nap
  - wake up routine
  - morning routine
metadata:
  openclaw:
    runtime:
      node: ">=18"
---

# 睡眠助手

> 睡眠助手 — 晨间唤醒 · 睡前放松 · 助眠引导 · 失眠改善

## 何时使用

- 用户说"失眠""睡不好""帮我睡觉"
- 用户说"睡前放松""助眠""入睡困难"
- 用户说"sleep""insomnia""can't sleep"
- 用户说"睡眠质量差""怎么改善睡眠"

---

## 推送管理

```bash
node scripts/push-toggle.js on <userId>
node scripts/push-toggle.js on <userId> --morning 07:00 --evening 22:00 --channel feishu
node scripts/push-toggle.js off <userId>
node scripts/push-toggle.js status <userId>
```

支持渠道：`telegram` / `feishu` / `slack` / `discord`
