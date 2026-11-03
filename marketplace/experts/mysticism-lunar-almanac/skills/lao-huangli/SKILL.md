---
name: lao-huangli
description: Use when users ask for 老黄历/黄历/择日/宜忌/冲煞/干支/节气 explanations, or need a reproducible engineering workflow to compute calendar fields and derive traditional almanac recommendations.
license: MIT
metadata:
  clawdbot:
    requires:
      bins:
        - python3
        - uv
---

# 老黄历计算技能（Lao Huangli）

## 何时使用

当用户出现以下需求时启用：

- 询问“老黄历是怎么算出来的”
- 指定日期要查询：农历、干支、节气、宜忌、冲煞、值日神
- 需要解释“哪些部分可精确计算、哪些部分来自规则流派”
- 关键词触发：`老黄历`、`黄历`、`万年历`、`宜忌`、`择日`、`通胜`、`冲煞`、`彭祖百忌`、`建除十二神`、`黄道吉日`

## 核心原则

1. **先算历法，再套规则**：先得到可靠的天文/历法基础字段，再生成宜忌。
2. **区分“确定性”与“流派性”**：节气、干支、农历可精确计算；宜忌、吉凶级别常依赖规则库。
3. **必须可追溯**：输出时明确计算边界、时区、采用的规则版本。

## 双原典边界

- **基础历法层**：以 `GB/T 33661-2017《农历的编算和颁行》` 为准，负责农历、节气、朔望、闰月、干支。
- **黄历规则层**：以 `《钦定协纪辨方书》` 为准，负责建除、黄黑道、神煞、冲煞、胎神、彭祖百忌和宜忌裁决。
- **补充古籍**：若某事实层字段暂未在 `《钦定协纪辨方书》` 中结构化落盘，可使用其他可追溯古籍补充，但必须在 `provenance.sourceRefs` 中逐项显式标明，不得冒称为协纪辨方书原文。
- **术语/展示材料**：只用于解释字段含义，不得直接替代规则原典。

## 计算总流程（工程化）

1. **输入标准化**
   - 输入：公历日期时间、时区（默认 Asia/Shanghai）、可选地点。
   - 约束：明确“日界”规则（通常以 23:00 子初或 00:00 作为换日点，需在输出声明）。

2. **基础历法计算（确定性）**
   - 公历 → 儒略日（JDN）
   - 计算当年 24 节气时刻（太阳黄经每 15°）
   - 计算朔望（新月）序列，确定农历月、闰月、月日

3. **干支计算（确定性）**
   - 年柱：以立春或春节为界（系统需固定一种并声明）
   - 月柱：以节气月为界（寅月起）
   - 日柱：基于 JDN 与甲子基准日取模 60
   - 时柱：由日干 + 时支映射得到

4. **黄历神煞/值日体系（规则表）**
   - 建除十二神、黄黑道、值神、吉神凶煞等，通常来自规则映射表。
   - 规则表需版本化（如 `ruleset: zh-traditional-v1`）。

5. **宜忌生成（规则引擎）**
   - 输入：干支、节气、建除、神煞、冲煞、月令。
   - 处理：
     - 候选事项打分（嫁娶、开市、动土、出行等）
     - 冲突裁决（优先级规则）
     - 输出宜/忌/次吉，并附理由。

6. **可解释输出**
   - 输出字段：公历、农历、干支四柱、节气、值神、建除、冲煞、胎神、彭祖百忌、宜忌。
   - 附“计算说明”：哪些是天文历法精算，哪些来自流派规则。

## 精确计算 vs 规则依赖

- **可精确计算**：公历换算、JDN、节气时刻、朔望月、农历日期、干支。
- **依赖规则库**：宜忌、吉凶等级、部分神煞解释、事项冲突裁决。
- **可能分歧点**：年界（立春/春节）、日界（23:00/00:00）、流派差异（通书体系不同版本）。

