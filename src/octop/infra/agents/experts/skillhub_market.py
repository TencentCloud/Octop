"""SkillHub skillset marketplace integration for expert templates.

SkillHub currently exposes expert-like assets as *skillsets*. A skillset is a
workflow prompt plus a list of skill slugs. We normalize that package into the
same on-disk shape as bundled experts:

``manifest.json`` + ``SOUL.md`` + ``skills/<slug>/SKILL.md``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

MARKET_EXPERT_PREFIX = "skillhub-skillset-"
DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
_HTTP_TIMEOUT = 30
_SKILLSET_PAGE_SIZE = 100
_MAX_SKILLSET_PAGES = 20
_MAX_WORKFLOW_QUICK_PROMPTS = 6
_SKILLSET_LIST_CACHE_TTL_SECONDS = 300.0
_MAX_HTTP_BYTES = 32 * 1024 * 1024
_MAX_ZIP_ENTRIES = 2_000
_MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100.0
_HTTP_READ_CHUNK = 64 * 1024
# Product nav order for expert market scene tabs (matches dashboard copy).
_SCENE_ORDER = (
    "ecommerce",
    "finance",
    "content-creation",
    "lifestyle",
    "marketing",
    "mysticism",
    "academic",
    "legal",
    "tech",
    "education",
    "healthcare",
    "hr",
    "media",
    "design",
)
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_STEP_HEADING_RE = re.compile(r"^##\s*步骤\s*(\d+)\s*[：:]\s*(.+?)\s*$", re.MULTILINE)
_QUICK_PROMPT_COLORS = (
    "#e8f4ff",
    "#fef3c7",
    "#dcfce7",
    "#f1f5f9",
    "#fff1f2",
    "#eef2ff",
    "#ecfeff",
    "#f0fdf4",
    "#faf5ff",
)


class SkillHubMarketErrorKind(StrEnum):
    NOT_FOUND = "not_found"
    INVALID_SLUG = "invalid_slug"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_BAD_PAYLOAD = "upstream_bad_payload"
    PACKAGE_INVALID = "package_invalid"
    PACKAGE_TOO_LARGE = "package_too_large"
    UPSTREAM_FAILED = "upstream_failed"


class SkillHubMarketError(RuntimeError):
    """Raised when SkillHub marketplace fetch/install fails."""

    def __init__(
        self,
        message: str,
        *,
        kind: SkillHubMarketErrorKind = SkillHubMarketErrorKind.UPSTREAM_FAILED,
    ) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class SkillHubSkillset:
    slug: str
    display_name: str
    display_name_en: str = ""
    summary: str = ""
    summary_en: str = ""
    scene: str = ""
    sub_scene: str = ""
    content: str = ""
    content_en: str = ""
    icon_url: str = ""
    skill_slugs: tuple[str, ...] = ()
    skill_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def expert_id(self) -> str:
        return market_expert_id(self.slug)

    def api_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        name_zh = _expert_label_zh(self)
        name_en = _expert_label_en(self)
        out: dict[str, Any] = {
            "id": self.expert_id,
            "slug": self.slug,
            "label": {
                "zh": name_zh,
                "en": name_en,
            },
            "description": {
                "zh": self.summary,
                "en": _expert_summary_en(self, name_en),
            },
            "scene": self.scene,
            "sub_scene": self.sub_scene,
            "icon_url": self.icon_url or None,
            "icon_name": _scene_icon_name(self.scene),
            "color": _scene_color(self.scene),
            "skill_slugs": list(self.skill_slugs),
            "skill_count": self.skill_count or len(self.skill_slugs),
            "source": "skillhub",
        }
        if include_content:
            out["content"] = {"zh": self.content, "en": self.content_en}
            out["quick_prompts"] = quick_prompts_for_skillset(self)
        return out


_skillset_list_cache: list[SkillHubSkillset] | None = None
_skillset_list_cache_at: float = 0.0
_skillset_list_lock = threading.Lock()
_skillset_list_cv = threading.Condition(_skillset_list_lock)
_skillset_list_loading = False

_install_locks_guard = threading.Lock()
_install_locks: dict[str, threading.Lock] = {}


def market_expert_id(slug: str) -> str:
    return f"{MARKET_EXPERT_PREFIX}{slug}"


def validate_skillset_slug(slug: str) -> str:
    trimmed = slug.strip()
    if not trimmed or not _SLUG_RE.fullmatch(trimmed):
        raise SkillHubMarketError(
            "invalid skillset slug",
            kind=SkillHubMarketErrorKind.INVALID_SLUG,
        )
    return trimmed


def _install_lock_for(slug: str) -> threading.Lock:
    with _install_locks_guard:
        lock = _install_locks.get(slug)
        if lock is None:
            lock = threading.Lock()
            _install_locks[slug] = lock
        return lock


def fetch_skillsets(query: str = "", *, scene: str = "") -> list[SkillHubSkillset]:
    items, _scenes = browse_skillsets(query, scene=scene)
    return items


def list_skillset_scenes() -> list[str]:
    """Return distinct SkillHub scenes in product nav order."""
    _items, scenes = browse_skillsets()
    return scenes


def _ordered_scenes(present: set[str]) -> list[str]:
    ordered = [scene for scene in _SCENE_ORDER if scene in present]
    extras = sorted(scene for scene in present if scene not in _SCENE_ORDER)
    return ordered + extras


def browse_skillsets(
    query: str = "",
    *,
    scene: str = "",
) -> tuple[list[SkillHubSkillset], list[str]]:
    """Fetch skillsets once and return ``(filtered_items, all_scenes)``."""
    all_items = _fetch_all_skillsets()
    present = {item.scene.strip() for item in all_items if item.scene.strip()}
    scenes = _ordered_scenes(present)

    items = all_items
    scene_key = scene.strip().lower()
    if scene_key:
        items = [item for item in items if item.scene.lower() == scene_key]
    q = query.strip().lower()
    if q:
        items = [
            item
            for item in items
            if q in item.slug.lower()
            or q in item.display_name.lower()
            or q in item.display_name_en.lower()
            or q in item.summary.lower()
            or q in item.summary_en.lower()
            or q in item.scene.lower()
            or q in item.sub_scene.lower()
        ]
    return items, scenes


def _fetch_all_skillsets(*, force: bool = False) -> list[SkillHubSkillset]:
    """Fetch the full SkillHub skillset list.

    The SkillHub endpoint defaults to 20 rows even though it returns ``total``.
    ``limit=`` is ignored by the current API; ``page`` + ``pageSize`` is the
    supported shape. Results are cached in-process for a short TTL with
    single-flight refresh and stale fallback on upstream failure.
    """
    global _skillset_list_cache, _skillset_list_cache_at, _skillset_list_loading

    with _skillset_list_cv:
        now = time.monotonic()
        if (
            not force
            and _skillset_list_cache is not None
            and (now - _skillset_list_cache_at) < _SKILLSET_LIST_CACHE_TTL_SECONDS
        ):
            return list(_skillset_list_cache)

        while _skillset_list_loading:
            _skillset_list_cv.wait(timeout=_HTTP_TIMEOUT + 5)
            now = time.monotonic()
            if (
                not force
                and _skillset_list_cache is not None
                and (now - _skillset_list_cache_at) < _SKILLSET_LIST_CACHE_TTL_SECONDS
            ):
                return list(_skillset_list_cache)

        stale = list(_skillset_list_cache) if _skillset_list_cache is not None else None
        _skillset_list_loading = True

    try:
        items = _load_all_skillsets_uncached()
        with _skillset_list_cv:
            _skillset_list_cache = items
            _skillset_list_cache_at = time.monotonic()
            return list(items)
    except SkillHubMarketError:
        if stale is not None and not force:
            logger.warning("SkillHub skillset list refresh failed; serving stale cache")
            return stale
        raise
    finally:
        with _skillset_list_cv:
            _skillset_list_loading = False
            _skillset_list_cv.notify_all()


def _load_all_skillsets_uncached() -> list[SkillHubSkillset]:
    items: list[SkillHubSkillset] = []
    seen: set[str] = set()
    total: int | None = None
    page = 1

    while page <= _MAX_SKILLSET_PAGES:
        data = _http_json_get(
            _api_url(
                "/api/v1/skillsets",
                params={"page": page, "pageSize": _SKILLSET_PAGE_SIZE},
            )
        )
        raw_items = data.get("skillSets") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            raise SkillHubMarketError(
                "SkillHub skillsets response is invalid",
                kind=SkillHubMarketErrorKind.UPSTREAM_BAD_PAYLOAD,
            )
        if total is None:
            total = _coerce_positive_int(data.get("total")) if isinstance(data, dict) else None

        page_items = [_skillset_from_raw(x) for x in raw_items if isinstance(x, dict)]
        for item in page_items:
            if not item.slug or item.slug in seen:
                continue
            seen.add(item.slug)
            items.append(item)

        if not raw_items:
            break
        if total is not None and len(items) >= total:
            break
        if len(raw_items) < _SKILLSET_PAGE_SIZE:
            break
        page += 1

    return items


def fetch_skillset(slug: str) -> SkillHubSkillset:
    safe_slug = validate_skillset_slug(slug)
    data = _http_json_get(_api_url(f"/api/v1/skillsets/{quote(safe_slug, safe='')}"))
    if not isinstance(data, dict):
        raise SkillHubMarketError(
            f"SkillHub skillset {safe_slug!r} not found",
            kind=SkillHubMarketErrorKind.NOT_FOUND,
        )
    item = _skillset_from_raw(data)
    if not item.slug:
        raise SkillHubMarketError(
            f"SkillHub skillset {safe_slug!r} not found",
            kind=SkillHubMarketErrorKind.NOT_FOUND,
        )
    return item


def install_skillset_template(*, slug: str, cache_root: Path) -> SkillHubSkillset:
    """Download a SkillHub skillset and cache it as an ExpertCatalog directory."""
    safe_slug = validate_skillset_slug(slug)
    with _install_lock_for(safe_slug):
        return _install_skillset_template_locked(slug=safe_slug, cache_root=cache_root)


def _install_skillset_template_locked(*, slug: str, cache_root: Path) -> SkillHubSkillset:
    item = fetch_skillset(slug)
    package = _download_skillset_package(item.slug)
    try:
        manifest, prompt = _parse_skillset_package(
            package,
            skillset_slug=item.slug,
            fallback_content=item.content,
        )
    except SkillHubMarketError:
        raise
    except zipfile.BadZipFile as exc:
        raise SkillHubMarketError(
            "SkillHub skillset package is not a valid zip",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        ) from exc
    skill_slugs = _manifest_skill_slugs(manifest) or list(item.skill_slugs)
    if not skill_slugs:
        raise SkillHubMarketError(
            f"SkillHub skillset {item.slug!r} has no skills",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        )

    cache_root.mkdir(parents=True, exist_ok=True)
    staging = cache_root / f".tmp-{item.expert_id}-{os.getpid()}-{time.time_ns()}"
    try:
        _write_expert_template(
            expert_dir=staging,
            item=item,
            skill_slugs=skill_slugs,
            skillset_prompt=prompt,
        )
        for skill_slug in skill_slugs:
            _download_skill_into_template(
                skill_slug=skill_slug,
                expert_dir=staging,
            )
        _replace_dir(staging, cache_root / item.expert_id)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return item


def _replace_dir(src: Path, dest: Path) -> None:
    """Atomically replace ``dest`` with ``src`` on the same filesystem."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup: Path | None = None
    if dest.exists():
        backup = dest.with_name(f".{dest.name}.old-{os.getpid()}-{time.time_ns()}")
        dest.rename(backup)
    try:
        src.rename(dest)
    except Exception:
        if backup is not None and backup.exists() and not dest.exists():
            backup.rename(dest)
        raise
    if backup is not None:
        shutil.rmtree(backup, ignore_errors=True)


