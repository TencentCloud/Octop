"""portable 记忆迁移的域内约束（纯函数）。

`namespace_scope` 是**唯一**的命名空间作用域判定，供
`api/routers/memory_portable.py` 在调用 octop-memory 的 ``adopt()`` **之前**执行 ——
写盘之前拦，理由见该模块 docstring（第 5 条写入路径）。
"""

from __future__ import annotations

from octop.infra.agents.memory.portable.namespace_scope import (
    ALLOWED_HOST_KINDS,
    HOST_KIND_AGENT,
    MAX_NAMESPACE_LEN,
    allowed_agent_namespace,
    assert_manifest_scope_is_safe,
    namespace_is_well_formed,
    resolve_namespace_to_adopt,
    split_host_spec,
)

__all__ = [
    "ALLOWED_HOST_KINDS",
    "HOST_KIND_AGENT",
    "MAX_NAMESPACE_LEN",
    "allowed_agent_namespace",
    "assert_manifest_scope_is_safe",
    "namespace_is_well_formed",
    "resolve_namespace_to_adopt",
    "split_host_spec",
]
