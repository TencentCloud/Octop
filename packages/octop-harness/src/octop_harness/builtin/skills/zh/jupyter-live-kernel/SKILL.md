---
name: jupyter-live-kernel
description: "通过实时 Jupyter kernel 进行交互式 Python（hamelnb）。"
version: 1.0.0
author: Octop
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "Jupyter 内核"
      en: "Live Jupyter"
    summary:
      zh: "通过实时 Jupyter kernel 交互式运行 Python。"
      en: "Run interactive Python against a live Jupyter kernel."
  harness:
    emoji: "▶️"
    tags: [jupyter, notebook, repl, data-science, exploration, iterative]
    category: data-science
---

# Jupyter Live Kernel (hamelnb)

## Harness-agent tools#

本技能从 Octop 移植。使用以下 harness/deepagents 工具：

| 概念 | 工具 |
|---------|------|
| Shell | `execute` |
| 读/写/编辑文件 | `read_file`, `write_file`, `edit_file` |
| 查找文件/搜索内容 | `glob`, `grep` |
| 获取 URL | `web_fetch` |
| 浏览器自动化 | `browser_use` |
| 子代理工作 | `task` |
| 记忆 | `memory_store`, `memory_recall`, `memory_search` |

内置技能文件位于 `/_builtin_skills/<name>/`。用户安装的技能位于 `/skills/<name>/`。

通过实时 Jupyter kernel 为你提供**有状态的 Python REPL**。变量在多次执行之间持续存在。当你需要逐步构建状态、探索 API、检查 DataFrames 或迭代复杂代码时，使用此技能代替 `execute`。

## 何时使用此工具 vs 其他工具#

| 工具 | 何时使用 |
|------|----------|
| **此技能** | 迭代探索、跨步骤状态、数据科学、机器学习、"让我试试这个然后检查" |
| `execute`（Python 一次性） | 短脚本、安装、文件转换——调用之间无状态 |
| `execute`（shell） | git、构建、系统命令 |

**经验法则：** 如果任务需要 Jupyter notebook，就使用此技能。

## 先决条件#

1. **uv** 必须已安装（检查：`which uv`）
2. **JupyterLab** 必须已安装：`uv tool install jupyterlab`
3. 必须运行 Jupyter 服务器（见下方设置）

## 设置#

hamelnb 脚本（克隆一次，或使用同步后的此技能中的副本）：

```
SCRIPT="_builtin_skills/jupyter-live-kernel/scripts/jupyter_live_kernel.py"
```

如果 hamelnb 未捆绑，请克隆上游：

```
git clone https://github.com/hamelsmu/hamelnb.git ~/.agent-skills/hamelnb
SCRIPT="$HOME/.agent-skills/hamelnb/skills/jupyter-live-kernel/scripts/jupyter_live_kernel.py"
```

### 启动 JupyterLab#

检查是否已有服务器正在运行：

```
uv run "$SCRIPT" servers
```

如果未找到服务器，请启动一个：

```
jupyter-lab --no-browser --port=8888 --notebook-dir=$HOME/notebooks \
  --IdentityProvider.token='' --ServerApp.password='' > /tmp/jupyter.log 2>&1 &
sleep 3
```

注意：为本地代理访问禁用了令牌/密码。服务器无头运行。

### 为 REPL 使用创建 Notebook#

如果你只需要 REPL（没有现有 notebook），请创建一个最小 notebook 文件：

```
mkdir -p ~/notebooks
```

写入一个带一个空代码单元的 .ipynb JSON 文件，然后通过 Jupyter REST API 启动 kernel 会话：

```
curl -s -X POST http://127.0.0.1:8888/api/sessions \
  -H "Content-Type: application/json" \
  -d '{"path":"scratch.ipynb","type":"notebook","kernel":{"name":"python3"}}'
```

## 核心工作流#

所有命令都返回结构化 JSON。始终使用 `--compact` 以节省 token。

### 1. 发现服务器和 notebooks#

```
uv run "$SCRIPT" servers --compact
uv run "$SCRIPT" notebooks --compact
```

### 2. 执行代码（主要操作）#

```
uv run "$SCRIPT" execute --path <notebook.ipynb> --code '<python code>' --compact
```

状态在多次 execute 调用之间持续存在。变量、导入、对象全部保留。

多行代码使用 `$'...'` 引用：

```
uv run "$SCRIPT" execute --path scratch.ipynb --code $'import os\nfiles = os.listdir(".")\nprint(f"Found {len(files)} files")' --compact
```

### 3. 检查实时变量#

```
uv run "$SCRIPT" variables --path <notebook.ipynb> list --compact
uv run "$SCRIPT" variables --path <notebook.ipynb> preview --name <varname> --compact
```

### 4. 编辑 notebook 单元#

```
# 查看当前单元
uv run "$SCRIPT" contents --path <notebook.ipynb> --compact

# 插入新单元
uv run "$SCRIPT" edit --path <notebook.ipynb> insert \
  --at-index <N> --cell-type code --source '<code>' --compact

# 替换单元源（使用 contents 输出的 cell-id）
uv run "$SCRIPT" edit --path <notebook.ipynb> replace-source \
  --cell-id <id> --source '<new code>' --compact

# 删除单元
uv run "$SCRIPT" edit --path <notebook.ipynb> delete --cell-id <id> --compact
```

### 5. 验证（重启 + 全部运行）#

仅当用户要求干净验证或你需要确认 notebook 从上到下运行时使用：

```
uv run "$SCRIPT" restart-run-all --path <notebook.ipynb> --save-outputs --compact
```

## 来自经验的实用技巧#

1. **服务器启动后的首次执行可能超时** —— kernel 需要一点时间来初始化。如果你遇到超时，只需重试。

2. **kernel 的 Python 是 JupyterLab 的 Python** —— 包必须安装在那个环境中。如果你需要额外的包，请先将它们安装到 JupyterLab 工具环境中。

3. **`--compact` 标志节省大量 token** —— 始终使用它。没有它，JSON 输出可能非常冗长。

4. **对于纯 REPL 使用**，创建一个 scratch.ipynb 并且不要费心编辑单元。只需重复使用 `execute`。

5. **参数顺序很重要** —— 子命令标志如 `--path` 放在子子命令*之前*。例如：`variables --path nb.ipynb list` 而不是 `variables list --path nb.ipynb`。

6. **如果会话尚不存在**，你需要通过 REST API（见设置部分）启动一个。工具在没有实时 kernel 会话的情况下无法执行。

7. **错误以 JSON 形式返回** —— 带有回溯 —— 读取 `ename` 和 `evalue` 字段以理解出错原因。

8. **偶尔的 websocket 超时** —— 某些操作可能在首次尝试时超时，特别是在 kernel 重启后。在升级之前重试一次。

## 超时默认值#

脚本每个执行有 30 秒的默认超时。对于长时间运行的操作，传递 `--timeout 120`。对于初始设置或重度计算，使用宽松的超时（60+）。
