"""Create, validate, and package Octop Skill and Plugin drafts.

The service only works through ``BackendWorkspace``. It never imports generated
Plugin code and never installs a generated artifact into the Octop process.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

import yaml
from octop_harness.plugins import PluginManifest

from octop.infra.skills.skill_packages import (
    SkillPackageError,
    SkillPackageTooLarge,
    resolve_skill_package,
    validate_skill_slug,
)
from octop.infra.utils.ulid import new_ulid

if TYPE_CHECKING:
    from octop.infra.agents.extensions.catalog import ExtensionCatalog

ExtensionKind = Literal["skill", "plugin", "hybrid"]

PROJECTS_ROOT = "extension-projects"
ARTIFACTS_ROOT = "artifacts/extensions"
_PROJECT_SCHEMA_VERSION = 1
_PROJECT_ID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---(?:\s*\n|$)", re.DOTALL)
_MAX_FILES = 256
_MAX_FILE_BYTES = 1_000_000
_MAX_TOTAL_BYTES = 8_000_000
_MAX_DEPTH = 12
_PLACEHOLDERS = ("[REPLACE_ME]", "TODO:", "NotImplementedError")
_SENSITIVE_IMPORTS = frozenset({"ctypes", "multiprocessing", "resource", "subprocess"})
_SENSITIVE_CALLS = frozenset({"eval", "exec", "os.system", "os.popen"})


class ExtensionBuilderError(ValueError):
    """A safe error that can be returned to the builder agent."""


@dataclass(frozen=True)
class ExtensionProject:
    project_id: str
    artifact_type: ExtensionKind
    slug: str
    goal: str
    created_at: str

    @property
    def root(self) -> str:
        return f"{PROJECTS_ROOT}/{self.project_id}"

    @property
    def source_root(self) -> str:
        return f"{self.root}/source/{self.slug}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": _PROJECT_SCHEMA_VERSION,
            "project_id": self.project_id,
            "artifact_type": self.artifact_type,
            "slug": self.slug,
            "goal": self.goal,
            "created_at": self.created_at,
        }


def _entry_value(entry: Any, name: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _safe_relative_path(value: str) -> str:
    text = str(value).strip().replace("\\", "/")
    path = PurePosixPath(text)
    if not text or path.is_absolute() or ".." in path.parts or "\x00" in text:
        raise ExtensionBuilderError(f"unsafe relative path: {value!r}")
    return path.as_posix()


def _normalize_kind(value: str) -> ExtensionKind:
    kind = str(value or "").strip().lower()
    if kind not in {"skill", "plugin", "hybrid"}:
        raise ExtensionBuilderError("artifact_type must be skill, plugin, or hybrid")
    return kind  # type: ignore[return-value]


def _normalize_slug(value: str) -> str:
    raw = str(value or "").strip()
    if not _SLUG_RE.fullmatch(raw):
        raise ExtensionBuilderError("slug must use lowercase letters, digits, and hyphens")
    try:
        return validate_skill_slug(raw)
    except SkillPackageError as exc:
        raise ExtensionBuilderError("slug must use lowercase letters, digits, and hyphens") from exc


def _skill_template(slug: str, goal: str) -> str:
    description = " ".join(goal.strip().split())
    return f"---\nname: {slug}\ndescription: {description}\n---\n\n# {slug}\n\n[REPLACE_ME]\n"


def _plugin_manifest(slug: str, goal: str, *, include_skills: bool) -> str:
    payload = {
        "id": slug,
        "version": "0.1.0",
        "name": slug,
        "description": " ".join(goal.strip().split()),
        "kind": "tool",
        "entry": "main.py",
        "requires": [],
    }
    if include_skills:
        payload["skills"] = "skills"
    return str(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))


def _python_name(slug: str) -> str:
    return slug.replace("-", "_")


def _plugin_entry(slug: str) -> str:
    fn_name = f"run_{_python_name(slug)}"
    return (
        '"""Generated Octop plugin draft."""\n\n'
        "from __future__ import annotations\n\n"
        "from octop_harness.plugins import PluginContext\n\n\n"
        f"async def {fn_name}(value: str) -> str:\n"
        '    """Handle one plugin request."""\n'
        '    return "[REPLACE_ME]"\n\n\n'
        "def setup(ctx: PluginContext) -> None:\n"
        f'    ctx.tool("{fn_name}", {fn_name}, description="[REPLACE_ME]")\n'
    )


class ExtensionBuilderService:
    """Workspace-backed extension project service."""

    def __init__(
        self,
        workspace: Any,
        *,
        catalog: ExtensionCatalog | None = None,
        owner_user_id: int | None = None,
    ) -> None:
        self._workspace = workspace
        self._catalog = catalog
        self._owner_user_id = owner_user_id

    async def scaffold(
        self,
        *,
        artifact_type: str,
        slug: str,
        goal: str,
    ) -> dict[str, Any]:
        kind = _normalize_kind(artifact_type)
        normalized_slug = _normalize_slug(slug)
        normalized_goal = " ".join(str(goal or "").strip().split())
        if not normalized_goal:
            raise ExtensionBuilderError("goal is required")
        if len(normalized_goal) > 2_000:
            raise ExtensionBuilderError("goal exceeds 2000 characters")

        project = ExtensionProject(
            project_id=new_ulid(),
            artifact_type=kind,
            slug=normalized_slug,
            goal=normalized_goal,
            created_at=datetime.now(UTC).isoformat(),
        )
        files: list[tuple[str, bytes]] = [
            (
                f"{project.root}/project.json",
                (json.dumps(project.as_dict(), ensure_ascii=False, indent=2) + "\n").encode(),
            )
        ]
        if kind == "skill":
            files.append(
                (
                    f"{project.source_root}/SKILL.md",
                    _skill_template(normalized_slug, normalized_goal).encode(),
                )
            )
        else:
            files.extend(
                [
                    (
                        f"{project.source_root}/plugin.yaml",
                        _plugin_manifest(
                            normalized_slug,
                            normalized_goal,
                            include_skills=kind == "hybrid",
                        ).encode(),
                    ),
                    (
                        f"{project.source_root}/main.py",
                        _plugin_entry(normalized_slug).encode(),
                    ),
                ]
            )
            if kind == "hybrid":
                files.append(
                    (
                        f"{project.source_root}/skills/{normalized_slug}/SKILL.md",
                        _skill_template(normalized_slug, normalized_goal).encode(),
                    )
                )
        await self._workspace.aupload_many(files)
        return {
            **project.as_dict(),
            "project_root": project.root,
            "source_root": project.source_root,
            "files": [path for path, _data in files if not path.endswith("project.json")],
            "next_action": "replace scaffold placeholders, then validate the project",
        }

    async def validate(self, project_id: str) -> dict[str, Any]:
        project = await self._load_project(project_id)
        files = await self._collect_source_files(project)
        revision = self._revision(files)
        errors: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        self._validate_placeholders(files, errors)
        self._validate_text_file_format(files, errors)
        if project.artifact_type == "skill":
            self._validate_skill(project.slug, files, errors)
        else:
            self._validate_plugin(project, files, errors, warnings)
            if project.artifact_type == "hybrid":
                self._validate_hybrid_skills(project, files, errors)

        return {
            "project_id": project.project_id,
            "artifact_type": project.artifact_type,
            "slug": project.slug,
            "valid": not errors,
            "revision": revision,
            "file_count": len(files),
            "total_bytes": sum(len(data) for data in files.values()),
            "errors": errors,
            "warnings": warnings,
        }

    async def package(
        self,
        project_id: str,
        *,
        expected_revision: str,
    ) -> dict[str, Any]:
        report = await self.validate(project_id)
        if not report["valid"]:
            raise ExtensionBuilderError("project validation failed")
        revision = str(report["revision"])
        if not expected_revision or expected_revision != revision:
            raise ExtensionBuilderError("source revision changed; validate the project again")

        project = await self._load_project(project_id)
        files = await self._collect_source_files(project)
        if self._revision(files) != expected_revision:
            raise ExtensionBuilderError("source revision changed; validate the project again")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for rel_path in sorted(files):
                info = zipfile.ZipInfo(
                    f"{project.slug}/{rel_path}", date_time=(1980, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                bundle.writestr(info, files[rel_path])
        payload = output.getvalue()
        digest = hashlib.sha256(payload).hexdigest()
        artifact_path = f"{ARTIFACTS_ROOT}/{project.slug}-{digest[:12]}.zip"
        await self._workspace.aupload_bytes(artifact_path, payload)
        catalog_entries: list[dict[str, Any]] = []
        if self._catalog is not None and self._owner_user_id is not None:
            catalog_entries = self._catalog.publish(
                owner_user_id=self._owner_user_id,
                project_id=project.project_id,
                artifact_type=project.artifact_type,
                slug=project.slug,
                goal=project.goal,
                created_at=project.created_at,
                revision=revision,
                sha256=digest,
                files=files,
            )
        return {
            "project_id": project.project_id,
            "artifact_type": project.artifact_type,
            "slug": project.slug,
            "revision": revision,
            "artifact_path": artifact_path,
            "sha256": digest,
            "size_bytes": len(payload),
            "installed": False,
            "catalog_entries": catalog_entries,
        }

    async def _load_project(self, project_id: str) -> ExtensionProject:
        project_id = str(project_id or "").strip().upper()
        if not _PROJECT_ID_RE.fullmatch(project_id):
            raise ExtensionBuilderError("invalid project_id")
        raw = await self._workspace.aread_text(f"{PROJECTS_ROOT}/{project_id}/project.json")
        if raw is None:
            raise ExtensionBuilderError("extension project not found")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ExtensionBuilderError("project metadata is invalid") from exc
        if not isinstance(data, dict) or data.get("schema_version") != _PROJECT_SCHEMA_VERSION:
            raise ExtensionBuilderError("unsupported project metadata")
        stored_id = str(data.get("project_id") or "").upper()
        if stored_id != project_id:
            raise ExtensionBuilderError("project metadata does not match project_id")
        return ExtensionProject(
            project_id=project_id,
            artifact_type=_normalize_kind(str(data.get("artifact_type") or "")),
            slug=_normalize_slug(str(data.get("slug") or "")),
            goal=str(data.get("goal") or ""),
            created_at=str(data.get("created_at") or ""),
        )

    async def _collect_source_files(self, project: ExtensionProject) -> dict[str, bytes]:
        files: dict[str, bytes] = {}

        async def walk(path: str, depth: int) -> None:
            if depth > _MAX_DEPTH:
                raise ExtensionBuilderError("project directory is too deep")
            result = await self._workspace.als(path)
            if result is None or getattr(result, "error", None):
                raise ExtensionBuilderError(f"cannot list project path: {path}")
            for entry in getattr(result, "entries", None) or []:
                raw_path = str(_entry_value(entry, "path", ""))
                safe_path = _safe_relative_path(raw_path)
                prefix = f"{project.source_root}/"
                if not safe_path.startswith(prefix):
                    raise ExtensionBuilderError("project entry escaped the source root")
                if bool(_entry_value(entry, "is_dir", False)):
                    await walk(safe_path, depth + 1)
                    continue
                rel = safe_path[len(prefix) :]
                if not rel:
                    raise ExtensionBuilderError("invalid empty source path")
                if len(files) >= _MAX_FILES:
                    raise ExtensionBuilderError(f"project exceeds {_MAX_FILES} files")
                data = await self._workspace.adownload_bytes(safe_path)
                if data is None:
                    raise ExtensionBuilderError(f"cannot read project file: {rel}")
                if len(data) > _MAX_FILE_BYTES:
                    raise ExtensionBuilderError(
                        f"project file exceeds {_MAX_FILE_BYTES} bytes: {rel}"
                    )
                files[rel] = data

        await walk(project.source_root, 0)
        if not files:
            raise ExtensionBuilderError("project source is empty")
        if sum(len(data) for data in files.values()) > _MAX_TOTAL_BYTES:
            raise ExtensionBuilderError(f"project exceeds {_MAX_TOTAL_BYTES} total bytes")
        return files

    @staticmethod
    def _revision(files: dict[str, bytes]) -> str:
        digest = hashlib.sha256()
        for path in sorted(files):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[path])
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _validate_placeholders(
        files: dict[str, bytes],
        errors: list[dict[str, str]],
    ) -> None:
        for path, data in files.items():
            if PurePosixPath(path).suffix not in {".md", ".py", ".yaml", ".yml", ".json"}:
                continue
            text = data.decode("utf-8", errors="replace")
            for marker in _PLACEHOLDERS:
                if marker in text:
                    errors.append(
                        {
                            "code": "unfinished_placeholder",
                            "path": path,
                            "message": f"replace scaffold marker {marker}",
                        }
                    )
                    break

    @staticmethod
    def _validate_text_file_format(
        files: dict[str, bytes],
        errors: list[dict[str, str]],
    ) -> None:
        for path, data in files.items():
            if PurePosixPath(path).suffix not in {".md", ".py", ".yaml", ".yml", ".json"}:
                continue
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                errors.append(
                    {
                        "code": "invalid_text_encoding",
                        "path": path,
                        "message": f"text files must use UTF-8: {exc}",
                    }
                )
                continue
            if data and not data.endswith(b"\n"):
                errors.append(
                    {
                        "code": "missing_final_newline",
                        "path": path,
                        "message": "text files must end with a newline",
                    }
                )

    @staticmethod
    def _validate_skill(
        slug: str,
        files: dict[str, bytes],
        errors: list[dict[str, str]],
    ) -> None:
        try:
            resolve_skill_package(
                slug=slug,
                files=list(files.items()),
                source="extension-builder",
            )
        except (SkillPackageError, SkillPackageTooLarge) as exc:
            errors.append(
                {
                    "code": "invalid_skill",
                    "path": "SKILL.md",
                    "message": str(exc),
                }
            )
            return
        manifest = files.get("SKILL.md")
        if manifest is None:
            return
        try:
            text = manifest.decode("utf-8")
            match = _FRONTMATTER_RE.match(text)
            if match is None:
                raise ValueError("SKILL.md is missing YAML frontmatter")
            metadata = yaml.safe_load(match.group(1))
            if not isinstance(metadata, dict):
                raise ValueError("SKILL.md frontmatter must be a mapping")
            if str(metadata.get("name") or "").strip() != slug:
                raise ValueError("SKILL.md name must match the skill slug")
            if not str(metadata.get("description") or "").strip():
                raise ValueError("SKILL.md description is required")
        except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            errors.append(
                {
                    "code": "invalid_skill_manifest",
                    "path": "SKILL.md",
                    "message": str(exc),
                }
            )

    @staticmethod
    def _validate_hybrid_skills(
        project: ExtensionProject,
        files: dict[str, bytes],
        errors: list[dict[str, str]],
    ) -> None:
        prefix = "skills/"
        slugs = sorted(
            {
                path[len(prefix) :].split("/", 1)[0]
                for path in files
                if path.startswith(prefix) and "/" in path[len(prefix) :]
            }
        )
        if not slugs:
            errors.append(
                {
                    "code": "missing_plugin_skill",
                    "path": "skills",
                    "message": "hybrid plugins require at least one bundled skill",
                }
            )
            return
        for slug in slugs:
            skill_prefix = f"skills/{slug}/"
            skill_files = {
                path[len(skill_prefix) :]: data
                for path, data in files.items()
                if path.startswith(skill_prefix)
            }
            ExtensionBuilderService._validate_skill(slug, skill_files, errors)

    @staticmethod
    def _validate_plugin(
        project: ExtensionProject,
        files: dict[str, bytes],
        errors: list[dict[str, str]],
        warnings: list[dict[str, str]],
    ) -> None:
        raw_manifest = files.get("plugin.yaml")
        if raw_manifest is None:
            errors.append(
                {
                    "code": "missing_plugin_manifest",
                    "path": "plugin.yaml",
                    "message": "plugin.yaml is required",
                }
            )
            return
        try:
            loaded = yaml.safe_load(raw_manifest.decode("utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("plugin.yaml must be a mapping")
            manifest = PluginManifest.from_dict(loaded)
        except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
            errors.append(
                {
                    "code": "invalid_plugin_manifest",
                    "path": "plugin.yaml",
                    "message": str(exc),
                }
            )
            return
        if manifest.id != project.slug:
            errors.append(
                {
                    "code": "plugin_id_mismatch",
                    "path": "plugin.yaml",
                    "message": "plugin id must match the project slug",
                }
            )
        if project.artifact_type == "hybrid" and loaded.get("skills") != "skills":
            errors.append(
                {
                    "code": "missing_plugin_skills_declaration",
                    "path": "plugin.yaml",
                    "message": "hybrid plugins must declare skills: skills",
                }
            )
        try:
            entry = _safe_relative_path(manifest.entry)
        except ExtensionBuilderError as exc:
            errors.append(
                {
                    "code": "unsafe_plugin_entry",
                    "path": "plugin.yaml",
                    "message": str(exc),
                }
            )
            return
        entry_source = files.get(entry)
        if entry_source is None:
            errors.append(
                {
                    "code": "missing_plugin_entry",
                    "path": entry,
                    "message": "plugin entry file is missing",
                }
            )
            return
        if manifest.requires:
            warnings.append(
                {
                    "code": "plugin_dependencies_require_review",
                    "path": "plugin.yaml",
                    "message": "plugin dependencies require administrator review before install",
                }
            )
        for path, source in sorted(files.items()):
            if PurePosixPath(path).suffix != ".py":
                continue
            ExtensionBuilderService._validate_python_source(
                path,
                source,
                errors,
                warnings,
                require_entrypoint=path == entry,
            )

    @staticmethod
    def _validate_python_source(
        path: str,
        source: bytes,
        errors: list[dict[str, str]],
        warnings: list[dict[str, str]],
        *,
        require_entrypoint: bool,
    ) -> None:
        try:
            tree = ast.parse(source.decode("utf-8"), filename=path)
        except (SyntaxError, UnicodeDecodeError) as exc:
            errors.append(
                {
                    "code": "invalid_plugin_python",
                    "path": path,
                    "message": str(exc),
                }
            )
            return
        if require_entrypoint:
            setup_found = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "setup"
                for node in tree.body
            )
            if not setup_found:
                errors.append(
                    {
                        "code": "missing_plugin_setup",
                        "path": path,
                        "message": "plugin entry must define setup(ctx)",
                    }
                )
            tool_calls = [
                node
                for node in ast.walk(tree)
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "tool"
                )
            ]
            if not tool_calls:
                errors.append(
                    {
                        "code": "missing_plugin_tool",
                        "path": path,
                        "message": "plugin entry must register at least one tool",
                    }
                )
            for tool_call in tool_calls:
                if not tool_call.args or not isinstance(tool_call.args[0], ast.Constant):
                    warnings.append(
                        {
                            "code": "dynamic_plugin_tool_name",
                            "path": path,
                            "message": "tool names should use a static string for validation",
                        }
                    )
                    continue
                tool_name = tool_call.args[0].value
                if not isinstance(tool_name, str) or not _TOOL_NAME_RE.fullmatch(tool_name):
                    errors.append(
                        {
                            "code": "invalid_plugin_tool_name",
                            "path": path,
                            "message": (
                                "tool names must use 1-64 ASCII letters, digits, '_' or '-'"
                            ),
                        }
                    )
        warned: set[str] = set()
        for ast_node in ast.walk(tree):
            name = ""
            if isinstance(ast_node, ast.Import):
                for alias in ast_node.names:
                    root = alias.name.split(".", 1)[0]
                    if root in _SENSITIVE_IMPORTS:
                        name = root
                        break
            elif isinstance(ast_node, ast.ImportFrom) and ast_node.module:
                root = ast_node.module.split(".", 1)[0]
                if root in _SENSITIVE_IMPORTS:
                    name = root
            elif isinstance(ast_node, ast.Call):
                if isinstance(ast_node.func, ast.Name):
                    name = ast_node.func.id
                elif isinstance(ast_node.func, ast.Attribute) and isinstance(
                    ast_node.func.value, ast.Name
                ):
                    name = f"{ast_node.func.value.id}.{ast_node.func.attr}"
                if name not in _SENSITIVE_CALLS:
                    name = ""
            if name and name not in warned:
                warned.add(name)
                warnings.append(
                    {
                        "code": "sensitive_plugin_code",
                        "path": path,
                        "message": f"review sensitive operation: {name}",
                    }
                )
