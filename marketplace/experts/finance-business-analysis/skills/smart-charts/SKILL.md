---
name: smart-charts
version: 8.4.0
display_name: 智能图表
display_name_en: Smart Charts

description: "将数据文件（CSV/TSV/TXT/XLSX/XLS/JSON）转化为独立交互式 ECharts HTML 图表——32 类图表、3 套主题，全离线无需 CDN。出图前可先取数据画像（--profile：每列 dtype/基数/缺失/样本/统计、实体粒度、候选洞察信号、疑似非数据行），让 agent 在用户没说想看什么时自己读懂数据并决定出什么图——哪列是 ID、哪列是维度、出什么图，全部由 agent 从画像的客观事实自行判断，技能不代笔；每张图内置事实卡（plot_stats + data_preview），其数值是解读时唯一可引用的数字。本技能负责出图与算事实，不产出书面报告或叙事文档。触发：用户提供或指向表格数据文件并要求出图；提到「画图/出图/可视化/生成图表/generate a chart/make a graph」；想把表格渲染成交互式 HTML 图表。不触发：要的是书面报告、叙事分析或幻灯片；没有数据文件；需要后端的仪表盘；图片/音频/视频等非表格内容。"
description_en: "Turn a data file (CSV/TSV/TXT/XLSX/XLS/JSON) into standalone interactive ECharts HTML charts - 32 chart types, 3 themes, fully offline with no CDN. A data profile (--profile: per-column dtype, cardinality, missingness, samples, statistics, entity grain, candidate insight signals, suspected non-data rows) lets the agent read the data itself and decide what to plot when the user has no stated intent - the agent decides which column is an ID, a dimension, or a measure, and which chart to draw, from the profile's objective facts; each chart ships with an embedded fact sheet (plot_stats plus data_preview) whose numbers are the only values an agent may quote in its caption. This skill produces charts and facts, not written reports or narrative documents. TRIGGER: user supplies or points to a tabular data file and wants a chart; asks to 画图/出图/可视化/生成图表/generate a chart/make a graph; wants a table rendered as an interactive HTML chart. DO-NOT-TRIGGER: wants a written report, narrative analysis or slide deck; no data file is supplied; dashboards needing a backend; images, audio, video or other non-tabular content."
license: MIT
compatibility: "Python 3.11+; requires pandas>=3.0.1,<4, numpy>=2.4.3,<3, openpyxl>=3.1.5,<4, xlrd>=2.0.1,<3; no network access needed (ECharts JS bundled offline); install with: pip install -r requirements.txt; verify with: python scripts/cli.py --doctor"
metadata:
  author: smart-charts
  input_formats: ["csv", "tsv", "txt", "xlsx", "xls", "json"]
  output_format: html
  sandbox: "LLM-generated transform code runs in a restricted sandbox (keyword blacklist + AST whitelist + safe builtins); file and network I/O are blocked at the attribute and module-path level. No user confirmation required."
---

# Smart Charts

> 将数据文件（CSV/Excel/JSON）转化为交互式 ECharts HTML。支持 32 种图表类型、3 套主题预设（default/classic/dark）、多文件合并、LLM 数据转换代码（沙箱执行）。
> CLI 全参数、flags 语义、多图/多文件细节、能力边界、错误码表、交付解读完整规范、FAQ 见 [REFERENCE.md](./references/REFERENCE.md)。

***

## Activation Triggers

**TRIGGER**

* 用户提供 / 指向一个表格数据文件，要求出图、可视化、生成图表
* 用户提到「画图」「出图」「生成图表」「数据可视化」「chart」「visualization」

**DO-NOT-TRIGGER**（命中任一条请改推其他技能，不要硬接）

* 要的是带结论叙事的报告/周报/复盘/汇报文档 → 用报告类技能（本技能出图 + 可溯源事实 + 候选洞察信号，不写叙事文档）
* 没有数据文件（纯文字描述、口头想法）
* 需要后端的 dashboard、图片/音频/视频等非表格内容
* 地图渲染：内置中国省级（`china`，含港澳台）与世界国家级（`world`，英文国名精确匹配）；市级/区县级等更细区域需用户自备 GeoJSON 文件（`--geo-path`），本技能不代为下载

