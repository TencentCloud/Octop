---
name: nano-pdf
description: "通过 nano-pdf CLI（自然语言提示）编辑 PDF 文本/标题。"
version: 1.0.0
author: community
license: MIT
compatibility: linux, macos, windows
metadata:
  octop:
    label:
      zh: "PDF 编辑"
      en: "nano-pdf"
    summary:
      zh: "用自然语言提示修改 PDF 中的文字与标题。"
      en: "Edit PDF text and titles with natural-language prompts."
  harness:
    emoji: "📄"
    tags: [PDF, Documents, Editing, NLP, Productivity]
    homepage: https://pypi.org/project/nano-pdf/
---

# nano-pdf

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

使用自然语言指令编辑 PDF。指向页面并描述要更改的内容。

## 先决条件

```bash
# 使用 uv 安装（推荐）或 pip
uv pip install nano-pdf
```

## 用法

```bash
nano-pdf edit <file.pdf> <page_number> "<instruction>"
```

## 示例

```bash
# 更改第 1 页的标题
nano-pdf edit deck.pdf 1 "将标题更改为 'Q3 Results' 并修正副标题中的拼写错误"

# 更新特定页面上的日期
nano-pdf edit report.pdf 3 "将日期从 January 更新为 February 2026"

# 修复内容
nano-pdf edit contract.pdf 2 "将客户名称从 'Acme Corp' 更改为 'Acme Industries'"
```

## 注意事项

- 页码可能基于 0（从 0 开始计数）或基于 1（从 1 开始计数），具体取决于版本——如果编辑命中错误页面，请使用 ±1 重试
- 编辑后始终验证输出 PDF（使用 `read_file` 检查文件大小，或打开它）
- 该工具在底层使用 LLM——需要 API 密钥（检查 `nano-pdf --help` 以获取配置）
- 适用于文本更改；复杂的布局修改可能需要不同的方法
