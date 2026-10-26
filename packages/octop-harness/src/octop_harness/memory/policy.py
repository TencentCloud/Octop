"""Runtime memory policy injected into the compiled system prompt.

Workspace ``AGENTS.md`` does not own this policy. The same agent can have
structured memory on or off, and already-copied workspace files keep whatever
rules they were seeded with. The compiled prompt is rebuilt when that switch
changes, so it is the instruction the model should follow.
"""

from __future__ import annotations

from typing import Literal

ManualDocumentPolicy = Literal["auto", "user", "agent"]

_PRIORITY_ZH = "本段优先于工作区 AGENTS.md、BOOTSTRAP.md、记忆技能, 以及 USER.md / MEMORY.md 里关于如何更新记忆的说明。"
_PRIORITY_EN = (
    "This section overrides memory-update instructions in workspace AGENTS.md, "
    "BOOTSTRAP.md, the memory skill, and comments inside USER.md / MEMORY.md."
)

_ZH_ON = "\n".join(
    (
        "## 记忆",
        "",
        _PRIORITY_ZH,
        "",
        "USER.md 和 MEMORY.md 由用户在记忆页手动维护, Agent 只读。"
        "每个会话开始时加载一次全文, 之后复用该快照; 修改对新会话生效。",
        "",
        "用户说「记住」时调用 memory_save, 成功后才能确认已记住。"
        "每次保存一条简洁事实, 保留作用范围和限定条件。"
        "密码、密钥、Token 不进入记忆。临时闲聊留给后台提炼, 不要主动保存。",
        "",
        "需要更多历史时调用 memory_search, 再用 memory_get 查看来源。"
        "手动文档优先于召回记忆。发现冲突要告诉用户, 不能改这两份文件, "
        "也不能把冲突的旧记忆当作当前事实。",
    )
)

_ZH_OFF = "\n".join(
    (
        "## 记忆",
        "",
        _PRIORITY_ZH,
        "",
        "结构化记忆已关闭, 不要调用 memory_save、memory_search 或 memory_get。"
        "USER.md 和 MEMORY.md 仍在每个会话开始时加载一次全文, 之后复用该快照; "
        "写入对新会话生效。",
        "",
        "用户要求记住、改称呼或改沟通偏好时, 用 edit_file 或 write_file 修改这两份文件。"
        "档案、称呼和沟通偏好写入 USER.md。"
        "需要每次对话都参考的事实、决定和约定写入 MEMORY.md。先读再改。"
        "不要删除或移动这两个文件; 清空时写入空内容。"
        "密码、密钥、Token 不写入。临时闲聊不要写入。",
        "",
        "当前会话仍使用开始时的快照。写入成功只说明文件已更新, 新内容从下一个会话进入上下文。",
    )
)

_EN_ON = "\n".join(
    (
        "## Memory",
        "",
        _PRIORITY_EN,
        "",
        "USER.md and MEMORY.md are maintained manually by the user on the memory page. "
        "Agents are read-only. Each session loads the full text once and then reuses "
        "that snapshot; edits apply to new sessions.",
        "",
        "When the user asks you to remember something, call memory_save and confirm "
        "only after it succeeds. Save one concise fact per call, preserving its scope "
        "and qualifiers. Do not store passwords, keys, or tokens. Leave transient chat "
        "to background distillation; do not save it yourself.",
        "",
        "For additional history, call memory_search and then memory_get to inspect "
        "sources. Manual documents outrank recalled memory. Tell the user about "
        "conflicts, leave both files unchanged, and do not present a conflicting old "
        "memory as a current fact.",
    )
)

_EN_OFF = "\n".join(
    (
        "## Memory",
        "",
        _PRIORITY_EN,
        "",
        "Structured memory is off. Do not call memory_save, memory_search, or "
        "memory_get. USER.md and MEMORY.md are still loaded in full once per session "
        "and then reused; writes apply to new sessions.",
        "",
        "When the user asks you to remember something, or to change how they are "
        "addressed or how you should communicate, edit these files with edit_file or "
        "write_file. Put identity, names, and communication preferences in USER.md. "
        "Put facts, decisions, and agreements that every conversation should see in "
        "MEMORY.md. Read the file before editing it. Do not delete or move either "
        "file; clear one by writing empty content. Do not store passwords, keys, or "
        "tokens. Do not write down transient chat.",
        "",
        "The current session keeps its opening snapshot. A successful write means the "
        "file changed; the new text enters context on the next session.",
    )
)


