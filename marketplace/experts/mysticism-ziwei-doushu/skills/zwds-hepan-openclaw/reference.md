# zwds-hepan 参考

## 与 zwds 排盘的关系

- **排盘**必须使用 [../zwds/zwds-cli](../zwds/zwds-cli)（或等价方式）生成两份 `success: true` 下的 **`data`** JSON；规则与字段含义见 [../zwds/reference.md](../zwds/reference.md)。
- **合盘**仅消费 `chart_a`、`chart_b` 两份 `data`；不得脱离 JSON 臆造星曜或宫位。

## 分数与对称性

- **总分** `score` 为 0–100 的整数，由维度加权归一后再叠加惩罚项并裁剪得到；表示在当前 `rule_version` 规则包下的**结构化相容指数**，不作命运或婚姻结果断言。
- **`dimensions[].max` 之和为 100**（`compat/v1`：`palace_alignment` + `star_harmony` + `mutagen_interaction` + `life_rhythm`），便于 UI 展示「各维满分」与总分口径一致；各维内部仍按权重参与加权，与「分项满分之和」不必数值相等。
- **四化维度对称结构**：`mutagen_interaction` 额外返回 `positive_score`、`negative_score`、`raw_score_before_clip`。同时 `hits` 对每条 `mutagen_rule` 都给出 `matched: true/false`，可直接看出「加分来自哪条」「扣分来自哪条」「未命中哪些条」。
- **对称性**：宫位对照类规则对 `(A→B)` 与 `(B→A)` 成对取平均；主星维度同时包含命命、夫夫与交叉命夫。
- **`confidence`**：0–1，由可选的 `meta_a` / `meta_b`（如 `longitude_resolution.source === "default"`、`warnings`）推导，**不参与**加权分，仅供展示与风险提示。

## 三方四正（与 zwds 技能一致）

对本宫索引 `i`：对宫 `(i+6)%12`，财帛位 `(i+4)%12`，官禄位 `(i+8)%12`。当前 `compat/v1` 合盘逻辑以宫名查找为主，未单独实现飞宫链；后续版本可在引擎中扩展。

## 规则版本

- 默认 **`compat/v1`**：权重与维度上限见 [hepan-cli/src/rules/compat/v1.json](hepan-cli/src/rules/compat/v1.json)。
- 数据表：[hepan-cli/src/tables/star_groupings.json](hepan-cli/src/tables/star_groupings.json)、[hepan-cli/src/tables/star_pair_scores.json](hepan-cli/src/tables/star_pair_scores.json)。
- 地支关系（冲、合、三合）在 [hepan-cli/src/branchRelation.js](hepan-cli/src/branchRelation.js) 中实现。

## 运限维度（`life_rhythm`）

`compat/v1` 中 **`life_rhythm.enabled` 为 `true`**：自 `reference_year` 起连续 `years` 年（默认 10），按虚岁落在本命盘上**大限所在宫**（`palaces[].decadal.range` 覆盖该岁者），取双方该宫 `earthly_branch` 做冲合三合等比对，得 0–1 因子后线性映射到维度满分 `dimension_caps.life_rhythm`（默认 12）。

- **`reference_year`**：可选，整数阳历年；缺省时用运行环境当前年（Node `new Date().getFullYear()`）。stdin 与 `computeCompat` 的 `reference_year` 或 `payload.reference_year` 均可传入。
- **`reference_age_a` / `reference_age_b`**：可选；若提供，则在 `reference_year` 当年使用该虚岁，其后每年 +1，用于与 `decadal.range` 对齐；未提供则从 `birth_info.solar_date` 公历年推算 `虚岁 ≈ 阳历年 − 出生年`。
- **`life_rhythm.enabled` 为 `false`** 时：该维度 `max` 为 0，其权重由 `normalizeWeights` 分摊到其他维度。

## Roadmap（未纳入首版）

- 完整飞宫、流月流日、立春交接时刻细分。
- `hepan-cli` 子进程自动调用 `zwds-cli` 的双生辰模式（减少 Agent 手工两次排盘）。

## 免责声明

合盘输出仅供文化娱乐与自我认知参考，不构成心理咨询、法律或投资建议。