## 对话执行模板

1. 先确认日期时间与时区。
2. 给出历法基础结果（农历 + 干支 + 节气）。
3. 再给宜忌结果，并说明规则来源。
4. 明确风险提示：黄历建议仅作文化参考，不替代法律、医疗、财务和安全决策。

## 计算执行（脚本优先）

优先使用脚本计算“可精算字段”，不要直接凭网页汇总给结论。

```bash
skills/lao-huangli/scripts/huangli 2026 3 2 12 --profile market-folk-v1 --format calendar
skills/lao-huangli/scripts/huangli 2026 3 2 12 --profile xiejibianfang-v1 --format json
skills/lao-huangli/scripts/huangli 2026 3 2 23 --profile bazi-v1 --format calendar
skills/lao-huangli/scripts/huangli 2026 3 2 23 --profile bazi-v1 --overlay-ruleset xiejibianfang-v1 --format json
```

脚本产出保证：

- 公历→农历
- 年/月/日/时干支
- 节气区间与交节时刻
- 12 时辰干支

当前脚本支持三种 profile：

- `market-folk-v1`：春节换年 + 00:00 换日（更贴近大众挂历）
- `xiejibianfang-v1`：春节换年 + 00:00 换日（规则来源预留为《协纪辨方书》体系）
- `bazi-v1`：立春换年 + 23:00 换日（更贴近八字排盘）

默认直接查询时，优先按 `market-folk-v1` 输出，效果更接近常见挂历版老黄历。

兼容说明：

- 仍兼容旧参数 `--mode market|bazi`
- 推荐新调用方式统一使用 `--profile`

脚本不会伪造：

- 宜/忌、建除、值神、吉神凶神、冲煞、胎神、彭祖百忌等规则字段（未加载规则库时明确输出“待规则库补齐”）

推荐直接运行（无需本地安装依赖）：

```bash
skills/lao-huangli/scripts/huangli 2026 3 9 12 --profile market-folk-v1 --format markdown
```

