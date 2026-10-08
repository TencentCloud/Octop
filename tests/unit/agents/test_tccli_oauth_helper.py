"""Unit tests for the cvm-cluster-doctor tccli OAuth helper script.

The helper lives under an expert skill directory (dashes in the path), so it
is loaded by file path instead of a package import.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import types
from pathlib import Path

_HELPER_SRC = (
    Path(__file__).resolve().parents[3]
    / "src/octop/infra/agents/experts/library/cvm-cluster-doctor"
    / "skills/tencentcloud-infra/scripts/tccli-oauth-helper.py"
)


def _load_helper():
    spec = importlib.util.spec_from_file_location("tccli_oauth_helper", _HELPER_SRC)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _code_args(state: str) -> types.SimpleNamespace:
    code = base64.b64encode(json.dumps({"accessToken": "tok", "state": state}).encode()).decode()
    return types.SimpleNamespace(code=code, profile="default")


def test_generate_state_is_high_entropy_and_unique() -> None:
    helper = _load_helper()
    state = helper.generate_state()
    assert isinstance(state, str)
    assert len(state) >= 32
    assert len({helper.generate_state() for _ in range(50)}) == 50


def test_state_mismatch_rejects_code(monkeypatch, tmp_path, capsys) -> None:
    helper = _load_helper()
    monkeypatch.setattr(helper, "_STATE_FILE", str(tmp_path / ".oauth_state"))
    helper.save_state("expected")

    assert helper.do_login_with_code(_code_args("other")) == 1
    out = capsys.readouterr().out
    assert "state 不匹配" in out


def test_missing_saved_state_rejects_code(monkeypatch, tmp_path, capsys) -> None:
    helper = _load_helper()
    monkeypatch.setattr(helper, "_STATE_FILE", str(tmp_path / ".oauth_state"))

    assert helper.do_login_with_code(_code_args("whatever")) == 1
    out = capsys.readouterr().out
    assert "state 校验失败" in out