def _skillset_from_raw(raw: dict[str, Any]) -> SkillHubSkillset:
    skill_slugs = raw.get("skillSlugs")
    if not isinstance(skill_slugs, list):
        skill_slugs = []
    cleaned_slugs = tuple(str(s).strip() for s in skill_slugs if str(s).strip())
    return SkillHubSkillset(
        slug=str(raw.get("slug") or "").strip(),
        display_name=str(raw.get("displayName") or raw.get("name") or "").strip(),
        display_name_en=str(raw.get("displayNameEn") or "").strip(),
        summary=str(raw.get("summary") or raw.get("description") or "").strip(),
        summary_en=str(raw.get("summaryEn") or "").strip(),
        scene=str(raw.get("scene") or "").strip(),
        sub_scene=str(raw.get("subScene") or raw.get("sub_scene") or "").strip(),
        content=str(raw.get("content") or "").strip(),
        content_en=str(raw.get("contentEn") or "").strip(),
        icon_url=str(raw.get("iconUrl") or "").strip(),
        skill_slugs=cleaned_slugs,
        skill_count=_coerce_nonneg_int(raw.get("skillCount"), default=len(cleaned_slugs)),
        raw=raw,
    )


def _coerce_positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _coerce_nonneg_int(value: Any, *, default: int) -> int:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return default
    return out if out >= 0 else default