_ZH_USER_ONLY = "\n".join(
    (
        "## 记忆",
        "",
        _PRIORITY_ZH,
        "",
        "结构化记忆已关闭, 这两份文档仍由你手动维护, Agent 只读。",
        "不要调用 memory_save、memory_search 或 memory_get, 也不要修改 USER.md 或 MEMORY.md。",
        "需要改档案或强记忆时, 请用户到记忆页编辑。",
        "每个会话开始时加载一次全文, 之后复用该快照; 修改对新会话生效。",
    )
)

_ZH_AGENT_WITH_MEMORY = "\n".join(
    (
        "## 记忆",
        "",
        _PRIORITY_ZH,
        "",
        "结构化记忆已开启, 同时允许修改 USER.md 和 MEMORY.md。",
        "用户说「记住」时仍调用 memory_save, 成功后才能确认已记住。",
        "不要用改这两份文件代替 memory_save。",
        "只有用户明确要求修改档案或强记忆时, 才用 edit_file 或 write_file 改对应文件。",
        "先读再改。不要删除或移动这两个文件; 清空时写入空内容。",
        "手动文档优先于召回记忆。发现冲突要告诉用户, 不能把冲突的旧记忆当作当前事实。",
        "密码、密钥、Token 不进入记忆。临时闲聊留给后台提炼。",
        "每个会话开始时加载一次全文, 之后复用该快照; 文件修改对新会话生效。",
    )
)

_EN_USER_ONLY = "\n".join(
    (
        "## Memory",
        "",
        _PRIORITY_EN,
        "",
        "Structured memory is off, and USER.md / MEMORY.md stay user-maintained. Agents are read-only.",
        "Do not call memory_save, memory_search, or memory_get, and do not edit USER.md or MEMORY.md.",
        "When the profile or strong memory should change, ask the user to edit it on the memory page.",
        "Each session loads the full text once and then reuses that snapshot; edits apply to new sessions.",
    )
)

_EN_AGENT_WITH_MEMORY = "\n".join(
    (
        "## Memory",
        "",
        _PRIORITY_EN,
        "",
        "Structured memory is on, and edits to USER.md and MEMORY.md are also allowed.",
        "When the user asks you to remember something, still call memory_save and "
        "confirm only after it succeeds. Do not edit those files instead of memory_save.",
        "Edit USER.md or MEMORY.md only when the user explicitly asks to change the "
        "profile or strong memory. Read the file first. Do not delete or move either "
        "file; clear one by writing empty content.",
        "Manual documents outrank recalled memory. Tell the user about conflicts, and "
        "do not present a conflicting old memory as a current fact.",
        "Do not store passwords, keys, or tokens. Leave transient chat to background distillation.",
        "Each session loads the full text once and then reuses that snapshot; file edits apply to new sessions.",
    )
)


_ZH_PROMPTS = {
    "on": _ZH_ON,
    "off": _ZH_OFF,
    "user": _ZH_USER_ONLY,
    "agent": _ZH_AGENT_WITH_MEMORY,
}
_EN_PROMPTS = {
    "on": _EN_ON,
    "off": _EN_OFF,
    "user": _EN_USER_ONLY,
    "agent": _EN_AGENT_WITH_MEMORY,
}


def manual_documents_locked(*, memory_enabled: bool, policy: str) -> bool:
    """Whether agent file tools must leave USER.md and MEMORY.md unchanged.

    ``auto`` follows structured memory: locked while it is on, editable when it
    is off. ``user`` keeps the files owner-maintained. ``agent`` allows edits
    even while structured memory is on.
    """
    if policy == "user":
        return True
    if policy == "agent":
        return False
    return memory_enabled


def render_memory_policy_prompt(
    *,
    language: str,
    memory_enabled: bool,
    policy: str = "auto",
) -> str:
    """Return the memory policy for the compiled system prompt."""
    locked = manual_documents_locked(memory_enabled=memory_enabled, policy=policy)
    if locked and memory_enabled:
        key = "on"
    elif locked:
        key = "user"
    elif memory_enabled:
        key = "agent"
    else:
        key = "off"
    prompts = _EN_PROMPTS if language == "en" else _ZH_PROMPTS
    return prompts[key]