如需本地固定环境，再手动安装依赖：

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r skills/lao-huangli/requirements.txt
```

当前实现状态：

- profile/ruleset 目录结构已建立
- `calendar_core` 与 `rule_engine` 模块骨架已建立
- `meta` 已输出 `profileId`、`profileLabel`、边界信息、`ruleLayer`、`overlayRuleset`
- `xiejibianfang-v1` 与 `market-folk-v1` 已输出可用的 `daily/decision`
- `daily` 已稳定承载 `jianchu`、`yellowBlackDao`、`dutyGod`、`goodStars`、`badStars`、`chongsha`、`taishen`、`pengzu`
- `xiejibianfang-v1` 的 `宜/忌` 已覆盖 `建/除/满/平/定/执/破/危/成/收/开/闭` 的一批卷十直引条目
- `market-folk-v1` 已补齐常用 `冲煞`、`胎神`、`彭祖百忌`，并沿用同一批高频 `建除` 宜忌收口
- `market-folk-v1` 已补齐常用 `财神 / 喜神 / 福神` 方位
- `bazi-v1` 默认只输出 `bazi-core`，如指定 `--overlay-ruleset` 则输出 hybrid 黄历层
- `provenance` 已输出 `ruleLayer`、`ruleSourceLevel`、`sourceRefs`、`isHybrid`
- 节气现已改为 `Skyfield + JPL ephemeris` 的天文时刻窗口输出，并带 `currentAt` / `nextAt`
- `solar_terms` 现已提供 `table`、`currentJie`、`currentQi`、`nextJie`、`nextQi`，便于后续按 6tail 风格继续派生字段
- `lunar` 现已提供 `monthStartDate`、`monthEndDate`、`monthDayCount`、`leapMonth`、`zhongQi`、`containsZhongQi`、`anchorYear`、`yearMonthTable`、`yearMonthCount`、`yearLeapMonth`、`currentMonthIndex`、`calculationMode`
- 农历月序、定朔与无中气置闰仍未完整升级到 `GB/T 33661-2017` 口径

规则来源约束：

- 每条规则文件必须带 `sourceLevel`
- 每条规则文件必须带 `sourceRef`
- `xiejibianfang-v1` 当前混合 `L1-primary` 与 `L2-derived-documented`
- `market-folk-v1` 目前使用 `L2-derived-documented` / `L3-market-observed` 混合标记

## 输出格式（仿挂历，默认详细版）

默认输出采用“**挂历完整版**”（正常版本），只有用户明确要求“简版/速览”时才降级精简。
下面只示意版式，不表示某个真实日期的计算结果。

```text
┌────────────────────────────────────────────────────────────┐
│ YYYY年MM月DD日 星期X                                      │
│ 农历：二〇二六年 正月十四（闰月：否）                      │
│ 干支：年柱 / 月柱 / 日柱（时柱按用户时刻另算）             │
│ 节气：当前 节气A → 下个 节气B                              │
├────────────────────────────────────────────────────────────┤
│ 【宜】出行  会友  祭祀  祈福  纳财                          │
│ 【忌】动土  开仓  破屋                                      │
├────────────────────────────────────────────────────────────┤
│ 建除十二神：定日      黄黑道：黄道日      值神：天德        │
│ 冲煞：冲鸡(乙酉)煞西   生肖冲合：鸡冲 / 狗合 / 猪三合      │
│ 胎神：仓库门外正南     彭祖百忌：丁不剃头，卯不穿井          │
│ 吉神宜趋：天德、月德、天恩   凶神宜忌：五虚、土符            │
│ 财神：正西   喜神：正南   福神：西北                         │
├────────────────────────────────────────────────────────────┤
│ 时辰吉凶（示例）                                            │
│ 子时 23:00-00:59  吉  宜：祈福/求财   忌：动土               │
│ 丑时 01:00-02:59  凶  宜：静守         忌：远行/开市          │
│ 寅时 03:00-04:59  吉  宜：出行/见贵     忌：争讼              │
│ ...（其余时辰按同样结构列出）                               │
└────────────────────────────────────────────────────────────┘
说明：历法/干支/节气为可精算；宜忌/神煞依赖 rulesetVersion=zh-traditional-v1
```

### 字段顺序（固定）

1. 顶部主栏：公历日期 + 星期
2. 历法层：农历（含闰月）、干支、节气（当前/下个与时刻）
3. 宜忌层：`【宜】` 与 `【忌】`（宜在前）
4. 日神层：建除、黄黑道、值神、冲煞、胎神、彭祖百忌、吉神凶煞
5. 方位层：财神/喜神/福神
6. 时辰层：12 时辰吉凶（每行含时间段、吉凶、宜忌）
7. 末尾说明：规则版本与边界（年界/日界）

### 模式规则

- **默认：详细版（正常版）**
- **仅当用户明确要求**“简版、速览、只看宜忌”时，输出精简版

### 排版规则

- `【宜】` 与 `【忌】` 必须分行且“宜在前”
- 时辰吉凶固定为 12 行（可折叠但不可省略为 1 行总结）
- 若字段缺失，必须写 `待规则库补齐`，不可静默忽略
- 末尾必须附：
  - 可精算字段（农历/干支/节气）
  - 规则字段（宜忌/神煞）与 `rulesetVersion`

## 示例

用户：`帮我看 2026-03-02 的老黄历，为什么今天宜出行？`

回答结构建议：

1. 历法层：公历/农历/干支/节气
2. 规则层：建除/值神/冲煞
3. 结论层：宜出行的规则依据 + 忌事项 + 边界说明

## 按需阅读

- 计算细化：`references/calculation-pipeline.md`
- 规则分歧处理：`references/rules-and-variants.md`
- 脚本实现：`scripts/huangli_calc.py`