def _api_host() -> str:
    return (os.environ.get("SKILLHUB_HOST", "").strip() or DEFAULT_SKILLHUB_HOST).rstrip("/")


def _api_url(path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{_api_host()}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _http_get(url: str, *, accept: str) -> bytes:
    req = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "octop-expert-skillhub/1.0",
        },
    )
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return _read_response_limited(resp, url=url)
    except HTTPError as exc:
        if exc.code == 404:
            raise SkillHubMarketError(
                "SkillHub resource not found",
                kind=SkillHubMarketErrorKind.NOT_FOUND,
            ) from exc
        raise SkillHubMarketError(
            f"SkillHub request failed: HTTP {exc.code}",
            kind=SkillHubMarketErrorKind.UPSTREAM_FAILED,
        ) from exc
    except TimeoutError as exc:
        raise SkillHubMarketError(
            "SkillHub request timed out",
            kind=SkillHubMarketErrorKind.UPSTREAM_TIMEOUT,
        ) from exc
    except URLError as exc:
        reason = str(getattr(exc, "reason", "") or exc).lower()
        kind = (
            SkillHubMarketErrorKind.UPSTREAM_TIMEOUT
            if "timed out" in reason or "timeout" in reason
            else SkillHubMarketErrorKind.UPSTREAM_FAILED
        )
        raise SkillHubMarketError(
            "SkillHub request failed",
            kind=kind,
        ) from exc
    except OSError as exc:
        raise SkillHubMarketError(
            "SkillHub request failed",
            kind=SkillHubMarketErrorKind.UPSTREAM_FAILED,
        ) from exc


