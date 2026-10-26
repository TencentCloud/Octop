---
name: memory-management
description: 按系统提示中的记忆规则保存和召回长期知识。
metadata:
  octop:
    label:
      zh: "记忆管理"
      en: "Memory"
    summary:
      zh: "按系统提示中的记忆规则保存与召回长期知识。"
      en: "Save and recall durable knowledge using the system-prompt memory rules."
  harness:
    emoji: "💾"

---

# 记忆管理

记忆写到哪里，以系统提示中的「记忆」规则为准。本技能不覆盖该规则。工作区 `AGENTS.md` 里如果还有旧的记忆写法，同样以系统提示为准。

结构化记忆开启时可以使用：

- `memory_save(content, topic)`：一条简洁事实，保留作用范围。工具成功后才能确认已记住。
- `memory_search`：查找历史。
- `memory_get`：查看 `memory_search` 返回的来源。

密码、密钥、Token 不进入记忆。仅限当前对话的内容留在聊天记录里。
