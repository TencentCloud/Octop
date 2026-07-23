"""Direct HTTP client for Tencent SkillHub marketplace operations."""

from __future__ import annotations

import asyncio
import http.client
import io
import json
import logging
import os
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
SEARCH_ENDPOINT = "/api/v1/search"
DOWNLOAD_ENDPOINT = "/api/v1/download"
RANKING_ENDPOINTS = {
    "hot": "/api/v1/showcase/hot",
    "featured": "/api/v1/showcase/featured",
    "newest": "/api/v1/showcase/newest",
    "recommended": "/api/v1/showcase/recommended",
    "trending": "/api/v1/showcase/trending",
    "paid": "/api/v1/showcase/paid",
}
_MAX_HTTP_BYTES = 32 * 1024 * 1024
_MAX_ZIP_ENTRIES = 2_000
_MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100
_HTTP_READ_CHUNK = 64 * 1024


class SkillHubMarketError(RuntimeError):
    """A SkillHub marketplace HTTP request failed."""


class SkillHubMarketTimeout(SkillHubMarketError):
    """A SkillHub marketplace HTTP request timed out."""


class SkillHubPackageError(SkillHubMarketError):
    """A downloaded SkillHub package failed validation."""


class SkillHubPackageTooLarge(SkillHubPackageError):
    """A downloaded SkillHub package exceeded a safety limit."""


def _resolve_host(host: str | None) -> str:
    resolved = (host or "").strip() or os.environ.get("SKILLHUB_HOST", "").strip()
    resolved = (resolved or DEFAULT_SKILLHUB_HOST).rstrip("/")
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SkillHubMarketError(f"Invalid SkillHub API host: {resolved}")
    return resolved


