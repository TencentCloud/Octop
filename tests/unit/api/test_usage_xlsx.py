"""``usage_xlsx`` timezone handling: unresolvable server zones must not break export."""

from __future__ import annotations

from octop.api.common.usage_xlsx import build_usage_xlsx


def _build(timezone: str) -> bytes:
    return build_usage_xlsx(
        rows=[],
        by_day=[],
        by_agent=[],
        by_model=[],
        agent_names={},
        usernames={},
        timezone=timezone,
        locale="zh",
    )


def test_build_usage_xlsx_falls_back_for_unresolvable_timezone() -> None:
    assert isinstance(_build("Asia/Shanghai"), bytes)
    assert isinstance(_build("not-a-zone"), bytes)
    # ``zoneinfo`` raises ValueError, not ZoneInfoNotFoundError, for keys it refuses
    # to resolve at all — the export used to return 500 on these.
    assert isinstance(_build("/etc/localtime"), bytes)
    assert isinstance(_build("./Asia/Shanghai"), bytes)
