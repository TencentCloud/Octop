# 老黄历计算流程（工程实现版）

本文给出可落地的“先历法、后规则”流水线。

## 1. 输入与标准化

- 必填：`datetime`（ISO 8601）、`timezone`（默认 `Asia/Shanghai`）
- 可选：经纬度（用于部分真太阳时/地理修正流派）
- 全局约定（必须写入配置）：
  - `yearBoundary`: `lichun` | `spring-festival`
  - `dayBoundary`: `23:00` | `00:00`
  - `rulesetVersion`: 例如 `zh-traditional-v1`

## 2. 基础历法层（确定性）

1. 公历时间 -> 儒略日（JDN / JD）
2. 太阳黄经计算，定位 24 节气（每 15° 一节）
3. 朔望计算（新月时刻序列）
4. 结合“无中气置闰”等规则确定农历月序、闰月与月日

产出：

- `lunarYear`, `lunarMonth`, `lunarDay`, `isLeapMonth`
- `solarTerms`（当前节气、下个节气与时刻）

## 3. 干支层（确定性）

- 年柱：按 `yearBoundary` 取界点
- 月柱：按节气月（寅月起）映射
- 日柱：`(JDN - baseJiaZiDay) mod 60`
- 时柱：由日干 + 时支映射表得到

产出：`ganzhiYear`, `ganzhiMonth`, `ganzhiDay`, `ganzhiHour`

## 4. 神煞/值神层（规则映射）

该层通常非纯天文推导，而是规则表：

- 建除十二神
- 黄道/黑道
- 值神
- 吉神凶煞
- 冲煞、胎神、彭祖百忌

产出：`dailyGod`, `jianchu`, `goodStars[]`, `badStars[]`, `chongsha`

## 5. 宜忌生成层（规则引擎）

1. 依据上层字段生成候选事项评分（如嫁娶、开市、动土、出行）
2. 冲突裁决（优先级 + 黑名单规则）
3. 生成 `yi[]`、`ji[]` 及每项理由

建议输出结构：

```json
{
  "date": "2026-03-02",
  "timezone": "Asia/Shanghai",
  "lunar": {"year": "...", "month": "...", "day": "...", "isLeap": false},
  "ganzhi": {"year": "...", "month": "...", "day": "...", "hour": "..."},
  "terms": {"current": "...", "next": "...", "nextAt": "..."},
  "daily": {"jianchu": "...", "dutyGod": "...", "chongsha": "..."},
  "yi": [{"item": "出行", "reason": "..."}],
  "ji": [{"item": "动土", "reason": "..."}],
  "meta": {
    "yearBoundary": "lichun",
    "dayBoundary": "23:00",
    "rulesetVersion": "zh-traditional-v1"
  }
}
```

## 6. 可解释性与审计

每次输出都应附带：

- 规则版本
- 分界设定（年界/日界）
- 关键推导路径（例如“因值神 X + 建除 Y，故宜出行”）
