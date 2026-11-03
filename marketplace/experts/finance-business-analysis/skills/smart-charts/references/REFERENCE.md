# Reference

Detailed reference for installation, capability boundaries, CLI usage, programmatic API, and delivery annotation. For the contract, hard constraints, chart type table, and transform templates, see [SKILL.md](../SKILL.md).

---

## Installation

```bash
pip install -r requirements.txt
```

Dependencies (compatible ranges, no longer `==` pinned): `pandas>=3.0.1,<4.0.0`, `numpy>=2.4.3,<3.0.0`, `openpyxl>=3.1.5,<4.0.0`, `xlrd>=2.0.1,<3.0.0`. ECharts JS is bundled in `assets/` (no CDN, fully offline).

Environment self-check: `python {skill_base}/scripts/cli.py --doctor` — prints a version matrix (Python / pandas / numpy / openpyxl / xlrd: required minimum vs installed vs `ok`) plus `assets/` integrity, as JSON. Read-only: parses no data and writes no files. Run it before blaming the skill when versions have drifted; to reproduce an exact old environment, `pip install pkg==<installed version from --doctor>`.

Self-test (developer): `python {skill_base}/scripts/regression_check.py` — end-to-end regression suite (real CLI subprocesses): validator unit tests incl. sandbox escape PoCs, all parsers, 32 chart types, multi-chart mode, flags/themes/lang, transform golden patterns, error paths, plus the historical fix cases (sandbox closure, trend ordering, gauge target, grain reconciliation, column-name collision) and the profile cases (`--profile` 结构/信号、值形态保护、未聚合告警与误报防护). Test data goes to a temp dir; independent CLI cases run in parallel; exit 0 = all pass.

---

## Capability Boundaries

**Supported:** CSV (.csv=comma / .tsv=tab / .txt=auto-detect delimiter), Excel (.xlsx/.xls), JSON (.json，支持 1 层嵌套对象，自动展开为「父.子」点分列，列名规范化后为「父_子」); 32 chart types (see SKILL.md); 3 themes (`--theme default|classic|dark`); multi-file auto-merge (recommended ≤ 10 files); single file ≤ 100 MB (≤ 50 MB recommended); auto-detects UTF-8/GBK/GB2312/UTF-16/Latin-1.

**Not supported:** Databases (export to CSV first), real-time/streaming data, >100 MB files, nested JSON >1 level, non-tabular data (images/audio/video). Auto-merge requires ≥50% column overlap.

**Map capability (map / lines):** offline GeoJSON is bundled under `assets/` — `china.json` (中国省级，含港澳台，default) and `world.json` (国家级). `--geo china|world` selects a built-in map (auto-registered as `map: "<name>"`); region names for `china` accept full names or common short names (北京/广东/新疆/内蒙古…) normalized via `_REGION_ALIASES`, while `world` matches English country names exactly. Non-matching names are skipped and disclosed in `plot_stats.extra.unmatched`. For city-level maps, districts, or custom regions supply your own file with `--geo-path <path>`; the skill does not download GeoJSON on your behalf.

**Network requirement:** None. ECharts JS is bundled in `assets/` and inlined into each HTML output; charts render fully offline with no external dependencies.

**Security:** transform 代码由沙箱强制校验（关键字黑名单 + AST 白名单 + 安全 builtins + 危险属性名/模块路径封禁），违规会返回带 `suggestion` 的结构化错误，按提示修正重试即可，无需用户确认。除裸名关键字外，`pd.read_csv`/`np.save`/`to_pickle` 这类属性名，以及 `pd.io.*` / `np.lib.*` 整棵子树（`pd.io.common.get_handle`、`np.lib.format.open_memmap` 等文件与网络句柄工厂）均在 AST 层被拦。机制细节见下方 Transform Code Generation。

---

## Data Parsing — CLI Reference

> `{skill_base}` = root directory of this skill (contains `SKILL.md`).

```bash
# Single file
python {skill_base}/scripts/data_parser.py <file_path> [--summary] [--profile] [--skiprows N] [--header-row N] [--drop-rows 0,1] [--sheet <name|index>]

# Multiple files
python {skill_base}/scripts/data_parser.py <file1> <file2> ... [--summary]

# Multiple files with auto-merge
python {skill_base}/scripts/data_parser.py <file1> <file2> ... [--merge] [--summary]
```

