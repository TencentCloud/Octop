# 本地 HTML 一键上云（.aipage 导入）

本文档定义「把本地 HTML 打包成 `.aipage` 并上传到腾讯文档」的标准工作流，
适用场景：

- 上游 skill（如 `smart-page`）只产出 HTML 目录 / 单文件，**打包与导入由本 skill 接手完成**。
- 用户直接给出本地 `.html` 路径并要求「上传 / 导入 / 上云 / 发布到腾讯文档」。

> ⚠️ 上游 skill **禁止**自行实现 `prepare-pack` / `pack` / 拼接 `pre_import + async_import`
> 的逻辑；必须改为调用本工作流。

---

## 触发条件

任一满足即触发：

1. 用户输入包含本地 `.html` 文件路径，且语义包含「上传 / 导入 / 上云 / 发布 / 同步到腾讯文档」。
2. 上游 skill（典型为 `smart-page`）显式声明「HTML 已生成，请用 tencent-docs 打包并导入」，
   并提供：
   - 单文件入口：`html_path`（推荐）
   - 或目录入口：`html_dir`（目录内必须有 `index.html`，或唯一一个 `*.html`）
   - 可选：`title`（缺省时自动从 `<title>` 标签或文件名推导）

---

## 标准链路（4 步）

### Step 1：本地打包成 `.aipage`

调用本 skill 自带的脚本 `aipage_pack.js`（**纯 Node.js，零 npm 依赖，跨平台**：macOS / Linux / Windows 原生 cmd / PowerShell 直接可用，不需要 bash / Git Bash / WSL）：

```bash
# 单文件模式（最常见）
node scripts_path/aipage_pack.js --html "<html_path>" [--title "<title>"]

# 目录模式（含 assets/ 等附属资源时）
node scripts_path/aipage_pack.js --dir  "<html_dir>"  [--title "<title>"]
```

> `scripts_path` 为本 SKILL 文件所在目录，例如：
> `backend/application/open/mcpserver/tencent-docs/aipage_pack.js`
>
> 运行环境要求：Node.js >= 14（同 `ocr.js`）。Windows 上可直接 `node aipage_pack.js ...`。

脚本以稳定格式输出，可直接 `grep` / 正则解析：

```
AIPAGE_PATH=/tmp/xxx.aipage
AIPAGE_SIZE=123456
AIPAGE_MD5=abcd1234...
AIPAGE_TITLE=立项方案
```

退出码：`0` 成功；`1` 参数错；`2` 源 HTML 不合法；`3` 打包失败 / 工具缺失。

### Step 2：调用 `manage.pre_import` 获取 COS 上传链接

```bash
mcporter call "tencent-docs" "manage.pre_import" --args \
  '{"file_name": "<basename(AIPAGE_PATH)>", "file_size": <AIPAGE_SIZE>, "file_md5": "<AIPAGE_MD5>"}'
```

返回字段中需要：`upload_url`、`file_key`、`task_id`。

> 也可以直接复用 `import_file.sh`（位于本 skill 同目录），它已封装 Step 1 之后的
> 「pre_import + PUT 上传 COS」两步，输出 `IMPORT_READY` + 关键字段。
> 推荐写法：先用 `node aipage_pack.js` 打出 `.aipage`，再 `bash import_file.sh <AIPAGE_PATH>`。

### Step 3：PUT 上传到 COS

```bash
curl -sS -X PUT \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@<AIPAGE_PATH>" \
  "<upload_url>"
```

HTTP 2xx 视为上传成功。

### Step 4：触发异步导入并轮询

```bash
# 触发
mcporter call "tencent-docs" "manage.async_import" --args \
  '{"task_id":"<task_id>","file_key":"<file_key>","file_name":"<file_name>","file_md5":"<AIPAGE_MD5>","file_size":<AIPAGE_SIZE>}'

# 轮询（建议每 3s 一次，最多 60s）
mcporter call "tencent-docs" "manage.import_progress" --args '{"task_id":"<task_id>"}'
```

`progress=100` 时视为成功，从返回中拿 `file_id` / `file_url`，必要时用
`?_fid=<file_id>` 拼接到 `file_url`。

---

## 推荐执行模板（agent 内复用）

