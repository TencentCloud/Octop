"""Tests for direct HTTP SkillHub search and package installation."""

from __future__ import annotations

import io
import json
import stat
import urllib.parse
import zipfile
from typing import Any

import pytest

from octop.infra.agents import skillhub_market


class _BytesResponse:
    def __init__(self, payload: bytes, *, headers: dict[str, str] | None = None) -> None:
        self._stream = io.BytesIO(payload)
        self.headers = headers or {}

    def __enter__(self) -> _BytesResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _zip_bytes(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_search_skillhub_uses_http_api_and_preserves_rich_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    payload = {
        "results": [
            {
                "slug": "pdf-reader",
                "displayName": "PDF 阅读器",
                "summary": "读取 PDF",
                "version": "1.2.3",
                "iconUrl": "https://cdn.example.com/pdf.png",
                "description_zh": "中文说明",
                "downloads": 42,
            }
        ]
    }

    def fake_urlopen(request: Any, timeout: float) -> _BytesResponse:
        seen["url"] = request.full_url
        seen["accept"] = request.headers["Accept"]
        seen["timeout"] = timeout
        return _BytesResponse(json.dumps(payload).encode())

    monkeypatch.setattr(skillhub_market.urllib.request, "urlopen", fake_urlopen)

    result = skillhub_market._fetch_search_json(
        "https://api.example.com",
        "PDF 中文",
        limit=12,
        timeout=7,
    )

    parsed = urllib.parse.urlparse(seen["url"])
    assert parsed.path == "/api/v1/search"
    assert urllib.parse.parse_qs(parsed.query) == {"q": ["PDF 中文"], "limit": ["12"]}
    assert seen["accept"] == "application/json"
    assert seen["timeout"] == 7
    assert result == [
        {
            "slug": "pdf-reader",
            "displayName": "PDF 阅读器",
            "name": "PDF 阅读器",
            "summary": "读取 PDF",
            "description": "读取 PDF",
            "version": "1.2.3",
            "iconUrl": "https://cdn.example.com/pdf.png",
            "description_zh": "中文说明",
            "downloads": 42,
        }
    ]


def test_download_skillhub_package_follows_endpoint_and_strips_wrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}
    payload = _zip_bytes(
        {
            "wrapped/SKILL.md": "---\nname: demo\n---\n",
            "wrapped/references/readme.txt": "hello",
        }
    )

    def fake_urlopen(request: Any, timeout: float) -> _BytesResponse:
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _BytesResponse(payload, headers={"Content-Length": str(len(payload))})

    monkeypatch.setattr(skillhub_market.urllib.request, "urlopen", fake_urlopen)

    files = skillhub_market._download_skillhub_package(
        "https://api.example.com",
        "demo skill",
        timeout=9,
    )

    parsed = urllib.parse.urlparse(seen["url"])
    assert parsed.path == "/api/v1/download"
    assert urllib.parse.parse_qs(parsed.query) == {"slug": ["demo skill"]}
    assert seen["timeout"] == 9
    assert dict(files) == {
        "SKILL.md": b"---\nname: demo\n---\n",
        "references/readme.txt": b"hello",
    }


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.txt",
        "/absolute.txt",
        "folder\\..\\escape.txt",
        "C:/windows.txt",
    ],
)
def test_parse_skillhub_package_rejects_unsafe_paths(filename: str) -> None:
    payload = _zip_bytes(
        {
            "SKILL.md": "---\nname: demo\n---\n",
            filename: "unsafe",
        }
    )

    with pytest.raises(skillhub_market.SkillHubPackageError, match="zip path"):
        skillhub_market.parse_skillhub_package(payload)


def test_parse_skillhub_package_rejects_symlinks() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", "---\nname: demo\n---\n")
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "SKILL.md")

    with pytest.raises(skillhub_market.SkillHubPackageError, match="entry type"):
        skillhub_market.parse_skillhub_package(buffer.getvalue())


def test_parse_skillhub_package_requires_root_manifest() -> None:
    payload = _zip_bytes({"README.md": "not a skill"})

    with pytest.raises(skillhub_market.SkillHubPackageError, match="root SKILL.md"):
        skillhub_market.parse_skillhub_package(payload)


def test_parse_skillhub_package_enforces_uncompressed_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skillhub_market, "_MAX_ZIP_UNCOMPRESSED_BYTES", 8)
    payload = _zip_bytes({"SKILL.md": "123456789"})

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market.parse_skillhub_package(payload)


def test_http_request_rejects_oversized_content_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(_request: Any, timeout: float) -> _BytesResponse:
        return _BytesResponse(b"", headers={"Content-Length": "101"})

    monkeypatch.setattr(skillhub_market.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(skillhub_market.SkillHubPackageTooLarge, match="exceeds"):
        skillhub_market._http_request(
            "https://api.example.com/file",
            accept="application/zip",
            timeout=1,
            max_bytes=100,
        )
