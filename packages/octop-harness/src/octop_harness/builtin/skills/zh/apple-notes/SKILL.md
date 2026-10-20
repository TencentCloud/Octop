---
name: apple-notes
description: "通过 memo CLI 管理 Apple Notes：创建、搜索、编辑。"
version: 1.0.0
author: Octop
license: MIT
compatibility: macos only
metadata:
  octop:
    label:
      zh: "备忘录"
      en: "Apple Notes"
    summary:
      zh: "在 macOS 上创建、搜索和编辑 Apple 备忘录。"
      en: "Create, search, and edit Apple Notes on macOS."
  harness:
    emoji: "📝"
    tags: [Notes, Apple, macOS, note-taking]
    related_skills: [obsidian]
prerequisites:
  commands: [memo]
---

# Apple Notes

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

使用 `memo` 直接从终端管理 Apple Notes。笔记通过 iCloud 在所有 Apple 设备间同步。

## 先决条件

- **macOS** 带 Notes.app
- 安装：`brew tap antoniorodr/memo && brew install antoniorodr/memo/memo`
- 出现提示时授予 Notes.app 自动化访问权限（系统设置 → 隐私 → 自动化）

## 何时使用

- 用户要求创建、查看或搜索 Apple Notes
- 将信息保存到 Notes.app 以实现跨设备访问
- 将笔记组织到文件夹中
- 将笔记导出为 Markdown/HTML

## 何时不使用

- Obsidian  vault 管理 → 使用 `obsidian` 技能
- Bear Notes → 独立应用（此处不支持）
- 快速仅代理笔记 → 改用 `memory_store`

## 快速参考

### 查看笔记

```bash
memo notes                        # 列出所有笔记
memo notes -f "Folder Name"       # 按文件夹过滤
memo notes -s "query"             # 搜索笔记（模糊）
```

### 创建笔记

```bash
memo notes -a                     # 交互式编辑器
memo notes -a "Note Title"        # 快速添加带标题的笔记
```

### 编辑笔记

```bash
memo notes -e                     # 交互式选择编辑
```

### 删除笔记

```bash
memo notes -d                     # 交互式选择删除
```

### 移动笔记

```bash
memo notes -m                     # 移动笔记到文件夹（交互式）
```

### 导出笔记

```bash
memo notes -ex                    # 导出为 HTML/Markdown
```

## 限制

- 无法编辑包含图像或附件的笔记
- 交互式提示需要终端访问（如需要，使用 pty=true）
- 仅 macOS——需要 Apple Notes.app

## 规则

1. 当用户需要跨设备同步时，优先使用 Apple Notes（iPhone/iPad/Mac）
2. 对于不需要同步的代理内部笔记，使用 `memory_store`
3. 对于 Markdown 原生知识管理，使用 `obsidian` 技能