***

## 工作流（先画像，后选型）

`chart_type` 是 CLI 必填参数，而选型的依据（基数、分布、粒度、实体 vs 明细）本来只在选完型之后的 `plot_stats` 里才有——先决策、后取证会让选型变成瞎猜。所以按用户有没有说清意图分两条路：

**A. 用户意图明确**（"对比各地区销售额""看月度趋势""占比构成"）
→ 直接按选型表挑图型 + 轴 + 聚合口径，出图。**不要**为了走流程去跑 profile。若数据撑不起该意图（要趋势却没有时间列、要占比却全是明细行），如实说明并给出可行替代（例如把"趋势"换成按类别对比），不要硬画。

**B. 用户只给了数据，没说想看什么**（最高频）→ 两条命令：

1. `python {skill_base}/scripts/cli.py <file> --profile`（一条命令；只读不渲染不落盘），拿到：每列的 dtype/基数/缺失率/样本/统计、实体粒度（`grain`）、候选洞察信号（`signals`）、疑似非数据行（`row_quality`）。
2. **由你决定**出哪 1~3 张图：读 `columns` 的 dtype/样本/基数自行判断哪列是 ID、哪列是维度、哪列是度量，结合 `signals` 挑出值得讲的发现，据此定图型 + 轴 + 聚合口径，直接出图（`--transform-code` 聚合/透视 + `--title` 结论 + `--annotation` 解读）。交付时说明"为什么是这几张"。

> `signals` 里最值得优先出图的是 `divergent_category`（某类别逆势变化）与 `trend`：它们最容易被整体均值掩盖，也正是"用户自己没想到但一看就懂"的发现。

> **MUST NOT** 把选型责任推回给用户（"你想看趋势、对比还是占比？"）——哪列是 ID、哪列是维度、出什么图，是 agent 从画像客观事实自行判断的活，不是菜单让用户挑。

***

## 契约（8 条，MUST）

1. 列名解析后会被规范化：转小写、特殊字符→`_`（如 `总学时`→`总_学时`），中文保留；`--x-axis`/`--y-axis`/transform 必须引用规范化后的列名
2. transform 沙箱：可用变量仅 `df`/`pd`/`np`（`np.select`/`np.where` 可用），支持多语句（`;` 或换行分隔），必须产出名为 `result` 的 DataFrame；禁止 import/open/try/类定义（黑名单 + AST 白名单强制校验，违规返回带 `suggestion` 的错误）
3. pie/bar/treemap/funnel 等按「1 个分类列 + 1 个数值列」读数据（文档里的 `name`/`value` 指**角色**，不是要求列名叫这个——保留原列名可读性好，也不必多写一次 rename）；分类频次图先用 transform 聚合成这两列，再用 `--x-axis <分类列> --y-axis <数值列>` 指定
4. 成功时 stdout：`success`/`html_path`/`chart_type`/`title`/`source_rows`/`plotted_rows`/`unique_entities`/`data_rows`/`data_preview`（绘图数据前 10 行，口径校对用）/`annotation_source`/`plot_stats`（绘图数据完整统计摘要，写解读用；32 类全覆盖）；`assumptions`（CLI 代做的自动选择）与 `advisories`（口径提醒）仅在非空时出现——**没有该字段表示"本次无自动选择/无提醒"**，不是缺失
5. **校对口径直接读 stdout 的 `data_preview` + `data_rows`，不要打开 HTML 去搜数据**——`data_preview` 是渲染帧中 **x/y 列的前 10 行**（与渲染同源同帧，但不含未参与绘图的辅助列）；`data_rows` 是实际绘图行数。需要核对 transform 产出的辅助列时，用 transform 内 `print(df.columns)`/`print(df.head())`（走 stderr、不污染 stdout）或另行 `--dry-run`
6. **聚合口径对账读 `source_rows` / `plotted_rows` / `unique_entities`**：`source_rows`=transform 前原始行数，`plotted_rows`=实际绘图行数，`unique_entities`=去重实体数（有 `--label-col` 取该列，否则取 x 列）。**注意**：`plotted_rows == source_rows` 只说明"没有聚合"，而散点/箱线等以行为单位的图本来就不该聚合——判据要配合图型语义使用，别把它当通用错误信号。真正的机械判据是 `advisories` 里的「疑似未聚合」：x 轴取值数 < 行数且该图型要求"一个 x 对应一个 y"，此时 `plot_stats` 的 max/min/mean 是行级而非该维度整体
7. **意图不明确时 MUST 先跑 `--profile`**（`python {skill_base}/scripts/cli.py <file> --profile`，不需要图表类型）。它返回每列的 dtype/基数/缺失率/样本/统计、`grain`、`signals`、`row_quality`——这些是**客观事实**，是选型的依据；哪列是 ID、哪列是维度、出什么图，由你从这些事实自行判断，profile 不代笔（不产出 role 归类或图型建议）
8. **交付前 MUST 读 `assumptions` + `advisories`**：`assumptions` 是 CLI 替你做的自动选择（x/y 自动取值等），`advisories` 是"生成成功但你可能想要另一种口径"的提醒（疑似未聚合、饼图类别过多、数值列部分降级…）。两者都要在交付语里呼应——用户不同意的假设，一句话就能重生成

