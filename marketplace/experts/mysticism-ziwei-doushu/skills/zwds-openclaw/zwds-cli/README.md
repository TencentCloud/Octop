# zwds-cli

紫微斗数排盘命令行工具：使用 npm 包 `iztro@2.5.0`，并内置简化真太阳时与中国大陆夏令时修正、时辰到 `time_index` 的映射（规则说明见上级目录 `reference.md`）。

## 环境

- Node.js **>= 18**

## 安装

```bash
cd openclaw-skill/zwds/zwds-cli
npm ci
```

（若无 lockfile 可用 `npm install`。）

## 用法

从标准输入读入 **一行 JSON**，向标准输出打印 **一行 JSON**。

```bash
# 推荐：用 UTF-8 文件作 stdin（避免 Windows PowerShell 管道把中文弄成 ???）
node src/index.js < examples/sample-payload.json
```

在 **PowerShell** 里若使用 `echo '...中文...' | node`，默认代码页常导致 `birth_place` 乱码、`meta` 出现 `place_not_in_database`。可改用：

- `cmd /c "node src/index.js < examples/sample-payload.json"`
- 或先 `chcp 65001`，并确保终端为 UTF-8

### 输入字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `birth_time` | 是 | ISO 8601 日期时间，如 `2000-08-16T06:00:00` 或带时区 |
| `gender` | 否 | `male` / `female`，缺省按 `male` |
| `birth_place` | 否 | 地名；有则按内置 `data/longitudes.json` 查经度并做真太阳时 |
| `longitude` | 否 | 数字经度；若提供则**优先**于 `birth_place` 解析 |
| `language` | 否 | 默认 `zh-CN`，与 iztro 一致 |

### 输出

成功：`{"success":true,"data":{...},"meta":{...}}`  
失败：`{"success":false,"error":"..."}`（退出码 1）

## 地名经度数据

`data/longitudes.json` 覆盖中国大陆地级行政区（及直辖市全市）中心经度；另含香港、澳门、台北及若干海外常用城市（后者为脚本内固定坐标，非 DataV）。名单来自 [modood/Administrative-divisions-of-China](https://github.com/modood/Administrative-divisions-of-China) 的 `cities.json`，大陆经度取自阿里云 DataV `areas_v3/bound/{adcode}.json` 中 `center[0]`。需联网重新生成大陆部分时：

```bash
npm run generate-longitudes
```

（约 300+ 次请求，耗时约 1～2 分钟；请勿高频重复执行。）

## 固定命盘存档（给读盘复用）

在 `zwds` 目录下生成 `fixtures/*.json`（含 `_fixture.input` 与完整 `success`/`data`/`meta`），避免每次对话重新排盘：

```bash
npm run save-fixture
# 或：node scripts/save-fixture.mjs <入参.json> <../fixtures/输出.json> "标题"
```

详见上级 `examples.md` 中「固定命盘（fixtures）」一节。

## 测试

```bash
npm test
```
