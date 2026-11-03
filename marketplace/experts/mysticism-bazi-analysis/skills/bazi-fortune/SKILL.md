---
name: bazi-fortune
slug: bazi-fortune
version: "1.0.0"
display_name: 生辰八字排盘与运势分析
display_name_en: Chinese BaZi (Four Pillars) Fortune Analysis
description_zh: 输入出生日期时间、性别、出生地点，即可排出生辰八字四柱（十神、纳音、星运、空亡、藏干）、判断日主强弱与喜用神、列出大运流年并逐年批断运势；支持真太阳时校正、夏令时还原、十二时辰定盘、姓名五格与五行补益分析，可输出可视化 HTML 命理报告。
description_en: Compute a Chinese BaZi (Four Pillars of Destiny) chart from birth date, time, gender and birthplace — including ten gods, na-yin, hidden stems, shensha, day-master strength, favorable elements, and a full decade-luck (da yun) plus annual-luck (liu nian) forecast. Supports true solar time correction, DST reversal, unknown-birth-hour calibration, and Chinese name analysis. Outputs a styled HTML fortune report.
description: 根据出生日期时间、姓名、出生地点、成长经历与家庭条件排算生辰八字（四柱、十神、纳音、神煞、大运流年）、判断日主强弱与喜用神，并撰写未来运势分析报告，可输出 HTML 命理报告。当用户提到生辰八字、八字排盘、批八字、算命、命理、运势、流年大运、五行缺什么、喜用神、日主强弱、起名改名、合婚择日等需求时使用。
trigger: ["生辰八字", "八字", "排盘", "批八字", "算命", "命理", "运势", "流年", "大运", "喜用神", "日主强弱", "五行缺什么", "起名", "改名", "合婚", "择日", "转运", "BaZi", "Four Pillars"]
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
agent_created: true
xiaping_trigger: ["八字", "命理", "运势", "传统文化", "起名"]
xiaping_category: ["效率工具"]
xiaping_tags: ["八字", "生辰八字", "命理", "运势分析", "传统文化", "WorkBuddy"]
xiaping_eval_strategy: developer
---

# 生辰八字排盘与运势分析

把出生时间（真太阳时校正后）转成干支四柱，再据此分析性格、事业、财运、婚姻、健康与逐年运势。

## 何时使用

- 用户报出生年月日时（哪怕只有日期），想看八字、五行、运势。
- 用户问"我五行缺什么""我适合做什么行业""今年/明年运势如何""什么时候转运"。
- 用户提供姓名，想看与八字是否配合、想改名或给新生儿起名。
- 用户想知道婚姻、事业、财运、健康方面的命理倾向。

## 三步走

### 1. 采集信息（缺什么问什么，别一次追问太多）

| 必需 | 说明 |
|---|---|
| 出生日期时间 | 阳历优先；只有农历也行。**时辰很关键** |
| 性别 | 决定大运顺逆 |
| 出生地点 | 用于真太阳时校正，精确到市即可 |

| 可选但强烈建议 | 用途 |
|---|---|
| 姓名 | 五格 + 五行补益分析 |
| 3–5 个关键人生事件（带年份） | 定盘校时、复盘、增强说服力 |
| 家庭条件与成长背景 | 参断父母宫、早年环境 |
| 当前最关心的问题 | 决定报告重点 |

**时辰不明时不要瞎猜**：先用 `--hour-scan` 出十二时辰比对表，再请用户补充事件或时辰；报告中必须标注"时辰待定"。

### 2. 排盘（必须跑脚本，不要心算）

排盘涉及干支历与二十四节气边界，手算极易出错。**始终使用脚本**：

```bash
PY="C:/Users/hp/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
SK="C:/Users/hp/.workbuddy/skills/bazi-fortune/scripts"
OUT="E:/WorkBuddy文件缓存/2026-09-29-11-08-40"

"$PY" "$SK/bazi.py" --datetime "1995-06-15 14:30" --gender male --place 武汉 \
     --name 李梓涵 --event "2014:考上大学" --family "工薪家庭" \
     --years 30 --out "$OUT/chart.json" --text
```

常用参数：
- `--gender male|female`、`--place 城市名/省名`（内置 100+ 城市经纬度，匹配不到用 `--lon 114.30`）
- `--no-tst` 关闭真太阳时校正；`--no-dst` 关闭夏令时回退（1986–1991 出生者默认自动回退 1 小时）
- `--hour-scan` 时辰不定时的十二时辰比对
- `--years N` 向后推算年数（默认 30）；`--from-year` / `--to-year` 指定区间
- `--stroke 曦=20` 手工补康熙笔画（可重复）
- `--text` 同时打印易读摘要到 stderr

依赖 `lunar-python`，缺失时脚本会自动 pip 安装；失败则手动 `pip install lunar-python`。

输出 JSON 关键字段：`pillars`（四柱+十神+纳音+星运+空亡+藏干）、`strength`（日主强弱/喜忌/调候）、`wuxing`（五行个数与力量分）、`shensha`、`interactions`（刑冲合害）、`dayun[].liu_nian[]`（含 `hits` 冲合关系、`ben_ming_nian`、`fan_taisui`）、`name_analysis`、`time_correction`。

### 3. 撰写解读

- 快问快答：直接在对话里给结论（四柱 → 日主强弱 → 喜用 → 未来 3 年要点），不必出文件。
- 完整信息：按 [references/report_writing.md](references/report_writing.md) 写 `narrative.json` 并渲染 HTML 报告，最后用 present_files 打开预览。

判读规则查 [references/bazi_theory.md](references/bazi_theory.md)（十神、格局、强弱取用、神煞、大运流年应期）；
分项断语、事件定盘与家庭条件参断查 [references/interpretation.md](references/interpretation.md)。

```bash
"$PY" "$SK/render_report.py" "$OUT/chart.json" -n "$OUT/narrative.json" -o "$OUT/八字命理报告.html"
```

## 硬规则

1. **排盘必须跑脚本**，不得凭记忆或心算给出干支。
2. **不绝对化**：禁用"必然、注定、一定会、必死、必离婚、必破产"；改用"更倾向于、比较容易、需要留意、相对而言"。
3. **不越界**：不诊断疾病、不预测死亡、不断言意外灾祸与寿命；健康内容只作养生提醒并注明以医嘱为准。
4. **重大决策留口子**：涉及求职、创业、投资、婚姻、生育、手术，必须提示咨询专业人士。
5. **时辰存疑要明说**，不给假确定性。
6. **用户事实优先**：若用户给的经历与命局参断冲突，以事实为准并说明可能原因，不要圆谎。
7. 免责声明不得删除（报告模板已内置）。
