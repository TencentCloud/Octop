# -*- coding: utf-8 -*-
"""Rename the remaining ``_invalid_transition`` call sites to their specific helper.

The old single helper covered three different semantics that now have distinct
error codes, so this is a per-line mapping (with an assertion that each target
line still looks like what we expect) rather than a blind replace-all.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PATH = Path(r"D:\nancc\octop\Octop-develop\src\octop\infra\projects\service.py")

# 1-based line -> replacement helper
TARGETS: dict[int, str] = {
    343: "_project_status_invalid",  # _assert_transition: project graph
    352: "_project_status_invalid",  # _assert_activation_ready: no members
    357: "_project_status_invalid",  # _assert_activation_ready: owner role
    395: "_member_invalid",  # remove_member: owner cannot be removed
    405: "_member_invalid",  # _assert_owner_role_untouched
    486: "_task_status_invalid",  # transition_task: task graph
}


def main() -> int:
    lines = PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = 0
    for line_no, helper in sorted(TARGETS.items()):
        idx = line_no - 1
        current = lines[idx]
        if "_invalid_transition" not in current:
            raise SystemExit(f"ABORT {line_no}: no _invalid_transition in {current!r}")
        lines[idx] = current.replace("_invalid_transition", helper, 1)
        changed += 1
        print(f"  {line_no}: {current.strip()[:70]} -> {helper}")
    PATH.write_text("".join(lines), encoding="utf-8", newline="")
    print(f"\nchanged {changed} call sites")

    text = PATH.read_text(encoding="utf-8")
    if "_invalid_transition" in text:
        raise SystemExit("ABORT: _invalid_transition still present")
    print("no _invalid_transition remains")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
