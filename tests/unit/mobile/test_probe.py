"""tests/unit/mobile/test_probe.py"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from octop.infra.mobile.probe import probe_host_capability


@pytest.mark.parametrize(
    ("system", "binder", "kvm", "enabled", "backend"),
    [
        ("Darwin", False, False, True, "physical"),
        ("Windows", False, False, True, "physical"),
        ("Linux", True, False, True, "redroid"),
        ("Linux", False, True, True, "emulator"),
        ("Linux", False, False, False, "none"),
    ],
)
def test_probe_host_matrix(
    system: str,
    binder: bool,
    kvm: bool,
    enabled: bool,
    backend: str,
) -> None:
    with (
        patch("octop.infra.mobile.probe.platform.system", return_value=system),
        patch("octop.infra.mobile.probe.linux_binder_available", return_value=binder),
        patch("octop.infra.mobile.probe.kvm_available", return_value=kvm),
    ):
        result = probe_host_capability(probed_at="2026-01-01T00:00:00Z")
    assert result.enabled is enabled
    assert result.backend == backend
    assert result.probed_at == "2026-01-01T00:00:00Z"