def _read_response_limited(resp: Any, *, url: str) -> bytes:
    content_length = resp.headers.get("Content-Length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError:
            declared = -1
        if declared > _MAX_HTTP_BYTES:
            raise SkillHubMarketError(
                f"SkillHub response too large for {url}",
                kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
            )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = resp.read(_HTTP_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_HTTP_BYTES:
            raise SkillHubMarketError(
                f"SkillHub response too large for {url}",
                kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _http_json_get(url: str) -> Any:
    payload = _http_get(url, accept="application/json")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SkillHubMarketError(
            "SkillHub returned invalid JSON",
            kind=SkillHubMarketErrorKind.UPSTREAM_BAD_PAYLOAD,
        ) from exc


def _download_skillset_package(slug: str) -> bytes:
    url = _api_url(f"/api/v1/skillsets/{quote(slug, safe='')}/download")
    return _http_get(url, accept="application/zip,*/*")


def _download_skill_package(slug: str) -> bytes:
    url = _api_url("/api/v1/download", params={"slug": slug})
    return _http_get(url, accept="application/zip,*/*")


def _parse_skillset_package(
    zip_bytes: bytes,
    *,
    skillset_slug: str,
    fallback_content: str,
) -> tuple[dict[str, Any], str]:
    try:
        import io

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            _validate_zip(zf)
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            prompt = ""
            zip_names = zf.namelist()
            skillset_files = [
                n for n in zip_names if n.startswith("skillsets/") and n.endswith(".md")
            ]
            if skillset_files:
                preferred = f"skillsets/{skillset_slug}.md"
                selected = preferred if preferred in zip_names else skillset_files[0]
                prompt = zf.read(selected).decode("utf-8")
            elif "identify.md" in zip_names:
                prompt = zf.read("identify.md").decode("utf-8")
            elif fallback_content:
                prompt = fallback_content
    except SkillHubMarketError:
        raise
    except KeyError as exc:
        raise SkillHubMarketError(
            "SkillHub skillset package missing manifest.json",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        ) from exc
    except zipfile.BadZipFile as exc:
        raise SkillHubMarketError(
            "SkillHub skillset package is not a valid zip",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SkillHubMarketError(
            "Failed to parse SkillHub skillset package",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        ) from exc
    if not isinstance(manifest, dict):
        raise SkillHubMarketError(
            "SkillHub skillset manifest is invalid",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        )
    if not prompt.strip():
        raise SkillHubMarketError(
            "SkillHub skillset package missing workflow prompt",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        )
    return manifest, _dedupe_frontmatter(prompt)


def _manifest_skill_slugs(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get("skillSlugs")
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    skillsets = manifest.get("skillSets")
    if not isinstance(skillsets, list):
        return []
    out: list[str] = []
    for item in skillsets:
        if not isinstance(item, dict):
            continue
        slugs = item.get("skillSlugs")
        if isinstance(slugs, list):
            out.extend(str(s).strip() for s in slugs if str(s).strip())
    seen: set[str] = set()
    deduped: list[str] = []
    for slug in out:
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append(slug)
    return deduped


def _write_expert_template(
    *,
    expert_dir: Path,
    item: SkillHubSkillset,
    skill_slugs: list[str],
    skillset_prompt: str,
) -> None:
    expert_dir.mkdir(parents=True, exist_ok=True)
    (expert_dir / "manifest.json").write_text(
        json.dumps(
            _expert_manifest(item, skill_slugs, skillset_prompt=skillset_prompt),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (expert_dir / "SOUL.md").write_text(_expert_soul(item, skill_slugs), encoding="utf-8")
    skillset_dir = expert_dir / "skills" / item.slug
    skillset_dir.mkdir(parents=True, exist_ok=True)
    (skillset_dir / "SKILL.md").write_text(skillset_prompt, encoding="utf-8")


def _download_skill_into_template(*, skill_slug: str, expert_dir: Path) -> None:
    validate_skillset_slug(skill_slug)
    zip_bytes = _download_skill_package(skill_slug)
    target_dir = expert_dir / "skills" / skill_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        _extract_zip(zip_bytes, target_dir)
    except zipfile.BadZipFile as exc:
        raise SkillHubMarketError(
            f"SkillHub skill package {skill_slug!r} is not a valid zip",
            kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
        ) from exc


def _extract_zip(zip_bytes: bytes, target_dir: Path) -> None:
    import io

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        _validate_zip(zf)
        for member in zf.infolist():
            if member.is_dir():
                continue
            dest = target_dir / member.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src:
                dest.write_bytes(_read_zip_member_limited(src, member))


def _read_zip_member_limited(src: Any, member: zipfile.ZipInfo) -> bytes:
    remaining = member.file_size
    if remaining < 0 or remaining > _MAX_ZIP_UNCOMPRESSED_BYTES:
        raise SkillHubMarketError(
            f"zip entry too large: {member.filename}",
            kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = src.read(_HTTP_READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > remaining or total > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise SkillHubMarketError(
                f"zip entry too large: {member.filename}",
                kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_zip(zf: zipfile.ZipFile) -> None:
    infos = zf.infolist()
    if len(infos) > _MAX_ZIP_ENTRIES:
        raise SkillHubMarketError(
            "zip has too many entries",
            kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
        )
    total_uncompressed = 0
    for member in infos:
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise SkillHubMarketError(
                f"unsafe zip path entry: {member.filename}",
                kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
            )
        if member.file_size < 0:
            raise SkillHubMarketError(
                f"invalid zip entry size: {member.filename}",
                kind=SkillHubMarketErrorKind.PACKAGE_INVALID,
            )
        total_uncompressed += member.file_size
        if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise SkillHubMarketError(
                "zip uncompressed size exceeds limit",
                kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
            )
        compressed = member.compress_size or 0
        if (
            compressed > 0
            and member.file_size / compressed > _MAX_ZIP_COMPRESSION_RATIO
            and member.file_size > 1024 * 1024
        ):
            raise SkillHubMarketError(
                f"zip compression ratio too high: {member.filename}",
                kind=SkillHubMarketErrorKind.PACKAGE_TOO_LARGE,
            )


def _dedupe_frontmatter(text: str) -> str:
    """Remove a repeated leading YAML frontmatter block if SkillHub duplicated it."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    block = text[: end + 4]
    rest = text[end + 4 :].lstrip("\n")
    if rest.startswith(block):
        return f"{block}\n\n{rest[len(block) :].lstrip()}"
    return text


def _expert_label_zh(item: SkillHubSkillset) -> str:
    name = (item.display_name or item.slug).strip()
    if not name:
        return "专家"
    return name if name.endswith("专家") else f"{name}专家"


def _expert_label_en(item: SkillHubSkillset) -> str:
    name = (item.display_name_en or _title_from_slug(item.slug) or item.slug).strip()
    if not name:
        return "Expert"
    return name if name.lower().endswith("expert") else f"{name} Expert"


def _expert_summary_en(item: SkillHubSkillset, name_en: str) -> str:
    return item.summary_en.strip() if item.summary_en.strip() else f"Expert workflow for {name_en}."


_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _looks_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _capability_welcome_line(
    summary: str,
    *,
    fallback: str,
    max_chars: int,
    require_chinese: bool | None = None,
) -> str:
    """One complete capability line for the chat welcome subtitle.

    Never truncates with an ellipsis. If the summary cannot fit as one full
    sentence, fall back to a short complete line instead.
    """
    cleaned = " ".join((summary or "").split())
    if require_chinese is True and cleaned and not _looks_chinese(cleaned):
        cleaned = ""
    if require_chinese is False and cleaned and _looks_chinese(cleaned):
        cleaned = ""
    if cleaned:
        for sep in ("。", "！", "？", ".", "!", "?"):
            idx = cleaned.find(sep)
            if idx >= 6:
                cleaned = cleaned[:idx].strip()
                break
        if 6 <= len(cleaned) <= max_chars:
            return cleaned
    fb = " ".join((fallback or "").split())
    return fb if fb else fallback


def _title_from_slug(slug: str) -> str:
    words = [word for word in re.split(r"[-_.\s]+", slug.strip()) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _expert_manifest(
    item: SkillHubSkillset,
    skill_slugs: list[str],
    *,
    skillset_prompt: str = "",
) -> dict[str, Any]:
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    summary_zh = item.summary
    summary_en = _expert_summary_en(item, name_en)
    return {
        "id": item.expert_id,
        "label": {"zh": name_zh, "en": name_en},
        "description": {"zh": summary_zh, "en": summary_en},
        "welcome_message": {
            "zh": _capability_welcome_line(
                item.summary,
                fallback="提供专业、可落地的专家工作流支持",
                max_chars=40,
                require_chinese=True,
            ),
            "en": _capability_welcome_line(
                item.summary_en,
                fallback="Practical expert workflow support for your goals",
                max_chars=90,
                require_chinese=False,
            ),
        },
        "icon_name": _scene_icon_name(item.scene),
        "color": _scene_color(item.scene),
        "prompt_files": ["SOUL.md"],
        "quick_prompts": quick_prompts_for_skillset(item, skillset_prompt),
        "source": {
            "type": "skillhub",
            "kind": "skillset",
            "slug": item.slug,
            "scene": item.scene,
            "sub_scene": item.sub_scene,
        },
        "skillhub": {
            "slug": item.slug,
            "scene": item.scene,
            "sub_scene": item.sub_scene,
            "skill_slugs": skill_slugs,
        },
    }


def _expert_soul(item: SkillHubSkillset, skill_slugs: list[str]) -> str:
    name = _expert_label_zh(item)
    skill_list = "\n".join(f"- `{slug}`" for slug in skill_slugs)
    summary = item.summary or "围绕该 SkillHub skillset 提供专家级工作流支持。"
    return f"""# {name}

你是「{name}」，来源于 SkillHub skillset `{item.slug}`。

## 专家定位

{summary}

## 工作方式

- 优先遵循 `skills/{item.slug}/SKILL.md` 中的工作流编排。
- 根据用户目标主动拆解步骤、识别输入缺口，并给出可执行产物。
- 需要具体能力时，调用已安装的配套技能；不要把技能清单当作用户可见负担。
- 输出时保持结构清晰，先给结论和下一步，再补充必要依据。

## 配套技能

{skill_list}
"""


def _default_quick_prompts(item: SkillHubSkillset) -> list[dict[str, Any]]:
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    cards = [
        (
            "开始处理任务",
            "Start a task",
            "描述目标与上下文，马上开始",
            "Describe the goal and start now",
            f"请作为「{name_zh}」，帮我完成以下任务：\n我的情况/目标/材料是：\n",
            f"As the {name_en}, help me complete this task:\nMy context, goals, or materials are:\n",
            "zap",
        ),
        (
            "先制定计划",
            "Make a plan",
            "先拆步骤、材料与交付物",
            "Break down steps and deliverables",
            f"请根据「{name_zh}」工作流，先制定执行计划：\n我的情况/目标/材料是：\n",
            f"Using the {name_en} workflow, first create a plan:\nMy context, goals, or materials are:\n",
            "list-todo",
        ),
        (
            "分析现状",
            "Analyze status",
            "梳理问题、风险与优先级",
            "Review issues, risks, and priorities",
            f"请作为「{name_zh}」，帮我分析当前情况：\n我的情况/目标/材料是：\n",
            f"As the {name_en}, analyze the current situation:\nMy context, goals, or materials are:\n",
            "activity",
        ),
        (
            "产出结果",
            "Produce result",
            "直接生成可交付成果",
            "Generate a ready-to-use deliverable",
            f"请作为「{name_zh}」，直接给出可交付结果：\n我的情况/目标/材料是：\n",
            f"As the {name_en}, produce a ready deliverable:\nMy context, goals, or materials are:\n",
            "presentation",
        ),
        (
            "优化修改",
            "Refine output",
            "基于反馈迭代改进",
            "Iterate based on feedback",
            f"请作为「{name_zh}」，帮我优化下面内容：\n我的情况/目标/材料是：\n",
            f"As the {name_en}, refine the following content:\nMy context, goals, or materials are:\n",
            "sparkles",
        ),
        (
            "答疑澄清",
            "Ask & clarify",
            "先问清关键细节再继续",
            "Clarify key details before continuing",
            f"请作为「{name_zh}」，先向我确认关键信息：\n我的情况/目标/材料是：\n",
            f"As the {name_en}, first clarify the key details:\nMy context, goals, or materials are:\n",
            "message-square",
        ),
    ]
    return [
        {
            "title": {"zh": title_zh, "en": title_en},
            "description": {"zh": desc_zh, "en": desc_en},
            "prompt": {"zh": prompt_zh, "en": prompt_en},
            "color": _QUICK_PROMPT_COLORS[idx % len(_QUICK_PROMPT_COLORS)],
            "icon_name": icon,
        }
        for idx, (
            title_zh,
            title_en,
            desc_zh,
            desc_en,
            prompt_zh,
            prompt_en,
            icon,
        ) in enumerate(cards)
    ]


def quick_prompts_for_skillset(
    item: SkillHubSkillset,
    workflow_prompt: str | None = None,
) -> list[dict[str, Any]]:
    prompts = _workflow_quick_prompts(item, workflow_prompt or item.content)
    return _ensure_min_quick_prompts(item, prompts)


def _ensure_min_quick_prompts(
    item: SkillHubSkillset,
    prompts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pad with default entry cards so each expert exposes at least six starters."""
    out = list(prompts[:_MAX_WORKFLOW_QUICK_PROMPTS])
    if len(out) >= _MAX_WORKFLOW_QUICK_PROMPTS:
        return out
    seen = {
        (
            str((p.get("title") or {}).get("zh") or "").strip(),
            str((p.get("title") or {}).get("en") or "").strip(),
        )
        for p in out
    }
    for filler in _default_quick_prompts(item):
        if len(out) >= _MAX_WORKFLOW_QUICK_PROMPTS:
            break
        key = (
            str((filler.get("title") or {}).get("zh") or "").strip(),
            str((filler.get("title") or {}).get("en") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(filler)
    return out


def _workflow_quick_prompts(
    item: SkillHubSkillset,
    workflow_prompt: str,
) -> list[dict[str, Any]]:
    steps = _workflow_steps(workflow_prompt)
    if not steps:
        return []
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    prompts: list[dict[str, Any]] = []
    for idx, step in enumerate(steps[:_MAX_WORKFLOW_QUICK_PROMPTS]):
        title = _clip_text(step["title"], 16)
        description = _clip_text(_step_description(step["section"]), 28)
        if not description:
            description = f"完成「{title}」"
        prompts.append(
            {
                "title": {
                    "zh": title,
                    "en": _english_step_title(title, idx),
                },
                "description": {
                    "zh": description,
                    "en": _clip_text(
                        _english_step_description(step["section"], idx),
                        40,
                    ),
                },
                "prompt": {
                    "zh": _workflow_prompt_zh(name_zh, step),
                    "en": _workflow_prompt_en(name_en, idx, step),
                },
                "color": _QUICK_PROMPT_COLORS[idx % len(_QUICK_PROMPT_COLORS)],
                "icon_name": _quick_prompt_icon(step["title"], step["section"], idx),
            }
        )
    return prompts


def _workflow_steps(workflow_prompt: str) -> list[dict[str, str]]:
    matches = list(_STEP_HEADING_RE.finditer(workflow_prompt or ""))
    steps: list[dict[str, str]] = []
    for idx, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(workflow_prompt)
        raw_title = match.group(2).strip()
        title = _clean_step_title(raw_title)
        if not title:
            continue
        steps.append(
            {
                "number": match.group(1),
                "title": title,
                "section": workflow_prompt[section_start:section_end].strip(),
            }
        )
    return steps


def _clean_step_title(raw: str) -> str:
    text = re.sub(r"[（(][^）)]*层[）)]", "", raw).strip()
    return text.strip(" ：:-")


def _workflow_prompt_zh(name_zh: str, step: dict[str, str]) -> str:
    title = _clip_text(step["title"], 24)
    return f"请作为「{name_zh}」，帮我完成「{title}」。\n我的情况/目标/材料是：\n"


def _workflow_prompt_en(
    name_en: str,
    idx: int,
    step: dict[str, str],
) -> str:
    title_en = _english_step_title(step["title"], idx)
    return f"As the {name_en}, help me with: {title_en}.\nMy context, goals, or materials are:\n"


def _english_step_title(title: str, idx: int) -> str:
    """Use the source title when it is already English; otherwise a neutral step label."""
    clean = _clip_text(title, 24)
    if clean and not re.search(r"[\u3400-\u9fff]", clean):
        return clean
    return f"Workflow step {idx + 1}"


def _english_step_description(section: str, idx: int) -> str:
    output = _step_output_target(section)
    if output and not re.search(r"[\u3400-\u9fff]", output):
        return output
    return "Share context for a ready result"


def _step_description(section: str) -> str:
    output = _step_output_target(section)
    if output:
        return _normalize_output_line(output)
    for line in section.splitlines():
        text = _clean_markdown_line(line)
        if not text:
            continue
        if text.startswith("- "):
            return text[2:].strip().rstrip("。")
    return ""


def _step_output_target(section: str) -> str:
    for line in section.splitlines():
        text = _clean_markdown_line(line)
        if not text:
            continue
        if text.startswith("输出物"):
            return _normalize_output_target(text.removeprefix("输出物"))
        if text.startswith("输出"):
            return _normalize_output_target(text.removeprefix("输出"))
    return ""


def _clean_markdown_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^\s*[-*]\s+", "- ", text)
    text = text.replace("**", "").replace("`", "")
    return text.strip()


def _normalize_output_target(text: str) -> str:
    text = text.strip(" ：:。")
    if text.startswith("：") or text.startswith(":"):
        text = text[1:].strip()
    return text.rstrip("。")


def _normalize_output_line(text: str) -> str:
    target = _normalize_output_target(text)
    if not target:
        return ""
    if target.startswith(("生成", "输出", "给出", "形成", "交付")):
        return target.rstrip("。")
    return f"生成{target}".rstrip("。")


def _clip_text(text: str, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _quick_prompt_icon(title: str, section: str, idx: int) -> str:
    text = f"{title}\n{section}"
    keyword_icons = [
        (("巡检", "健康", "诊断", "异常", "日志", "监控", "分析"), "activity"),
        (("评分", "指标", "数据", "统计", "预算", "投研", "经营", "趋势"), "trending-up"),
        (("修复", "调试", "排查", "配置", "风险"), "wrench"),
        (("云", "实例", "OS", "服务器", "集群", "节点"), "server"),
        (("代码", "测试", "脚本", "命令", "自动化"), "terminal"),
        (("视频", "分镜", "镜头", "画面", "剪辑", "脚本"), "video"),
        (("合同", "文书", "报告", "纪要", "简历", "法条"), "file-text"),
        (("检索", "搜索", "法规", "跨境", "市场"), "globe"),
        (("计划", "方案", "策略", "SOP", "流程", "清单"), "list-todo"),
        (("输出", "生成", "导出", "PPT", "PDF", "交付"), "presentation"),
    ]
    for keywords, icon in keyword_icons:
        if any(k in text for k in keywords):
            return icon
    return [
        "zap",
        "list-todo",
        "activity",
        "file-text",
        "presentation",
        "sparkles",
        "message-square",
        "book-open",
        "globe",
    ][idx % 9]


def _scene_icon_name(scene: str) -> str:
    mapping = {
        "academic": "book-open",
        "content-creation": "pen-tool",
        "design": "palette",
        "ecommerce": "globe",
        "education": "book-open",
        "finance": "candlestick-chart",
        "healthcare": "heart",
        "lifestyle": "heart",
        "marketing": "trending-up",
        "mysticism": "sparkles",
        "tech": "cpu",
        "media": "video",
        "legal": "file-text",
        "hr": "user",
        "office": "presentation",
        "data": "trending-up",
    }
    return mapping.get(scene, "zap")


def _scene_color(scene: str) -> str:
    mapping = {
        "academic": "#4f46e5",
        "content-creation": "#c026d3",
        "design": "#db2777",
        "ecommerce": "#16a34a",
        "education": "#2563eb",
        "finance": "#059669",
        "healthcare": "#dc2626",
        "lifestyle": "#f97316",
        "marketing": "#ca8a04",
        "mysticism": "#7c3aed",
        "tech": "#2563eb",
        "media": "#db2777",
        "legal": "#0f766e",
        "hr": "#7c3aed",
        "office": "#ea580c",
        "data": "#0891b2",
    }
    return mapping.get(scene, "#6366f1")
