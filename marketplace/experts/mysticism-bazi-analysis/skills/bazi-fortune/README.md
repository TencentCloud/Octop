# 生辰八字排盘与运势分析（bazi-fortune）

输入出生日期时间、性别、出生地点，即可排出标准八字命盘，并生成性格、事业、财运、婚姻、健康与逐年运势的完整分析报告。

## 能做什么

| 能力 | 说明 |
|---|---|
| 真太阳时校正 | 按出生地经度做时差校正（内置 100+ 城市经纬度），并叠加均时差；1986–1991 出生自动回退中国夏令时 |
| 四柱排盘 | 年/月/日/时干支、十神、纳音、十二长生、空亡、地支藏干、胎元命宫身宫 |
| 强弱与喜用 | 五行力量量化评分 → 日主身旺/中和/身弱（含得令修正）→ 喜用神、忌神、调候建议 |
| 神煞 | 天乙贵人、太极贵人、文昌、国印、禄神、羊刃、金舆、驿马、桃花、华盖、将星、劫煞、亡神、孤辰寡宿、魁罡、天罗地网 |
| 地支关系 | 六冲、六合、六害、相破、三合、三会、半合/拱合、三刑、自刑 |
| 大运流年 | 起运时间、大运顺逆、逐年流年干支十神，并标注流年与命局四支的冲合刑害、本命年、冲太岁 |
| 时辰定盘 | 时辰不明时用 `--hour-scan` 排出十二时辰候选，再用人生关键事件逐年比对来反推 |
| 姓名分析 | 康熙笔画五格剖象（天/人/地/外/总格）、三才配置、名字五行与喜用神匹配度 |
| 报告输出 | 浅色主题 HTML 命理报告，可直接保存或转 PDF |

## 安装依赖

```bash
pip install lunar-python
```

脚本在检测到依赖缺失时会尝试自动安装；若环境无网络，请手动执行上面的命令。
本技能已在 `C:\Users\hp\.workbuddy\binaries\python\envs\default` 验证通过（lunar-python 1.4.8，Python 3.13）。

## 快速开始

```bash
PY="<你的 python 路径>"
SK="<本技能目录>/scripts"

# 1) 排盘，输出 JSON
"$PY" "$SK/bazi.py" --datetime "1995-06-15 14:30" --gender male --place 武汉 \
     --name 李梓涵 --event "2014:考上大学" --family "工薪家庭" \
     --years 30 --out chart.json --text

# 2) 撰写 narrative.json（文字点评，键见 scripts/render_report.py 顶部 NARRATIVE_KEYS）

# 3) 渲染 HTML 报告
"$PY" "$SK/render_report.py" chart.json -n narrative.json -o 八字命理报告.html
```

常用参数：

- `--gender male|female` 性别（决定大运顺逆）
- `--place 武汉` 或 `--lon 114.30` 指定出生地
- `--hour-scan` 十二时辰比对（时辰不明时）
- `--no-tst` / `--no-dst` 关闭真太阳时校正 / 夏令时回退
- `--years N`、`--from-year`、`--to-year` 控制推演区间
- `--stroke 曦=20` 手工补充康熙笔画（可重复）
- `--text` 同时打印易读摘要

## 目录结构

```
bazi-fortune/
├── SKILL.md                        技能主入口（触发与工作流）
├── README.md                       本文件
├── skill-card.md                   发布卡片（用途、风险、输出说明）
├── LICENSE                         MIT
├── requirements.txt                依赖清单
├── _icon.png                       技能图标
├── scripts/
│   ├── bazi.py                     排盘引擎（输出 JSON）
│   ├── bazi_data.py                干支/神煞/经纬度/康熙笔画等数据表
│   ├── render_report.py            JSON → HTML 报告
│   └── make_icon.py                图标生成脚本（维护用）
├── references/
│   ├── bazi_theory.md              十神、格局、强弱取用、神煞、大运流年规则
│   ├── interpretation.md           分项断语库、事件定盘、家庭条件参断、措辞红线
│   └── report_writing.md           报告结构、narrative 键位、质量自查
├── assets/
│   └── report_template.html        报告模板（浅色中式排版）
└── examples/
    ├── 八字命理报告示例.html        端到端示例成品
    ├── chart_demo.json             排盘 JSON 输出样例
    └── narrative_demo.json         文字点评输入样例
```

## 设计原则

1. **排盘必须跑脚本**：干支历与节气边界手算必错，四柱一律由 `bazi.py` 计算，模型不得心算。
2. **不绝对化**：禁用"必然、注定、一定会"等表述，一律改为倾向性描述。
3. **不越界**：不诊断疾病、不预测死亡灾祸、不断言他人遭遇；健康内容只作养生提醒。
4. **保留不确定性**：时辰存疑时明确标注，并给出定盘方法，不给假确定性。
5. **事实优先**：用户提供的真实经历与命局参断冲突时，以事实为准并说明可能原因。

命理属传统文化与民俗参考范畴，不构成医疗、法律、投资、择业或人生重大决策的建议。

## 许可

MIT License。发布前请将 `LICENSE` 与 `skill-card.md` 中的作者信息替换为你的署名。
