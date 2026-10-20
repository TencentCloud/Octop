"""Environment isolation for unit tests.

``OctopSettings`` reads ``BROWSER_USE_*`` from the process environment, and
the module-level ``settings`` singleton is built once at import time. A
developer who exports any of those variables (a very normal thing to do while
driving the CLI by hand) would otherwise see unrelated failures here — e.g.
``BROWSER_USE_CDP_PORT_START=9412`` breaks every profile/port assertion.

Scope is deliberately limited to ``tests/unit``: integration tests talk to a
real browser and should keep honouring the ambient environment.
"""

from __future__ import annotations

import dataclasses
import os

import pytest

_ENV_PREFIX = "BROWSER_USE_"


@pytest.fixture(autouse=True)
def _isolate_octop_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in [key for key in os.environ if key.startswith(_ENV_PREFIX)]:
        monkeypatch.delenv(name, raising=False)

    # Reset the process-wide singleton too: it captured the environment at
    # import time, long before delenv above ran.
    from octop_browser.settings import OctopSettings
    from octop_browser.settings import settings as live_settings

    pristine = OctopSettings()
    for field in dataclasses.fields(pristine):
        monkeypatch.setattr(live_settings, field.name, getattr(pristine, field.name))
