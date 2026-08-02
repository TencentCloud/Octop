# Octop 插件示例

[English](./README.md)

本目录提供三类插件 demo，对应 Octop / harness-agent 支持的 `kind`。
结构参考 [octop-toolkit](https://github.com/veenyi/octop-plugins/tree/main/octop-toolkit)。

## 示例一览

| 目录 | `kind` | 作用 |
|------|--------|------|
| [`demo-toolkit`](./demo-toolkit/) | `tool` | 注册可调用工具（时间、文本统计、可配置前缀回显） |
| [`demo-greeting-skill`](./demo-greeting-skill/) | `skill` | 向 Agent 工作区同步一份示例 Skill |
| [`demo-turn-logger`](./demo-turn-logger/) | `hook` | 注册 `AgentMiddleware`，在模型调用前后打日志 |

## 目录约定

每个插件是一个文件夹，至少包含：

```text
my-plugin/
├── plugin.yaml    # id、version、name、kind、entry
├── main.py        # 必须定义 setup(ctx)
└── skills/        # 仅 skill 插件：<name>/SKILL.md
```

在 `setup(ctx)` 中按 `kind` 调用对应 API：

| `kind` | API |
|--------|-----|
| `tool` | `ctx.tool(name, fn, description=..., config_fields=...)` |
| `skill` | `ctx.skills("skills")` — 相对插件根目录 |
| `hook` | `ctx.middleware(instance, priority=...)` |

## 本地安装

```bash
# 从目录安装（开发时常用）
octop plugin install ./plugins/demo-toolkit --force
octop plugin install ./plugins/demo-greeting-skill --force
octop plugin install ./plugins/demo-turn-logger --force
octop plugin list
```

或先打包再安装：

```bash
cd plugins
zip -r demo-toolkit.zip demo-toolkit/
octop plugin install ./demo-toolkit.zip --force
```

**Dashboard：** Admin → Plugins → 安装。请粘贴 ZIP 的 **直接下载地址**
（GitHub 请用 `raw.githubusercontent.com` 或 Download / raw 链接，不要用 `/blob/` 页面）。

- **tool**：安装后到「工具管理」为具体 Agent 启用工具  
- **skill**：Agent 启动时同步到工作区 `skills/`  
- **hook**：全局启用的插件会挂上对应 middleware  

## 打包注意

ZIP 内应只有**一个**带 `plugin.yaml` 的插件根目录：

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

for name in ("demo-toolkit", "demo-greeting-skill", "demo-turn-logger"):
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
