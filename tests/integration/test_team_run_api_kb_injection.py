"""Where the KB archiver factory gets injected (T-71).

The tripwire this replaces counted **zero** production injectors (T-67 ④ measured 0:
T-45's archival hop was dead code in production because nothing ever handed
``write_artifact`` a factory). T-71 wired it, so the count is asserted to be exactly one
-- one place, so "two places deriving the same thing" cannot creep back in.
"""

from __future__ import annotations

from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "octop"


def test_the_kb_archiver_factory_has_exactly_one_production_injector() -> None:
    """原断言（T-67 ④ / 本卡之前）：生产注入点数量 == 0（``kb_archiver_factory`` 从无注入者）。

    Now: **exactly one** -- ``server.py``'s boot call passes it into the single
    ``bind_runtime`` call. ``run_service.py`` mentions the name as its own parameter,
    assignment and use site, which is not an injection; the assertion is about the
    *producer* side, so it filters to ``=`` call sites outside that module.
    """
    injectors: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        if path.name == "run_service.py":
            continue  # the seam's own parameter/assignment, not an injector
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "kb_archiver_factory=" in line:
                injectors.append(f"{path.relative_to(SOURCE_ROOT)}:{number}")
    assert len(injectors) == 1, injectors
    assert injectors[0].startswith("infra/server.py:"), injectors
