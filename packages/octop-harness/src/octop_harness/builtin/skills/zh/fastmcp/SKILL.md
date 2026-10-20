---
name: fastmcp
description: "使用 FastMCP 在 Python 中构建、测试、检查和部署 MCP 服务器。当创建新的 MCP 服务器、将 API 或数据库包装为 MCP 工具、暴露资源或提示，或为 Claude Code、Cursor 或 HTTP 部署准备 FastMCP 服务器时使用。"
version: 1.0.0
author: Octop
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "FastMCP"
      en: "FastMCP"
    summary:
      zh: "用 Python FastMCP 构建、测试并部署 MCP 服务器。"
      en: "Build, test, and deploy MCP servers with Python FastMCP."
  harness:
    emoji: "⚙️"
    tags: [MCP, FastMCP, Python, Tools, Resources, Prompts, Deployment]
    homepage: https://gofastmcp.com
    related_skills: [mcporter]
prerequisites:
  commands: [python3]
---

# FastMCP

## Harness-agent 工具

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

使用 FastMCP 在 Python 中构建 MCP 服务器，在本地验证它们，将它们安装到 MCP 客户端，并作为 HTTP 端点部署。

## 何时使用

当任务需要以下内容时使用此技能：

- 在 Python 中创建新的 MCP 服务器
- 将 API、数据库、CLI 或文件处理工作流包装为 MCP 工具
- 除了工具外还暴露资源或提示
- 在将服务器接入 octop-harness 或另一个 MCP 客户端之前，使用 FastMCP CLI 进行冒烟测试
- 将服务器安装到 Claude Code、Claude Desktop、Cursor 或类似的 MCP 客户端
- 为 HTTP 部署准备 FastMCP 服务器仓库

当服务器已存在且只需要 CLI 访问时，使用 `mcporter` 技能。对于 octop-harness 运行时集成，将服务器添加到你的代理配置中的 `mcp_server_configs`。

## 先决条件

首先在工作环境中安装 FastMCP：

```bash
pip install fastmcp
fastmcp version
```

对于 API 模板，如果 `httpx` 尚未存在，请安装：

```bash
pip install httpx
```

## 包含的文件

### 模板

- `templates/api_wrapper.py` - 支持认证头的 REST API 包装器
- `templates/database_server.py` - 只读 SQLite 查询服务器
- `templates/file_processor.py` - 文本文件检查和搜索服务器

### 脚本

- `scripts/scaffold_fastmcp.py` - 复制入门模板并替换服务器名称占位符

### 参考

- `references/fastmcp-cli.md` - FastMCP CLI 工作流、安装目标和部署检查

## 工作流

### 1. 选择最小可行服务器形态

首先选择最窄的有用表面区域：

- API 包装器：从 1-3 个高价值端点开始，而不是整个 API
- 数据库服务器：暴露只读自省和受约束的查询路径
- 文件处理器：暴露带有显式路径参数的确定性操作
- 提示/资源：仅当客户端需要可重用的提示模板或可发现的文档时添加

优先选择具有良好名称、文档字符串和模式的精简服务器，而不是具有模糊工具的庞大服务器。

### 2. 从模板搭建

直接复制模板或使用搭建助手：

```bash
python _builtin_skills/fastmcp/scripts/scaffold_fastmcp.py \
  --template api_wrapper \
  --name "Acme API" \
  --output ./acme_server.py
```

可用模板：

```bash
python /_builtin_skills/fastmcp/scripts/scaffold_fastmcp.py --list
```

如果手动复制，请将 `__SERVER_NAME__` 替换为真实的服务器名称。

### 3. 先实现工具

在添加资源或提示之前，从 `@mcp.tool` 函数开始。

工具设计规则：

- 给每个工具一个具体的基于动词的名称
- 将文档字符串编写为用户面向的工具描述
- 保持参数显式且类型化
- 尽可能返回结构化 JSON 安全数据
- 尽早验证不安全的输入
- 默认优先选择只读行为以用于第一个版本

好的工具示例：

- `get_customer`
- `search_tickets`
- `describe_table`
- `summarize_text_file`

糟糕的工具示例：

- `run`
- `process`
- `do_thing`

### 4. 仅当它们有帮助时添加资源和提示

当客户端从获取稳定的只读内容（如模式、策略文档或生成的报告）中受益时，添加 `@mcp.resource`。

当服务器应为已知工作流提供可重用的提示模板时，添加 `@mcp.prompt`。

不要将每个文档都变为提示。优先选择：

