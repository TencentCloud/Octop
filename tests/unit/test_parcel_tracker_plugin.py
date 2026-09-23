"""Parcel-tracker must treat kuaidi100's "no result" reply as a missing trace."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from typing import Any

from octop.infra.agents.plugins.bundled import default_bundled_plugins_root

_NUMBER = "78123456789012"

# Both payloads below are verbatim replies from the public endpoints on 2026-09-24.
_AUTONUMBER = {
    "comCode": "",
    "num": _NUMBER,
    "auto": [{"comCode": "zhongtong", "lengthPre": 14, "name": "中通快递"}],
}

# HTTP 200 + status "200" + a single placeholder row: what the endpoint answers
# when the carrier has nothing for this number.
_NO_RESULT = {
    "message": "ok",
    "nu": _NUMBER,
    "ischeck": "1",
    "com": "zhongtong",
    "status": "200",
    "condition": "F00",
    "state": "3",
    "data": [
        {"time": "2026-09-18 07:12:03", "context": "查无结果", "ftime": "2026-09-18 07:12:03"}
    ],
}

_REAL_TRACES = {
    "message": "ok",
    "nu": _NUMBER,
    "ischeck": "1",
    "condition": "003",
    "com": "zhongtong",
    "status": "200",
    "state": "3",
    "data": [
        {
            "time": "2026-09-20 15:04:11",
            "ftime": "2026-09-20 15:04:11",
            "context": "已签收，感谢使用中通快递",
            "location": "北京",
        },
        {
            "time": "2026-09-20 09:12:00",
            "ftime": "2026-09-20 09:12:00",
            "context": "派件中，快递员正在为您派送",
            "location": "北京",
        },
    ],
}


def _load_plugin():
    path = default_bundled_plugins_root() / "parcel-tracker" / "main.py"
    spec = importlib.util.spec_from_file_location("bundled_parcel_tracker", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeResp:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _StubClient:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def __enter__(self) -> _StubClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def get(self, url: str, **kwargs: Any) -> _FakeResp:
        return _FakeResp(self.payload)


def _install(monkeypatch: Any, mod: Any, payload: Any) -> None:
    client = _StubClient(payload)
    monkeypatch.setattr(mod.httpx, "Client", lambda *a, **k: client)


def test_autonumber_still_reads_the_detected_carrier(monkeypatch: Any) -> None:
    mod = _load_plugin()
    _install(monkeypatch, mod, _AUTONUMBER)
    assert mod._detect_company(_NUMBER) == "zhongtong"


def test_real_traces_are_kept_as_is(monkeypatch: Any) -> None:
    mod = _load_plugin()
    _install(monkeypatch, mod, _REAL_TRACES)
    traces = mod._query("zhongtong", _NUMBER)
    assert [t["context"] for t in traces] == [
        "已签收，感谢使用中通快递",
        "派件中，快递员正在为您派送",
    ]
    out = json.loads(asyncio.run(mod.track_parcel(_NUMBER, "zhongtong")))
    assert out["data"]["traces"] == traces
    assert "error" not in out["data"]
    assert out["text"].startswith(f"{_NUMBER}（zhongtong）最新：已签收")


def test_no_result_placeholder_is_not_reported_as_the_latest_trace(monkeypatch: Any) -> None:
    mod = _load_plugin()
    _install(monkeypatch, mod, _NO_RESULT)
    assert mod._query("zhongtong", _NUMBER) == []
    out = json.loads(asyncio.run(mod.track_parcel(_NUMBER)))
    data = out["data"]
    assert data["traces"] == []
    assert data["error"] == "no traces"
    assert data["url"] == f"https://www.kuaidi100.com/chaxun?nu={_NUMBER}"
    assert "暂无轨迹" in out["text"] and _NUMBER in out["text"]
