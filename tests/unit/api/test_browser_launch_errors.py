"""Browser launch diagnostics without starting Chromium or changing host policy."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, call

import pytest

from octop.api.routers.browser.harness import resolve_harness_session
from octop.api.routers.browser.stream import run_browser_stream_session
from octop.infra.errors import ErrorCode, OctopError

_SANDBOX_ERROR = (
    "Chromium exited: No usable sandbox! If you are running on Ubuntu 23.10+ "
    "or another Linux distro that has disabled unprivileged user namespaces with AppArmor, "
    "see the documentation.\nLong Chromium stack trace"
)
_SANDBOX_DOCS = (
    "https://chromium.googlesource.com/chromium/src/+/main/docs/security/"
    "apparmor-userns-restrictions.md"
)


@pytest.fixture
def browser_launch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    create = AsyncMock()
    prepare = AsyncMock()
    registry: dict[str, Any] = {}
    modules = {
        "octop_browser": SimpleNamespace(BrowserSession=SimpleNamespace(create=create)),
        "octop_browser.tool_interface": SimpleNamespace(_registry=registry),
        "octop_browser.profile": SimpleNamespace(ProfileManager=Mock()),
        "octop_browser.settings": SimpleNamespace(
            settings=SimpleNamespace(profiles_dir=str(tmp_path)),
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr("octop.infra.browser.setup.prepare_harness_profile_for_launch", prepare)
    monkeypatch.setattr("octop.infra.browser.setup.resolve_browser_display", lambda: None)
    return SimpleNamespace(create=create, prepare=prepare, registry=registry)


@pytest.mark.parametrize("retry", [False, True])
async def test_sandbox_launch_failure_has_actionable_diagnostic(browser_launch: Any, retry: bool):
    failure = RuntimeError(_SANDBOX_ERROR)
    browser_launch.create.side_effect = (
        [RuntimeError("ProcessSingleton"), failure] if retry else failure
    )

    with pytest.raises(OctopError) as caught:
        await resolve_harness_session("user-1")

    error = caught.value
    assert error.code.value == "BROWSER_SANDBOX_UNAVAILABLE"
    assert error.status == 503
    assert error.__cause__ is failure
    assert "AppArmor" in str(error)
    assert "Chrome/Chromium" in str(error)
    assert _SANDBOX_DOCS in str(error)
    assert "Long Chromium stack trace" not in str(error)
    assert "--no-sandbox" not in str(error)
    assert browser_launch.create.await_count == (2 if retry else 1)
    assert browser_launch.registry == {}
    expected_prepares = [call("user-1")]
    if retry:
        expected_prepares.append(call("user-1", force_recover=True))
    assert browser_launch.prepare.await_args_list == expected_prepares
    assert "沙箱" in error.to_envelope(locale="zh")["error"]["message"]


async def test_sandbox_error_does_not_trigger_profile_recovery(browser_launch: Any):
    browser_launch.create.side_effect = RuntimeError(_SANDBOX_ERROR + "\nprofile directory")

    with pytest.raises(OctopError) as caught:
        await resolve_harness_session("user-1")

    assert caught.value.code.value == "BROWSER_SANDBOX_UNAVAILABLE"
    browser_launch.create.assert_awaited_once()
    browser_launch.prepare.assert_awaited_once_with("user-1")


@pytest.mark.parametrize("retry", [False, True])
async def test_unrelated_launch_failure_keeps_existing_error(browser_launch: Any, retry: bool):
    failure = RuntimeError("unrelated browser failure")
    browser_launch.create.side_effect = (
        [RuntimeError("ProcessSingleton"), failure] if retry else failure
    )

    with pytest.raises(OctopError) as caught:
        await resolve_harness_session("user-1")

    assert caught.value.code is ErrorCode.INTERNAL_ERROR
    assert caught.value.status == 503
    assert (
        str(caught.value) == "failed to attach browser profile 'user-1': unrelated browser failure"
    )
    assert caught.value.__cause__ is failure


async def test_profile_recovery_still_registers_session(browser_launch: Any):
    session = object()
    browser_launch.create.side_effect = [RuntimeError("ProcessSingleton"), session]

    assert await resolve_harness_session("user-1") is session
    assert browser_launch.registry == {"user-1": session}


async def test_browser_stream_sends_sandbox_hint_to_client(browser_launch: Any):
    browser_launch.create.side_effect = RuntimeError(_SANDBOX_ERROR)
    send = AsyncMock()
    receive = AsyncMock()

    await run_browser_stream_session(
        send_json=send,
        is_connected=lambda: True,
        receive_text=receive,
        user_id=1,
        start_msg={"type": "start"},
    )

    payloads = [entry.args[0] for entry in send.await_args_list]
    assert payloads[0]["type"] == "error"
    assert "AppArmor" in payloads[0]["message"]
    assert _SANDBOX_DOCS in payloads[0]["message"]
    assert "Long Chromium stack trace" not in payloads[0]["message"]
    assert payloads[1] == {"type": "status", "status": "error"}
    receive.assert_not_awaited()
