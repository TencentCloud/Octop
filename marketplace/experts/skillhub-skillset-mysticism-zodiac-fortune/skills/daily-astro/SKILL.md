---
name: daily-astro
description: "Daily horoscope for all 12 zodiac signs — love, career & finance scores (1–5★), lucky color/number/direction, daily affirmation. Morning & evening push. Bilingual EN/CN."
keywords:
  - 星座运势
  - 今日星座
  - 每日星座
  - 星座今日
  - 白羊座
  - 金牛座
  - 双子座
  - 巨蟹座
  - 狮子座
  - 处女座
  - 天秤座
  - 天蝎座
  - 射手座
  - 摩羯座
  - 水瓶座
  - 双鱼座
  - 星座配对
  - 爱情运势
  - 事业运势
  - 财运
  - 幸运颜色
  - 幸运数字
  - 星座占卜
  - 上升星座
  - 月亮星座
  - horoscope
  - zodiac
  - daily horoscope
  - astrology
  - aries
  - taurus
  - gemini
  - cancer
  - leo
  - virgo
  - libra
  - scorpio
  - sagittarius
  - capricorn
  - aquarius
  - pisces
  - love horoscope
  - weekly horoscope
  - zodiac compatibility
metadata:
  openclaw:
    runtime:
      node: ">=18"
---

# 西方星座运势

> 西方星座运势 — 12星座每日运程 · 爱情事业财运 · 幸运元素 · 中英双语

## 何时使用

- 用户说"今日星座""我的星座运势""白羊座今天怎么样"
- 用户想查爱情运/事业运/财运
- 用户说"horoscope""zodiac""星座配对"
- 用户说"今天适合表白吗""今天适合谈合同吗"

---

## 推送管理

```bash
node scripts/push-toggle.js on <userId>
node scripts/push-toggle.js on <userId> --morning 08:00 --evening 21:00 --channel feishu
node scripts/push-toggle.js off <userId>
node scripts/push-toggle.js status <userId>
```

支持渠道：`telegram` / `feishu` / `slack` / `discord`