***

## 黄金示例（模板，复制改列名）

**1 分类频次 → pie/bar**（最高频场景）：

```bash
python {skill_base}/scripts/cli.py data.xlsx bar --title "标题" --output-dir ./out \
  --x-axis name --y-axis value \
  --transform-code "result = df['类别列'].fillna('未标注').value_counts().rename_axis('name').reset_index(name='value')"
```

（gauge/liquid 想出"达成率"时必须补 `--target <目标值>`；缺它 `plot_stats.achievement` 为 `null`。环境自查用 `python {skill_base}/scripts/cli.py --doctor`。）

**2 多图批量 + 防转义坑**（≥2 张图 MUST 批量；transform 含中文/引号时不要直接在 shell 传 `--charts`，写进 JSON 文件用 `--charts-file`）：

```bash
python {skill_base}/scripts/cli.py data.xlsx --sheet "Sheet1" \
  --charts-file charts.json --output-dir ./out
```

`charts.json` 每项：`type`（必填）+ `title`/`x_axis`/`y_axis`（字符串或数组）/`transform_code`（单图级）/`label_col`/`color_by`/`annotation`。配置由 **agent 自己写**——根据 `--profile` 的客观事实（dtype/基数/样本/signals）决定出什么图、配什么轴。

**3 分组聚合 → bar**：

```bash
python {skill_base}/scripts/cli.py data.xlsx bar --title "标题" --output-dir ./out \
  --x-axis 分组列 --y-axis 数值列 \
  --transform-code "result = df.groupby('分组列')['数值列'].sum().reset_index()"
```

（`reset_index()` 后列名仍是「分组列/数值列」，轴直接引用即可；改成 `rename_axis('name')+reset_index(name='value')` 也可以，但轴要跟着改成 `name`/`value`——二者必须一致。）

**口径陷阱**：聚合前想清楚「按数据行 vs 按去重实体」——统计实体属性（如每门课程的学时结构）先 `drop_duplicates`；生成后对照 `data_preview` 检查（若各行 value 之和等于原始行数而非实体数，就是忘了去重）。

***

## Hard Constraints (MUST follow)

