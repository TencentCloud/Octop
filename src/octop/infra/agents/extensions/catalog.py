"""Private catalog for extensions created by the Extension Builder expert."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import yaml

from octop.infra.agents.extensions.service import ExtensionBuilderError, ExtensionKind
from octop.infra.skills.skill_packages import validate_skill_slug
from octop.infra.utils.ulid import new_ulid

CatalogKind = Literal["skill", "plugin"]
_CATALOG_SCHEMA_VERSION = 1


def _safe_owner_id(value: int) -> str:
    owner_id = int(value)
    if owner_id < 1:
        raise ExtensionBuilderError("owner_user_id must be positive")
    return str(owner_id)


def _safe_slug(value: str) -> str:
    try:
        return validate_skill_slug(value)
    except Exception as exc:
        raise ExtensionBuilderError("invalid extension slug") from exc


def _safe_file_path(value: str) -> Path:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ExtensionBuilderError(f"unsafe catalog file path: {value!r}")
    return Path(*path.parts)


class ExtensionCatalog:
    """Store validated extensions in an owner-scoped, versioned catalog."""

    def __init__(self, root: Path, *, reserved_plugins_root: Path | None = None) -> None:
        self.root = root
        self._reserved_plugins_root = reserved_plugins_root

    def publish(
        self,
        *,
        owner_user_id: int,
        project_id: str,
        artifact_type: ExtensionKind,
        slug: str,
        goal: str,
        created_at: str,
        revision: str,
        sha256: str,
        files: dict[str, bytes],
    ) -> list[dict[str, Any]]:
        """Publish one validated project to the owner's visible catalogs."""
        owner = _safe_owner_id(owner_user_id)
        safe_slug = _safe_slug(slug)
        published_at = datetime.now(UTC).isoformat()
        entries: list[dict[str, Any]] = []

        if artifact_type in {"plugin", "hybrid"}:
            if (
                self._reserved_plugins_root is not None
                and (self._reserved_plugins_root / safe_slug).is_dir()
            ):
                raise ExtensionBuilderError(
                    f"plugin id conflicts with the built-in marketplace: {safe_slug}"
                )
            entries.append(
                self._publish_entry(
                    owner=owner,
                    kind="plugin",
                    slug=safe_slug,
                    project_id=project_id,
                    artifact_type=artifact_type,
                    goal=goal,
                    created_at=created_at,
                    published_at=published_at,
                    revision=revision,
                    sha256=sha256,
                    files=files,
                )
            )

        if artifact_type in {"skill", "hybrid"}:
            if artifact_type == "skill":
                skill_files = files
            else:
                prefix = f"skills/{safe_slug}/"
                skill_files = {
                    path.removeprefix(prefix): data
                    for path, data in files.items()
                    if path.startswith(prefix)
                }
            entries.append(
                self._publish_entry(
                    owner=owner,
                    kind="skill",
                    slug=safe_slug,
                    project_id=project_id,
                    artifact_type=artifact_type,
                    goal=goal,
                    created_at=created_at,
                    published_at=published_at,
                    revision=revision,
                    sha256=sha256,
                    files=skill_files,
                )
            )
        return entries

    def _publish_entry(
        self,
        *,
        owner: str,
        kind: CatalogKind,
        slug: str,
        project_id: str,
        artifact_type: ExtensionKind,
        goal: str,
        created_at: str,
        published_at: str,
        revision: str,
        sha256: str,
        files: dict[str, bytes],
    ) -> dict[str, Any]:
        if not files:
            raise ExtensionBuilderError(f"{kind} catalog entry has no files")
        item_root = self.root / "users" / owner / f"{kind}s" / slug
        release_root = item_root / "releases" / revision
        if not release_root.exists():
            for relative_path, payload in files.items():
                target = release_root / _safe_file_path(relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)

        metadata: dict[str, Any] = {
            "schema_version": _CATALOG_SCHEMA_VERSION,
            "owner_user_id": int(owner),
            "project_id": project_id,
            "artifact_type": artifact_type,
            "catalog_kind": kind,
            "slug": slug,
            "goal": goal,
            "created_at": created_at,
            "published_at": published_at,
            "revision": revision,
            "sha256": sha256,
            "release": f"releases/{revision}",
        }
        item_root.mkdir(parents=True, exist_ok=True)
        temp = item_root / f".catalog-{new_ulid()}.tmp"
        temp.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp.replace(item_root / "catalog.json")
        return {
            "kind": kind,
            "slug": slug,
            "revision": revision,
            "published_at": published_at,
        }

    def list_plugins(self, owner_user_id: int) -> list[dict[str, Any]]:
        return self._list_entries(owner_user_id, "plugin")

    def list_skills(self, owner_user_id: int) -> list[dict[str, Any]]:
        entries = self._list_entries(owner_user_id, "skill")
        out: list[dict[str, Any]] = []
        for entry in entries:
            skill_dir = self.resolve_skill_dir(owner_user_id, str(entry["slug"]))
            if skill_dir is None:
                continue
            try:
                text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
                metadata = self._skill_frontmatter(text)
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                metadata = {}
            out.append(
                {
                    **entry,
                    "name": str(metadata.get("name") or entry["slug"]),
                    "description": str(metadata.get("description") or entry.get("goal") or ""),
                }
            )
        return out

    def resolve_plugin_dir(self, owner_user_id: int, slug: str) -> Path | None:
        return self._resolve_release(owner_user_id, "plugin", slug)

    def resolve_skill_dir(self, owner_user_id: int, slug: str) -> Path | None:
        return self._resolve_release(owner_user_id, "skill", slug)

    def _list_entries(self, owner_user_id: int, kind: CatalogKind) -> list[dict[str, Any]]:
        root = self.root / "users" / _safe_owner_id(owner_user_id) / f"{kind}s"
        if not root.is_dir():
            return []
        out: list[dict[str, Any]] = []
        for item_root in sorted(root.iterdir()):
            if not item_root.is_dir() or item_root.is_symlink():
                continue
            metadata = self._read_metadata(item_root)
            if metadata is None or metadata.get("catalog_kind") != kind:
                continue
            release = self._release_from_metadata(item_root, metadata)
            if release is None:
                continue
            out.append({**metadata, "source": "created", "created": True})
        return out

    def _resolve_release(
        self,
        owner_user_id: int,
        kind: CatalogKind,
        slug: str,
    ) -> Path | None:
        safe_slug = _safe_slug(slug)
        item_root = self.root / "users" / _safe_owner_id(owner_user_id) / f"{kind}s" / safe_slug
        metadata = self._read_metadata(item_root)
        if metadata is None or metadata.get("catalog_kind") != kind:
            return None
        return self._release_from_metadata(item_root, metadata)

    @staticmethod
    def _read_metadata(item_root: Path) -> dict[str, Any] | None:
        try:
            raw = json.loads((item_root / "catalog.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _release_from_metadata(item_root: Path, metadata: dict[str, Any]) -> Path | None:
        raw = str(metadata.get("release") or "")
        relative = PurePosixPath(raw)
        if relative.is_absolute() or ".." in relative.parts:
            return None
        release = (item_root / Path(*relative.parts)).resolve()
        try:
            release.relative_to(item_root.resolve())
        except ValueError:
            return None
        return release if release.is_dir() else None

    @staticmethod
    def _skill_frontmatter(text: str) -> dict[str, Any]:
        if not text.startswith("---\n"):
            return {}
        end = text.find("\n---", 4)
        if end < 0:
            return {}
        raw = yaml.safe_load(text[4:end]) or {}
        return raw if isinstance(raw, dict) else {}


__all__ = ["ExtensionCatalog"]
