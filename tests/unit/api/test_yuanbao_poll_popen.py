"""The yuanbao creator Popen must match the feishu one it sits next to."""

from __future__ import annotations

import inspect

from octop.api.routers import channels

SOURCE = inspect.getsource(channels)


def test_no_creator_uses_a_text_stdout():
    # parse_json_lines() decodes bytes, so universal_newlines made every poll that
    # saw output raise AttributeError on Windows.
    assert "universal_newlines" not in SOURCE


def test_both_creators_merge_stderr():
    # stderr=PIPE was never drained, so a chatty child blocked on a full pipe.
    assert SOURCE.count("stderr=subprocess.STDOUT") == 2
    assert "stderr=subprocess.PIPE" not in SOURCE