1. **MUST 走 CLI 工作流**（`data_parser.py` → `cli.py`），不要自写脚本替代。
2. **脏表头 MUST 用 CLI flags**（`--skiprows N` / `--header-row N` / `--drop-rows 0,1` / `--sheet`，语义见 REFERENCE.md），N 由实际数据决定（先无 flags 跑一次看原始布局），不得拍脑袋固定。**注**：`--skiprows N` 与 `--header-row N` 是同一行为（都是"第 N 行作表头、其上行丢弃"），二选一即可，不要把 N 想成两个不同的决策；推荐统一用 `--header-row`。
   - **两行表头 + 分值行/子表头行**（`--header-row N` 只能选「哪一行作列名」，无法既保留主表头又合并子表头）走**三段式**：① 跑 `--profile`，读 `row_quality.suspicious_non_data_rows`（或 `advisories`）定位残留的非数据行位置；② 用 `--drop-rows 0,1`（位置由 profile 给出，不要拍脑袋）或 `--transform-code "result = df.drop(index=[0,1])"` 丢行；③ **重跑 `--profile` 确认干净**（`rows` 变少、`row_quality` 零命中）再出图。
3. **列重命名/重塑/聚合 MUST 用 `--transform-code`**。解析层只解决"哪行是表头"，其余清洗归 transform。
4. **轴名/系列名要改显示名，MUST 用 `--x-name`/`--y-name`/`--series-name(s)`，不要靠改列名**。改列名会同时改轴名和系列名（两者都绑定列名），且原本写死默认文本的图（heatmap「热力图」/gauge「仪表盘」/sankey「桑基图」等）改列名也改不了系列名。显示名才是唯一干净的入口：`--x-name` 改 x 轴、`--y-name` 改 y 轴、`--series-name`（单）或 `--series-names`（多，按可见系列顺序）改系列名。
5. **MUST report unsupported scenarios**: CLI 确实不支持的（如嵌套 JSON 超过 1 层），先向用户说明并给建议，不得静默绕过。
6. **MUST NOT** 在生成代码中硬编码绝对路径；运行时解析路径。
7. **不要主动传 `--lang`**；CLI 自动跟随数据语言。仅当用户明确要求某种语言时才传。
8. **MUST 附解读交付**：交付图表时必须附由 LLM 写的文字解读，并通过 `--annotation` 注入 HTML（见下方「交付解读规范」），不得只交付裸图。成功输出里的 `annotation_source` 会标明解读来源：`'user'`=你传的，`'default'`=代码用模板填充的（此时输出还会挂 advisory）——**交付前确认它是 `user'`**。
9. **MUST 显式传 `--output-dir`**，指向用户可见的目录（如 `./out`、桌面目录、当前工作目录下的显式子目录）。默认值 `./smart_charts_output` 会随当前工作目录落盘，用户不易发现产物。
10. **`{skill_base}` = 技能根目录**（含 `SKILL.md`）。若当前宿主不替换该占位符，先定位一次再改成绝对路径使用：`SKILL_DIR=$(dirname "$(find "$HOME" -maxdepth 6 -type f -path "*smart-charts/scripts/cli.py" | head -1)")/..`，后续用 `$SKILL_DIR/scripts/cli.py`。不要凭印象拼路径。

***

## 默认策略（不向用户确认）

生成图表是廉价可逆动作（重生成 1-10s，零外部副作用）。图表类型、多文件合并策略、取值口径均由 agent 内部决定，不打断用户——**依据**是：用户明确意图（A 分支）或 `--profile` 给出的客观事实（dtype/基数/样本/signals，B 分支）。

**事后审阅代替事前确认**：交付语中显式列出本次关键假设（如"选了 line，因 month 是时间序列列""多文件按列名完全相同走纵向拼接，已注入 source_file 列""销量按金额口径"）。用户不同意任一假设，可一句话要求换口径/换类型/换合并方式重生成。

**唯一必须的用户介入点**：见 Exit Criteria 的"仍失败"分支。

***

## Exit Criteria（机械可判定）

* ✅ **成功**: stdout 为 `{"chart": {"success": true, ...}}`（多图模式为 `{"charts": [...], "summary": ...}`），且 `html_path` 指向的文件存在且非空 → 用同一 stdout 的 `data_preview`/`data_rows`/`plotted_rows`/`unique_entities` 校对聚合口径（按行 vs 按去重实体），确认无误后附文字解读交付。
* ℹ️ `--dry-run` 不算交付：`html_path` 为 null、不落盘，仅用于试错列名或试聚合脚本。**写解读不需要先跑它**——正式输出已带 `plot_stats`。
* ❌ **失败**: `success: false` 或 exit code 1 → 读 `error.details.suggestion`，修正后重试；**同一环节最多重试 2 次**。
* 🛑 **仍失败（唯一必须的用户介入点）**: 把 `code_name`、`suggestion`、已尝试的修复如实报告用户并给出建议，等待用户决策。**不得**静默改用自写脚本兜底（违反约束 1/4）。

