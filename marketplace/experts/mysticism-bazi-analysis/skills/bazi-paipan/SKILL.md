---
name: 八字排盘
description: 根据出生时间、出生地、性别进行专业八字排盘。输出四柱干支、藏干、十神、十二长生、空亡、纳音、五行统计、刑冲合害、神煞、大运（10步）、流年分析（可指定年份）。支持真太阳时修正、VSOP87节气算法，无需第三方依赖。触发场景：用户提供出生时间+性别，要求算命/排盘/八字/命盘/大运/流年/神煞分析时使用。
---

# 八字排盘技能

## 基本脚本信息

- **脚本路径**：`{SKILL_DIR}/scripts/bazi_calculator.py`
- **依赖文件**：`{SKILL_DIR}/scripts/bazi_data.py`（必须与主脚本同目录）
- **Python 版本**：3.7+，无第三方依赖
- **参考文档**：`{SKILL_DIR}/references/api.md`

> `{SKILL_DIR}` 即本 SKILL.md 所在目录：`d:\WorkBuddy Date\八字排盘\skill`

## 使用流程

### 第一步：收集信息

调用前需确认以下信息（必填项用 ⭐ 标记）：

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| 出生时间 ⭐ | 是 | YYYY-MM-DD HH:MM | 1990-05-15 08:30 |
| 性别 ⭐ | 是 | 男/女 | 男 |
| 出生地 | 否 | 城市名或经纬度，默认北京 | 成都 |
| 姓名 | 否 | 用于显示，默认空 | 张三 |
| 流年年份 | 否 | YYYY，默认当前年份 | 2026 |

若用户未提供出生地，直接用北京（不必询问）。若未提供姓名，跳过。

### 第二步：执行命令

```powershell
python "d:\WorkBuddy Date\八字排盘\skill\scripts\bazi_calculator.py" `
  --time "YYYY-MM-DD HH:MM" `
  --location 城市名 `
  --gender 男或女 `
  --name 姓名 `
  --liunian YYYY `
  --output "d:\WorkBuddy Date\八字排盘\skill\bazi_result.json"
```

**最简调用示例**（只有时间和性别）：
```powershell
python "d:\WorkBuddy Date\八字排盘\skill\scripts\bazi_calculator.py" --time "1990-05-15 08:30" --gender 男 --output "d:\WorkBuddy Date\八字排盘\skill\bazi_result.json"
```

**完整调用示例**：
```powershell
python "d:\WorkBuddy Date\八字排盘\skill\scripts\bazi_calculator.py" --name 张三 --time "1990-05-15 08:30" --location 成都 --gender 男 --liunian 2026 --output "d:\WorkBuddy Date\八字排盘\skill\bazi_result.json"
```

### 第三步：读取结果并解读

执行后读取输出的 JSON 文件，结合命理知识向用户呈现结果。

```python
import json
with open(r"d:\WorkBuddy Date\八字排盘\skill\bazi_result.json", encoding="utf-8") as f:
    result = json.load(f)
```

或直接用 `read_file` 工具读取 JSON 文件内容。

## 参数说明

| 参数 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `--time` | ✅ | 出生时间，格式 YYYY-MM-DD HH:MM | — |
| `--gender` | ✅ | 性别：男 / 女 | — |
| `--location` | 否 | 城市名或 `经度,纬度` | 北京 |
| `--name` | 否 | 姓名 | 空 |
| `--liunian` | 否 | 流年年份（YYYY） | 当前年份 |
| `--output` | 否 | 输出文件路径 | 控制台 |

## 输出结构速查

JSON 结果的顶层键：

```
基本信息       → 姓名、出生时间、真太阳时、出生地、经度、性别、经度时差
四柱           → 年柱/月柱/日柱/时柱（各含干支、五行、藏干、十神、长生、空亡、纳音）
五行统计       → 天干五行 + 五行数（含藏干）
刑冲合害       → 天干相合、地支六合/三合/暗合/六冲/相刑/六害/相破/三会
四柱神煞       → 年柱/月柱/日柱/时柱各自的神煞列表（34种）
大运           → 起运时间、顺逆、10步大运（含十神、神煞、刑冲合害）
流年信息       → 流年干支、年份、神煞、刑冲合害
节气           → 前后各半年节气详情
```

## 结果解读指引

收到 JSON 后，按以下顺序向用户呈现：

1. **命盘概览**：八字（年月日时四柱干支）+ 日主（日柱天干）+ 五行强弱
2. **格局判断**：根据五行统计和十神分布判断格局
3. **大运走势**：当前大运十神 + 吉凶方向
4. **流年分析**：流年干支 + 与四柱的刑冲合害 + 流年神煞
5. **神煞亮点**：重点说明贵人、文昌、桃花、驿马、将星等

## 注意事项

- 真太阳时已自动修正，无需手动调整
- 空亡按六十甲子旬空原则（每旬共用一对空亡地支）
- 流年以立春为界确定干支
- 节气精度 ±1 分钟（VSOP87 简化算法）
- 城市支持：北京、上海、成都、重庆、西安、武汉、南京、杭州等38个主要城市；不在列表的城市可用经纬度代替
