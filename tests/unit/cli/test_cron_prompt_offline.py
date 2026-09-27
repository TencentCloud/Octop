"""tests/unit/cli/test_cron_prompt_offline.py — ``octop cron create`` rejects bad prompts cleanly.

``create_job`` catches ``OctopError`` and renders it via ``fail_octop``; the prompt
guard used to raise a bare ``ValueError``, so ``octop cron create --prompt "  "``
escaped the handler as a traceback.
"""

from __future__ import annotations

import pytest

from octop.cli.support.offline_ops import create_cron_offline
from octop.infra.errors import ErrorCode, OctopError


def test_create_cron_offline_blank_prompt_raises_octop_error() -> None:
    with pytest.raises(OctopError, match="empty") as exc:
        create_cron_offline(agent_id="ag_1", user_id=1, trigger="interval:60", prompt="   ")
    assert exc.value.code is ErrorCode.CRON_PROMPT_INVALID
    assert exc.value.status == 400