- 用于操作的工具
- 用于数据/文档检索的资源
- 用于可重用 LLM 指令的提示

### 5. 在 anywhere 集成之前测试服务器

使用 FastMCP CLI 进行本地验证：

```bash
fastmcp inspect acme_server.py:mcp
fastmcp list acme_server.py --json
fastmcp call acme_server.py search_resources query=router limit=5 --json
```

为了快速迭代调试，在本地运行服务器：

```bash
fastmcp run acme_server.py:mcp
```

要在本地测试 HTTP 传输：

```bash
fastmcp run acme_server.py:mcp --transport http --host 127.0.0.1 --port 8000
fastmcp list http://127.0.0.1:8000/mcp --json
fastmcp call http://127.0.0.1:8000/mcp search_resources query=router --json
```

在声称服务器工作之前，始终对每个新工具运行至少一个真实的 `fastmcp call`。

### 6. 当本地验证通过时安装到客户端

FastMCP 可以向支持的 MCP 客户端注册服务器：

```bash
fastmcp install claude-code acme_server.py
fastmcp install claude-desktop acme_server.py
fastmcp install cursor acme_server.py -e .
```

使用 `fastmcp discover` 检查计算机上已配置的命名 MCP 服务器。

当目标是 octop-harness 集成时，将服务器添加到你的部署配置中的 `mcp_server_configs`，或在接口稳定之前继续使用 FastMCP CLI 命令进行开发。

### 7. 本地契约稳定后部署

对于托管托管，Prefect Horizon 是 FastMCP 最直接记录的路径。在部署之前：

```bash
fastmcp inspect acme_server.py:mcp
```

确保仓库包含：

- 带有 FastMCP 服务器对象的 Python 文件
- `requirements.txt` 或 `pyproject.toml`
- 部署所需的任何环境变量文档

对于通用 HTTP 托管，首先在本地验证 HTTP 传输，然后部署在任何可以暴露服务器端口的与 Python 兼容的平台上。

## 常见模式

### API 包装器模式

当将 REST 或 HTTP API 暴露为 MCP 工具时使用。

推荐的第一切片：

- 一个读取路径
- 一个列表/搜索路径
- 可选的健康检查

实现注意事项：

- 将认证保存在环境变量中，而不是硬编码
- 在一个助手中集中请求逻辑
- 用简洁的上下文暴露 API 错误
- 在返回之前规范化不一致的上游负载

从 `templates/api_wrapper.py` 开始。

### 数据库模式

当暴露安全的查询和检查能力时使用。

推荐的第一切片：

- `list_tables`
- `describe_table`
- 一个受约束的读取查询工具

实现注意事项：

- 默认为只读数据库访问
- 在早期版本中拒绝非 `SELECT` SQL
- 限制行数
- 返回行加上列名称

从 `templates/database_server.py` 开始。

### 文件处理器模式

当服务器需要根据 demand 检查或转换文件时使用。

推荐的第一切片：

- 总结文件内容
- 在文件内搜索
- 提取确定性元数据

实现注意事项：

- 接受显式文件路径
- 检查丢失的文件和编码失败
- 限制预览和结果计数
- 除非需要特定的外部工具，否则避免 shell 调用

从 `templates/file_processor.py` 开始。

## 质量门槛

在交付 FastMCP 服务器之前，验证以下所有内容：

- 服务器干净地导入
- `fastmcp inspect <file.py:mcp>` 成功
- `fastmcp list <server spec> --json` 成功
- 每个新工具至少有一个真实的 `fastmcp call`
- 环境变量已记录
- 工具表面足够小，无需猜测工作

## 故障排除

### FastMCP 命令丢失

在工作环境中安装包：

```bash
pip install fastmcp
fastmcp version
```

### `fastmcp inspect` 失败

检查：

- 文件导入没有导致崩溃的副作用
- FastMCP 实例在 `<file.py:object>` 中正确命名
- 模板的可选依赖已安装

### 工具在 Python 中工作但通过 CLI 不工作

运行：

```bash
fastmcp list server.py --json
fastmcp call server.py your_tool_name --json
```

这通常暴露命名不匹配、缺少必需参数或不可序列化的返回值。

### octop-harness 无法看到部署的服务器

服务器构建部分可能是正确的，而代理 MCP 配置不是。将服务器添加到 `mcp_server_configs` 并重新启动代理进程。

## 参考

有关 CLI 详细信息、安装目标和部署检查，请阅读 `references/fastmcp-cli.md`。
