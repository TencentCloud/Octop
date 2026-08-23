# Octop 插件示例

[English](./README.md)

本目录提供插件 demo，对应 Octop / harness-agent 支持的 `kind`，以及**前后端一体**的 UI 渲染示例。
结构参考 [octop-toolkit](https://github.com/veenyi/octop-plugins/tree/main/octop-toolkit)。

## 示例一览

| 目录 | `kind` | 作用 |
|------|--------|------|
| [`demo-toolkit`](./demo-toolkit/) | `tool` | 注册可调用工具（时间、文本统计、可配置前缀回显） |
| [`demo-greeting-skill`](./demo-greeting-skill/) | `skill` | 向 Agent 工作区同步一份示例 Skill |
| [`demo-turn-logger`](./demo-turn-logger/) | `hook` | 注册 `AgentMiddleware`，在模型调用前后打日志 |
| [`demo-ui-card`](./demo-ui-card/) | `tool` + `ui/` | 后端返回 `octop_ui` JSON；前端在聊天页渲染可交互卡片 |
| [`bilibili-anime`](./bilibili-anime/) | `tool` + `ui/` | 搜索哔哩哔哩番剧，聊天内 iframe 播放 + 分集导航 |
| [`server-status`](./server-status/) | `tool` + `ui/` | 展示服务器 OS/内核与 CPU/内存/磁盘负载卡片 |

## 目录约定

每个插件是一个文件夹，至少包含：

```text
my-plugin/
├── plugin.yaml    # id、version、name、kind、entry；可选 icon / ui
├── main.py        # 必须定义 setup(ctx)
├── skills/        # 仅 skill 插件：<name>/SKILL.md
└── ui/            # 可选：预构建前端（安装时不跑 npm）
    └── dist/
        ├── index.js       # ESM，导出 setup(host)
        └── manifest.json  # 声明 renderer ↔ tool
```

在 `setup(ctx)` 中按 `kind` 调用对应 API：

| `kind` | API |
|--------|-----|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` |
| `skill` | `ctx.skills("skills")` — 相对插件根目录 |
| `hook` | `ctx.middleware(instance, priority=...)` |

### 带 UI 的 tool 插件

`plugin.yaml` 可选字段：

```yaml
icon: "🧩"   # 或 https://… 图片 URL，Dashboard 卡片展示
ui:
  entry: ui/dist/index.js
  manifest: ui/dist/manifest.json
```

工具返回 JSON 字符串（推荐）：

```json
{
  "octop_ui": { "renderer": "demo_card", "version": 1 },
  "data": { "title": "…", "count": 1 },
  "text": "纯文本回退"
}
```

Dashboard 通过 `GET /api/plugins/{id}/ui/…` 加载 `index.js`，调用 `setup(host)` 注册渲染器。
`host.patchResult(callId, data)` 可在不重跑 LLM 的情况下刷新气泡（L2）；流式仍走 SSE 整段替换 `output`（L1）。

插件 ESM 为自包含文件；React 由 Dashboard 注入 `window.__OCTOP_REACT__` / `__OCTOP_JSX__`。

## 本地安装

```bash
# 从目录安装（开发时常用）
octop plugin install ./plugins/demo-toolkit --force
octop plugin install ./plugins/demo-greeting-skill --force
octop plugin install ./plugins/demo-turn-logger --force
octop plugin install ./plugins/demo-ui-card --force
octop plugin list
```

或先打包再安装：

```bash
cd plugins
zip -r demo-ui-card.zip demo-ui-card/
octop plugin install ./demo-ui-card.zip --force
```

**Dashboard：** Admin → Plugins → 安装。请粘贴 ZIP 的 **直接下载地址**
（GitHub 请用 `raw.githubusercontent.com` 或 Download / raw 链接，不要用 `/blob/` 页面）。

- **tool**：安装后到「工具管理」为具体 Agent 启用工具  
- **skill**：Agent 启动时同步到工作区 `skills/`  
- **hook**：全局启用的插件会挂上对应 middleware  
- **ui**：随插件安装；打开聊天页后自动加载渲染器  

## 打包注意

ZIP 内应只有**一个**带 `plugin.yaml` 的插件根目录；若含 UI，请一并打入预构建的 `ui/dist/`（**不要**依赖服务器执行 `npm install`）。

```bash
# 正确：一层插件目录
zip -r demo-toolkit.zip demo-toolkit/

# 错误：多个插件塞进同一 ZIP，或只有散落文件没有插件根目录
```

## 快速校验

在仓库根目录执行（无需启动服务）：

```bash
uv run python - <<'PY'
from pathlib import Path
from harness_agent.plugins import PluginRegistry, load_plugin_dir

for name in ("demo-toolkit", "demo-greeting-skill", "demo-turn-logger", "demo-ui-card"):
    PluginRegistry.reset()
    p = load_plugin_dir(Path("plugins") / name, install_deps=False)
    print(
        p.manifest.id,
        p.manifest.kind,
        f"tools={len(p.tools)}",
        f"mw={len(p.middleware)}",
        f"skills={p.skills_dir}",
    )
PY
```

期望结果：

- `demo-toolkit` → `tool`，3 个工具  
- `demo-greeting-skill` → `skill`，存在 `skills/`  
- `demo-turn-logger` → `hook`，1 个 middleware  
- `demo-ui-card` → `tool`，1 个工具  
