# Cyber I Ching Master

三千年周易智慧之数字化觉醒

## 项目简介

Cyber I Ching Master（赛博易经大师）是一个融合传统易经智慧与现代编程技术的占卜系统。它不仅提供传统的起卦方法（大衍之数、金钱卦、数字卦），还包含完整的六十四卦数据库和八字排盘模块。

## 功能特性

### 卦象占卜
- **大衍之数（蓍草法）**：传统最正统的起卦方法
- **金钱卦**：用三枚铜钱抛掷六次，简单易行
- **数字卦**：随意报三个数字，随缘自在
- **变卦计算**：自动计算老阴老阳之变

### 🧮 八字排盘
- 四柱八字（年柱、月柱、日柱、时柱）
- 天干地支五行
- 地支藏干十神
- 纳音五行
- 旺衰判断
- 命局简评

### 📖 卦象解读
- 完整六十四卦数据库
- 卦辞、彖传、大象传
- 爻辞、小象传
- 现代义译

## 安装

```bash
pip install -r requirements.txt
```

## 快速开始

### 起卦示例

```python
from scripts import CyberIChingMaster

# 创建实例
master = CyberIChingMaster()

# 金钱卦起卦
result = master.coin(question="我的事业发展如何？")

# 渲染输出
print(master.render(result))
```

### 八字排盘示例

```python
from scripts import BaZiMaster

# 创建实例
bazi = BaZiMaster()

# 排盘
result = bazi.parse_birth(1990, 8, 15, 10)

# 渲染输出
print(bazi.render(result))
```

### 命令行使用

```bash
# 起卦
python scripts/core.py --method coin --question "事业发展" --seed "123"

# 八字排盘
python scripts/bazi.py --year 1990 --month 8 --day 15 --hour 10

# 卦象解读
python scripts/interpret.py --hexagram 000000 --data hexagrams.json
```

## 项目结构

```
cyber_iching_mastar/
├── scripts/
│   ├── __init__.py          # 模块入口
│   ├── core.py               # 起卦核心引擎
│   ├── bazi.py               # 八字排盘模块
│   ├── interpret.py          # 义理解读引擎
│   └── data/
│       └── hexagrams.json    # 六十四卦数据库
├── SOUL.md                   # 人格灵魂定义
├── SKILL.md                  # OpenClaw Skill 入口
├── skill.json                # Skill 配置
├── requirements.txt          # 依赖
└── tests/
    └── test_master.py         # 测试
```

## 核心哲学

> **易者不占**：真正精通易理之人，遇事观其势即可决断。起卦是为问事者明心，非为占卜未来。

> **吉凶在人**：卦象示势，人事定吉凶。同一卦，君子得之则吉，小人得之则凶。

> **变易为常**：无不变之卦，无不变之事。老阴老阳之变，正是天道好生之机。

## 注意事项

1. 易经智慧在于启迪心智，而非宿命论
2. 占问之事需明确具体，不可含糊
3. 同一事短期内不可反复起卦
4. 涉及重大决策（医疗、法律等）请寻求专业帮助

## License

MIT License