***

## Chart Types 选型表

选型前核对 Required Format；不匹配则用 transform 代码适配。

> **量纲提示**：heatmap / boxplot / radar 等多列图表，若各列量纲差异大（如满分 10 与满分 100 混合），需先用 transform 代码归一化，否则小量纲列会被大量纲列主导。

| ID | Best For | Trigger Keywords | y_axis | Required DataFrame Format |
|----|----------|------------------|:------:|---------------------------|
| `line` | Time-series trends | trend, change, over time, 趋势, 变化, 走势 | 1~N | 1 category/time + 1~N numeric |
| `bar` | Category comparison | compare, rank, difference, 对比, 比较, 排名, 差异 | 1~N | 1 category + 1~N numeric |
| `area` | Cumulative change | cumulative, change, 累计, 变化 | 1~N | 1 category/time + 1~N numeric |
| `pie` | Composition/share | share, composition, proportion, 占比, 构成, 比例 | 1 | 1 name + 1 value |
| `scatter` | Correlation | correlation, relationship, scatter, 相关, 关系, 散点 | 1 | 2 numeric, or 1 category + 1 numeric |
| `radar` | Multi-dimension comparison | multi-dimension, comprehensive, radar, 多维, 综合, 雷达 | N | 1 indicator + N numeric |
| `heatmap` | Density/cross-tab | density, cross, matrix, heatmap, 密度, 交叉, 矩阵, 热力 | 1~N | 1 category + 1~N numeric（每列是一"列"矩阵；交叉表先用 pivot_table 摊成列） |
| `treemap` | Hierarchical proportion | hierarchy, proportion, nested, 层级, 占比, 嵌套 | 1 | 1 name + 1 value |
| `graph` | Entity relationships | relationship, network, topology, 关系, 网络, 拓扑 | special | source + target (+ value) |
| `boxplot` | Distribution/outliers | distribution, outlier, quartile, 分布, 离群, 四分位 | N | N numeric |
| `waterfall` | Incremental change | increment, change, waterfall, 增量, 变化, 瀑布 | 1 | 1 category + 1 numeric (increments) |
| `gauge` | KPI progress | progress, kpi, achievement, 进度, KPI, 达成 | 1 | 1 numeric (mean used) |
| `sankey` | Flow transfer | flow, transfer, sankey, 流向, 流量, 转移 | special | source + target + value |
| `funnel` | Conversion rate | conversion, funnel, churn, 转化, 漏斗, 流失 | 1 | 1 name + 1 value |
| `sunburst` | Single-level proportion | proportion, sunburst, 占比, 比例 | 1 | 1 name + 1 value |
| `wordcloud` | Frequency/keywords | word frequency, keywords, text, 词频, 关键词, 词云 | 1 | 1 name + 1 value |
| `histogram` | Distribution shape | distribution, histogram, 分布, 直方图 | 1 | 1 numeric column（`--x-axis` 或 `--y-axis` 均可，数值型 `--x-axis` 优先） |
| `stacked_bar` | Composition over categories | composition, stacked, 堆叠, 构成 | 1~N | 1 category + 1~N numeric |
| `bubble` | 3-variable correlation | bubble, 3-variable, 气泡, 三变量 | 2 | 2 numeric + 1 size |
| `pareto` | 80/20 analysis | pareto, 80/20, 帕累托, 二八 | 1 | 1 category + 1 numeric |
| `combo` | Dual-axis comparison | dual-axis, combo, 双轴, 组合 | 1~N | 1 category + 1 bar + 1~N line |
| `venn` | Set overlap (2~3 sets) | overlap, intersection, venn, 交集, 重叠, 韦恩 | 1 | 1 name + 1 value；交集行命名为 `A∩B`（分隔符：∩ & + × 与） |
| `mindmap` | Hierarchical ideas | mind map, outline, 思维导图, 脑图, 大纲 | 1 | 1 parent + 1 child（分类列） |
| `orgchart` | Organization structure | org chart, hierarchy, 组织架构, 汇报关系, 层级 | 1 | 1 parent + 1 child（分类列） |
| `liquid` | Percentage/progress | liquid, progress, percent, 水波, 进度, 百分比, 完成率 | 1 | 1 numeric (mean used) |
| `spreadsheet` | Raw table / pivot display | table, detail, spreadsheet, 表格, 明细, 清单 | N | 任意列（x/y 可选地筛选显示列；聚合用 transform） |
| `map` | Geo choropleth | map, region, province, geo, 地图, 地区, 省份, 地域 | 1 | 1 region name + 1 numeric（默认中国省级；`--geo`/`--geo-path` 换任意区域） |
| `lines` | Route/migration on map | route, migration, flow map, 航线, 迁徙, 流向地图 | special | source + target (+ value)（默认省级名称；`--geo`/`--geo-path` 换任意区域） |
| `effect_scatter` | Animated scatter highlights | ripple, highlight, scatter animation, 涟漪散点, 动态散点 | 1 | 2 numeric, or 1 category + 1 numeric |
| `calendar` | Daily heatmap (GitHub-style) | calendar heatmap, daily activity, 日历热力, 每日活跃 | 1 | 1 date + 1 numeric |
| `pictorial_bar` | Symbolic/iconic bars | pictorial, icon bar, symbol bar, 象形柱, 图标柱 | 1~N | 1 category + 1~N numeric |
| `theme_river` | Theme evolution over time | theme river, event evolution, 主题河流, 事件演化 | 1~N | 1 date + 1~N numeric |

