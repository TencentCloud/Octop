"""Unit tests for mobile agent-control binding."""

from __future__ import annotations

from octop.infra.mobile.agent_control import (
    clear_mobile_agent_control_if_device,
    get_mobile_agent_control,
    set_mobile_agent_control,
)


def setup_function() -> None:
    set_mobile_agent_control(enabled=False, device=None)


def test_enable_requires_device() -> None:
    try:
        set_mobile_agent_control(enabled=True, device=None)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert get_mobile_agent_control().enabled is False


def test_enable_and_disable() -> None:
    st = set_mobile_agent_control(enabled=True, device="3b678f5c")
    assert st.enabled is True
    assert st.device == "3b678f5c"
    st = set_mobile_agent_control(enabled=False, device="3b678f5c")
    assert st.enabled is False
    assert st.device is None


def test_clear_when_bound_device_leaves() -> None:
    set_mobile_agent_control(enabled=True, device="phone")
    clear_mobile_agent_control_if_device("emulator-5554")
    assert get_mobile_agent_control().enabled is True
    clear_mobile_agent_control_if_device("phone")
    assert get_mobile_agent_control().enabled is False
    assert get_mobile_agent_control().device is None
