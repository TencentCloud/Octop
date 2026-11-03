# zwds 技能参考：排盘规则与输出说明

## iztro 官方文档

库 API、运限结构、链式调用等以官方为准：[iztro 快速开始](https://iztro.com/quick-start.html)。`zwds-cli` 固定依赖 `iztro@2.5.0`；文档站点版本号可能略新，以 npm 实际安装版本为准。

## 本技能内模块分工

| 逻辑 | 说明 | 实现位置 |
|------|------|----------|
| 安星与十二宫 | 使用 iztro 默认全书系安星 | `iztro@2.5.0` 的 `astro.bySolar` |
| 真太阳时 | 夏令时 + 相对东八区 120° 的经度修正 | `zwds-cli/src/solarTime.js` |
| 时辰索引 | 由真太阳时小时映射为 `time_index` | `zwds-cli/src/timeIndex.js` |
| 经度 | 静态地名表 + 可选显式经度 | `zwds-cli/data/longitudes.json` 与 stdin 的 `longitude` |

## 经度与地名表

- 本技能**不**在排盘时调用在线地理编码或外部数据库；经度仅来自随技能附带的 `longitudes.json` 或用户/Agent 在 JSON 里提供的 `longitude`。表内中国大陆地级数据可由维护者运行 `zwds-cli` 的 `npm run generate-longitudes` 离线再生成（依赖 modood 区划名单与阿里云 DataV 边界中心点，见该目录 `README.md`）。
- 地名不在表中时：经度默认为 **120.0**，并在 CLI 的 `meta.warnings` 中说明。
- **建议**：小地名或表外地点请让用户直接提供 **`longitude`（十进制度）**。

## 真太阳时与夏令时

- **钟表时间 − 夏令时（若在 1986–1991 中国夏令时段内则减 1 小时）+ (经度 − 120) × 4 分钟**，结果按日界折叠到 0–24 时。
- **不是**天文意义上的完整真太阳时（未加入均时差）。

## 子时与 `time_index`

本技能约定：

- 真太阳时小时为 **23** 或 **0** 时，`time_index = 0`（早子时）。
- 未使用 iztro 文档中的 `time_index = 12`（晚子时）分支。

若用户流派要求「晚子时换日」，可能与上述约定不一致，解盘时应向用户说明「本盘按技能内规则排定」。

## 输出 `data` 结构（概要）

CLI 将 iztro 返回的 camelCase 转为便于阅读的 snake_case，主要包括：

- `birth_info`：`solar_date`、`lunar_date`、`chinese_date`、`time`、`time_range`、`sign`、`zodiac`、`gender`、`birth_place`、`true_solar_time`（仅在有出生地且完成经度流程时为对象，否则 `null`）
- `soul_palace` / `body_palace`：含 `earthly_branch`、`soul` / `body`；命宫另有 `index`、`name`
- `five_elements_class`
- `palaces`：十二宫数组，每宫含 `major_stars`、`minor_stars`、`adjective_stars`、`decadal`、`ages`（小限）、`yearly`（流年命宫落该宫时的年龄列表）

### `yearly` 字段如何生成（重要）

- **不要**用 `horoscope(...).yearly.palaceNames` 的下标去对齐本命 `palaces` 下标：前者是流年盘的宫名旋转序列，与后者**不是**同一索引顺序。
- **正确做法**（与 `zwds-cli` 实现一致）：对阳历年 `Y` 取锚点日期 **`Y-02-04`（立春当日）**，调用 `chart.horoscope('Y-2-4')`，读取 `result.yearly.index`（本命十二宫下标），该下标对应宫位即该锚点下的**流年命宫**；令 `age = Y - 出生公历年`，把 `age` 记入该宫的 `yearly`。
- 锚点固定为立春当日口径；当前 JSON **不按小时细分立春交接时刻**，若用户问到当日交接前后差异，应说明边界或另行用具体时刻调用 iztro（不在 CLI JSON 内则不得编造）。

星曜 `mutagen` 空字符串在 JSON 中为 `null`。

## `meta` 字段（CLI 扩展）

便于排错与审计：

- `iztro_version`
- `time_index`
- `longitude_resolution`：`source` 为 `input` | `database` | `default`
- `warnings`：字符串数组

解盘时**以 `data` 为准**；`meta` 用于判断经度是否降级。
