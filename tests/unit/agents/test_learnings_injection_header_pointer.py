"""The injected header points at the file it promises -- checked, not assumed (T-46).

原断言（本文件建立时，T-46 未落地）：**当前为红** ⇒ **已翻转（原：当前为红）**。header 逐字说
「完整版见 team/LEARNINGS.md」，而权威写入路径是
`{host_workspace}/.octop/team/LEARNINGS.md`（``learnings.py`` 的 ``TEAM_DIR_PARTS``），
host 的内容根是 ``{host_workspace}``（``BackendWorkspace(..., workspace_dir, ...)``，
``.octop`` 是系统树）。⇒ 那句话指向一个**从未被写入的位置**。

T-46 按 (甲) 把 header 改成 `.octop/team/LEARNINGS.md` 之后，本断言**转绿**
（**翻转，不删除**；旧形态即上面这段 docstring 记录的"引用路径 == 无前缀相对路径"）。
"""

from __future__ import annotations

import re
from pathlib import Path

from octop.infra.agents.teams.learnings import INJECTION_HEADER, team_learnings_path

#: `…完整版见 <path>…` —— 只取到第一个分隔符，避免把整句吃进来。
_REFERENCE_RE = re.compile(r"见\s*([^\s，,；;）)]+)")


def test_the_injection_header_points_at_a_path_that_exists() -> None:
    """The header's pointer, resolved the way the host resolves it, is the real file.

    Deliberately **not** a filesystem probe on a temp directory: an empty workspace
    would make any pointer look broken, so the red would not mean anything. The check
    compares the referenced path against the authoritative path *expressed relative to
    the same root* -- it fails if and only if the header names a different location.
    """
    match = _REFERENCE_RE.search(INJECTION_HEADER)
    assert match, INJECTION_HEADER
    referenced = match.group(1)

    workspace = Path("/ws")  # symbolic: the host's content root (no IO)
    expected = team_learnings_path(workspace).relative_to(workspace).as_posix()

    assert referenced == expected, (
        f"header points at {referenced!r}, the authoritative file is {expected!r}"
    )
