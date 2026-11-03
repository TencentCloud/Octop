# zwds-cli 输入输出示例

## 1. 无出生地（不经真太阳时经度修正）

**输入（stdin）：**

```json
{"birth_time":"2000-08-16T06:00:00","gender":"female"}
```

**要点**：`birth_info.true_solar_time` 为 `null`；`meta.longitude_resolution.source` 一般为 `default`。

---

## 2. 有出生地（内置表匹配）

**输入：**

```json
{"birth_time":"2000-08-16T06:00:00","gender":"female","birth_place":"广州市"}
```

**要点**：`birth_info.true_solar_time` 非空，`is_applied: true`，含 `hour`、`minute`、`longitude`、`original_time`、`true_solar_time_str`。

---

## 3. 直接提供经度（优先于地名）

**输入：**

```json
{"birth_time":"1988-07-15T12:00:00","gender":"male","birth_place":"某小镇","longitude":118.8}
```

**要点**：真太阳时使用 `118.8`，`meta.longitude_resolution.source` 为 `input`。

---

## Shell 调用

```bash
cd openclaw-skill/zwds/zwds-cli
npm ci
echo '{"birth_time":"2000-08-16T06:00:00","gender":"female","birth_place":"北京市"}' | node src/index.js
```

成功时 stdout 首字符为 `{`，且 JSON 根级含 `"success":true` 与 `"data"`。

---

## 固定命盘（fixtures）：按生辰地点性别存档，读盘不必每次重排

将 **CLI 入参**（`birth_time`、`gender`、`birth_place`、可选 `longitude`）与 **当次完整 stdout**（`success` / `data` / `meta`）写在同一文件里，以后对模型 **@ 该文件** 即可解盘，无需再跑 `node src/index.js`。

**生成或更新**（在 `zwds-cli` 目录，入参文件须 UTF-8）：

```bash
cd openclaw-skill/zwds/zwds-cli
# 默认：examples/sample-payload.json → ../fixtures/sample-ningbo-1993-05-03-male.json
npm run save-fixture

# 自定义：输入 JSON、输出路径、可选标题
node scripts/save-fixture.mjs path/to/birth.json ../fixtures/我的别名.json "展示用标题"
```

根对象含 **`_fixture`**（`schema: zwds-fixture-v1`、`title`、`input`、`saved_at` 等）及与 CLI 一致的 **`success` / `data` / `meta`**。读盘时规则不变：**只认 `data`**（及 `meta` 里经度告警）；`_fixture.input` 仅作「这张盘对应谁」的说明。

本仓库已带示例：**`fixtures/sample-ningbo-1993-05-03-male.json`**。新增个人盘时请另存文件名（建议带日期与地点，避免覆盖示例）。

---

## 解盘（读盘）如何测试

**排盘**由 `zwds-cli` 与 `npm test` 覆盖；**读盘**是技能 `SKILL.md` 中的**阶段 B**：由 Agent / 大模型**只根据** `success === true` 时的 **`data`** 做分析，CLI **不会**输出解读文字，因此也没有「一条命令断言解盘对错」的自动化金样例。

### 推荐做法（人工 + 技能约束）

1. **先固定一张盘**：优先用 **`fixtures/*.json`**（`npm run save-fixture` 生成）；或自行用 UTF-8 stdin 跑 CLI 后保存 stdout；也可只保留 `data` 备用。
2. **在 Cursor 里启用本技能**（`.cursor/skills` 已链到 `openclaw-skill/zwds` 时）：新开对话，**@** `fixtures/某文件.json` 或粘贴 `data`，明确写：「请严格按 zwds 技能阶段 B，只根据附件 JSON 解读……」。
3. **用具体问题测读盘质量**，例如：「只看命宫与夫妻宫的主星与四化，先列依据再推论」「若问 32 岁大限，对应哪一宫、宫干地支与主星是什么」。
4. **审查清单（是否合格）**：
   - 提到的宫位名、星曜名、四化、庙旺利陷能否在对应 `palaces[]` 条目里**逐条对上**；
   - 是否出现 **JSON 里没有的星或宫**（若有则读盘不合格）；
   - 若 `meta.warnings` 非空或经度为 `default`，解读里是否**提醒**时辰/真太阳时仅供参考。

### 可选半自动（自查用）

把某次 CLI 输出的 `data` 存为 `test/fixtures/chart-xxx.json`，自拟「必须出现的词」列表（如某盘命宫必有 `太阴`、`mutagen` 为 `科`），用脚本对模型回答做**子串检查**；只能防明显胡编，**不能**代替人对理路、分寸的评判。

更细的解盘规则与宫位映射表见同目录 **`SKILL.md`（阶段 B）**。