```bash
# ① 打包（跨平台：macOS / Linux / Windows 通用，零依赖）
PACK_OUT=$(node <skill_dir>/aipage_pack.js --html "$HTML_PATH" --title "$TITLE")
AIPAGE_PATH=$(echo "$PACK_OUT" | awk -F= '/^AIPAGE_PATH=/{print $2}')
AIPAGE_SIZE=$(echo "$PACK_OUT" | awk -F= '/^AIPAGE_SIZE=/{print $2}')
AIPAGE_MD5=$( echo "$PACK_OUT" | awk -F= '/^AIPAGE_MD5=/{print $2}')

# ② + ③ pre_import + PUT（直接复用 import_file.sh）
IMPORT_OUT=$(bash <skill_dir>/import_file.sh "$AIPAGE_PATH")
TASK_ID=$( echo "$IMPORT_OUT" | awk -F: '/^TASK_ID:/{print $2}')
FILE_KEY=$(echo "$IMPORT_OUT" | awk -F: '/^FILE_KEY:/{print $2}')
FILE_NAME=$(echo "$IMPORT_OUT" | awk -F: '/^FILE_NAME:/{print $2}')

# ④ async_import + 轮询
mcporter call "tencent-docs" "manage.async_import" --args \
  "{\"task_id\":\"$TASK_ID\",\"file_key\":\"$FILE_KEY\",\"file_name\":\"$FILE_NAME\",\"file_md5\":\"$AIPAGE_MD5\",\"file_size\":$AIPAGE_SIZE}"
# 然后轮询 manage.import_progress 至 progress=100
```

---

## 行为约束

- **必须用 `aipage_pack.js` 打包**：禁止 agent 自己 `zip` / 写 `manifest.json` / 写 `janus.manifest.json`；
  打包脚本是唯一真相源，避免与 aicanvas 后端结构契约漂移。Windows 等无 bash 环境必须使用本 `node aipage_pack.js`，**不要**回退到手写 zip。
- **失败重试**：`pre_import` / `async_import` / 轮询失败时最多重试 2 次（间隔 5s），
  仍失败则把 stderr 与 `trace_id`（如有）回报用户，不要静默吞掉错误。
- **成功输出**：拿到 `file_url` 后，独立发起一次 `preview_url` 工具调用，
  然后告知用户「已完成，在线地址如下 ↓」。
- **常见错误码** 参见主 SKILL 的「问题定位指南」，鉴权失败优先看 `references/auth.md`。

---

## 二次编辑：整份覆盖已有 Page（`aicanvas.reimport_page`）

适用场景：用户要「修改 / 编辑 / 更新」一个**已存在的** Page（拿到其 `file_id`），
而不是新做一个。覆盖后 `file_id` 与在线链接不变、已绑定的智能表关系保留，
**不要**重新走 `async_import`（会生成新文档导致 file_id 漂移）。

标准链路（3 步）：

1. **打包**：`node aipage_pack.js --dir <dist_dir>` 得到 `.aipage`（同上）。
2. **上传**：`manage.pre_import`（传 file_name / file_size / file_md5）拿 `upload_url` +
   `file_key`，curl PUT 上传（同 Step 2/3）。
3. **覆盖**：

```bash
mcporter call "tencent-docs" "aicanvas.reimport_page" --args \
  '{"file_id":"<已有Page的file_id>","file_key":"<file_key>","file_name":"<file_name>"}'
```

返回 `version`（覆盖后的新版本号）。要求当前用户对该 Page 有编辑权限，
无权限时返回权限错误。失败最多重试 2 次（间隔 5s）。

> 覆盖语义：新制品整份替换当前版本并落一个新版本号（旧版本在服务端保留，
> 可用于历史版本）。已发布（publish）的 Page 覆盖后不会自动更新发布内容，
> 需重新发布。

---

## 读取已有 Page 源码（`aicanvas.read_page_source`）

二次编辑前，通常先读回 Page 当前的**入口 HTML 源码**作为改造基线。本工具用法
**类似读取本地文件**：只返回入口 HTML 单个文件（不含外链的 js/css 等其它产物），
并支持**按行范围**读取，避免一次性把整份源码塞进上下文。

参数：

- `file_id`（必填）：已有 Page 的 file_id。
- `start_line`（可选）：起始行号，从 1 开始，默认 1。
- `end_line`（可选）：结束行号（含），默认 `start_line + 499`（即一次最多 500 行）；
  传 `-1` 表示读到文件末尾（返回完整源码）。

```bash
# 默认读前 500 行
mcporter call "tencent-docs" "aicanvas.read_page_source" --args \
  '{"file_id":"<已有Page的file_id>"}'

# 指定行范围（第 501~1000 行）
mcporter call "tencent-docs" "aicanvas.read_page_source" --args \
  '{"file_id":"<file_id>","start_line":501,"end_line":1000}'

# 一次读完整源码（用于整份二次改造）
mcporter call "tencent-docs" "aicanvas.read_page_source" --args \
  '{"file_id":"<file_id>","end_line":-1}'
```

返回：`html`（本次行范围的源码片段）、`entry`（入口文件相对路径，如 `index.html`，
也可能是其它 html 文件名）、`version`（版本号）、`start_line` / `end_line`（本次实际
返回的行区间）、`total_lines`（总行数）、`has_more`（是否还有后续内容）。

翻页读法：若 `has_more=true`，下次将 `start_line` 设为上次返回的 `end_line + 1` 继续读；
要拿全文做整份覆盖式二次编辑时，直接传 `end_line=-1` 一次读全即可。
要求当前用户对该 Page 有查看权限。