def _http_request(
    url: str,
    *,
    accept: str,
    timeout: float,
    max_bytes: int,
) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "octop-skillhub-market/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = getattr(response, "headers", None)
            content_length = headers.get("Content-Length") if headers is not None else None
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > max_bytes:
                    raise SkillHubPackageTooLarge(
                        f"SkillHub response exceeds {max_bytes // (1024 * 1024)} MB"
                    )

            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(_HTTP_READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise SkillHubPackageTooLarge(
                        f"SkillHub response exceeds {max_bytes // (1024 * 1024)} MB"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    except SkillHubPackageError:
        raise
    except urllib.error.HTTPError as exc:
        raise SkillHubMarketError(f"SkillHub request failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise SkillHubMarketTimeout("SkillHub request timed out") from exc
        raise SkillHubMarketError(f"SkillHub request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SkillHubMarketTimeout("SkillHub request timed out") from exc
    except (http.client.HTTPException, OSError) as exc:
        raise SkillHubMarketError(f"SkillHub request failed: {exc}") from exc


def _fetch_search_json(
    host: str,
    query: str,
    *,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "limit": max(1, min(limit, 100))})
    payload = _http_request(
        f"{host}{SEARCH_ENDPOINT}?{params}",
        accept="application/json",
        timeout=timeout,
        max_bytes=4 * 1024 * 1024,
    )
    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SkillHubMarketError(f"Invalid JSON from SkillHub search: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise SkillHubMarketError("SkillHub search response must contain a results array")

    results: list[dict[str, Any]] = []
    for raw in data["results"]:
        if not isinstance(raw, dict):
            continue
        slug = str(raw.get("slug") or "").strip()
        if not slug:
            continue
        item = dict(raw)
        item["slug"] = slug
        item["name"] = str(raw.get("displayName") or raw.get("name") or slug).strip() or slug
        item["description"] = str(raw.get("summary") or raw.get("description") or "").strip()
        item["version"] = str(raw.get("version") or "").strip()
        results.append(item)
    return results


def _safe_zip_path(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or "\x00" in normalized
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and path.parts[0].endswith(":"))
    ):
        raise SkillHubPackageError(f"Unsafe zip path entry: {filename}")
    clean = path.as_posix()
    if clean in {"", "."}:
        raise SkillHubPackageError(f"Invalid zip path entry: {filename}")
    return clean.rstrip("/")


def _validate_zip(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_ENTRIES:
        raise SkillHubPackageTooLarge("SkillHub package has too many entries")

    total_uncompressed = 0
    seen: set[str] = set()
    validated: list[tuple[zipfile.ZipInfo, str]] = []
    for member in infos:
        clean = _safe_zip_path(member.filename)
        if clean in seen:
            raise SkillHubPackageError(f"Duplicate zip path entry: {member.filename}")
        seen.add(clean)

        mode = member.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
            raise SkillHubPackageError(f"Unsupported zip entry type: {member.filename}")
        if member.flag_bits & 0x1:
            raise SkillHubPackageError(f"Encrypted zip entry is not supported: {member.filename}")
        if member.file_size < 0:
            raise SkillHubPackageError(f"Invalid zip entry size: {member.filename}")

        total_uncompressed += member.file_size
        if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise SkillHubPackageTooLarge("SkillHub package uncompressed size exceeds 64 MB")
        compressed = member.compress_size or 0
        if (
            compressed > 0
            and member.file_size > 1024 * 1024
            and member.file_size / compressed > _MAX_ZIP_COMPRESSION_RATIO
        ):
            raise SkillHubPackageTooLarge(f"Zip compression ratio is too high: {member.filename}")
        validated.append((member, clean))
    return validated


def _read_zip_member(zf: zipfile.ZipFile, member: zipfile.ZipInfo) -> bytes:
    chunks: list[bytes] = []
    total = 0
    with zf.open(member) as source:
        while True:
            chunk = source.read(_HTTP_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > member.file_size or total > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise SkillHubPackageTooLarge(f"Zip entry is too large: {member.filename}")
            chunks.append(chunk)
    if total != member.file_size:
        raise SkillHubPackageError(f"Zip entry size mismatch: {member.filename}")
    return b"".join(chunks)


def parse_skillhub_package(payload: bytes) -> list[tuple[str, bytes]]:
    """Validate a SkillHub ZIP and return workspace-relative file payloads."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            files = [
                (clean, _read_zip_member(zf, member))
                for member, clean in _validate_zip(zf)
                if not member.is_dir()
            ]
    except SkillHubPackageError:
        raise
    except (OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise SkillHubPackageError("SkillHub package is not a valid ZIP archive") from exc

    names = {name for name, _content in files}
    if "SKILL.md" not in names:
        top_levels = {name.split("/", 1)[0] for name in names}
        if len(top_levels) == 1:
            wrapper = next(iter(top_levels))
            prefix = f"{wrapper}/"
            if f"{prefix}SKILL.md" in names:
                files = [(name[len(prefix) :], content) for name, content in files]

    if not files or "SKILL.md" not in {name for name, _content in files}:
        raise SkillHubPackageError("SkillHub package does not contain a root SKILL.md")
    return files


def _download_skillhub_package(
    host: str,
    slug: str,
    *,
    timeout: float,
) -> list[tuple[str, bytes]]:
    params = urllib.parse.urlencode({"slug": slug})
    payload = _http_request(
        f"{host}{DOWNLOAD_ENDPOINT}?{params}",
        accept="application/zip,application/octet-stream,*/*",
        timeout=timeout,
        max_bytes=_MAX_HTTP_BYTES,
    )
    return parse_skillhub_package(payload)


def _fetch_ranking_json(
    host: str,
    ranking_type: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    path = RANKING_ENDPOINTS.get(ranking_type)
    if path is None:
        raise SkillHubMarketError(f"Unsupported ranking type: {ranking_type}")

    url = f"{host}{path}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "octop-skillhub-market/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise SkillHubMarketError(
            f"Failed to fetch {ranking_type} rankings: HTTP {exc.code}"
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise SkillHubMarketTimeout(f"Timed out fetching {ranking_type} rankings") from exc
        raise SkillHubMarketError(f"Failed to fetch {ranking_type} rankings: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SkillHubMarketTimeout(f"Timed out fetching {ranking_type} rankings") from exc

    try:
        data = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SkillHubMarketError(f"Invalid JSON from {ranking_type} rankings: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillHubMarketError(f"Ranking response must be a JSON object: {ranking_type}")
    return data


async def search_skillhub(
    query: str,
    *,
    limit: int = 50,
    host: str | None = None,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    """Search the public SkillHub registry directly over HTTP."""
    return await asyncio.to_thread(
        _fetch_search_json,
        _resolve_host(host),
        query.strip() or "a",
        limit=limit,
        timeout=timeout,
    )


async def download_skillhub_package(
    slug: str,
    *,
    host: str | None = None,
    timeout: float = 30.0,
) -> list[tuple[str, bytes]]:
    """Download and validate a public SkillHub skill package over HTTP."""
    return await asyncio.to_thread(
        _download_skillhub_package,
        _resolve_host(host),
        slug,
        timeout=timeout,
    )


async def fetch_skillhub_rankings(
    ranking_type: str,
    *,
    host: str | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Fetch one ranking or all rankings directly over HTTP.

    ``all`` requests every section concurrently and returns successful sections
    even when another section fails. The optional ``errors`` map is additive to
    the existing CLI response shape and is ignored by older dashboard clients.
    """
    resolved_host = _resolve_host(host)
    if ranking_type != "all":
        return await asyncio.to_thread(
            _fetch_ranking_json,
            resolved_host,
            ranking_type,
            timeout=timeout,
        )

    names = list(RANKING_ENDPOINTS)
    rows = await asyncio.gather(
        *(
            asyncio.to_thread(
                _fetch_ranking_json,
                resolved_host,
                name,
                timeout=timeout,
            )
            for name in names
        ),
        return_exceptions=True,
    )
    rankings: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    failures: list[BaseException] = []
    for name, row in zip(names, rows, strict=True):
        if isinstance(row, asyncio.CancelledError):
            raise row
        if isinstance(row, BaseException):
            failures.append(row)
            errors[name] = str(row)
            logger.warning("SkillHub %s rankings failed: %s", name, row)
        else:
            rankings[name] = row

    if not rankings:
        if failures and all(isinstance(exc, SkillHubMarketTimeout) for exc in failures):
            raise SkillHubMarketTimeout("All SkillHub ranking requests timed out")
        detail = errors.get("hot") or next(iter(errors.values()), "unknown error")
        raise SkillHubMarketError(f"All SkillHub ranking requests failed: {detail}")

    result: dict[str, Any] = {"rankings": rankings}
    if errors:
        result["errors"] = errors
    return result


__all__ = [
    "DOWNLOAD_ENDPOINT",
    "RANKING_ENDPOINTS",
    "SEARCH_ENDPOINT",
    "SkillHubMarketError",
    "SkillHubMarketTimeout",
    "SkillHubPackageError",
    "SkillHubPackageTooLarge",
    "download_skillhub_package",
    "fetch_skillhub_rankings",
    "parse_skillhub_package",
    "search_skillhub",
]