> **`gauge`/`liquid` 要出"达成率"必须传 `--target <目标值>`**：`achievement` = mean ÷ target。不传时该字段为 `null`（自动推断的量程不是业务目标，比值无业务含义），且输出会挂 advisory。

**y_axis cardinality key**: `1` = only first column used; `1~N` = each column becomes a series; `N` = multiple columns expected; `2` = exactly 2 numeric columns required; `special` = 关系图（graph/sankey/lines）由 `--x-axis`（source）+ `--y-axis`（target，可选 value）**显式指定**，不做列名词表自动检测。scatter/bubble/boxplot 的身份列由 `--label-col` 显式指定，不传则不显示身份（tooltip 只显示坐标值）。

***

## Transform Code Contract

契约（由沙箱强制，违反会收到带 `suggestion` 的错误，按提示修正即可）：

* 可用变量只有 `df`, `pd`, `np`；必须产出名为 `result` 的 `pd.DataFrame`
* 不要原地修改 `df`（用 `df.copy()` 或链式操作）
* 原始数据已匹配目标格式时，不传 `--transform-code`

**Common transform patterns:**

* Long→multi-series: `result = df.pivot_table(index='<time>', columns='<category>', values='<value>', aggfunc='sum').reset_index()`
* Long→pie (filter): `result = df[df['metric']=='revenue'][['category','value']].rename(columns={'category':'name'})`
* Wide→long: `result = df.melt(id_vars=['date'], var_name='name', value_name='value')`
* Aggregate→bar: `result = df.groupby('<category>')['<value>'].sum().reset_index()`
* Rename columns: `result = df.rename(columns={'来源':'source','去向':'target','金额':'value'})`
* Compute delta→waterfall: `tmp = df.copy(); tmp['delta'] = tmp['profit'].diff().fillna(tmp['profit'].iloc[0]); result = tmp[['month','delta']]`
* Rename messy/uninformative column names (after `--header-row` leaves columns like `score_a`, `unnamed_3`): `result = df.rename(columns={'unnamed_0':'student_id','unnamed_1':'name','score_a':'homework_score','score_b':'exam_score'})`
* Forward-fill merged cells (when only the first row of a group is populated): `result = df.ffill()`
* Drop non-data rows (位置由 `--profile` 的 `row_quality.suspicious_non_data_rows` 给出，不要拍脑袋；等价于出图前用 `--drop-rows` 落盘，但 transform 里更直观): `result = df.drop(index=[0,1])`
* Combine sub-headers into a single column name (when `--header-row N` flattens one row but loses context): `result = df.rename(columns={c: f'{c}_score' for c in df.columns if c not in ['student_id','name']})`

