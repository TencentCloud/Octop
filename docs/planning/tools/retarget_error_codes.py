# -*- coding: utf-8 -*-
"""Point the project tests at the new entity-specific error codes.

The old assertions used the generic ``FORBIDDEN`` / ``NOT_FOUND`` and one shared
``PROJECT_INVALID_TRANSITION``. Those now split into distinct codes, so this is
an explicit per-line mapping with a guard on each target line.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(r"D:\nancc\octop\Octop-develop\tests\unit\projects")

# file -> {1-based line: (expected_current, replacement)}
PLAN: dict[str, dict[int, tuple[str, str]]] = {
    "test_project_service.py": {
        317: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),  # viewer writes
        327: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),  # admin archives
        354: ("ErrorCode.NOT_FOUND", "ErrorCode.PROJECT_NOT_FOUND"),
        371: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_STATUS_INVALID"),
        384: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_STATUS_INVALID"),
        385: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_FORBIDDEN"),
        419: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_STATUS_INVALID"),
        434: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_STATUS_INVALID"),
        452: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_MEMBER_INVALID"),
        465: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_MEMBER_INVALID"),
        494: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),  # viewer add_member
        547: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),  # admin deletes
    },
    "test_project_tasks.py": {
        172: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),  # viewer create
        261: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_TASK_STATUS_INVALID"),
        285: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_TASK_STATUS_INVALID"),
        296: ("ErrorCode.PROJECT_INVALID_TRANSITION", "ErrorCode.PROJECT_TASK_STATUS_INVALID"),
        370: ("ErrorCode.NOT_FOUND", "ErrorCode.PROJECT_TASK_NOT_FOUND"),
        380: ("ErrorCode.NOT_FOUND", "ErrorCode.PROJECT_TASK_NOT_FOUND"),
        423: ("ErrorCode.FORBIDDEN", "ErrorCode.PROJECT_ROLE_FORBIDDEN"),
    },
}


def main() -> int:
    total = 0
    for name, targets in PLAN.items():
        path = ROOT / name
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for line_no, (expected, replacement) in sorted(targets.items()):
            idx = line_no - 1
            current = lines[idx]
            if expected not in current:
                raise SystemExit(f"ABORT {name}:{line_no}: expected {expected!r} in {current!r}")
            lines[idx] = current.replace(expected, replacement, 1)
            total += 1
            print(f"  {name}:{line_no}  {expected} -> {replacement}")
        path.write_text("".join(lines), encoding="utf-8", newline="")
    print(f"\nchanged {total} assertions")
    leftover = [
        p.name
        for p in ROOT.glob("test_project_*.py")
        if "PROJECT_INVALID_TRANSITION" in p.read_text(encoding="utf-8")
    ]
    if leftover:
        raise SystemExit(f"ABORT: stale code still referenced in {leftover}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
