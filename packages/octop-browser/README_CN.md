<p align="center">
  <img src="assets/images/banner.jpeg" alt="Octop Browser Banner" width="600" />
</p>

<p align="center">
  <strong>面向 Agent 的轻量浏览器自动化 —— 直连 CDP，去掉 Playwright，定位更准、更稳。</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-browser/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-green" /></a>
  <a href="https://pypi.org/project/octop-browser/"><img src="https://img.shields.io/pypi/v/octop-browser" alt="PyPI" /></a>
  <a href="https://github.com/astral-sh/ruff"><img alt="Code Style: Ruff" src="https://img.shields.io/badge/code%20style-ruff-000000?logo=ruff&logoColor=white" /></a>
  <a href="https://github.com/TencentCloud/octop-browser"><img alt="GitHub stars" src="https://img.shields.io/github/stars/TencentCloud/octop-browser?style=social" /></a>
</p>

<p align="center">
  <a href="README.md">English</a> · <b>中文</b>
</p>

<p align="center">
  <a href="#-概述">概述</a> ·
  <a href="#-亮点">亮点</a> ·
  <a href="#-核心技术">核心技术</a> ·
  <a href="#-功能特性">功能特性</a> ·
  <a href="#-快速开始">快速开始</a> ·
  <a href="#-目录">目录</a>
</p>

---

## 📌 概述

**Octop Browser** 是一个轻量的 browser-use 场景工具，目标是让 Agent 使用浏览器**更准确、更可靠**。与典型方案在 Playwright 之上再包一层不同，它直接启动一个真实的 Chromium，并通过 **Chrome DevTools Protocol（CDP）直连**——去掉中间层之后，元素定位基于实时 DOM 的稳定 ref，提升准确度。

在实现上，它启动一个带 `--remote-debugging-port` 的 Chromium 进程，并自行与 CDP 通信。由于元素 ref 直接来自实时页面，Agent 操作的是*真实*节点，且这些 ref 在回流与重渲染后依然有效——因此动作准确度更高、token 占用更低；配合持久化 profile，登录态也不会在任务中途失效。

> Octop Browser 的设计目标：给 Agent 一个可以放心操作的浏览器——点击准确、token 占用低、登录态可保持——以一组小而规整的工具，外加一个对等的 CLI。

*说明：* `install-browser` 命令为了下载 Chromium 二进制，**可能**一次性引导 Playwright 来取浏览器；但 Playwright **不是**运行时依赖——Agent 始终通过 CDP 驱动浏览器。

## ✨ 亮点

| | 特性 | 说明 |
|---|------|------|
| ⚡ | **直连 CDP** | 直接通过 CDP 连接 Chrome，没有 Playwright / 中间层 |
| 🎯 | **基于 ref 的定位** | 稳定的元素 ref 在布局回流后依然有效，点击精准命中 |
| 🪶 | **轻量 DOM** | 省 token 的多级 DOM，保持提示词精简 |
| 🔐 | **登录态持久化** | 基于 profile 的登录在会话间保持，无需反复登录 |
| 🛠️ | **Agent 工具** | 一组无状态的 `browser_tool`，约 20 个动作 |
| 💻 | **CLI** | 每个动作都是一条一等命令 |
| 🎬 | **录制与回放** | 录制一段操作流程，再按"技能引导的智能体执行"回放 |
| 🤖 | **MCP 服务** | 把浏览器暴露给任意支持 MCP 的 Agent |

## 🧠 核心技术

| 层级 | 技术 |
|------|------|
| **语言** | Python 3.11+ |
| **传输** | 基于 `websockets` 的 CDP（自研异步客户端） |
| **启动** | `subprocess` 启动带 `--remote-debugging-port` 的 Chromium |
| **DOM** | 多级构建器 + 稳定 `ref` 体系 |
| **工具** | 无状态的 `browser_tool` 动作集 |
| **录制** | 注入式 JS 录制 + 语义归并 + 技能生成 |
| **接口** | CLI + MCP 服务 |
| **构建 / 质量** | hatchling · ruff · mypy · pytest |

## 🤔 功能特性

### 浏览器工具

`browser_tool(action=...)` 提供以下动作：

