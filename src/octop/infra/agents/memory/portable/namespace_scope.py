"""portable 记忆迁移的**命名空间作用域**约束 —— 纯函数，零 IO。

``POST /api/agents/{agent_id}/memory/portable/adopt`` 是**既有已发布功能**，而它把三个
外部可控的值直接送进 octop-memory 的路径构造：

* 表单 ``target_namespace``
* 表单 ``target_host`` 里的 ``host:namespace``（`octop_memory …/adopter.py · @208-211`）
* **上传包内 ``manifest.json`` 的 ``agent_name``**（`…/adopter.py · agent_name = manifest.get(...) @252`
  → `_build_target_namespace @267-268`）—— 这条**不需要任何表单字段**即可命中

而 ``_resolve_target_db_path @53`` 把它拼成 ``~/.octop/agents/{名字}/memory.sqlite``，
紧接着 ``mkdir(parents=True, exist_ok=True) @295``。

⇒ 在本设计的方案 A（namespace 隔离）里，这是**四条写入路径之外的第 5 条**：任何拥有任一
agent 的用户都能把内容写进**不属于自己**的命名空间/目录（含路径穿越）。

本模块给出**唯一**的判定，供路由在调用 ``adopt()`` **之前**执行（写盘之前拦）。它不修
octop-memory（第三方包，不在本仓写区），只约束**喂给它的入参**。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from octop.infra.agents.memory.backend import agent_memory_namespace
from octop.infra.errors import ErrorCode, OctopError

#: 目标宿主取值域（闭集）。与 `octop_memory …/portable/models.py · HOST_KIND_* @30-32`
#: ＋ `HOST_KIND_OCTOPMEMORY` 同口径；**认不出的一律拒绝**，不退回默认
#: （对齐 `AGENTS.md`/SPEC 的「参数闭集校验，非法值显式拒绝并列出合法值」）。
HOST_KIND_AGENT = "agent"
ALLOWED_HOST_KINDS: frozenset[str] = frozenset({"agent", "openclaw", "hermes", "octopmemory"})

#: namespace 的最大长度（防御性上限；正常形如 ``agent_<id>`` / ``project_<id>``）。
MAX_NAMESPACE_LEN = 128

#: 允许的字符集：字母数字开头，随后字母数字 / ``_`` / ``.`` / ``-``。
#: **不含** 路径分隔符（``/`` ``\\``）、不含盘符与 UNC 前缀。
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: 包内 manifest 里会流进路径构造的字段（见模块 docstring 第三条通道）。
_MANIFEST_PATH_KEYS: tuple[str, ...] = ("agent_name", "source_namespace")


def split_host_spec(host_spec: str) -> tuple[str, str | None]:
    """``host`` / ``host:namespace`` → ``(host_kind, namespace | None)``。

    与 `octop_memory …/adopter.py · @208-213` **同语义**（``split(":", 1)`` + 小写化宿主名），
    这样路由的判定与 adopt 的实际取用永远是同一个值。
    """
    raw = str(host_spec or "")
    if ":" in raw:
        host_kind, namespace = raw.split(":", 1)
        return host_kind.strip().lower(), namespace or None
    return raw.strip().lower(), None


def namespace_is_well_formed(namespace: str) -> bool:
    """格式门：非空、长度上限、字符集、**无 ``..``**。

    ``..`` 单独判一次（字符集已排除 ``/``，但 ``..`` 本身仍在允许字符集内）。
    """
    value = str(namespace or "")
    if not value or len(value) > MAX_NAMESPACE_LEN:
        return False
    if ".." in value:
        return False
    return bool(_NAMESPACE_RE.match(value))


def allowed_agent_namespace(agent_id: str) -> str:
    """该 agent **自己的**命名空间 —— 真源 `infra/agents/memory/backend.py · agent_memory_namespace @21`。

    本模块**不另写** ``agent_`` 前缀（`backend.py @16` 是唯一权威；另一个 ``_MEMORY_NS_PREFIX``
    在 `api/common/memory_client.py @23`，但 ``infra/`` 不得 import ``api/``）。
    """
    return agent_memory_namespace(agent_id)


def _reject(message: str, *, status: int, code: ErrorCode) -> OctopError:
    return OctopError(code, message, status=status)


def _check_well_formed(namespace: str, *, source: str) -> None:
    if not namespace_is_well_formed(namespace):
        raise _reject(
            f"{source} 不是合法的命名空间：只允许字母数字与 `_ . -`（数字/字母开头），"
            f"不得含路径分隔符或 `..`，长度 ≤ {MAX_NAMESPACE_LEN}。",
            status=400,
            code=ErrorCode.SLASH_BAD_ARGS,
        )


def resolve_namespace_to_adopt(
    *,
    agent_id: str,
    target_host: str,
    target_namespace: str | None,
) -> tuple[str, str | None]:
    """校验并解析要喂给 ``adopt()`` 的 ``(host_kind, target_namespace)``。

    **保守默认（裁决口径）**：``host_kind == "agent"`` 时——也就是唯一会把文件写进
    Octop 自己的 ``~/.octop/agents/`` 树、进而能碰到方案 A 隔离命名空间的那条分支——
    adopt **只允许写进该 agent 自己的命名空间** ``agent_{agent_id}``；
    调用方**未指定**时由服务端**钉死**为该值（这样包内 ``manifest.agent_name``
    那条通道也一并失效，而不是只挡表单字段）。

    ``openclaw`` / ``hermes`` / ``octopmemory`` 的 namespace 落在 ``~/.octopmemory/`` /
    ``~/.openclaw/`` 下，**不在** Octop 的项目/团队命名空间空间里（项目记忆读的是
    host 工作区的 ``memory.sqlite``），因此仍允许自定义 —— 但一律过格式门，且
    ``manifest`` 那侧另由 :func:`assert_manifest_scope_is_safe` 兜住。

    :returns: ``(host_kind, namespace)``；``namespace`` 为 ``None`` 表示让 ``adopt()``
        用它的默认（仅外部宿主会出现）。
    :raises OctopError: 宿主名不在闭集 ⇒ 400；格式非法 ⇒ 400；越出该 agent 的命名空间 ⇒ 403。
    """
    host_kind, embedded = split_host_spec(target_host)
    if host_kind not in ALLOWED_HOST_KINDS:
        raise _reject(
            f"未知的目标宿主 {host_kind!r}；可用：{', '.join(sorted(ALLOWED_HOST_KINDS))}。",
            status=400,
            code=ErrorCode.SLASH_BAD_ARGS,
        )

    # 字段与 `host:namespace` 嵌入值**都**校验：当前 adopt 的优先级是「字段优先」，
    # 但把两个候选都过门，可以在优先级将来变化时仍然安全（也更便宜）。
    for candidate, source in (
        (target_namespace, "target_namespace"),
        (embedded, "target_host 的命名空间"),
    ):
        if candidate:
            _check_well_formed(candidate, source=source)

    own = allowed_agent_namespace(agent_id)

    if host_kind != HOST_KIND_AGENT:
        return host_kind, (target_namespace or embedded or None)

    for candidate in (target_namespace, embedded):
        if candidate and candidate != own:
            raise _reject(
                f"该端点只能把记忆写入它自己的命名空间 {own!r}（收到 {candidate!r}）。"
                "跨命名空间写入请走项目/团队记忆的正式写入路径，不要从这个端点绕行。",
                status=403,
                code=ErrorCode.FORBIDDEN,
            )
    return host_kind, own


def assert_manifest_scope_is_safe(manifest: Mapping[str, Any]) -> None:
    """校验包内 manifest 里会流进路径构造的字段。

    为什么必须查**包**而不是只查表单：`adopter.py · @252` 在调用方没给 namespace 时，
    会用 ``manifest["agent_name"]``（缺省再退回 ``source_namespace``）生成目标 namespace
    ⇒ 一个精心构造的 ``.hmpkg`` **不需要任何表单字段**就能决定写入目录
    （含 ``../`` 穿越）。``read_manifest`` 读的就是上传 zip 里的 ``manifest.json``。
    """
    for key in _MANIFEST_PATH_KEYS:
        raw = manifest.get(key)
        if raw in (None, ""):
            continue
        _check_well_formed(str(raw), source=f"包内 manifest 的 {key}")


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
