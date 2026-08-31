"""tests/unit/mobile/test_docker_install.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from octop.infra.mobile import docker_install
from octop.infra.mobile.docker_install import (
    _merge_registry_mirror,
    _probe_tencent_mirror,
    select_download_source,
)


def _with_measure(delays: dict[str, float | None]):
    def deco(fn):
        async def wrapper():
            async def fake(url: str) -> float | None:
                return delays[url]

            with patch.object(docker_install, "_measure_source_delay", fake):
                return await fn()

        wrapper.__name__ = fn.__name__
        return wrapper

    return deco


@pytest.mark.asyncio
@_with_measure(
    {
        "https://download.docker.com": 0.1,
        "https://mirrors.aliyun.com/docker-ce": 0.4,
        "https://mirrors.tencent.com/docker-ce": 0.5,
        "https://mirrors.163.com/docker-ce": 0.6,
        "https://mirrors.cernet.edu.cn/docker-ce": 0.7,
    }
)
async def test_select_download_source_official_wins_no_override() -> None:
    source, delay = await select_download_source()
    assert source is None  # official wins → no DOWNLOAD_URL override
    assert delay == pytest.approx(0.1)


@pytest.mark.asyncio
@_with_measure(
    {
        "https://download.docker.com": 0.9,
        "https://mirrors.aliyun.com/docker-ce": 0.2,
        "https://mirrors.tencent.com/docker-ce": 0.5,
        "https://mirrors.163.com/docker-ce": 0.6,
        "https://mirrors.cernet.edu.cn/docker-ce": 0.7,
    }
)
async def test_select_download_source_mirror_wins() -> None:
    source, delay = await select_download_source()
    assert source == "https://mirrors.aliyun.com/docker-ce"
    assert delay == pytest.approx(0.2)


@pytest.mark.asyncio
@_with_measure(
    {
        "https://download.docker.com": None,
        "https://mirrors.aliyun.com/docker-ce": None,
        "https://mirrors.tencent.com/docker-ce": None,
        "https://mirrors.163.com/docker-ce": None,
        "https://mirrors.cernet.edu.cn/docker-ce": None,
    }
)
async def test_select_download_source_all_unreachable_falls_back() -> None:
    source, delay = await select_download_source()
    assert source is None
    assert delay is None


def test_merge_registry_mirror_fresh_file(tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    assert _merge_registry_mirror(daemon, "https://mirror.example/") is True
    data = json.loads(daemon.read_text(encoding="utf-8"))
    assert data["registry-mirrors"] == ["https://mirror.example/"]


def test_merge_registry_mirror_backs_up_existing(tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    daemon.write_text('{"log-level": "warn"}', encoding="utf-8")
    assert _merge_registry_mirror(daemon, "https://mirror.example/") is True
    backup = tmp_path / "daemon.json.backup"
    assert json.loads(backup.read_text(encoding="utf-8")) == {"log-level": "warn"}
    data = json.loads(daemon.read_text(encoding="utf-8"))
    assert data["registry-mirrors"] == ["https://mirror.example/"]
    assert data["log-level"] == "warn"  # other keys preserved


def test_merge_registry_mirror_skips_when_configured(tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    daemon.write_text('{"registry-mirrors": ["https://old/"]}', encoding="utf-8")
    assert _merge_registry_mirror(daemon, "https://mirror.example/") is False
    assert json.loads(daemon.read_text(encoding="utf-8")) == {"registry-mirrors": ["https://old/"]}


def test_merge_registry_mirror_skips_corrupt_file(tmp_path: Path) -> None:
    daemon = tmp_path / "daemon.json"
    daemon.write_text("{not json", encoding="utf-8")
    assert _merge_registry_mirror(daemon, "https://mirror.example/") is False
    assert daemon.read_text(encoding="utf-8") == "{not json"  # left untouched


@pytest.mark.asyncio
async def test_probe_tencent_mirror_unreachable() -> None:
    # 127.0.0.1:1 → connection refused → probe returns False quickly.
    with patch.object(docker_install, "_TENCENT_MIRROR_HOST", "127.0.0.1"):
        assert await _probe_tencent_mirror() is False


@pytest.mark.asyncio
async def test_install_mobile_stream_auto_installs_docker_then_proceeds() -> None:
    from octop.infra.mobile import setup as mobile_setup

    async def fake_auto_install(*, locale: str = "en"):
        yield "docker install log line"

    class FakeProc:
        def __init__(self) -> None:
            self.stdout = self
            self._lines = [b"container install log line"]

        async def readline(self) -> bytes:
            return self._lines.pop(0) if self._lines else b""

        async def wait(self) -> int:
            return 0

    async def fake_exec(*args: object, **kwargs: object) -> FakeProc:
        return FakeProc()

    async def collect():
        events = []
        async for evt in mobile_setup.install_mobile_stream(locale="en"):
            events.append(evt)
        return events

    script = mobile_setup.bundled_scripts_dir() / "install.sh"
    with (
        patch.object(mobile_setup, "_docker_available", return_value=False),
        patch.object(mobile_setup, "platform") as fake_platform,
        patch.object(mobile_setup, "can_install_without_password", return_value=True),
        patch.object(mobile_setup, "auto_install_docker_stream", side_effect=fake_auto_install),
        patch.object(mobile_setup, "docker_daemon_ready", return_value=True),
        patch.object(mobile_setup, "bundled_scripts_dir", return_value=script.parent),
        patch.object(mobile_setup.asyncio, "create_subprocess_exec", new=fake_exec),
    ):
        fake_platform.system.return_value = "Linux"
        events = await collect()

    logs = [
        json.loads(e.removeprefix("data: ").strip())["log"]
        for e in events
        if "log" in json.loads(e.removeprefix("data: ").strip())
    ]
    assert any("docker install log line" in line for line in logs)
    done = [json.loads(e.removeprefix("data: ").strip()) for e in events][-1]
    assert done.get("done") is True


@pytest.mark.asyncio
async def test_install_mobile_stream_auto_install_fails_reports_docker_missing() -> None:
    from octop.infra.mobile import setup as mobile_setup

    async def fake_auto_install(*, locale: str = "en"):
        yield "failed log"

    async def collect():
        events = []
        async for evt in mobile_setup.install_mobile_stream(locale="en"):
            events.append(evt)
        return events

    with (
        patch.object(mobile_setup, "_docker_available", return_value=False),
        patch.object(mobile_setup, "platform") as fake_platform,
        patch.object(mobile_setup, "can_install_without_password", return_value=True),
        patch.object(mobile_setup, "auto_install_docker_stream", side_effect=fake_auto_install),
        patch.object(mobile_setup, "docker_daemon_ready", return_value=False),
    ):
        fake_platform.system.return_value = "Linux"
        events = await collect()

    last = [json.loads(e.removeprefix("data: ").strip()) for e in events][-1]
    assert last.get("done") is False
    assert last.get("error") == "docker_missing"


@pytest.mark.asyncio
async def test_install_mobile_stream_no_sudo_reports_docker_missing() -> None:
    from octop.infra.mobile import setup as mobile_setup

    async def collect():
        events = []
        async for evt in mobile_setup.install_mobile_stream(locale="en"):
            events.append(evt)
        return events

    with (
        patch.object(mobile_setup, "_docker_available", return_value=False),
        patch.object(mobile_setup, "platform") as fake_platform,
        patch.object(mobile_setup, "can_install_without_password", return_value=False),
    ):
        fake_platform.system.return_value = "Linux"
        events = await collect()

    last = [json.loads(e.removeprefix("data: ").strip()) for e in events][-1]
    assert last.get("done") is False
    assert last.get("error") == "docker_missing"
