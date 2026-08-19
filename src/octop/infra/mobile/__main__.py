"""CLI entry: ``python -m octop.infra.mobile <config.json>`` (install.sh hook)."""

from __future__ import annotations

import sys
from pathlib import Path

from octop.infra.mobile.config_probe import persist_mobile_probe


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m octop.infra.mobile <config.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    result = persist_mobile_probe(path)
    print(f"mobile: enabled={result.enabled} backend={result.backend}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