**Flags:**
- `--summary` — output a JSON data summary (shape, columns, dtypes, missing, sample, stats) instead of a text preview.
- `--profile` — output a JSON data profile (per-column dtype/cardinality/missing/sample/statistics, entity grain, insight signals, suspected non-data rows) — 出图前的第 0 步，详见 [Data Profile](#data-profile--profile)。
- `--merge` — attempt to merge multiple files into one DataFrame.
- `--skiprows N` / `--header-row N` *(single-file only)* — **these two are the same operation, not two decisions**: both make the 0-indexed row N the header and drop everything above it (`skiprows=N` → pandas `skiprows=N`; `header_row=N` → pandas `header=N`; when both are passed, `header-row` wins). Always go straight to `--header-row N` — pick the row you want as column names and count from 0. Use when the file has leading junk rows (notes, blanks) or multi-row headers (merged cells, sub-headers).
- `--sheet <name|index>` *(single-file only)* — pick an Excel sheet by name or 0-indexed position (default: 0). An explicitly named/numbered sheet that does not exist returns a structured `DATA_PARSE_ERROR` listing `available_sheets`; only the default sheet 0 falls back automatically (first non-empty sheet is used when sheet 0 is empty).
- `--drop-rows 0,1` *(single-file only)* — drop the given **0-based row positions of the cleaned DataFrame** (comma-separated; not raw file row numbers). Order of application: header positioning (`--skiprows`/`--header-row`) → `--drop-rows` → `--transform-code`. Out-of-range positions return a structured `DATA_PARSE_ERROR`. Use it to delete sub-header/value rows that `--header-row` can't reach (two-row headers plus a 分值 row); the positions should come from `--profile`'s `row_quality.suspicious_non_data_rows`, never guessed.
- N must be determined by inspecting the actual data (run `data_parser.py` once without flags to see the raw layout). Never assume a fixed N.

**Merge behavior:**
- Identical columns → vertical concat (adds a `source_file` column to indicate each row's origin file — 下游 transform 代码必须考虑这个额外列).
- ≥50% overlap → horizontal join on shared key. Overlapping non-key columns from later files are merged back with `combine_first` (non-null values from both files survive); genuinely `_dup`-suffixed source column names are preserved untouched.
- No common structure → error (advise analyzing separately).
- `--merge --summary` 模式下 stdout 为纯 JSON，合并方式体现在 JSON 的 `merge_type` 字段（不打印额外文本行，保证机器可读）。

**Value-shape protection (not column-name guessing):** columns whose values have leading zeros (e.g. `007`) or are pure numeric strings of ≥16 digits (float64 loses the last-digit precision, e.g. 18-digit IDs) are kept as strings — never silently coerced to numbers (which would irreversibly destroy information). Whether a column is an identifier is a semantic judgment left to the agent (read `--profile`'s `sample` + `cardinality` + `dtype`), not decided by a column-name word list. All other numeric-looking string columns are still auto-converted.

**Numeric coercion is observable:** string columns are cleaned (currency symbols → thousands separators → `%` → Chinese magnitude suffixes `亿`/`万`/`千`, so `8.5万` → `85000`) and then coerced. If only *some* cells fail to parse but ≥50% succeed, the column still becomes numeric with the failures set to missing, and an advisory is emitted naming the column and the number of discarded cells. Below 50% the column is left as text. Previously a single stray `-` silently degraded a whole column to string with no warning.

**Total/subtotal rows are NOT auto-excluded:** whether a row is a hand-added total row is a semantic judgment, so the parser keeps all rows and exposes them via `data_parser.py --summary`'s `tail` (total rows almost always sit at the end). The agent spots them and drops them with `--drop-rows` or `--transform-code` before charting. No word-list matching is done at parse time.

**Column-name collisions are de-duplicated:** after normalization, colliding names get `_2`, `_3` suffixes (e.g. `Sales Amount` + `sales-amount` → `sales_amount`, `sales_amount_2`). Previously the collision made `df[col]` return a DataFrame and crashed with `'DataFrame' object has no attribute 'dtype'`.

**Delimited files are read as strings** (`dtype=str`) and numerified in one cleaning pass — this is what makes leading-zero protection possible; missing-value tokens (`NA`, empty, etc.) are still normalized to NaN by pandas.

**Argparse CLI:** both `data_parser.py` and `cli.py` parse arguments with argparse; unknown flags / missing values / bad types return the same structured JSON error (`code_name` + `details.suggestion`) instead of bare usage text.

**Formats:** .csv (comma) / .tsv (tab) / .txt (auto-detect delimiter: `,`/`\t`/`;`/`|`) + auto-detect encoding (UTF-8/UTF-8-BOM/GBK/GB2312/UTF-16/Latin-1, single shared fallback list), .xlsx/.xls (first non-empty sheet), .json (array format; 1-level nested objects are flattened into `parent.child` columns, which become `parent_child` after column-name normalization — reference the normalized names in `--x-axis`/`--y-axis`/transform code. Nested depth ≥2 or array-valued fields are rejected with a structured error).

**Column name normalization:** Parsed column names are normalized by `_normalize_col`:
1. Non-word characters (anything except letters, digits, `_`, and whitespace) are replaced with `_`. CJK characters count as word characters and are preserved.
2. Consecutive spaces/underscores collapse into a single `_`.
3. Leading/trailing `_` are stripped, then the name is lowercased.
4. Empty or NaN names become `unnamed`.

| Input | Normalized |
|-------|-----------|
| `Sales Amount` | `sales_amount` |
| `Revenue($)` | `revenue` |
| `销售-额%` | `销售_额` |
| `A/B` | `a_b` |
| `  Total  ` | `total` |
| (blank / NaN) | `unnamed` |

`--x-axis`, `--y-axis`, and transform code must use the **normalized** column names, not the raw header text.

**Error output:** When a `SmartChartsError` occurs, the CLI prints a JSON object to stderr:
```json
{"error": "<message>", "code": <int>, "code_name": "<NAME>", "details": {...}}
```
The `details` field always includes a `suggestion` for recovery. Any other exception is wrapped as `UNKNOWN_ERROR` (9999) JSON on stderr — in both `cli.py` and `data_parser.py`.

**Error codes:**

| Code | Name | Meaning |
|------|------|---------|
| 1001 | FILE_NOT_FOUND | File path does not exist |
| 1002 | FILE_NOT_REGULAR | Path is not a regular file |
| 1003 | FILE_FORMAT_INVALID | Unsupported file extension |
| 1004 | FILE_SIZE_EXCEEDED | File exceeds 100 MB limit |
| 2001 | DATA_PARSE_ERROR | Parsing failed (encoding, structure, sheet missing, etc.) |
| 2002 | DATA_MERGE_ERROR | Auto-merge impossible (no common structure between files) |
| 2003 | DATA_EMPTY | File or cleaned data is empty |
| 3001 | TRANSFORM_EXEC_ERROR | Transform code execution failed (blacklist/AST/timeout) |
| 3002 | TRANSFORM_NO_RESULT | Transform code did not produce `result` variable |
| 3003 | TRANSFORM_INVALID_RESULT | `result` is not a DataFrame |
| 3004 | TRANSFORM_EMPTY_RESULT | `result` DataFrame is empty |
| 4001 | CHART_GENERATION_ERROR | Chart generation failed |
| 4002 | CHART_TYPE_UNSUPPORTED | Unsupported chart type |
| 4003 | CHART_CONFIG_ERROR | Axis field does not exist in DataFrame |
| 9999 | UNKNOWN_ERROR | Unclassified error |

---

## Chart Generation — CLI Reference

```bash
python {skill_base}/scripts/cli.py \
  <file_path> <chart_type> \
  --title "Chart Title" \
  --x-axis "date" \
  --y-axis "revenue profit" \
  --transform-code "<pandas code>" \
  --annotation "<delivery text>" \
  --subtitle "<time range / filter / source>" \
  --x-name "<X axis display name>" \
  --y-name "<Y axis display name>" \
  --series-name "<series display name>" \
  --sort none|value --y-scale --label auto|all|key \
  --skiprows N --header-row N --drop-rows 0,1 --sheet <name|index> \
  --lang zh|en \
  --theme default|classic|dark \
  --output-dir "./output" \
  --width 900 --height 560
```

**Parameters:**
- `file_path` (required) — path to the data file.
- `chart_type` (required) — one of the 32 types listed in SKILL.md.
- `--title` (default follows `--lang` / data language) — chart title.
- `--x-axis` (auto-detected if omitted) — column name for x-axis.
- `--y-axis` (space-separated; defaults to first 5 numeric columns, or first 3 other columns if none numeric) — column name(s) for y-axis.
- `--transform-code` (optional) — LLM-generated pandas code, validated + executed before rendering.
- `--annotation "<text>"` (optional) — delivery annotation text injected into the HTML below the chart（「图表说明」区块）. Pass it on the single generating call — you do **not** need a prior `--dry-run` (see 交付解读规范 below). The success output's `annotation_source` is `'user'` when you supplied it and `'default'` when the built-in template was substituted (a `default` value also raises an advisory).
- `--subtitle "<text>"` (optional) — context line under the title: time range, filter conditions, data source. Rendered as `<subtitle> · Smart Charts · <timestamp>`; omitted → the default `Smart Charts · <timestamp>` line is kept unchanged. Pairs with a conclusion-style `--title` (标题写结论，副标题补口径).
- `--x-name "<text>"` (optional) — X 轴显示名，覆盖列名。缺省时轴名 = `--x-axis` 列名。仅对**显示轴名的图表**生效（line/bar/area/stacked_bar/pie/scatter/effect_scatter/pictorial_bar/waterfall/histogram/pareto/combo 等有 `axisName-x` graphic 的图）；heatmap/gauge/sankey/map/lines/calendar/theme_river 等本就无轴名的图不受影响（也不报错）。
- `--y-name "<text> ..."` (optional) — Y 轴显示名，可多个，按 `--y-axis` 顺序对应；缺省时回退到列名。多 y 轴（combo 双轴等）可传多个：`--y-name "营收额" "利润率"`。
- `--series-name "<text>"` (optional) — 系列显示名，覆盖**第一个可见系列**。适用于单系列图（bar/line/gauge/heatmap/treemap/sankey 等），也覆盖原本写死默认文本的 B 类图（如 heatmap 的「热力图」、gauge 的「仪表盘」）。多系列请用 `--series-names`。
- `--series-names "<text> ..."` (optional) — 系列显示名，按**可见系列顺序**对应覆盖（combo 的柱/线、boxplot 的箱线图/异常值、pareto 的柱/累计线等）。waterfall 的透明底座是内部系列，自动跳过、不占名额。缺省时回退到列名（A 类图）或默认文本（B 类图）。
- `--sort none|value` (default: `none`) — category ordering for bar/stacked_bar. `value` sorts categories by the first numeric y column, descending; `none` keeps data order (月份/流程阶段等自然顺序不会被误动). Pie is always frequency-descending already.
- `--y-scale` (optional, off by default) — lets the line chart's y-axis start at a non-zero baseline to amplify fluctuation (仅 `line` 生效；`area` 恒为零基线——面积编码量级，非零基线会扭曲面积占比). Bar/stacked_bar never use a non-zero baseline.
- `--label auto|all|key` (default: `auto`) — bar value labels. `auto` labels every bar when categories ≤ 20 and switches to key values only beyond that; `all` forces full labeling; `key` labels only top-3 + max/min (其余靠 tooltip；交互 HTML 悬停可读全量数值).
- `--skiprows` / `--header-row` / `--drop-rows` / `--sheet` (optional) — same semantics as `data_parser.py`; passed through to the parsing step so chart generation works directly on messy-header files. `--drop-rows 0,1` deletes sub-header/value rows after header positioning.
- `--lang zh|en` (optional) — force the chart text language. If omitted, the CLI auto-detects from the data: CJK character ratio > 5% in column names + string cells → `zh`, otherwise `en`. Pass `--lang` only when the user explicitly requests a specific language.
- `--label-col` (optional) — identity column (e.g. name/title). Its values become each point's `name` and appear as the tooltip title. Applies to scatter/bubble/boxplot (boxplot uses it for outlier points). **Must be specified explicitly** — no auto-detection by column-name word list; if omitted, points have no identity label (tooltip shows coordinates only).
- `--color-by` (optional) — color-encoding column for scatter/bubble. Numeric column → continuous coloring via `visualMap`; categorical column → one series per category with legend. Off by default — 无分析意义的着色只是视觉噪音.
- `--output-dir` (default: `./smart_charts_output`) — output directory for HTML files. **Always pass it explicitly** and point it at a user-visible location; the default lands next to whatever the current working directory happens to be, so the user may never find the files.
- `--width` / `--height` (default: 900 / 560) — HTML canvas size in px.
- `--theme` (default: `default`) — theme preset unifying the series palette and page colors: `default` (Okabe-Ito color-blind-safe palette), `classic` (ECharts native palette, blue accents), `dark` (dark background, light text; ECharts text/labels switch to light colors automatically). Applies to all 32 chart types including venn/mindmap/orgchart/liquid/spreadsheet/map/lines. Pass the same theme across a batch for visual consistency.
- `--target <float>` (optional) — business target for `gauge`/`liquid`. `plot_stats.extra.achievement` = mean ÷ target; **without `--target` it is `null`** (the auto-inferred dial scale is not a business target, so calling the ratio "达成率" would be meaningless) and an advisory is raised. Also settable per chart as `target` inside a `--charts` item.
- `--geo <name>` (optional, default `china`) — built-in map for `map`/`lines`: loads `assets/<name>.json` offline. Built-in ships `china` (中国省级，含港澳台) and `world` (国家级，英文国名精确匹配); any other name raises a structured error with a hint to use `--geo-path`.
- `--geo-path <path>` (optional) — self-supplied GeoJSON file for `map`/`lines`, for **any region** (cities, districts, custom shapes). Takes priority over `--geo`; the map name is the file's stem (e.g. `beijing.json` → `registerMap("beijing")`). Region-name matching is **exact only** (no 简称 aliases), so the data's region column must equal the GeoJSON `properties.name` values verbatim (or normalize with `transform_code`). The GeoJSON is inlined into the HTML, keeping the output self-contained; larger/finer maps inflate the file size accordingly.
- `--profile` (optional) — **数据画像（出图前第 0 步）**：只读解析文件并输出每列 dtype / 基数 / 缺失 / 样本 / 统计、实体粒度、候选洞察信号、疑似非数据行；**不需要 `chart_type`、不渲染、不落盘**。用于"用户只给了数据、没说想看什么"的场景，详见下方 Data Profile。哪列是 ID、哪列是维度、出什么图，由 agent 从这些客观事实自行判断，profile 不代笔。
- `--doctor` (optional) — environment self-check: prints the Python/dependency/asset version matrix as JSON and exits. Parses no data, writes no files.
- `--dry-run` (optional) — stats-only mode: outputs `plot_stats`/`data_preview` with `dry_run: true` and `html_path: null`, without rendering or writing HTML. Use it only for probing column names or aggregation scripts — **not** as a required step before writing the annotation, since the real (non-`--dry-run`) output already carries `plot_stats`. Works in both single- and multi-chart mode.
- `--charts-file <path>` (multi-chart mode, recommended) — read the `--charts` JSON array from a UTF-8 file instead of a shell argument; avoids shell-escaping corruption when transform code contains CJK text or quotes. Missing/unreadable file returns a structured `FILE_NOT_FOUND` error on stderr (exit 1).
- `spreadsheet` file naming — hash covers full table content (columns + values), so two same-schema tables with different data never overwrite each other.

**Output:** On success, prints a JSON object to stdout and exits with code 0:
```json
{"chart": {"success": true, "dry_run": false, "html_path": "./output/Title_abc123.html", "chart_type": "bar", "title": "Title", "source_rows": 34, "plotted_rows": 2, "unique_entities": 2, "data_rows": 2, "data_preview": [{"name": "兼职", "value": 20}, {"name": "专职", "value": 12}], "annotation_source": "user", "plot_stats": {"family": "A", "x_col": "name", "x_cardinality": 2, "series": [{"name": "value", "max": {"value": 20, "at": "兼职"}, "min": {"value": 12, "at": "专职"}, "mean": 16.0, "sum": 32.0, "top3": [], "bottom3": []}]}}}
```
**Note `plot_stats` is present in the normal (non-dry-run) response** — there is no need for a separate `--dry-run` call to obtain it.

`data_rows` is the number of rows fed into plotting (after transform); `data_preview` is the first 10 rows of the final plotting data (the same data the renderer consumed, with NaN → null). Use them to sanity-check aggregation grain in-band — no need to open the HTML to verify values.

**Grain reconciliation triple** — `source_rows` (rows before transform) / `plotted_rows` (rows actually plotted) / `unique_entities` (distinct entities, from `--label-col` if given else the x column). Mechanical check for the "forgot to de-duplicate" trap: if each series' values sum to `source_rows` rather than `unique_entities`, the aggregation counted rows instead of entities.
Caveat: `plotted_rows == source_rows` 只说明"没有聚合"，而 scatter/boxplot/histogram/graph 等**本就以行为单位**，不聚合是正确行为——别把它当通用错误信号。真正的机械判据是 `advisories` 里的「疑似未聚合」（x 轴取值数 < 行数，且该图型要求"一个 x 对应一个 y"）。
On failure, prints a structured JSON and exits with code 1:
- **File-level errors** (file not found, parse error, etc.): error JSON printed to **stderr**.
- **Chart-level errors** (unsupported type, transform failure, axis field missing, etc.): result JSON with `"success": false` printed to **stdout**.

Both include a `details.suggestion` field for recovery. Other exceptions are printed as plain text to stderr.

**Multi-chart mode:** when generating **2+ charts**, pass `--charts` instead of a positional `chart_type`. The file is parsed once and all charts are generated in a single process (several times faster than repeated single-chart calls):

```bash
python {skill_base}/scripts/cli.py data.csv \
  --charts '[{"type":"bar","title":"Revenue","x_axis":"city","y_axis":["revenue"]},
             {"type":"line","title":"Trend","x_axis":"date","y_axis":["revenue","profit"]}]' \
  --output-dir "./output"
```

- Each item requires `type`; optional per-chart keys: `title`, `subtitle`, `x_axis`, `y_axis` (string or array), `transform_code` (per-chart), `label_col`, `color_by`, `annotation` (per-chart delivery text), `sort`, `y_scale` (boolean), `label`, `width`, `height`, `geo`, `geo_path` (per-chart map source, same semantics as `--geo`/`--geo-path`).
- A global `--transform-code` (optional) is applied to the DataFrame once before all charts; each chart may also carry its own `transform_code`.
- Output shape: `{"charts": [{...}, ...], "summary": {"total": N, "succeeded": M, "failed": K}}` — each item has the same structure as the single-chart `chart` object (including `success`, `html_path`, and `error.details.suggestion` on failure).
- Exit code 1 only when **all** charts fail; partial failure exits 0 with per-chart errors in the `charts` array.
- Invalid `--charts` JSON (malformed, empty array, or an item missing `type`) prints a `CHART_CONFIG_ERROR` JSON with a `suggestion` to stderr and exits 1.
- `--dry-run` 同样适用于多图模式：输出各图 `plot_stats`/`data_preview`（`dry_run: true`、`html_path` 为 null），不渲染不落盘。

**多文件并行**: 各文件配置已确定且互不依赖时，用 shell 后台并行（墙钟时间 ≈ 最慢一个文件）：

```bash
for f in data/*.xlsx; do
  python {skill_base}/scripts/cli.py "$f" --charts-file "cfg_$(basename "$f" .xlsx).json" --output-dir ./out &
done; wait
```

**Language behavior:** every piece of chart text — title, series names, tooltip labels, action buttons, scroll hint, footer, and the HTML `lang` attribute — is rendered in a single consistent language. By default that language follows the data; pass `--lang zh` or `--lang en` to override (e.g. when the user explicitly asks for an English chart on Chinese data).

**Overflow behavior:** when data points exceed the zoom threshold (default 15), the HTML enables ECharts `dataZoom` (slider + inside-drag) and a horizontal scrollbar on the chart container. Users can drag the slider, scroll horizontally, or click the fullscreen button to inspect all data points. No agent action needed.

**Inline title editing:** every generated HTML title is `contenteditable`. Users can double-click the title in the browser, type a new name, and press Enter — the ECharts chart title and the saved image filename update immediately. No backend round-trip needed.

**Visualization contracts（渲染层保证的视觉规范）:**
- **Zero baseline**: bar/stacked_bar（含 combo 的 bar 系列）在数据全非负时显式锁定 y 轴 `min: 0`——从 95 画到 100 会夸大差异，零基线是柱状图的准确性红线。数据含负值时不锁定，负值柱照常显示。line 默认含 0 基线，仅显式传 `--y-scale` 才允许非零基线；area 恒为零基线。
- **`advisories` field（建议性提醒，非错误）**: 当某张图成功生成、但存在更优呈现方式或存在agent必须知道的口径改动时，成功输出的 chart 对象里会出现 `advisories: [...]` 数组。`success` 仍为 `true`、`html_path` 正常落盘——**是否换图由 agent 按语境判断，禁止机械重试**（刻意不叫 `suggestion`，避免与错误恢复语义混淆）。触发点：

  | 触发条件 | 含义 | agent 该做什么 |
  |---|---|---|
  | 饼图类别数 > 8 | 人眼难以比较角度 | 改用 `bar --sort value`，或用 transform 聚合小类 |
  | `gauge`/`liquid` 未传 `--target` | `achievement`（达成率）不可计算，已置 `null` | 需要达成率就补 `--target <目标值>`；不需要就别在解读里提这个指标 |
  | `annotation` 未由 `--annotation` 提供 | 图表说明是代码模板填充的（`annotation_source: 'default'`） | 按交付规范补写解读并重新生成 |
  | **疑似未聚合**：x 轴取值数 < 行数，且该图型要求"一个 x 对应一个 y" | `plot_stats` 的 max/min/mean 是**行级**统计，不是该 x 维度的整体 | 要按 x 维度下结论就先聚合（`groupby`）；散点/箱线等以行为单位的图不会触发 |
  | 数值列部分单元格无法解析（成功率 ≥ 50% 时转数值） | 被丢弃的单元格数已在 advisory 中披露 | 核对列口径；要保留为分类就用 transform 显式处理 |
- **Heatmap gradient semantics**: 全非负数据（顺序型）用主题单色渐变（浅→深）；含负值数据（发散型，如相关矩阵 -1~1）自动切换双色渐变 + 中性中点，负值不再被错误地压进单色渐变。渐变取色随 `--theme` 走。
- **Title & subtitle（标题写结论）**: `--title` 应写结论而非名词短语——「营收同比增长 23%」优于「各月营收」；口径与范围信息（时间范围、筛选条件、数据来源）放 `--subtitle`，不要塞进标题。

---

## Data Profile（--profile）

```bash
python {skill_base}/scripts/cli.py <file_path> --profile [--skiprows N] [--header-row N] [--drop-rows 0,1] [--sheet NAME|INDEX] [--transform-code "<code>"]
# 等价入口（无 --transform-code）：python {skill_base}/scripts/data_parser.py <file_path> --profile
```

**它解决什么问题**：`chart_type` 是必填参数，而选型的依据（基数、分布、时间粒度、实体 vs 明细行）原本只能在选完型之后由 `plot_stats` 给出——先决策、后取证。`--profile` 把取证提到选型之前，且**不需要图表类型**。只读：不渲染、不写文件。

**何时用**：用户只给了数据、没说想看什么。**不要**在意图明确时为了走流程去跑它。

**输出结构**（只摆客观事实，不做语义判断）

| 字段 | 内容 | agent 用来判断什么 |
|---|---|---|
| `columns[].dtype` | pandas dtype（如 float64/object） | 数值列 vs 文本列（客观） |
| `columns[].cardinality` | 去重取值数 | 维度基数高低（基数高做维度柱子多，需自己权衡） |
| `columns[].sample` | 前 5 个非空值 | **一眼看出这列是什么**——学号/姓名/金额/日期 |
| `columns[].numeric` | min/max/mean/median/std/p25/p75/sum/zeros/negatives/outliers/monotonic（数值列才有） | 量纲、离群、是否需要归一化 |
| `columns[].time` | distinct/min/max/granularity/day\|month\|year（时间列才有） | 能否画趋势、按什么粒度聚合 |
| `columns[].top_values` | 文本列 top10 取值 + 计数 + 占比 | 分布是否均匀、有无长尾 |
| `grain` | `unique_keys` / `unique_key_pairs` / `note` | 一行是"一个实体"还是"一条明细"——决定要不要先去重/聚合 |
| `relations.correlations` | \|r\| ≥ 0.7 的数值列对（计算前已跳过有效样本 <3 或标准差为 0 的列对） | 值得画散点看关系 |
| `row_quality` | `suspicious_non_data_rows`（行位置 + 非空单元格样例）/ `empty_rows` | 定位残留的子表头/分值/单位等非数据行——**只披露不删除**，删哪行交给 agent |
| `signals[]` | 候选洞察信号（见下） | **出什么图的直接依据** |
| `advisories` | 解析期提醒（数值列降级、--drop-rows 丢行…） | 与图表输出的 `advisories` 同源 |

> profile **不产出** `role` 归类、`recommendations` 图型建议、`--emit-charts` 配置——哪列是 ID、哪列是维度、出什么图，是 agent 从 `columns` 的 dtype/样本/基数 + `signals` 自行判断的活，技能不代笔。

> **`--profile` 模式下白名单外的出图参数会报错**（如 `--x-axis`/`--title`/`--theme` 等，出图阶段才生效），不会再被静默忽略。白名单：`--skiprows` / `--header-row` / `--drop-rows` / `--sheet` / `--transform-code`。`--transform-code` 在画像阶段同样生效（取证前先清洗，避免 `grain`/`signals` 被脏帧污染）。

**signals 的 kind 与含义**

| kind | 触发条件 | headline 形态 |
|---|---|---|
| `trend` | 时间列 + 数值列（≥3 个时间点） | 「X 按 T 合计整体上升：341.3 → 358.1（+4.9%）」 |
| `divergent_category` | 某类别在时间上逆势变化（后段 vs 前段 ≤ −25% 且与整体反向） | 「地区=华南 逆势变化：−46.7%，而同期整体 +0.5%」 |
| `concentration` | 文本列（基数 ≤30） + 数值列 | 「销售额集中在头部：华东占 40.2%，前 3 占 86.6%」 |
| `outlier` | 数值列存在 IQR 离群值 | 「X 有 3 个离群值（IQR 法），极值 1560」 |
| `correlation` | 两数值列 \|r\| ≥ 0.7 | 「X 与 Y 强正相关（r=0.88）」 |
| `missing` | 列缺失率 ≥ 20% | 「列 X 缺失率 62%（15/24）」 |
| `constant` | 列只有 1 个取值 | 「列 X 只有 1 个取值，不携带区分信息」 |

> `divergent_category` 与 `trend` 优先级最高：整体均值最容易掩盖个体分化，也最常是"用户自己没想到"的发现。

**与 `plot_stats` 的分工**：profile 是**假设生成器**（出图前，基于全表），plot_stats 是**最终口径的事实**（出图后，基于实际绘制的数据）。两者冲突时以 `plot_stats` 为准——解读里引用的数字必须来自实际绘制的数据。

---

## Programmatic API

```python
from scripts.chart_generator import ChartGenerator

# Single chart — returns {'chart': {'success', 'html_path'/'error', ...}}
# lang=None auto-detects from data; pass 'zh'/'en' to override (only when user asks).
# theme: 'default' | 'classic' | 'dark'（默认 default）
result = ChartGenerator(output_dir="./output", theme="default").generate_chart(
    df=df, chart_type="bar", title="Regional Revenue",
    x_axis="region", y_axis=["revenue"], lang=None,
)

# Batch — returns {'charts': [...]}，每项结构与单图一致
result = ChartGenerator(output_dir="./output").generate_multi_charts(
    df=df,
    chart_configs=[
        {"type": "bar",  "title": "Regional Revenue", "x_axis": "region", "y_axis": ["revenue"]},
        {"type": "line", "title": "Monthly Trend",   "x_axis": "month",  "y_axis": ["revenue", "profit"]},
    ],
    lang=None,
)
```

失败时 `success` 为 `False`、`error` 为结构化错误字典，不抛异常——检查 `success` 决定下一步。

数据画像也有对应的编程入口（等价于 `--profile`）：

```python
from scripts import build_profile

prof = build_profile(df)   # 每列 dtype/基数/缺失/样本/统计 + 粒度 + signals + row_quality
# 选型（出什么图、哪列是维度/度量）由调用方从 prof 的客观事实自行判断
```

---

## 交付解读规范（完整）

技能负责算事实（`plot_stats` / `profile.signals`），**判断哪个发现值得说、并把它说清楚，是 agent 的活**。解读写完后用 `--annotation` 注入 HTML（图表下方「图表说明」区块）。

**解读要回答的是「这份数据里最值得注意的发现是什么」，不是复述图上有什么。** 结构为「结论 → 证据 → 边界」。

**事实锚点**（三处，均可引用）：`profile.signals`（出图前的候选洞察）、`plot_stats` / `data_preview`（实际绘制数据的统计，**最终口径以此为准**）、`assumptions` / `advisories`（CLI 的自动选择与口径提醒）。每个数字都必须能在其中找到出处——不得凭印象编造。注意 `plot_stats` 里的 `x_cardinality` 是 x 轴去重后的个数，写解读时要结合 x 列语义说清（如 x 是「姓名」则说「59 名学生」，而不是笼统的「59 个类别」）。

**流程**：意图不明确 → 先 `--profile` 挑出要讲的发现并据此定图型与聚合口径 → 带 `--annotation` 正式生成一次（正式输出已含 `plot_stats`，**不需要先跑 `--dry-run`**）→ 读 `plot_stats` 校对自己要讲的数字；需要换口径/换图就重生成第二次（1~10s，廉价可逆）。

**最小结构**（2~4 句，结论先行）：

1. **发现**：一句话给结论。写「华南 4 月起销售额腰斩，其余三地同期仍在增长」，不写「本图展示各地区月度销售额」。
2. **证据**：1~2 个具体数值 + 对应标签 + 出处（`plot_stats` 还是 `profile.signals`）。
3. **边界**：一句话交代口径（聚合方式、覆盖范围、样本量），并呼应 `assumptions`/`advisories` 里的假设——用户不同意任一假设，一句话就能重生成。

**硬边界**：

* 只陈述证据能支撑的事实，不夸大；"为什么 / 怎么办"可结合上下文发挥，但必须标注为推测，不能混进事实。
* `advisories` 出现「疑似未聚合」时先按提示聚合再写解读——否则引用的极值/均值是行级值而非维度整体。

**示例**（先 `--profile` 拿到 `divergent_category` 信号，再聚合出图并注入解读）：

```bash
# 透视后列名是「月份 + 各地区」，故轴要引用透视之后的列名
python {skill_base}/scripts/cli.py sales.csv line --x-axis 月份 --y-axis 华东 华南 华北 西南 \
  --transform-code "result = df.pivot_table(index='月份', columns='地区', values='销售额', aggfunc='sum').reset_index()" \
  --annotation "华南自 4 月起逆势下滑：后两月较前两月下降 46.7%，同期其余三地平均增长 18.6%；6 月华南仅 52.6，不到华东（156）的三分之一。口径：按月份合计销售额，覆盖 1—6 月共 24 行明细。" \
  --subtitle "1—6 月 · 按月份合计 · 来源 sales.csv"
```

---

## Transform Code Generation

When raw data doesn't match the target chart's input format, the LLM should generate pandas code following the template in [SKILL.md](../SKILL.md). The code is validated (keyword blacklist + AST whitelist) and executed in a sandbox before chart rendering.

**Safety rules enforced:**
- Only allowed variables: `df`, `pd`, `np`
- Must produce a `result` variable (pd.DataFrame)
- Do not modify `df` in-place
- No `import`, `open`, `exec`, `eval`, `os`, `sys`, `subprocess`, file I/O, or network calls
- Only safe builtins exposed (`len`, `range`, `sorted`, etc.); `open`/`exec`/`eval`/`__import__` removed
- File/network I/O blocked at the AST attribute level, including the whole `pd.io.*` / `np.lib.*` subtrees
- **Single namespace execution**: top-level assignments, lambdas, generator expressions and nested `def`s all see the same variables, so `k = 2; df.assign(x=lambda d: d['a'] * k)` works
- Execution timeout: 10 seconds
- Max recursion depth: 500

On violation, a `CodeValidationError` is raised with `details.violations` listing the offending keywords or AST nodes, and `details.reason` explaining why.

---

## FAQ — Common Data Issues

**Q: The Excel file has multi-row headers (merged cells, sub-headers). How do I parse it?**

First run `data_parser.py` without flags to inspect the raw layout:
```bash
python {skill_base}/scripts/data_parser.py data.xls
```
Look at the printed `head(5)` to count how many rows are headers. Then re-run with `--header-row N` (0-indexed) where row N is the one you want as column names:
```bash
python {skill_base}/scripts/data_parser.py data.xls --header-row 2
```
Rows above N are dropped. The value of N depends on the actual file — never assume a fixed number.

**Q: The Excel file has a two-row header plus a 分值/unit row (e.g. a main header row, a sub-header row, then a 满分/分值 row). `--header-row` can only pick one row as column names — how do I drop the leftover rows?**

`--header-row N` 只能决定「哪一行作列名」，无法同时保留主表头又合并子表头。用三段式：
```bash
# 1) 画像：读 row_quality.suspicious_non_data_rows 定位残留的非数据行位置
python {skill_base}/scripts/cli.py data.xls --profile
# 2) 按位置丢行（0-based，位置来自 row_quality，不要拍脑袋），或等价用 transform
python {skill_base}/scripts/cli.py data.xls --profile --drop-rows 0,1
#    等价：--transform-code "result = df.drop(index=[0,1])"
# 3) 重跑 --profile 确认干净（rows 变少、row_quality 零命中）再出图
```

**Q: After `--header-row`, the columns are still messy (e.g. `score_a`, `unnamed_3`). What next?**

Use `--transform-code` at chart generation to rename columns:
```bash
python {skill_base}/scripts/cli.py data.xls bar \
  --header-row 2 \
  --transform-code "result = df.rename(columns={'unnamed_0':'student_id','unnamed_1':'name','score_a':'homework','score_b':'exam'})" \
  --x-axis student_id --y-axis homework exam
```

**Q: The Excel file has multiple sheets. How do I pick one?**

```bash
python {skill_base}/scripts/data_parser.py data.xlsx --sheet "Sheet2"
# or by index
python {skill_base}/scripts/data_parser.py data.xlsx --sheet 1
```

**Q: Some cells are blank because of merged cells (only the first row of a group is filled).**

Forward-fill in transform code:
```bash
--transform-code "result = df.ffill()"
```

**Q: The data has leading note rows / blank rows before the actual header.**

Use `--skiprows N` to skip the first N rows, then read the next row as the header:
```bash
python {skill_base}/scripts/data_parser.py data.csv --skiprows 2
```

**Q: The chart shows mixed languages (e.g. Chinese data but English buttons, or vice versa).**

The CLI auto-detects the data language and renders all chart text (title, series names, tooltip, buttons, footer, HTML `lang`) in that language. If the auto-detection is wrong (e.g. a Chinese dataset with mostly English column names), force the language explicitly:
```bash
python {skill_base}/scripts/cli.py data.csv bar --lang zh
# or
python {skill_base}/scripts/cli.py data.csv bar --lang en
```
Only pass `--lang` when the user explicitly requests a specific language; otherwise let the data drive the choice.