| 动作 | 说明 | 动作 | 说明 |
|------|------|------|------|
| `navigate` | 当前标签页跳转 | `select` | 选择一个 `<select>` 选项 |
| `dom_tree` | 输出多级 DOM | `scroll` | 滚动视口 |
| `screenshot` | 截图 | `hover` | 悬停元素 |
| `click` | 按 ref 点击 | `eval_js` | 执行 JavaScript |
| `type` | 按 ref 输入文本 | `go_back` / `go_forward` | 历史导航 |
| `fill` | 按 ref 填表 | `reload` | 刷新页面 |
| `press` | 按下按键 | `new_tab` / `close_tab` | 标签页控制 |
| `wait` | 等待条件满足 | `switch_tab` / `list_tabs` | 标签页管理 |
| | | `close_session` | 关闭 CDP 连接（传 `kill=True` 可同时结束 Chrome） |

### CDP 会话
- `BrowserSession.create(profile=...)` 打开一个持久化的 Chromium 会话。
- 无状态辅助：`browser_tool(action="navigate", url=..., profile="work")`。
- 设置 `BROWSER_USE_IDLE_TIMEOUT_MINUTES` 后，本地 Chrome profile 在没有真实
  CDP 操作达到指定分钟数时自动退出；默认 `0` 表示禁用。
- `await session.close(kill=True)` 或
  `browser_tool(action="close_session", profile="work", kill=True)` 可立即结束
  本地 Chrome 进程；磁盘 profile 和登录状态会保留。

### CLI
每个工具同时是一条 CLI 命令：

```bash
octop-browser install-browser     # 下载 Chromium 二进制（一次性）
octop-browser navigate "https://example.com" --profile work
octop-browser dom-tree --profile work
octop-browser click --ref inp_1 --profile work
octop-browser type "octop" --ref inp_1 --profile work
octop-browser screenshot --profile work
octop-browser close-session --kill --profile work   # 同时结束 Chrome 进程
# 会话：open / close-session / new-tab / switch-tab / close-tab / list-tabs
```

### 录制与回放
Octop Browser 可以**录制**真实浏览过程并**回放**：

1. `octop-browser record daemon-start` —— 启动常驻录制守护进程。
2. `octop-browser record start` —— 开始录制当前标签页。
3. 正常浏览。一小段注入脚本会捕获点击、输入、跳转与提交，并对敏感字段做脱敏。
4. `octop-browser record stop` —— 停止录制。
5. `octop-browser record generate-steps <id>` —— 查看语义化步骤；`record generate-skill <id>` 生成一份草稿版 **Skill**（`draft.skill.md`）。
6. `octop-browser replay run <id>` —— 以**技能引导的智能体执行**方式回放（模型复现意图，而非脆弱的坐标/ref）。

可用 `record list` / `record show <id>` / `record status` / `record doctor` 管理录制内容。

### MCP 服务
`octop-browser` 自带一个 MCP 服务，任意支持 MCP 的 Agent 都能通过同一套工具驱动浏览器。

```bash
python -m octop_browser.mcp_server   # 或：make mcp
```

它通过 stdio 提供 MCP 协议，这也是多数 Agent 客户端默认使用的传输方式。

在 MCP 侧，每个动作都是一个以其命名的独立工具 —— `browser_navigate`、`browser_click`、
`browser_dom_tree`、`browser_close_session`、`browser_record_start`、`install_browser` ……
而不是一个统一分发的工具。参数与 Python API 一致，因此 `browser_close_session` 同样
接受 `kill` 来结束 Chrome 进程。

### Agent 技能
`skills/` 目录提供了开箱可用的 Skill 文件，供支持技能加载的 Agent 直接使用——
`skills/octop-browser/SKILL.md`（英文）与 `skills/octop-browser-zh/SKILL.md`（中文）。
它们固化了安全用法：每次 `click` 之前先跑 `dom-tree`、传 `ref` 而不是坐标、
用命名 profile 复用登录态。`record generate-skill` 生成的草稿 Skill 也是同一格式。

## 🚀 快速开始

