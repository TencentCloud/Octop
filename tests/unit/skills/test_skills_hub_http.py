"""Tests for the size cap on skills-hub text/JSON fetches."""

import io

import pytest

from octop.infra.skills import skills_hub


class _FakeResponse:
    """Minimal urlopen stand-in serving a fixed payload in chunks."""

    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)
        self.read_bytes = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._buf.read(size)
        self.read_bytes += len(chunk)
        return chunk

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _serve(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> _FakeResponse:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    response = _FakeResponse(payload)
    monkeypatch.setattr(skills_hub, "urlopen", lambda req, timeout: response)
    return response


def test_http_get_rejects_response_larger_than_default_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skills_hub, "MAX_SKILL_BYTES", 64 * 1024)
    payload = b"x" * (64 * 1024 * 5)
    response = _serve(monkeypatch, payload)
    with pytest.raises(ValueError, match="size limit"):
        skills_hub._http_get("https://skills.sh/api/v1/skills/demo/file")
    assert response.read_bytes <= 64 * 1024 * 5


def test_http_get_rejects_response_larger_than_explicit_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"x" * (64 * 1024 * 3)
    response = _serve(monkeypatch, payload)
    with pytest.raises(ValueError, match="size limit"):
        skills_hub._http_get(
            "https://skills.sh/api/v1/skills/demo/file",
            max_bytes=64 * 1024,
        )
    assert response.read_bytes <= 128 * 1024


def test_http_get_accepts_body_exactly_at_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cap = 64 * 1024
    _serve(monkeypatch, b"x" * cap)
    body = skills_hub._http_get(
        "https://skills.sh/api/v1/skills/demo/file",
        max_bytes=cap,
    )
    assert body == "x" * cap


def test_http_get_returns_body_under_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, b'{"ok": true}')
    body = skills_hub._http_get("https://skills.sh/api/v1/skills/demo")
    assert body == '{"ok": true}'
