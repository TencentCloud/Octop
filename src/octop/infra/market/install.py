"""Download one portal expert package into the local library cache."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import octop.infra.market.http as market_http
from octop.infra.market.errors import PortalMarketError
from octop.infra.market.experts import get_market_expert
from octop.infra.market.normalize import valid_id

logger = logging.getLogger(__name__)

_MAX_ZIP_ENTRIES = 2_000
_MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100.0


@dataclass(frozen=True)
class PortalExpertInstall:
    slug: str
    expert_id: str
    icon_url: str | None


def install_portal_expert(slug: str, cache_root: Path) -> PortalExpertInstall | None:
    """Cache a portal expert library under ``cache_root``.

    Returns ``None`` when the remote catalog is unavailable or does not list
    ``slug``. A listed expert with a bad package raises :class:`PortalMarketError`.
    """
    if not valid_id(slug):
        return None
    try:
        item = get_market_expert(slug)
    except PortalMarketError as exc:
        logger.warning("expert market catalog unavailable: %s", exc)
        return None
    if item is None:
        return None
    url = item.get("download_url")
    if not isinstance(url, str) or not market_http.is_market_archive_url(url):
        raise PortalMarketError("expert package url is missing")
    payload = market_http.fetch_bytes(url.split("?", 1)[0], limit=market_http.MAX_ARCHIVE_BYTES)
    expert_id = _install_zip(payload, cache_root, slug)
    icon = item.get("icon_url")
    return PortalExpertInstall(
        slug=slug,
        expert_id=expert_id,
        icon_url=icon if isinstance(icon, str) and icon else None,
    )


def _install_zip(payload: bytes, cache_root: Path, slug: str) -> str:
    if len(payload) < 2 or payload[:2] != b"PK":
        raise PortalMarketError("expert package is not a zip")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "extract"
        root.mkdir()
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                _validate_zip(archive, root)
        except zipfile.BadZipFile as exc:
            raise PortalMarketError("expert package is not a zip") from exc
        manifest = _find_manifest(root)
        if manifest is None:
            raise PortalMarketError("expert package has no manifest")
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PortalMarketError("expert manifest is invalid") from exc
        expert_id = str(meta.get("id") or "").strip() if isinstance(meta, dict) else ""
        if expert_id != slug:
            raise PortalMarketError("expert package id does not match")
        _replace_tree(manifest.parent, cache_root / expert_id)
    return slug


def _validate_zip(archive: zipfile.ZipFile, root: Path) -> None:
    infos = archive.infolist()
    if len(infos) > _MAX_ZIP_ENTRIES:
        raise PortalMarketError("expert package has too many files")
    total = 0
    root_resolved = root.resolve()
    for member in infos:
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise PortalMarketError("expert package path is unsafe")
        total += max(member.file_size, 0)
        if total > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise PortalMarketError("expert package is too large")
        compressed = member.compress_size or 0
        if (
            compressed > 0
            and member.file_size > 1024 * 1024
            and member.file_size / compressed > _MAX_ZIP_COMPRESSION_RATIO
        ):
            raise PortalMarketError("expert package compression ratio is too high")
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root_resolved):
            raise PortalMarketError("expert package path is unsafe")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member) as source, target.open("wb") as dest:
            shutil.copyfileobj(source, dest, length=market_http.READ_CHUNK)


def _find_manifest(root: Path) -> Path | None:
    direct = root / "manifest.json"
    if direct.is_file():
        return direct
    children = [path for path in root.iterdir() if path.is_dir()]
    if len(children) != 1:
        return None
    nested = children[0] / "manifest.json"
    return nested if nested.is_file() else None


def _replace_tree(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_name(f".{dest.name}.tmp-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(src, staging)
    backup: Path | None = None
    if dest.exists():
        backup = dest.with_name(f".{dest.name}.old-{os.getpid()}")
        dest.rename(backup)
    try:
        staging.rename(dest)
    except OSError:
        if backup is not None and backup.exists() and not dest.exists():
            backup.rename(dest)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)
