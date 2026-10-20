---
name: octop-browser-zh
description: AI 浏览器自动化工具，基于 CDP 协议。需要控制浏览器、页面导航、点击元素、填写表单、提取内容或截图时使用。
allowed-tools: Bash
---

# octop-browser 浏览器自动化

通过 Bash 工具调用 `octop-browser` CLI 来驱动一个真实的 Chrome 浏览器
（基于 Chrome DevTools Protocol）。同一个 profile 的多次命令会 attach 到
同一个 Chrome 进程，因此一连串命令共享一个持久会话。

## 核心规则

1. **`click` 之前必须先跑 `dom-tree`** — 页面跳转后 ref 会失效。
2. **默认用 `--level interactive`**（约 200-500 token），返回所有可交互元素。
3. **只想确认页面状态时用 `--level minimal`**（约 50 token）。
4. **需要读全文内容时才用 `--level full`**（约 1000-3000 token）。
5. **要 JSON 结构化数据用 `--level structured`**。
6. **禁止硬编码坐标** — 始终用 `dom-tree` 返回的 `--ref`。
7. **用命名 profile 持久化登录态**：`--profile work`、`--profile github`。
8. **遇到 CDP 错误**：跑 `dom-tree --level minimal` 确认页面状态，再重试。
9. **结束时跑 `close-session --profile <名称>`**：仅断开 CDP，Chrome 进程保留以便下次 attach。

## 标准工作流

```bash
# 1. 导航
octop-browser navigate "https://example.com" --profile default

# 2. 获取可交互元素和 ref
octop-browser dom-tree --profile default
# 输出：
#   [ref=inp_1] input[text] placeholder="搜索"
#   [ref=btn_2] button "搜索"

# 3. 用 ref 操作 —— 禁止猜测坐标
octop-browser click --ref inp_1 --profile default
octop-browser type "hello" --profile default
octop-browser click --ref btn_2 --profile default

# 4.（可选）保存截图作为证据
octop-browser screenshot --path /tmp/result.png --profile default
```

任何命令加 `--json` 即可返回完整的 `ToolResult` 结构（success / content /
metrics / metadata / error），适合脚本解析；不加则输出人类友好的文本。

## 命令速查表

| 命令 | 必填 | 常用选项 |
|---|---|---|
| `navigate <url>` | url | `--profile`、`--json` |
| `dom-tree` | — | `--level {minimal,interactive,full,structured}` |
| `screenshot` | — | `--full-page`、`--element-ref REF`、`--path PATH` |
| `click` | 三选一：`--ref REF` / `--selector CSS` / `--xy X Y` | |
| `type <text>` | text | `--ref REF`（先点击再输入） |
| `scroll` | — | `--direction {up,down,left,right}`、`--amount N` |
| `hover <ref>` | ref | |
| `eval-js <expression>` | expression | |
| `go-back` / `go-forward` / `reload` | — | |
| `list-tabs` | — | |
| `new-tab` | — | `--url URL` |
| `switch-tab <tab_id>` | tab_id | |
| `close-tab` | — | `--tab-id ID` |
| `close-session` | — | （仅 `--profile`） |

所有动作命令都支持 `--profile`、`--json`，以及 `--auto` / `--headed` /
`--headless` 三选一。注意：launch-mode 仅在该 profile 的 **首次** 调用时
生效，之后会复用已经在跑的 Chrome 进程。

## 截图

`screenshot` 直接落盘并打印**文件路径**（不是 base64）。加 `--json` 时
`metadata` 会带 `url` / `title` / `width` / `height` / `size_kb` / `full_page`。

- 默认路径：`BROWSER_USE_SCREENSHOTS_DIR/octop-<时间戳>.png`
  （默认 `~/.octop-browser/screenshots/`）
- `--full-page` —— 一次抓整页可滚动区域
- `--element-ref btn_2` —— 截某个元素（与 `--full-page` 互斥，元素优先）
- `--path /tmp/latest.png` —— 固定路径，重复调用覆盖

## 配置（环境变量）

所有配置都通过环境变量驱动，开发/CI/生产无需改代码。

| 变量 | 默认 | 用途 |
|---|---|---|
| `BROWSER_USE_MODE` | `auto` | `auto` / `headed` / `headless`（auto 按 `DISPLAY` 自动判定） |
| `BROWSER_USE_PROFILES_DIR` | `~/.octop-browser/profiles` | Chrome user-data-dir 根目录 |
| `BROWSER_USE_SCREENSHOTS_DIR` | `~/.octop-browser/screenshots` | 截图默认输出目录 |
| `BROWSER_USE_CHROME_BIN` | 自动探测 | Chrome 路径（也会自动发现 Playwright 自带的 Chromium） |
| `BROWSER_USE_CDP_HOST` | `localhost` | 远端/Docker 中的 Chrome 主机 |
| `BROWSER_USE_CDP_WS_URL` | — | 跳过启动器，直接连指定 WebSocket URL |

## 登录态复用

Profile 数据存储在 `~/.octop-browser/profiles/<名称>/`，复用相同 profile 名
即可自动复用 Chrome cookies，无需重新认证。

```bash
# 首次运行：手动完成登录（需要桌面/--headed 模式）
octop-browser navigate "https://github.com/login" --profile github --headed
# ... 在浏览器中完成登录 ...

# 后续所有调用：自动复用登录态
octop-browser navigate "https://github.com" --profile github
```

## 安装

```bash
pip install octop-browser

# 需要安装 Chrome 或 Chromium：
# Ubuntu: sudo apt install chromium-browser
# macOS:  brew install --cask google-chrome
# 没有系统浏览器时：octop-browser install-browser
#   （会自动 pip install playwright 并下载 Chromium；预装好的镜像可设
#    OCTOP_SKIP_PLAYWRIGHT_PIP=1 跳过 pip 步骤）
```

## Python API（可选）

如果你更愿意把 octop-browser 嵌进 Python 脚本而不是走 shell，
`from octop_browser import browser_tool` 提供等价的入口，返回 `ToolResult`。
但对 skill / agent 场景，推荐用 CLI —— 调用方无需管理状态，shell 上下文也更
直接。

## 代码仓库

https://github.com/TencentCloud/octop-browser
