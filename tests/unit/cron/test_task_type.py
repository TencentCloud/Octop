"""tests/unit/cron/test_task_type.py"""

from __future__ import annotations

import pytest

from octop.infra.cron.task_type import (
    CRON_NAME_FALLBACK_LEN,
    CRON_NAME_MAX_LEN,
    CRON_PROMPT_MAX_LEN,
    CRON_SCRIPT_MAX_LEN,
    default_cron_name,
    normalize_cron_task,
    require_cron_name,
    require_cron_prompt,
    require_script_path,
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


def test_agent_allow_all_is_kept_and_ignored_for_text() -> None:
    agent = normalize_cron_task(task_type="agent", prompt="summarize", allow_all=True)
    assert agent.allow_all is True
    assert agent.script_lang is None
    text = normalize_cron_task(task_type="text", prompt="hello", allow_all=True)
    assert text.allow_all is False


def test_inline_script_keeps_a_long_body() -> None:
    body = "print(1)\n" + ("#\n" * 100)
    spec = normalize_cron_task(
        task_type="script",
        prompt=body,
        script_lang="python",
        script_source="inline",
    )
    assert spec.prompt == body.strip()
    assert spec.script_source == "inline"
    assert spec.allow_all is False


def test_script_file_uses_workspace_relative_path() -> None:
    spec = normalize_cron_task(
        task_type="script",
        prompt="",
        script_lang="bash",
        script_source="file",
        script_path="scripts/nightly.sh",
    )
    assert spec.prompt == "scripts/nightly.sh"
    assert spec.script_path == "scripts/nightly.sh"


def test_script_path_rejects_escape() -> None:
    with pytest.raises(ValueError, match="workspace"):
        require_script_path("../etc/passwd")
    with pytest.raises(ValueError, match="workspace"):
        require_script_path("/tmp/x.sh")


def test_missing_script_lang_defaults_to_python() -> None:
    spec = normalize_cron_task(task_type="script", prompt='print("helloworld")')
    assert spec.script_lang == "python"
    assert spec.script_source == "inline"
    bash = normalize_cron_task(task_type="script", prompt="#!/bin/bash\necho hi")
    assert bash.script_lang == "bash"
    shell = normalize_cron_task(
        task_type="script",
        prompt="Write-Output hi",
        script_lang="null",
    )
    assert shell.script_lang == "powershell"


def test_script_rejects_empty_body_and_unknown_lang() -> None:
    with pytest.raises(ValueError, match="empty"):
        normalize_cron_task(task_type="script", prompt="  ", script_lang="python")
    with pytest.raises(ValueError, match="script_lang"):
        normalize_cron_task(task_type="script", prompt="print(1)", script_lang="ruby")


def test_script_path_normalizes_slashes_and_rejects_drives() -> None:
    spec = normalize_cron_task(
        task_type="script",
        prompt="",
        script_lang="powershell",
        script_source="file",
        script_path="scripts\\nightly.ps1",
    )
    assert spec.script_path == "scripts/nightly.ps1"
    with pytest.raises(ValueError, match="workspace"):
        require_script_path("C:/temp/job.ps1")


def test_inline_script_rejects_over_limit() -> None:
    with pytest.raises(ValueError, match=str(CRON_SCRIPT_MAX_LEN)):
        normalize_cron_task(
            task_type="script",
            prompt="x" * (CRON_SCRIPT_MAX_LEN + 1),
            script_lang="python",
        )


def test_require_cron_name_rejects_too_long() -> None:
    with pytest.raises(ValueError, match=str(CRON_NAME_MAX_LEN)):
        require_cron_name("x" * (CRON_NAME_MAX_LEN + 1), prompt="p", cron_id="cron_x")