### 环境要求
- **Python 3.11+** —— 已在 3.11 / 3.12 验证。基于它构建的上层应用（如 Octop）
  可能要求更高版本，以其自身文档为准。
- 一个 Chromium / Chrome 二进制（由 `install-browser` 自动下载）

### 1. 安装

```bash
pip install octop-browser
octop-browser install-browser    # 一次性下载 Chromium 二进制
```

### 2. 作为库使用

```python
from octop_browser import BrowserSession

async with await BrowserSession.create(profile="default") as session:
    await session.navigate("https://example.com")
    dom = await session.dom_tree()
    await session.click(ref="btn_1")
```

或以无状态方式：

```python
from octop_browser import browser_tool

await browser_tool(action="navigate", url="https://example.com", profile="work")
```

### 3. 作为 CLI 使用

```bash
octop-browser --help
octop-browser --version
octop-browser navigate "https://example.com" --profile work
octop-browser dom-tree --profile work
octop-browser dom-tree --help
```

顶层帮助会列出所有命令和常用示例。每个命令也有独立帮助页，包含录制等
嵌套命令，例如 `octop-browser record start --help`。

### 4. 录制一段流程

```bash
octop-browser record daemon-start
octop-browser record start
# ... 在页面上操作 ...
octop-browser record stop
octop-browser record generate-skill <recording_id>   # 生成一份草稿版 Skill
octop-browser replay run <recording_id>              # 回放
```

## 📑 目录

