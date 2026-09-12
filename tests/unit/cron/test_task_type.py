"""tests/unit/cron/test_task_type.py"""

from __future__ import annotations

import pytest

from octop.infra.cron.task_type import (
    CRON_NAME_FALLBACK_LEN,
    CRON_NAME_MAX_LEN,
    CRON_PROMPT_MAX_LEN,
    default_cron_name,
    require_cron_name,
    require_cron_prompt,
)


def test_require_cron_prompt_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        require_cron_prompt("   ")


def test_require_cron_prompt_rejects_too_long() -> None:
    with pytest.raises(ValueError, match=str(CRON_PROMPT_MAX_LEN)):
        require_cron_prompt("x" * (CRON_PROMPT_MAX_LEN + 1))


def test_require_cron_prompt_strips() -> None:
    assert require_cron_prompt("  hello  ") == "hello"


def test_default_cron_name_uses_first_line() -> None:
    assert default_cron_name("该喝水了\n更多说明", "cron_x") == "该喝水了"


def test_default_cron_name_truncates_long_prefix() -> None:
    prompt = "a" * (CRON_NAME_FALLBACK_LEN + 10)
    assert default_cron_name(prompt, "cron_x") == "a" * CRON_NAME_FALLBACK_LEN


def test_default_cron_name_falls_back_to_cron_id() -> None:
    assert default_cron_name("  \n  ", "cron_x") == "cron_x"


def test_require_cron_name_uses_explicit_name() -> None:
    assert require_cron_name("  喝水  ", prompt="ignored", cron_id="cron_x") == "喝水"


def test_require_cron_name_blank_uses_prompt_prefix() -> None:
    assert require_cron_name("  ", prompt="站起来活动", cron_id="cron_x") == "站起来活动"


def test_require_cron_name_rejects_too_long() -> None:
    with pytest.raises(ValueError, match=str(CRON_NAME_MAX_LEN)):
        require_cron_name("x" * (CRON_NAME_MAX_LEN + 1), prompt="p", cron_id="cron_x")
