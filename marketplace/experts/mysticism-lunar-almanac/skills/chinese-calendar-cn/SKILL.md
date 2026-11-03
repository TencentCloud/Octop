---
name: "chinese-calendar-cn"
version: "5.0.0"
description: "中国农历工具。节气查询、生肖年份、黄道吉日、传统节日、天干地支、农历转换。Chinese lunar calendar with solar terms, zodiac, auspicious dates, festivals, and Heavenly Stems."
author: "BytesAgain"
homepage: "https://bytesagain.com"
source: "https://github.com/bytesagain/ai-skills"
tags: [chinese-calendar, lunar, zodiac, solar-terms, festivals, 农历, 节气, 生肖]
category: "lifestyle"
---

# Chinese Calendar 中国农历

中国传统历法参考工具。二十四节气、十二生肖、天干地支、传统节日、黄道吉日速查。无需API，纯本地输出。

## Commands

| Command | Description |
|---------|-------------|
| `jieqi` | 二十四节气完整表（日期、含义、农事、习俗） |
| `shengxiao` | 十二生肖年份速查 + 性格 + 相合相冲 |
| `tiangan` | 天干地支六十甲子纪年法详解 |
| `jieri` | 中国传统节日（农历日期、来历、习俗、食物） |
| `jiri` | 黄道吉日择日参考（婚嫁、搬家、开业等） |
| `zhuanhuan` | 公历↔农历转换规则与闰月说明 |
| `minsu` | 民俗禁忌与传统讲究 |
| `faq` | 常见问题（闰月、节气偏移、新旧历差异等） |

## Usage

```bash
chinese-calendar-cn jieqi        # 二十四节气
chinese-calendar-cn shengxiao    # 十二生肖
chinese-calendar-cn tiangan      # 天干地支
chinese-calendar-cn jieri        # 传统节日
chinese-calendar-cn jiri         # 黄道吉日
chinese-calendar-cn zhuanhuan    # 公农历转换
chinese-calendar-cn minsu        # 民俗禁忌
chinese-calendar-cn faq          # 常见问题
```

## Output Format

All commands output plain-text reference documentation in Chinese. No external API calls, no credentials needed.

---

*Powered by BytesAgain | bytesagain.com*