- [概述](#-概述)
- [亮点](#-亮点)
- [核心技术](#-核心技术)
- [功能特性](#-功能特性)
- [快速开始](#-快速开始)
- **参考**
  - [CLI 参考](#-cli-参考)
  - [Python API](#-python-api)
  - [配置](#-配置)
  - [开发](#-开发)
- **项目信息**
  - [贡献](#-贡献)
  - [相关项目](#-相关项目)
  - [许可证](#-许可证)

## 📖 CLI 参考

使用 `octop-browser --help` 查看完整命令列表，使用
`octop-browser <command> --help` 查看具体参数。`--version` 会打印已安装包的版本。

| 命令 | 说明 |
|------|------|
| `install-browser` | 下载 Chromium 二进制（一次性引导） |
| `navigate` | 让当前标签页跳转到指定 URL |
| `open` | 启动会话，并把一个或多个 URL 分别开成标签页 |
| `dom-tree` | 打印多级 DOM |
| `screenshot` | 截图 |
| `click` / `type` / `fill` / `press` | 按 ref 交互 |
| `wait` / `select` / `scroll` / `hover` | 页面控制 |
| `eval-js` | 执行 JavaScript |
| `go-back` / `go-forward` / `reload` | 历史 / 刷新 |
| `new-tab` / `switch-tab` / `close-tab` / `list-tabs` | 标签页管理 |
| `close-session` | 断开该 profile 的 CDP 会话。Chrome 继续运行，后续命令可重新接入；加 `--kill` 则结束进程并释放端口 |
| `record ...` | `doctor`、`daemon-start`、`daemon-stop`、`status`、`start`、`stop`、`list`、`show`、`generate-steps`、`generate-skill` |
| `replay run <id>` | 回放一段录制流程 |

### 录制与回放选项

| 选项 | 取值 | 作用 |
|------|------|------|
| `record start --privacy` | `none` · `mask-sensitive` *（默认）* · `mask-all` | 在写入磁盘前对输入值做脱敏。`mask-sensitive` 仅脱敏看起来敏感的字段（`password`、`token`、`secret`、`otp`、`jwt` 等关键词，匹配字段的 type / name / id / placeholder / label）；`mask-all` 脱敏所有输入值 |
| `replay run --input key=value` | 可重复传入 | 在回放时为 `{{占位符}}` 步骤提供取值 |

被脱敏的值会以占位符 `{{sensitive_value}}` 保存，因此包含登录的录制依然可以安全回放——
把密钥放在环境变量里，回放时再传入：

```bash
octop-browser replay run <recording_id> --input sensitive_value="$MY_PASSWORD"
```

### DOM 级别

`dom-tree`（以及 `dom_tree` 动作）通过 `--level` 在细节与 token 之间取舍：

| 级别 | 开销 | 内容 |
|------|------|------|
| `minimal` | ~50 tokens | 仅标题 / URL |
| `interactive` *（默认）* | ~200–500 | 可点击 / 可输入元素，带 `ref` |
| `full` | ~1k–3k | 完整可读页面 |
| `structured` | 不固定 | JSON，便于程序化处理 |

```bash
octop-browser dom-tree --level minimal      # 低成本确认页面状态
octop-browser dom-tree --level structured   # 供脚本消费的 JSON
```

## 🐍 Python API

### 导出符号

以下都可以从包根导入：`from octop_browser import ...`

| 符号 | 类型 | 作用 |
|------|------|------|
| `BrowserSession` | 类 | 持久化 CDP 会话 —— `await BrowserSession.create(profile="work")` |
| `browser_tool` | 异步函数 | 无状态单次动作 —— `await browser_tool(action="click", ref="btn_1")` |
| `ToolResult` | 模型 | 所有会话方法与 `browser_tool()` 的返回值 |
| `ActionMetrics` | 模型 | 单次动作的耗时 / token 计数 |
| `TabInfo` | 模型 | 单个标签页：`tab_id` · `url` · `title` · `active` |
| `OctopSettings` | 模型 | 完整配置对象 —— 通过 `BrowserSession.create(settings=...)` 传入 |
| `settings` | 实例 | 进程级默认配置，导入时从环境变量构建 |
| `BrowserMode` | 类型 | `Literal["auto", "headed", "headless"]` |
| `chromium_executable` | 函数 | 返回受管 Chromium 二进制路径，不存在时为 `None` |
| `ensure_chromium` | 函数 | 阻塞式安装 —— 二进制就绪后返回 `True` |
| `install_chromium_stream` | 异步生成器 | 同样的安装流程，但以事件流输出，便于做进度界面 |
| `InstallEvent` | TypedDict | 单条安装事件：`log` 日志行，或终态 `done` / `success` / `error` |

### 返回结果

所有会话方法与 `browser_tool()` 调用都返回 `ToolResult`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | `bool` | `False` 表示动作失败 —— 需查看 `error` |
| `content` | `str` \| `dict` | 主要载荷：DOM 文本、截图路径、JS 返回值等 |
| `error` | `str` \| `None` | 失败原因；成功时为 `None` |
| `metrics` | `ActionMetrics` | `action` · `duration_ms` · `dom_nodes_scanned` · `estimated_tokens` · `screenshot_size_kb` |
| `metadata` | `dict` \| `None` | 可选旁路信息 —— 例如 `screenshot` 会在此回传页面 url / 标题 |

```python
res = await session.dom_tree(level="interactive")
if res.success:
    print(res.content, res.metrics.estimated_tokens)
```

`session.metrics_summary()` 可汇总整个会话的累计指标。

### 钩子（Hooks）

`BrowserSession` 混入了 `HooksMixin`，可以注册回调来观测每个动作：

```python
@session.on("after_action")
async def log_metrics(metrics):  # metrics: ActionMetrics
    print(metrics.action, metrics.duration_ms)
```

| 事件 | 载荷 | 触发时机 |
|------|------|----------|
| `before_action` | `dict` —— `{"action": str, "params": dict}` | 每个动作派发之前 |
| `after_action` | `ActionMetrics` | 动作执行成功之后 |
| `action_error` | `ToolResult` | 动作返回 `success=False` 之后 |
| `page_navigated` | —— | 预留：`on()` 接受该事件，但目前尚未触发 |

回调可以是同步或异步函数；钩子内部抛出的异常会被记录日志，不会打断动作本身。

## ⚙️ 配置

所有配置项都在导入时从环境变量读取。你也可以显式构造 `OctopSettings`
并传给 `BrowserSession.create()`：

```python
from octop_browser import BrowserSession, OctopSettings

settings = OctopSettings(cdp_port_start=9300, cdp_timeout=60.0)
session = await BrowserSession.create(profile="work", settings=settings)
```

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `BROWSER_USE_MODE` | `auto` | 启动模式：`auto` / `headed` / `headless`（auto 在 macOS/Windows 或设置了 `DISPLAY` 时使用有头模式） |
| `BROWSER_USE_CDP_WS_URL` | *（未设置）* | 直接连接已有的 Chrome DevTools WebSocket URL —— 用于远程 / Docker 中的 Chrome，跳过本地启动器 |
| `BROWSER_USE_CHROME_BIN` | 自动探测 | Chrome / Chromium 可执行文件的绝对路径 |
| `BROWSER_USE_PROFILES_DIR` | `~/.octop-browser/profiles` | Chrome user-data-dir 的根目录 |
| `BROWSER_USE_SCREENSHOTS_DIR` | `~/.octop-browser/screenshots` | `screenshot` 动作写入 PNG 的目录 |
| `BROWSER_USE_CDP_HOST` | `localhost` | 提供 CDP 端点的主机 |
| `BROWSER_USE_CDP_PORT_START` | `9222` | 分配给 profile 的起始 CDP 调试端口 |
| `BROWSER_USE_CDP_TIMEOUT` | `30.0` | 等待 CDP 命令响应的秒数 |
| `BROWSER_USE_VIEWPORT_WIDTH` | `1440` | 视口宽度（CSS 像素） |
| `BROWSER_USE_VIEWPORT_HEIGHT` | `900` | 视口高度（CSS 像素） |
| `BROWSER_USE_IDLE_TIMEOUT_MINUTES` | `0`（关闭） | 本地托管的 Chrome 在无真实 CDP 活动 N 分钟后自动关闭 |
| `BROWSER_USE_LAUNCH_RETRIES` | `20` | 启动后轮询 Chrome 的次数 |
| `BROWSER_USE_LAUNCH_DELAY` | `0.25` | 每次启动轮询的间隔秒数 |
| `BROWSER_USE_CDP_MAX_MESSAGE_SIZE` | `33554432`（32 MiB） | CDP WebSocket 单帧上限；`0` 表示不限制（超大页面截图时可调高） |
| `BROWSER_USE_NO_SANDBOX` | 自动探测 | 强制开启（`1`）或禁用（`0`）`--no-sandbox`。未设置时，仅在内核禁止非特权用户命名空间（容器中常见）时自动添加 |
| `BROWSER_USE_DISABLE_GPU` | 自动（无头时开启） | 强制开启（`1`）/ 禁用（`0`）`--disable-gpu`。默认无头模式开启，有头模式关闭 |
| `BROWSER_USE_DISABLE_DEV_SHM_USAGE` | 自动（Linux 开启） | 强制开启（`1`）/ 禁用（`0`）`--disable-dev-shm-usage`。默认在 Linux 开启——Docker 默认的 64 MiB `/dev/shm` 对 Chrome 来说太小 |

## 🛠️ 开发

**环境要求：** Python 3.11+、[uv](https://docs.astral.sh/uv/)

```bash
make install          # uv sync --extra dev（无 uv 时回退到 pip install -e ".[dev]"）
make all              # 格式化 + 静态检查 + 类型检查 + 测试
```

## 🤝 贡献

1. Fork 本仓库
2. 创建特性分支（`git checkout -b feature/amazing-feature`）
3. 提交前运行 `make all`
4. 向 `develop` 发起 Pull Request

分支、PR 与发版流程见 [CONTRIBUTING.md](CONTRIBUTING.md)（`release/*` → `main` 合并后自动发布到 PyPI）。

发现安全漏洞？请按 [SECURITY.md](SECURITY.md) 中的私密披露流程反馈，不要直接开公开 issue。
各版本的变更说明见 [CHANGELOG.md](CHANGELOG.md)。

## 🔗 相关项目

| 项目 | 说明 |
|------|------|
| [harness-agent](https://github.com/TencentCloud/harness-agent) | 驱动浏览器工具的 Agent 运行时 |
| [harness-memory](https://github.com/TencentCloud/harness-memory) | 面向浏览器 Agent 的记忆系统 |
| [harness-gateway](https://github.com/TencentCloud/harness-gateway) | 多平台 IM 通道桥接 |
| [Octop](https://github.com/TencentCloud/Octop) | 组合 Harness 技术栈的自托管助手 |

## 📄 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。
