---
name: memory-management
description: 通过 octop-memory 保存和召回长期知识，区分用户手动维护的 MEMORY.md 与工作区配置。
metadata:
  octop:
    label:
      zh: "记忆管理"
      en: "Memory"
    summary:
      zh: "通过 octop-memory 保存与召回记忆，区分强记忆和工作区配置。"
      en: "Save and recall octop-memory; distinguish strong memory from workspace configuration."
  harness:
    emoji: "💾"

---

# 记忆管理

遵循工作区 `AGENTS.md` 中的记忆规则。工作区上下文在每个会话开始时加载一次，后续复用 checkpoint 中的快照；文档修改对新会话生效。

## 文件说明

| 位置 | 用途 | 如何更新 |
|------|------|----------|
| octop-memory | 长期事实、偏好、决策和教训 | `memory_save`；后台对话提炼 |
| `MEMORY.md` | 会话中始终参考的强记忆 | 用户手动编辑，Agent 不修改 |
| `USER.md` | 用户与 Agent 档案 | 用户手动编辑，初始化时 Agent 也只读 |
| `AGENTS.md` | 工作区配置 | 用户明确要求修改配置 |

不使用文件工具或 Shell 创建、修改、追加、覆盖或删除 `MEMORY.md` 或 `USER.md`，也不使用其他 Markdown 文件代替普通记忆。

## 保存与召回

1. 用户要求记住时，调用 `memory_save`，每次保存一条简洁事实，保留作用范围和限定条件。工具成功后才能确认已记住。
2. 工具不可用或保存失败时，如实说明，不改写工作区文件。
3. 用 `memory_search` 查找相关历史，再用 `memory_get` 查看来源。强记忆已在当前会话上下文中。
4. 用户明确要求修改 `AGENTS.md` 配置时，先读取指定文档，再精确编辑相关部分。

## 什么不应该放入记忆

- 秘密/API 密钥/凭证。如果被要求，拒绝。
- 仅限会话的上下文（用户*当前*的问题）。那属于聊天历史；记忆是用于应该持久化的东西。
- 大量逐字记录的文字记录。总结。

## 冲突处理

以当前用户要求和已核实证据为准，过时的记忆事实仅供参考。用户手动维护的 `MEMORY.md` 由用户自行修改。
