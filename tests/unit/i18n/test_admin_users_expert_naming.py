"""Admin Users UI must call agents 「专家」 / Experts (issue #155)."""

from __future__ import annotations

import json
from pathlib import Path


def test_admin_users_agent_column_uses_expert_terminology() -> None:
    repo = Path(__file__).resolve().parents[3]
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    assert zh["adminUsers"]["colAgents"] == "专家"
    assert zh["adminUsers"]["agentsDrawerTitle"] == "{{username}} 的专家"
    assert zh["adminUsers"]["noAgents"] == "该用户暂无专家"
    assert en["adminUsers"]["colAgents"] == "Experts"
    assert en["adminUsers"]["agentsDrawerTitle"] == "{{username}}'s experts"
    assert en["adminUsers"]["noAgents"] == "This user has no experts yet"