> **核对清洗结果的常规动作**：transform 里的 `print(df.head())` / `print(df.columns)` 会被重定向到 **stderr**，不污染 stdout 的 JSON 契约——所以可以直接在 transform 里 `print` 检查丢行/聚合/重命名后的结果，把它当成清洗后的常规核对手段（不必只在报错时才用）。

***

## 交付解读规范（Delivery Annotation）

交付每张图表时，必须附一段**由 LLM 写的文字解读**（不是模板文字），再用 `--annotation` 注入 HTML（图表下方「图表说明」区块）。

**解读要回答的是「这份数据里最值得注意的发现是什么」，不是复述图上有什么。** 技能负责算事实，判断哪个发现值得说、并把它说清楚，是 agent 的活——所以解读的结构是「结论 → 证据 → 边界」，不是「图是什么 → 最大值是多少」。

**可引用的事实源（三处）**：

* `profile.signals` —— 出图前的候选洞察（趋势方向与涨跌幅、头部集中度、逆势类别、离群值、强相关对）
* `plot_stats` / `data_preview` —— 该图**实际绘制数据**的统计（最终口径以此为准）
* `assumptions` / `advisories` —— CLI 替你做的自动选择与口径提醒

**标准流程**：

1. 意图不明确时先 `--profile`，从 `signals` 里挑出要讲的发现，据此定图型与聚合口径（见「工作流」B 分支）。
2. 带 `--annotation "解读文字"` 正式生成一次。**正式输出本身已包含 `plot_stats` 与 `data_preview`**，无需先跑 `--dry-run` 取数。
3. 读该次 `plot_stats` 校对自己要讲的数字；**解读写完再回看**：若发现需要换口径/换图，才重新生成第二次——重生成是廉价可逆动作（1~10s）。

> `--dry-run` 只在"想先看数、明确不落盘"时才用（如试错列名、试聚合脚本）。把它当成写解读的前置必选步骤会让调用量翻倍且毫无收益。

**解读最小结构（2~4 句，结论先行）**：

1. **发现**：一句话给结论。写「华南 4 月起销售额腰斩，其余三地同期仍增长」，不写「本图展示各地区月度销售额」。
2. **证据**：1~2 个具体数值 + 对应标签 + 出处（来自 `plot_stats` 还是 `profile.signals`）。
3. **边界**：一句话交代口径（聚合方式、覆盖范围、样本量），并呼应 `assumptions`/`advisories` 里的假设——用户不同意任一假设，一句话就能重生成。

**标题写结论，副标题补口径**：`--title` 用结论式短语（主谓宾+数值，如「营收同比增长 23%」），数字直接取自 `plot_stats`，不用名词短语（「各月营收」）；时间范围/筛选条件/数据来源等上下文放 `--subtitle`，不塞进标题。

**硬边界**：

* 解读的每个数字都必须能在 `plot_stats`/`data_preview`/`profile.signals` 里找到出处——不得凭印象编造；`x_cardinality` 是去重个数，按 x 列语义表述（x 是「姓名」则说「59 名学生」而非「59 个类别」）。
* 只陈述证据能支撑的事实；"为什么/怎么办"可结合上下文发挥，但必须标注为推测，不能混进事实。
* **`advisories` 出现「疑似未聚合」时，先按提示聚合再写解读**——否则你引用的极值/均值是行级值，不是该维度的整体，结论会错（实测：月×地区明细画折线，`plot_stats` 报的"6月最高 156"其实只是华东一地）。

完整规范与示例见 REFERENCE.md。
