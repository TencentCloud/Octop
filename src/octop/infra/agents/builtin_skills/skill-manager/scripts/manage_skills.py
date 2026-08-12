#!/usr/bin/env python3
"""Safely inspect, install, list, remove, and restore workspace Skills."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

import yaml

MAX_FILES = 2_000
MAX_BYTES = 64 * 1024 * 1024
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
RESERVED_SKILL_SLUGS = frozenset({"skill-manager"})
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class SkillManagerError(RuntimeError):
    """A safe, user-facing Skill management failure."""


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _redact_urls(value: str) -> str:
    return re.sub(r"(?i)\b(?:https?|ssh|git)://[^\s'\"]+", "<redacted-url>", value)


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-_")
    if not _SLUG_RE.fullmatch(normalized):
        raise SkillManagerError(f"invalid skill name: {value!r}")
    return normalized


def _workspace(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise SkillManagerError("--workspace must be an absolute path")
    path = path.resolve()
    if path == Path(path.anchor):
        raise SkillManagerError("refusing to use a filesystem root as the workspace")
    if not path.is_dir():
        raise SkillManagerError(f"workspace does not exist: {path}")
    return path


def _default_workspace() -> Path:
    """Infer the workspace only from this deployed built-in's location."""
    script = Path(__file__).resolve()
    try:
        workspace = script.parents[3]
    except IndexError as exc:  # pragma: no cover - installed layout always has these parents
        raise SkillManagerError("cannot infer workspace from the manager script path") from exc
    if script.parents[1].name != "skill-manager" or script.parents[2].name != "_builtin_skills":
        raise SkillManagerError("--workspace is required outside a deployed expert workspace")
    return _workspace(str(workspace))


def _skillhub_source(source: str) -> tuple[str, str] | None:
    """Return ``(slug, namespace)`` for SkillHub shorthand or page URLs."""
    if source.startswith("skillhub:"):
        value = source.partition(":")[2].strip().strip("/")
        parts = value.split("/")
        if len(parts) == 1:
            return _slug(parts[0]), ""
        if len(parts) == 2:
            namespace, slug = parts
            if not _NAMESPACE_RE.fullmatch(namespace):
                raise SkillManagerError(f"invalid SkillHub namespace: {namespace!r}")
            return _slug(slug), namespace
        raise SkillManagerError(
            "SkillHub source must be skillhub:<slug> or skillhub:<namespace>/<slug>"
        )

    parsed = urlparse(source)
    if parsed.hostname not in {"skillhub.cn", "www.skillhub.cn"}:
        return None
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 3 or parts[0] != "skills":
        raise SkillManagerError(
            "unsupported SkillHub URL; expected https://skillhub.cn/skills/<namespace>/<slug>"
        )
    namespace, slug = parts[1:]
    if not _NAMESPACE_RE.fullmatch(namespace):
        raise SkillManagerError(f"invalid SkillHub namespace: {namespace!r}")
    return _slug(slug), namespace


