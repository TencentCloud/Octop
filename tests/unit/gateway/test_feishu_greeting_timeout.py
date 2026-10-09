"""The Feishu greeting HTTP calls must not be able to hang forever."""

from __future__ import annotations

import inspect
import re

from octop.infra.gateway.bot_creators import feishu_bot_creator


def test_every_greeting_urlopen_passes_a_timeout():
    source = inspect.getsource(feishu_bot_creator)
    calls = re.findall(r"urlopen\(([^)]*)\)", source)

    greeting_calls = [c for c in calls if "context=ctx" in c]
    assert greeting_calls, "the greeting calls were not found"
    # urlopen without timeout falls back to the global default, which is None.
    for call in greeting_calls:
        assert "timeout=" in call, f"urlopen without timeout: urlopen({call})"


def test_the_timeout_is_a_positive_number():
    assert isinstance(feishu_bot_creator._GREETING_TIMEOUT_S, int)
    assert feishu_bot_creator._GREETING_TIMEOUT_S > 0
