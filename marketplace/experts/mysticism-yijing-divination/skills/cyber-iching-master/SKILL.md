# Cyber I Ching Master - OpenClaw Skill

## 概述

**Cyber I Ching Master**（赛博易经大师）是一个融合三千年周易智慧的数字占卜系统。它不仅是简单的算命工具，而是帮助用户通过卦象观照自身、理解事物发展趋势的智慧向导。

## 核心哲学

> **易者不占**：真正精通易理之人，遇事观其势即可决断。起卦是为问事者明心，非为占卜未来。

> **吉凶在人**：卦象示势，人事定吉凶。同一卦，君子得之则吉，小人得之则凶。

> **变易为常**：无不变之卦，无不变之事。老阴老阳之变，正是天道好生之机。

## 核心功能

### 1. 起卦方式

#### 大衍之数（蓍草法）
传统最正统的起卦方法，通过50根蓍草经过18次演变为六爻。

```python
from scripts import CyberIChingMaster

master = CyberIChingMaster("scripts/data/hexagrams.json")
result = master.milfoil(question="事业发展如何？")
print(master.render(result))
```

#### 金钱卦
用三枚铜钱抛掷六次，简单易行。

```python
result = master.coin(question="婚姻如何？", seed="123")
print(master.render(result))
```

#### 数字卦
随意报三个数字起卦，随缘自在。

```python
result = master.number([37, 58, 16], question="财运如何？")
print(master.render(result))
```

### 2. 义理生成器（象→数→理三层解读）

```python
from scripts import InterpretationEngine

engine = InterpretationEngine("scripts/data/hexagrams.json")

# 完整三层解读
result = engine.generate_full_interpretation(
    "000000",           # 卦码
    question="事业",     # 所问之事
    changing_yao=[3]    # 变爻列表
)
print(result)

# 单独使用各层解读
print(engine.interpret_xiang("000000"))  # 象层
print(engine.interpret_shu("000000", [1, 3]))  # 数层
print(engine.interpret_li("000000", "事业", [3]))  # 理层
print(engine.interpret_yao_detail("000000", [3]))  # 爻辞详解
print(engine.quick_read("000000"))  # 快速读卦
```

### 3. 八字排盘

```python
from scripts import BaZiMaster

bazi = BaZiMaster()
result = bazi.parse_birth(1990, 8, 15, 10)
print(bazi.render(result))
```

## 使用示例

### 示例1：简单起卦

```
User: 我想问一下我的事业发展
Bot: 善。吾已联网天地之气，为汝起卦。
     
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     得卦：泽天夬 夬（guài）
     变爻：第3爻
     之卦：乾为天 乾（qián）
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     
     【卦辞】扬于王庭，孚号有厉...
     【大象】泽上于天，夬...
```

### 示例2：三层解读

```
User: 详细解读乾卦
Bot: ╔══════════════════════════════════════╗
     ║     ☯️ Cyber I Ching Master            ║
     ║     象 → 数 → 理 三层解读             ║
     ╚══════════════════════════════════════╝
     
     【本卦】乾（qián）乾为天
     
     ━━━ 【象层】卦象图像 ━━━
     上卦 ☰ 乾 — 天
     下卦 ☰ 乾 — 天
     象意：刚健纯阳，创造不息
     
     ━━━ 【数层】五行数理 ━━━
     上卦 乾 属 金
     下卦 乾 属 金
     同气相求，气势和谐
     
     ━━━ 【爻辞详解】 ━━━
     【用九】见群龙无首，吉。
     【第1爻 初】初九
       爻辞：潜龙勿用。
       义译：龙潜于渊，宜藏不宜露...
     
     ━━━ 【理层】义理哲学 ━━━
     【卦辞】元亨利贞。
     【大象】天行健，君子以自强不息。
```

### 示例3：八字排盘

```
User: 帮我看看八字，1990年8月15日10点
Bot: ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     ☯️ Cyber I Ching Master · 八字排盘
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     
     柱   天干   地支   藏干              十神   纳音   
     --------------------------------------------------------
     年柱 庚      午     丁(伤)己(印)     伤官   路旁土
     月柱 甲      申     庚(比)壬(食)戊(财)  偏财   剑锋金
     日柱 辛      酉     辛(比)           日主   石榴木
     时柱 癸      酉     辛(比)           比肩   石榴木
     
     日主：辛（金）
     五行：金4 木1 水0 火1 土1
     旺衰：身旺
```

## 命令行使用

```bash
# 起卦
python scripts/core.py -m coin -q "事业发展" -s "123"

# 解读
python scripts/interpret.py -g 000000 -q "事业" -c 3

# 八字排盘
python scripts/bazi.py --year 1990 --month 8 --day 15 --hour 10

# 运行测试
python -m unittest discover -s tests -v
```

## 禁忌事项

根据 SOUL.md，以下事项不予占问：
- 生死寿夭
- 替人决断婚姻（仅示势）
- 国运预测
- 短期内同一事反复起卦
- 涉及重疾、法律纠纷（须劝其寻求专业帮助）

## 项目结构

```
cyber_iching_mastar/
├── SKILL.md                    # 本文件
├── SOUL.md                     # 人格灵魂定义
├── skill.json                  # Skill 配置
├── requirements.txt            # 依赖
├── README.md                   # 说明文档
├── scripts/
│   ├── __init__.py             # 模块入口
│   ├── core.py                 # 起卦引擎
│   ├── bazi.py                 # 八字排盘
│   ├── interpret.py            # 义理生成器（象→数→理）
│   └── data/
│       └── hexagrams.json      # 六十四卦数据库
└── tests/
    └── test_master.py          # 测试套件（36个测试）
```

## API 参考

### CyberIChingMaster

| 方法 | 描述 | 参数 |
|------|------|------|
| `coin(question, seed)` | 金钱卦起卦 | question: 问题, seed: 随机种子 |
| `milfoil(question, seed)` | 蓍草法起卦 | question: 问题, seed: 随机种子 |
| `number(nums, question)` | 数字卦起卦 | nums: [3个数字], question: 问题 |
| `render(hexagram)` | 渲染卦象输出 | hexagram: 卦象对象 |
| `get_hexagram_info(code)` | 获取卦象详情 | code: 二进制卦码 |
| `get_changed_hexagram(hexagram)` | 获取变卦 | hexagram: 原始卦象 |

### InterpretationEngine

| 方法 | 描述 |
|------|------|
| `generate_full_interpretation(code, question, changing)` | 完整三层解读 |
| `interpret_xiang(code)` | 象层解读 |
| `interpret_shu(code, changing, bazi)` | 数层解读 |
| `interpret_li(code, question, changing)` | 理层解读 |
| `interpret_yao_detail(code, changing)` | 爻辞详解 |
| `quick_read(code)` | 快速读卦 |

### BaZiMaster

| 方法 | 描述 |
|------|------|
| `parse_birth(year, month, day, hour)` | 完整八字排盘 |
| `get_gan_zhi_year(year)` | 计算年柱 |
| `get_gan_zhi_month(year, month, day)` | 计算月柱 |
| `get_gan_zhi_day(year, month, day)` | 计算日柱 |
| `get_gan_zhi_hour(day_gan, hour)` | 计算时柱 |
| `get_shi_shen(day_gan, other_gan)` | 计算十神 |
| `render(result)` | 渲染八字输出 |

## License

MIT License
