---
name: memory-management
description: Save and recall durable knowledge using the memory rules in the system prompt.
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

# Memory Management

Where memory is written is decided by the Memory section in the system prompt. This skill does not override that section. If workspace `AGENTS.md` still contains an older memory policy, the system prompt wins.

When structured memory is on, these tools are available:

- `memory_save(content, topic)`: one concise fact, preserving its scope. Confirm only after the tool succeeds.
- `memory_search`: look up history.
- `memory_get`: read a source returned by `memory_search`.

Do not store passwords, keys, or tokens. Leave session-only context in the chat history.
