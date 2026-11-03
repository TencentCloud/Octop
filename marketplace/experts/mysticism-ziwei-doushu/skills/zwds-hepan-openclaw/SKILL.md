---
name: zwds-hepan-openclaw
description: 紫微斗数双人合盘：先以 zwds-cli 各排一盘，再将两份 data 送入 hepan-cli 得 0–100 匹配分、维度分项与 hits。用户提及合盘、配对、缘分指数、双人紫微匹配时使用。
---

# 紫微斗数合盘（OpenClaw / zwds-hepan）

## 何时使用

用户需要**双人紫微合盘**、**匹配度打分（0–100）**、**合盘结构化依据（hits）**或在此基础上做白话解读时启用本技能。

## 硬禁止

- **不得**脱离两份 `data` JSON 臆造星曜、宫位或四化。
- **不得**用 Python 直接调用 iztro；排盘须走 [zwds 技能](../zwds/SKILL.md) 约定的 **zwds-cli**。
- 解读阶段每条结论应能对应 `hits[].evidence` 或维度中的宫位、星曜字段。

## 环境前置

1. **Node.js >= 18**。
2. 已能运行 zwds-cli（见 `openclaw-skill/zwds/zwds-cli`，需 `npm ci`）。
3. 本技能 CLI 目录：`openclaw-skill/zwds-hepan/hepan-cli`（无需额外 `npm install`，无第三方依赖）。

## Shell 契约

### 阶段 A — 双人排盘（各一次）

工作目录：`openclaw-skill/zwds/zwds-cli`  
命令：`node src/index.js`  
标准输入：单行或多行 JSON（与 zwds 技能一致），含 `birth_time`、`gender`、`birth_place` 或 `longitude`。  
标准输出：**一行** JSON；解析 `success`，为 `true` 时取出 `data` 与 `meta` 分别作为 `chart_a` / `chart_b` 与 `meta_a` / `meta_b` 的输入。

对第二人重复上述步骤。

### 阶段 B — 合盘计算

工作目录：`openclaw-skill/zwds-hepan/hepan-cli`  
命令：`node src/index.js`  
标准输入：一行 JSON（可多行，解析前 `trim`），必填字段：

| 字段 | 说明 |
|------|------|
| `chart_a` | 第一人 zwds-cli 的 `data` |
| `chart_b` | 第二人 zwds-cli 的 `data` |
| `rule_version` | 可选，默认 `compat/v1` |
| `meta_a` / `meta_b` | 可选，对应 zwds-cli 的 `meta`，用于 `confidence` |
| `reference_year` | 可选，阳历年；运限维度 `life_rhythm` 从此年起算未来 `years` 年（见 [reference.md](reference.md)）。缺省为运行时的当前年 |
| `reference_age_a` / `reference_age_b` | 可选；在 `reference_year` 当年双方的虚岁，用于与大限区间对齐；缺省则由 `birth_info.solar_date` 推算 |

**成功**：仅向 **stdout** 打印一行 JSON：

```json
{
  "success": true,
  "data": {
    "score": 73,
    "confidence": 0.85,
    "rule_version": "compat/v1",
    "dimensions": [
      { "id": "palace_alignment", "score": 17.5, "max": 28, "hits": [] },
      { "id": "star_harmony", "score": 23.4, "max": 32, "hits": [] },
      { "id": "mutagen_interaction", "score": 2, "max": 28, "hits": [] },
      { "id": "life_rhythm", "score": 7.2, "max": 12, "hits": [] }
    ],
    "hits": [],
    "penalty_total": 0
  },
  "meta": { "engine": "hepan-cli", "engine_version": "1.0.0" }
}
```

**失败**：向 **stderr** 打印一行 JSON（`success: false`，含 `error`），进程退出码非 0。  
**与 zwds-cli 对齐**：成功只读 stdout；失败只读 stderr。

### 阶段 C — 解读（可选）

在阶段 B 的 `data.hits` 与 `dimensions[].hits` 基础上组织叙述；先列依据（宫位名、地支、星曜名、规则 id），再作推论；避免绝对化诅咒式断语。

## 示例（PowerShell）

```powershell
cd openclaw-skill/zwds/zwds-cli
$p1 = '{"birth_time":"1993-05-03T11:55:00","gender":"male","birth_place":"宁波市"}' | node src/index.js | ConvertFrom-Json
$p2 = '{"birth_time":"1988-06-20T14:30:00","gender":"female","longitude":113.3}' | node src/index.js | ConvertFrom-Json
$compat = @{ chart_a = $p1.data; chart_b = $p2.data; meta_a = $p1.meta; meta_b = $p2.meta; reference_year = 2026 } | ConvertTo-Json -Depth 100
cd ..\zwds-hepan\hepan-cli
$compat | node src/index.js
```

（Bash 用户可用 `jq` 组装 payload，逻辑相同。）

仓库内完整示例载荷（由 fixture 生成，体积较大）：[examples/sample-compat-payload.json](examples/sample-compat-payload.json)。在 `hepan-cli` 目录下可执行：

`Get-Content ..\examples\sample-compat-payload.json -Raw | node src/index.js`（PowerShell）或 `node src/index.js < ../examples/sample-compat-payload.json`（Bash）。

## 错误与版本

- 未知 `rule_version`：`error` 中会含 `unknown rule_version`。
- `chart_a` / `chart_b` 须含长度 12 的 `palaces` 数组，否则报错。
- 规则与表变更时递增 `hepan-cli` 的 `engine_version` 或新增 `compat/v2` 等规则文件；详见 [reference.md](reference.md)。
