"""Server-status plugin must report one consistent usage percent per bar."""

from __future__ import annotations

import importlib.util
from collections import namedtuple
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

sd = namedtuple("sdiskusage", ["total", "used", "free", "percent"])
svmem = namedtuple("svmem", ["total", "used", "available", "percent"])
sswap = namedtuple("sswap", ["total", "used", "free", "percent"])

# An ext4 volume with 5% reserved for root: ``used / total`` is 38.3 while the
# platform (and ``df``) reports 42.0 for the space an unprivileged user sees.
_DISK = sd(total=1_000_000_000, used=383_000_000, free=532_000_000, percent=42.0)


class _FakePsutil:
    def cpu_percent(self, interval: float | None = None) -> float:
        return 11.0

    def cpu_count(self, logical: bool = True) -> int:
        return 8 if logical else 4

    def cpu_freq(self) -> None:
        return None

    def virtual_memory(self) -> Any:
        return svmem(
            total=16_000_000_000, used=8_000_000_000, available=8_000_000_000, percent=50.0
        )

    def swap_memory(self) -> Any:
        return sswap(total=2_000_000_000, used=100_000_000, free=1_900_000_000, percent=5.0)

    def disk_usage(self, path: str) -> Any:
        return _DISK

    def boot_time(self) -> float:
        return 1_700_000_000.0


def _load_server_status():
    path = default_bundled_plugins_root() / "server-status" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_server_status", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _patched_module(monkeypatch):
    mod = _load_server_status()
    monkeypatch.setattr(mod, "psutil", _FakePsutil())
    return mod


def _collect(monkeypatch) -> dict[str, Any]:
    return _patched_module(monkeypatch)._collect()


def test_disk_percent_matches_the_platform_percentage(monkeypatch):
    data = _collect(monkeypatch)
    assert data["disk"]["percent"] == _DISK.percent


def test_summary_text_reports_the_platform_disk_percentage(monkeypatch):
    mod = _patched_module(monkeypatch)
    text = mod._text_summary(mod._collect())
    assert "磁盘 42%" in text