def _safe_relative(name: str) -> Path:
    if not name or "\\" in name or "\x00" in name:
        raise SkillManagerError(f"unsafe archive path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise SkillManagerError(f"unsafe archive path: {name!r}")
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        raise SkillManagerError(f"invalid archive path: {name!r}")
    return Path(*parts)


def _safe_target(root: Path, name: str) -> Path:
    target = (root / _safe_relative(name)).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as exc:
        raise SkillManagerError(f"archive path escapes destination: {name!r}") from exc
    return target


def _extract_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        files = [info for info in infos if not info.is_dir()]
        if len(files) > MAX_FILES:
            raise SkillManagerError("archive contains too many files")
        if sum(info.file_size for info in files) > MAX_BYTES:
            raise SkillManagerError("archive expands beyond 64 MB")
        for info in infos:
            if stat.S_ISLNK(info.external_attr >> 16):
                raise SkillManagerError(f"archive contains a symlink: {info.filename}")
            destination = _safe_target(target, info.filename)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if info.compress_size and info.file_size / info.compress_size > 1_000:
                raise SkillManagerError(f"suspicious compression ratio: {info.filename}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, destination.open("wb") as dst:
                shutil.copyfileobj(src, dst)


def _extract_tar(source: Path, target: Path) -> None:
    with tarfile.open(source) as archive:
        members = archive.getmembers()
        files = [member for member in members if member.isfile()]
        if len(files) > MAX_FILES:
            raise SkillManagerError("archive contains too many files")
        if sum(member.size for member in files) > MAX_BYTES:
            raise SkillManagerError("archive expands beyond 64 MB")
        for member in members:
            destination = _safe_target(target, member.name)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise SkillManagerError(f"unsupported archive entry: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise SkillManagerError(f"cannot read archive entry: {member.name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with stream, destination.open("wb") as dst:
                shutil.copyfileobj(stream, dst)


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "octop-skill-manager/1.0"})
    total = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise SkillManagerError("download exceeds 256 MB")
                output.write(chunk)
    except SkillManagerError:
        raise
    except OSError as exc:
        host = urlparse(url).hostname or "remote host"
        raise SkillManagerError(f"download failed from {host}") from exc


def _run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SkillManagerError(f"required command is not installed: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SkillManagerError(f"command timed out: {command[0]}") from exc
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise SkillManagerError(_redact_urls(detail))
    return result


def _github_source(source: str) -> tuple[str, str, str] | None:
    parsed = urlparse(source)
    if parsed.hostname not in {"github.com", "www.github.com"}:
        return None
    parts = [unquote(part) for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = ""
    subpath = ""
    if len(parts) >= 4 and parts[2] in {"tree", "blob"}:
        ref = parts[3]
        subpath = "/".join(parts[4:])
        if parts[2] == "blob" and subpath.endswith("/SKILL.md"):
            subpath = subpath[: -len("/SKILL.md")]
        elif parts[2] == "blob" and subpath == "SKILL.md":
            subpath = ""
    return f"https://github.com/{owner}/{repo}.git", ref, subpath


def _clone(source: str, target: Path, *, ref: str = "") -> None:
    command = ["git", "clone", "--depth", "1"]
    if ref:
        command.extend(["--branch", ref])
    command.extend([source, str(target)])
    _run(command)


def _manifest(text: str) -> dict[str, Any]:
    match = re.match(r"^---\s*\n(.*?)\n---(?:\s*\n|$)", text, re.DOTALL)
    if match is None:
        raise SkillManagerError("SKILL.md is missing YAML frontmatter")
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise SkillManagerError(f"SKILL.md frontmatter is invalid: {exc}") from exc
    if not isinstance(metadata, dict):
        raise SkillManagerError("SKILL.md frontmatter must be a mapping")
    for field in ("name", "description"):
        if not str(metadata.get(field) or "").strip():
            raise SkillManagerError(f"SKILL.md frontmatter is missing {field}")
    return metadata


def _materialize_file(source: Path, target: Path) -> Path:
    if zipfile.is_zipfile(source):
        unpacked = target / "unpacked"
        unpacked.mkdir()
        _extract_zip(source, unpacked)
        return unpacked
    if tarfile.is_tarfile(source):
        unpacked = target / "unpacked"
        unpacked.mkdir()
        _extract_tar(source, unpacked)
        return unpacked
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillManagerError(
            "input is not a Skill directory, SKILL.md, ZIP, TAR, or readable text"
        ) from exc
    _manifest(text)
    single = target / "single"
    single.mkdir()
    shutil.copy2(source, single / "SKILL.md")
    return single


def _select_subpath(root: Path, subpath: str) -> Path:
    if not subpath:
        return root
    selected = (root / _safe_relative(subpath)).resolve()
    try:
        selected.relative_to(root.resolve())
    except ValueError as exc:
        raise SkillManagerError(f"subpath escapes source: {subpath!r}") from exc
    if not selected.exists():
        raise SkillManagerError(f"subpath does not exist: {subpath}")
    return selected.parent if selected.is_file() and selected.name == "SKILL.md" else selected


def _materialize(source: str, target: Path) -> Path:
    skillhub_source = _skillhub_source(source)
    if skillhub_source is not None:
        slug, namespace = skillhub_source
        installed = target / "skillhub"
        installed.mkdir()
        command = ["skillhub", "--skip-self-upgrade", "install", slug]
        if namespace:
            command.extend(["--namespace", namespace])
        command.extend(["--dir", str(installed), "--json"])
        _run(command)
        return installed

    local = Path(source).expanduser()
    if local.exists():
        resolved = local.resolve()
        return resolved if resolved.is_dir() else _materialize_file(resolved, target)

    parsed = urlparse(source.removeprefix("git+"))
    if parsed.scheme not in {"http", "https", "ssh", "git"}:
        raise SkillManagerError("source does not exist and is not a supported URL")
    if parsed.scheme in {"http", "https"} and (parsed.username or parsed.password):
        raise SkillManagerError("credentials embedded in URLs are not supported")

    github = _github_source(source)
    if github is not None:
        repo_url, ref, subpath = github
        checkout = target / "repo"
        _clone(repo_url, checkout, ref=ref)
        return _select_subpath(checkout, subpath)

    if source.startswith("git+") or source.endswith(".git"):
        checkout = target / "repo"
        _clone(source.removeprefix("git+"), checkout)
        return checkout

    downloaded = target / "download"
    _download(source, downloaded)
    return _materialize_file(downloaded, target)


def _skill_roots(root: Path) -> list[Path]:
    direct = root / "SKILL.md"
    manifests = [direct] if direct.is_file() else sorted(root.rglob("SKILL.md"))
    selected: list[Path] = []
    for manifest in manifests:
        relative = manifest.relative_to(root)
        if any(part.startswith(".") or part == "__MACOSX" for part in relative.parts):
            continue
        candidate = manifest.parent.resolve()
        if any(candidate == parent or candidate.is_relative_to(parent) for parent in selected):
            continue
        selected.append(candidate)
    if not selected:
        raise SkillManagerError("no SKILL.md was found in the source")
    return selected


def _validate_tree(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise SkillManagerError(f"skill root is not a regular directory: {root}")
    manifest_path = root / "SKILL.md"
    try:
        metadata = _manifest(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise SkillManagerError(f"cannot read {manifest_path}") from exc
    count = 0
    total = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for dirname in list(dirnames):
            child = current_path / dirname
            if child.is_symlink():
                raise SkillManagerError(f"skill contains a symlink: {child}")
            if dirname == ".git":
                dirnames.remove(dirname)
        for filename in filenames:
            child = current_path / filename
            if child.is_symlink() or not child.is_file():
                raise SkillManagerError(f"skill contains an unsupported file: {child}")
            count += 1
            total += child.stat().st_size
            if count > MAX_FILES:
                raise SkillManagerError("skill contains too many files")
            if total > MAX_BYTES:
                raise SkillManagerError("skill exceeds 64 MB")
    return {
        "name": str(metadata["name"]),
        "description": str(metadata["description"]),
        "files": count,
        "bytes": total,
    }


def _discover(source_root: Path, *, subpath: str = "", name: str = "") -> list[dict[str, Any]]:
    roots = _skill_roots(_select_subpath(source_root, subpath))
    if name and len(roots) != 1:
        raise SkillManagerError("--name can only be used when the source contains one skill")
    found: list[dict[str, Any]] = []
    slugs: set[str] = set()
    for root in roots:
        summary = _validate_tree(root)
        slug = _slug(name or str(summary["name"]) or root.name)
        if slug in slugs:
            raise SkillManagerError(f"duplicate skill name in source: {slug}")
        slugs.add(slug)
        found.append({"slug": slug, "root": root, **summary})
    return found


def _copy_skill(source: Path, target: Path) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        return {name for name in names if name == ".git"}

    shutil.copytree(source, target, symlinks=False, ignore=ignore)
    _validate_tree(target)


def _install(workspace: Path, skills: list[dict[str, Any]], *, force: bool) -> list[dict[str, Any]]:
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    reserved = [item["slug"] for item in skills if item["slug"] in RESERVED_SKILL_SLUGS]
    if reserved:
        raise SkillManagerError(
            "cannot replace an Octop-owned built-in skill: " + ", ".join(reserved)
        )
    conflicts = [item["slug"] for item in skills if (skills_dir / item["slug"]).exists()]
    if conflicts and not force:
        raise SkillManagerError(
            "already installed; ask before using --force: " + ", ".join(conflicts)
        )

    staging = Path(tempfile.mkdtemp(prefix=".skill-manager-stage-", dir=skills_dir))
    backup = Path(tempfile.mkdtemp(prefix=".skill-manager-backup-", dir=skills_dir))
    installed: list[Path] = []
    moved_backups: list[tuple[Path, Path]] = []
    try:
        for item in skills:
            _copy_skill(item["root"], staging / item["slug"])
        for item in skills:
            slug = item["slug"]
            destination = skills_dir / slug
            if destination.exists():
                saved = backup / slug
                os.replace(destination, saved)
                moved_backups.append((destination, saved))
            os.replace(staging / slug, destination)
            installed.append(destination)
    except Exception:
        for destination in reversed(installed):
            if destination.exists():
                shutil.rmtree(destination)
        for destination, saved in reversed(moved_backups):
            if saved.exists():
                os.replace(saved, destination)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)

    return [
        {
            "slug": item["slug"],
            "path": str(skills_dir / item["slug"]),
            "files": item["files"],
            "bytes": item["bytes"],
        }
        for item in skills
    ]


def _list(workspace: Path) -> list[dict[str, Any]]:
    skills_dir = workspace / "skills"
    if not skills_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        try:
            summary = _validate_tree(entry)
        except SkillManagerError as exc:
            rows.append({"slug": entry.name, "valid": False, "error": str(exc)})
            continue
        rows.append({"slug": entry.name, "valid": True, **summary})
    return rows


def _remove(workspace: Path, name: str, *, confirmed: bool) -> dict[str, str]:
    if not confirmed:
        raise SkillManagerError("removal requires --yes after explicit user confirmation")
    slug = _slug(name)
    skills_dir = workspace / "skills"
    source = skills_dir / slug
    if source.is_symlink():
        raise SkillManagerError(f"refusing to remove a symlinked skill: {slug}")
    if not source.is_dir():
        raise SkillManagerError(f"skill is not installed: {slug}")
    trash = skills_dir / ".trash"
    trash.mkdir(parents=True, exist_ok=True)
    destination = trash / slug
    suffix = 1
    while destination.exists():
        destination = trash / f"{slug}-{suffix}"
        suffix += 1
    os.replace(source, destination)
    (destination / ".skill-manager-trash.json").write_text(
        json.dumps({"slug": slug}),
        encoding="utf-8",
    )
    return {"removed": slug, "trash_name": destination.name, "trash": str(destination)}


def _restore(workspace: Path, trash_name: str) -> dict[str, str]:
    safe_name = _slug(trash_name)
    skills_dir = workspace / "skills"
    source = skills_dir / ".trash" / safe_name
    if source.is_symlink():
        raise SkillManagerError(f"refusing to restore a symlinked trash entry: {safe_name}")
    if not source.is_dir():
        raise SkillManagerError(f"trash entry does not exist: {safe_name}")
    _validate_tree(source)
    metadata_path = source / ".skill-manager-trash.json"
    slug = safe_name
    if metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            slug = _slug(str(metadata.get("slug") or safe_name))
        except (OSError, json.JSONDecodeError, SkillManagerError) as exc:
            raise SkillManagerError(f"trash metadata is invalid: {safe_name}") from exc
    destination = skills_dir / slug
    if destination.exists():
        raise SkillManagerError(f"cannot restore because skill is installed: {slug}")
    if metadata_path.exists():
        metadata_path.unlink()
    os.replace(source, destination)
    return {"restored": slug, "path": str(destination)}


def _effective_name(source: str, name: str) -> str:
    if name:
        return name
    skillhub_source = _skillhub_source(source)
    return skillhub_source[0] if skillhub_source is not None else ""


def _inspect(source: str, *, subpath: str, name: str) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="skill-manager-source-") as tmp:
        root = _materialize(source, Path(tmp))
        return [
            {key: value for key, value in item.items() if key != "root"}
            for item in _discover(
                root,
                subpath=subpath,
                name=_effective_name(source, name),
            )
        ]


def _install_source(
    workspace: Path,
    source: str,
    *,
    subpath: str,
    name: str,
    force: bool,
) -> list[dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="skill-manager-source-") as tmp:
        root = _materialize(source, Path(tmp))
        found = _discover(
            root,
            subpath=subpath,
            name=_effective_name(source, name),
        )
        return _install(workspace, found, force=force)


def _skillhub_search(query: str, limit: int) -> None:
    result = _run(
        [
            "skillhub",
            "--skip-self-upgrade",
            "search",
            "--json",
            "--search-limit",
            str(max(1, min(limit, 100))),
            query,
        ],
        timeout=30,
    )
    try:
        _emit(json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise SkillManagerError("SkillHub returned invalid JSON") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        default="",
        help="absolute current agent workspace (normally inferred from the deployed script path)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="list installed workspace skills")

    for command in ("inspect", "install"):
        item = commands.add_parser(
            command,
            help=f"{command} a file, directory, URL, or skillhub:slug",
        )
        item.add_argument("source")
        item.add_argument("--subpath", default="")
        item.add_argument("--name", default="")
        if command == "install":
            item.add_argument("--force", action="store_true")

    remove = commands.add_parser("remove", help="move an installed skill to skills/.trash")
    remove.add_argument("name")
    remove.add_argument("--yes", action="store_true")

    restore = commands.add_parser("restore", help="restore an entry from skills/.trash")
    restore.add_argument("trash_name")

    search = commands.add_parser("skillhub-search", help="search with the SkillHub CLI")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        workspace = _workspace(args.workspace) if args.workspace else _default_workspace()
        if args.command == "list":
            _emit(_list(workspace))
        elif args.command == "inspect":
            _emit(_inspect(args.source, subpath=args.subpath, name=args.name))
        elif args.command == "install":
            _emit(
                _install_source(
                    workspace,
                    args.source,
                    subpath=args.subpath,
                    name=args.name,
                    force=args.force,
                )
            )
        elif args.command == "remove":
            _emit(_remove(workspace, args.name, confirmed=args.yes))
        elif args.command == "restore":
            _emit(_restore(workspace, args.trash_name))
        elif args.command == "skillhub-search":
            _skillhub_search(args.query, args.limit)
        else:
            raise SkillManagerError(f"unknown command: {args.command}")
    except SkillManagerError as exc:
        _emit({"error": str(exc)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
