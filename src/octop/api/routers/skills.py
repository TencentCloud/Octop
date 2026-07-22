"""Skills router — per-agent ``SKILL.md`` library.

Each agent's skills live under its harness backend at ``/skills/<name>/SKILL.md``
(matching finnie's convention). This router thinly wraps the workspace
backend so the dashboard sees a *named* skills view rather than a raw
file listing:

  GET    /api/agents/{aid}/skills                 → summaries
  GET    /api/agents/{aid}/skills/{name}          → full detail (frontmatter + body)
  POST   /api/agents/{aid}/skills                 → body { name, content }
  DELETE /api/agents/{aid}/skills/{name}          → remove SKILL.md
  POST   /api/agents/{aid}/skills/{name}/enable
  POST   /api/agents/{aid}/skills/{name}/disable

A skill is considered "enabled" unless its slug is listed in
``agent.config.skills_disabled``. The enable/disable endpoints toggle
that list and hot-sync ``HarnessAgentConfig.skills_disabled`` so
``SkillFilterMiddleware`` excludes disabled skills on every turn.

Limitations
-----------
The protocol has no ``delete``: removing a skill rewrites SKILL.md to
an empty file with the leading frontmatter block ``---\\nremoved: true\\n---``
so the directory listing still shows the entry but the dashboard knows
to filter it. This is a deliberate design compromise — protocol-level
delete is the right long-term answer.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Any, cast

import yaml
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from octop.api.common.agent import require_agent_row
from octop.api.deps import current_user, get_server
from octop.infra.agents.manager import skills_disabled_set as _disabled_set
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_request_locale

logger = logging.getLogger(__name__)

_SKILLHUB_INSTALL_URL = (
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/install.sh"
)

router = APIRouter()

_BUILTIN_ROOT = "_builtin_skills"
_SKILLS_ROOT = "skills"


@dataclass
class _AgentCtx:
    runtime: Any
    workspace: Any
    config: dict[str, Any]


async def _ctx(
    agent_id: str,
    *,
    user: Any,
    as_user: int | None,
    server: Any,
) -> _AgentCtx:
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    row = require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    cfg = registry.get_config(agent_id)
    agent = registry.get_agent(agent_id)
    return _AgentCtx(runtime=row, workspace=agent.workspace, config=cfg)


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split a markdown file with optional YAML frontmatter.

    Accepts both ``---``-delimited and ``+++`` (TOML) blocks; we only
    handle YAML for simplicity since finnie's skills all use YAML.
    Returns ``(metadata_dict, body)``. Malformed frontmatter is treated
    as no-frontmatter (the file is its own body).
    """
    if not text.startswith("---\n"):
        return {}, text
    # Find the closing delimiter
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    try:
        meta = yaml.safe_load(raw) or {}
        if not isinstance(meta, dict):
            return {}, text
        return meta, body
    except yaml.YAMLError:
        return {}, text


async def _aread_text(workspace: Any, path: str) -> str | None:
    return cast(str | None, await workspace.aread_text(path))


async def _aoverwrite_text(workspace: Any, path: str, content: str) -> str | None:
    try:
        await workspace.awrite_text(path, content, force=True)
    except Exception as exc:
        return f"{exc}"
    return None


def _summary_dict(
    name: str,
    meta: dict[str, Any],
    *,
    enabled: bool,
    kind: str,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        # ``slug`` is the directory name — the stable identifier used for all
        # by-name operations (detail / enable / disable / delete / install
        # check). ``name`` is the frontmatter display name, which may differ
        # from the slug (e.g. dir "tencent-meeting-skill" with frontmatter
        # name "tencent-meeting-mcp"); using ``name`` as the id 404s.
        "slug": name,
        "name": str(meta.get("name") or name),
        "description": str(meta.get("description") or ""),
        "enabled": enabled,
        "kind": kind,
    }
    # Optional metadata.octop.emoji passthrough — handy for finnie-
    # provenance skills.
    metadata = meta.get("metadata") or {}
    if isinstance(metadata, dict):
        ext = metadata.get("octop") or metadata.get("lightclaw") or metadata.get("orca") or {}
        if isinstance(ext, dict) and "emoji" in ext:
            out["emoji"] = str(ext["emoji"])
    return out


def _skill_manifest_path(name: str, kind: str, workspace: Any) -> str:
    root = _BUILTIN_ROOT if kind == "builtin" else _SKILLS_ROOT
    return f"{root}/{name}/SKILL.md"


async def _resolve_skill(
    workspace: Any,
    name: str,
) -> tuple[str, str, str] | None:
    """Resolve a skill by name. Workspace entries override builtin names."""
    for kind in ("workspace", "builtin"):
        manifest_path = _skill_manifest_path(name, kind, workspace)
        manifest = await _aread_text(workspace, manifest_path)
        if manifest is None:
            continue
        meta, body = _parse_frontmatter(manifest)
        if meta.get("removed"):
            continue
        return manifest_path, kind, body
    return None


def _resolve_skillhub_bin() -> str | None:
    """Return the skillhub binary path from PATH or common install locations."""
    skillhub_bin = shutil.which("skillhub")
    if skillhub_bin:
        return skillhub_bin
    home = os.path.expanduser("~")
    for candidate in [
        os.path.join(home, ".local", "bin", "skillhub"),
        os.path.join(home, ".skillhub", "bin", "skillhub"),
        "/usr/local/bin/skillhub",
    ]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


async def _close_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Kill and drain ``proc`` while the event loop is still alive.

    Leaving a live ``asyncio`` subprocess after ``wait_for`` times out (or after
    the caller abandons it) keeps pipe transports open; when the loop later
    closes, ``BaseSubprocessTransport.__del__`` raises
    ``RuntimeError: Event loop is closed`` as an unraisable warning.
    """
    if proc.returncode is not None:
        return
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await proc.communicate()
    except Exception:
        with contextlib.suppress(Exception):
            await proc.wait()


async def _install_skillhub_cli() -> str:
    """Download and run the official install script; return the binary path."""
    from fastapi import HTTPException  # noqa: PLC0415

    logger.info("skillhub CLI not found, attempting auto-install...")
    curl_proc: asyncio.subprocess.Process | None = None
    bash_proc: asyncio.subprocess.Process | None = None
    try:
        curl_proc = await asyncio.create_subprocess_exec(
            "curl",
            "-fsSL",
            _SKILLHUB_INSTALL_URL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        script_stdout, curl_stderr = await asyncio.wait_for(curl_proc.communicate(), timeout=30)
        if curl_proc.returncode != 0:
            raise RuntimeError(
                curl_stderr.decode("utf-8", errors="replace").strip() or "curl failed"
            )
        bash_proc = await asyncio.create_subprocess_exec(
            "bash",
            "-s",
            "--",
            "--no-skills",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "HOME": os.path.expanduser("~")},
        )
        _, bash_stderr = await asyncio.wait_for(
            bash_proc.communicate(input=script_stdout), timeout=60
        )
        if bash_proc.returncode != 0:
            raise RuntimeError(
                bash_stderr.decode("utf-8", errors="replace").strip() or "install script failed"
            )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="skillhub auto-install timed out") from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Failed to auto-install skillhub CLI: {exc}"
        ) from exc
    finally:
        if curl_proc is not None:
            await _close_subprocess(curl_proc)
        if bash_proc is not None:
            await _close_subprocess(bash_proc)

    skillhub_bin = _resolve_skillhub_bin()
    if not skillhub_bin:
        raise HTTPException(
            status_code=502,
            detail=(
                "skillhub CLI not found after install. "
                f"Install manually: curl -fsSL {_SKILLHUB_INSTALL_URL} | sh"
            ),
        )
    return skillhub_bin


async def _skillhub_supports_rankings(skillhub_bin: str) -> bool:
    """Return True when the CLI exposes ``skill rankings``."""
    try:
        rc, _stdout, _stderr = await _run_skillhub_cmd(
            skillhub_bin,
            ["skill", "rankings", "--help"],
            timeout=10,
        )
        return rc == 0
    except Exception:
        return False


async def _ensure_skillhub_cli(*, require_rankings: bool = False) -> str:
    """Return path to the ``skillhub`` binary, auto-installing or upgrading if needed."""
    from fastapi import HTTPException  # noqa: PLC0415

    skillhub_bin = _resolve_skillhub_bin()
    if skillhub_bin is None:
        skillhub_bin = await _install_skillhub_cli()

    if require_rankings and not await _skillhub_supports_rankings(skillhub_bin):
        logger.info("skillhub CLI missing skill rankings support, attempting self-upgrade...")
        if await _upgrade_skillhub_cli(skillhub_bin):
            skillhub_bin = _resolve_skillhub_bin() or skillhub_bin
        if not await _skillhub_supports_rankings(skillhub_bin):
            logger.info("skillhub self-upgrade insufficient, reinstalling CLI...")
            skillhub_bin = await _install_skillhub_cli()
        if not await _skillhub_supports_rankings(skillhub_bin):
            raise HTTPException(
                status_code=502,
                detail=(
                    "skillhub CLI does not support skill rankings after upgrade/reinstall. "
                    f"Install manually: curl -fsSL {_SKILLHUB_INSTALL_URL} | sh"
                ),
            )

    return skillhub_bin


def _skillhub_rankings_args(rtype: str, *, host: str | None = None) -> list[str]:
    """Build argv for ``skillhub skill rankings``."""
    args = ["skill", "rankings", "--type", rtype]
    if host:
        args += ["--host", host]
    return args


async def _run_skillhub_cmd(
    skillhub_bin: str,
    args: list[str],
    *,
    timeout: float,
) -> tuple[int, str, str]:
    """Run skillhub CLI and return ``(returncode, stdout, stderr)``."""
    proc = await asyncio.create_subprocess_exec(
        skillhub_bin,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        await _close_subprocess(proc)
        raise
    return (
        proc.returncode or 0,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
    )


async def _upgrade_skillhub_cli(skillhub_bin: str) -> bool:
    """Best-effort ``skillhub self-upgrade`` before install."""
    try:
        rc, _stdout, stderr = await _run_skillhub_cmd(
            skillhub_bin,
            ["self-upgrade"],
            timeout=120,
        )
        if rc != 0:
            logger.warning("skillhub self-upgrade failed (rc=%s): %s", rc, stderr.strip())
            return False
        return True
    except Exception:
        logger.warning("skillhub self-upgrade failed", exc_info=True)
        return False


def _map_skillhub_install_error(err_msg: str, skill_name: str) -> Any | None:
    """Map skillhub stderr to an HTTPException when the failure is user-actionable."""
    from fastapi import HTTPException  # noqa: PLC0415

    from octop.i18n import error_message  # noqa: PLC0415
    from octop.infra.utils.ssl_errors import looks_like_ssl_error  # noqa: PLC0415

    lower = err_msg.lower()
    if looks_like_ssl_error(err_msg):
        return HTTPException(
            status_code=502,
            detail=error_message("SKILLHUB_SSL_FAILED", "en"),
        )
    if "http 404" in lower or ("download failed" in lower and "404" in lower):
        return HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' not found in SkillHub",
        )
    if "not found" in lower or "no such" in lower:
        return HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' not found in SkillHub",
        )
    return None


def _skillhub_cli_failure_detail(action: str, stderr: str, *, locale: str = "en") -> str:
    """Build a 502 detail for a failed skillhub CLI invocation."""
    from octop.i18n import error_message  # noqa: PLC0415
    from octop.infra.utils.ssl_errors import looks_like_ssl_error  # noqa: PLC0415

    err = stderr.strip() or "unknown error"
    if looks_like_ssl_error(err):
        return error_message("SKILLHUB_SSL_FAILED", locale)
    return f"skillhub {action} failed: {err}"


def _skillhub_stderr_suggests_upgrade(err_msg: str) -> bool:
    lower = err_msg.lower()
    return "self-upgrade" in lower or "新版本" in err_msg or "invalid choice: 'rankings'" in lower


async def _enabled_skill_names(
    server: Any,
    *,
    agent_id: str,
    user: Any,
) -> set[str]:
    """Return installed, non-disabled skill names for an agent."""
    await _ctx(agent_id, user=user, as_user=None, server=server)
    assert server.app_runtime is not None
    names: set[str] = set()
    for summary in await server.app_runtime.agent_registry.list_skill_summaries(agent_id):
        if summary.get("enabled"):
            names.add(str(summary["name"]))
            slug = summary.get("slug")
            if slug:
                names.add(str(slug))
    return names


async def validate_chat_skills(
    server: Any,
    *,
    agent_id: str,
    user: Any,
    names: list[str] | None,
) -> list[str] | None:
    from octop.api.common.validators import validate_chat_skills as _validate

    return await _validate(server, agent_id=agent_id, user=user, names=names)


# --- read endpoints ---------------------------------------------------------


@router.get("/agents/{agent_id}/skills")
async def list_skills(
    agent_id: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    await _ctx(agent_id, user=user, as_user=as_user, server=server)
    assert server.app_runtime is not None
    return cast(
        list[dict[str, Any]],
        await server.app_runtime.agent_registry.list_skill_summaries(agent_id),
    )


@router.get("/agents/{agent_id}/skills/{name}")
async def get_skill(
    agent_id: str,
    name: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    resolved = await _resolve_skill(ctx.workspace, name)
    if resolved is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"skill {name!r} not found")
    manifest_path, kind, _body = resolved
    manifest = await _aread_text(ctx.workspace, manifest_path)
    assert manifest is not None
    meta, body = _parse_frontmatter(manifest)
    disabled = _disabled_set(ctx.config)
    return {
        **_summary_dict(name, meta, enabled=name not in disabled, kind=kind),
        "frontmatter": meta,
        "body": body,
        "raw": manifest,
    }


# --- write endpoints --------------------------------------------------------


class CreateSkillBody(BaseModel):
    name: str
    content: str


class ImportSkillBody(BaseModel):
    bundle_url: str
    version: str = ""
    enable: bool = True
    overwrite: bool = False


@router.post("/agents/{agent_id}/skills", status_code=201)
async def create_skill(
    agent_id: str,
    body: CreateSkillBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    name = body.name.strip()
    if not name or "/" in name or name.startswith("."):
        raise OctopError(ErrorCode.NOT_FOUND, "invalid skill name")
    target = f"skills/{name}/SKILL.md"
    # Don't clobber an existing skill — return 409 instead.
    existing = await _aread_text(ctx.workspace, target)
    if existing is not None:
        meta, _ = _parse_frontmatter(existing)
        if not meta.get("removed"):
            raise OctopError(ErrorCode.USERNAME_TAKEN, f"skill {name!r} already exists")
    err = await _aoverwrite_text(ctx.workspace, target, body.content)
    if err:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot write {target!r}: {err}")
    meta, _body = _parse_frontmatter(body.content)
    return _summary_dict(name, meta, enabled=True, kind="workspace")


@router.post("/agents/{agent_id}/skills/import", status_code=201)
async def import_skill_from_url(
    agent_id: str,
    body: ImportSkillBody,
    request: Request,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Import a skill bundle from a supported external URL into the agent workspace."""
    from urllib.error import HTTPError, URLError

    from octop.infra.agents.skills_hub import (  # noqa: PLC0415
        is_supported_skill_url,
        resolve_bundle_from_url,
    )

    locale = resolve_request_locale(request)
    bundle_url = body.bundle_url.strip()
    if not bundle_url:
        raise OctopError(ErrorCode.SLASH_BAD_ARGS, "bundle_url is required")
    if not is_supported_skill_url(bundle_url):
        raise OctopError.localized(ErrorCode.SKILL_IMPORT_UNSUPPORTED_URL, locale)

    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)

    try:
        resolved = await asyncio.to_thread(
            resolve_bundle_from_url,
            bundle_url=bundle_url,
            version=body.version,
        )
    except ValueError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason=str(exc),
        ) from exc

    skill_name = resolved.name
    if not skill_name or "/" in skill_name or skill_name.startswith("."):
        raise OctopError.localized(
            ErrorCode.SKILL_IMPORT_FAILED,
            locale,
            reason="invalid resolved skill name",
        )

    existing = await _resolve_skill(ctx.workspace, skill_name)
    if existing is not None and not body.overwrite:
        raise OctopError.localized(
            ErrorCode.SKILL_ALREADY_EXISTS,
            locale,
            name=skill_name,
        )

    await ctx.workspace.aupload_many(resolved.uploads)

    if body.enable:
        disabled = _disabled_set(ctx.config)
        disabled.discard(skill_name)
        await _persist_disabled(server, agent_id, disabled)

    skill_md = next(
        (content for path, content in resolved.uploads if path.endswith("SKILL.md")),
        b"",
    )
    meta, _body = _parse_frontmatter(skill_md.decode("utf-8"))
    return _summary_dict(
        skill_name,
        meta,
        enabled=body.enable,
        kind="workspace",
    )


@router.delete("/agents/{agent_id}/skills/{name}", status_code=204)
async def delete_skill(
    agent_id: str,
    name: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    """Soft-delete via marker — see module docstring for rationale."""
    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    resolved = await _resolve_skill(ctx.workspace, name)
    if resolved is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"skill {name!r} not found")
    manifest_path, kind, _body = resolved
    if kind == "builtin":
        raise OctopError(ErrorCode.NOT_FOUND, f"builtin skill {name!r} cannot be deleted")
    target = manifest_path
    existing = await _aread_text(ctx.workspace, target)
    if existing is None:
        raise OctopError(ErrorCode.NOT_FOUND, f"skill {name!r} not found")
    err = await _aoverwrite_text(ctx.workspace, target, "---\nremoved: true\n---\n")
    if err:
        raise OctopError(ErrorCode.NOT_FOUND, f"cannot remove {target!r}: {err}")


# --- enable / disable -------------------------------------------------------


async def _persist_disabled(server: Any, agent_id: str, disabled: set[str]) -> None:
    """Write back ``skills_disabled`` and hot-sync the running harness agent."""
    assert server.app_runtime is not None
    registry = server.app_runtime.agent_registry
    cfg = registry.get_config(agent_id)
    cfg["skills_disabled"] = sorted(disabled)
    await registry.update_config_json(agent_id, json.dumps(cfg))
    registry.sync_skills_disabled(agent_id, disabled)


@router.post("/agents/{agent_id}/skills/{name}/enable", status_code=204)
async def enable_skill(
    agent_id: str,
    name: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    disabled = _disabled_set(ctx.config)
    if name in disabled:
        disabled.discard(name)
        await _persist_disabled(server, agent_id, disabled)


@router.post("/agents/{agent_id}/skills/{name}/disable", status_code=204)
async def disable_skill(
    agent_id: str,
    name: str,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> None:
    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    disabled = _disabled_set(ctx.config)
    disabled.add(name)
    await _persist_disabled(server, agent_id, disabled)


class HubInstallBody(BaseModel):
    skill_name: str
    enable: bool = True


def _parse_skillhub_search_output(text: str) -> list[dict[str, Any]]:
    """Parse the plain-text output of ``skillhub search`` into a list of dicts.

    The CLI emits one block per skill:
        You can use "skillhub install [skill]" to install.
          <slug>  <Display Name>
            - <description line 1>
        <description line 2 (optional bilingual)>
            - version: <ver>

    We identify skill blocks by the leading two-space indent on the slug line,
    then collect description lines until the version line.
    """
    import re  # noqa: PLC0415

    results: list[dict[str, Any]] = []
    lines = text.splitlines()

    # Each skill entry starts with a line like "  slug  Name" (2-space indent,
    # slug contains no spaces, followed by at least one space, then the display name).
    slug_re = re.compile(r"^  (\S+)\s{2,}(.+)$")

    i = 0
    while i < len(lines):
        m = slug_re.match(lines[i])
        if m:
            slug = m.group(1).strip()
            name = m.group(2).strip()
            desc_parts: list[str] = []
            version = ""
            i += 1
            while i < len(lines):
                line = lines[i]
                # Version line ends the block
                ver_m = re.match(r"^\s+-\s+version:\s*(.+)$", line)
                if ver_m:
                    version = ver_m.group(1).strip()
                    i += 1
                    break
                # Desc line (may start with "    - " or be a raw continuation)
                stripped = line.strip()
                if stripped and not stripped.startswith("You can use"):
                    # Remove leading "- " prefix if present
                    cleaned = re.sub(r"^-\s+", "", stripped)
                    if cleaned:
                        desc_parts.append(cleaned)
                i += 1
            results.append(
                {
                    "slug": slug,
                    "name": name,
                    "description": " ".join(desc_parts),
                    "version": version,
                }
            )
        else:
            i += 1

    return results


@router.get("/agents/{agent_id}/skills/hub/search")
async def hub_search_skills(
    agent_id: str,
    request: Request,
    q: str = "",
    limit: int = 50,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> list[dict[str, Any]]:
    """Search Tencent SkillHub via the skillhub CLI.

    The agent_id param is accepted for auth/routing symmetry with
    the install endpoint but is not used for the search itself.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    # Verify the agent exists and belongs to this user. The skillhub CLI
    # runs globally, so we only need an existence/ownership check here —
    # the agent need not be running (unlike chat/workspace endpoints).
    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    locale = resolve_request_locale(request)
    skillhub_bin = await _ensure_skillhub_cli()
    query = q.strip() or "a"
    # Note: --json is not supported by this CLI version; parse text output instead.
    try:
        rc, stdout, stderr = await _run_skillhub_cmd(
            skillhub_bin,
            ["search", "--search-limit", str(limit), query],
            timeout=30,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="skillhub search timed out") from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to run skillhub CLI: {exc}") from exc

    if rc != 0:
        raise HTTPException(
            status_code=502,
            detail=_skillhub_cli_failure_detail("search", stderr, locale=locale),
        )

    return _parse_skillhub_search_output(stdout)


_RANKING_TYPES = {"all", "hot", "featured", "newest", "recommended", "trending", "paid"}


@router.get("/agents/{agent_id}/skills/hub/rankings")
async def hub_rankings(
    agent_id: str,
    request: Request,
    type: str = "all",
    host: str | None = None,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Fetch Tencent SkillHub rankings via the skillhub CLI.

    Runs ``skillhub skill rankings --type <type> [--host <host>]`` and returns
    the CLI JSON payload (typically ``section``, ``skills``, ``total``).
    ``type`` selects a section (all / hot / recommended / trending / newest /
    featured / paid). The host is resolved from the ``host`` query param, else
    the ``SKILLHUB_HOST`` env var, else the CLI default (https://api.skillhub.cn).
    Each source is stripped of surrounding whitespace; blank or whitespace-only
    values are ignored and fall through to the next source. The agent_id is
    accepted for auth/routing symmetry with search/install; rankings are global.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    require_agent_row(agent_id, user=user, as_user=as_user, server=server)
    locale = resolve_request_locale(request)

    rtype = type if type in _RANKING_TYPES else "all"
    skillhub_bin = await _ensure_skillhub_cli(require_rankings=True)
    # host param > SKILLHUB_HOST env > CLI default. Strip each source and skip
    # blank / whitespace-only values so they fall through to the next source
    # (a whitespace-only host param must not short-circuit past the env var).
    resolved_host = (host or "").strip() or os.environ.get("SKILLHUB_HOST", "").strip()
    args = _skillhub_rankings_args(rtype, host=resolved_host or None)

    try:
        rc, stdout, stderr = await _run_skillhub_cmd(skillhub_bin, args, timeout=20)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="skillhub rankings timed out") from None
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to run skillhub CLI: {exc}") from exc

    if (
        rc != 0
        and _skillhub_stderr_suggests_upgrade(stderr)
        and await _upgrade_skillhub_cli(skillhub_bin)
    ):
        skillhub_bin = _resolve_skillhub_bin() or skillhub_bin
        try:
            rc, stdout, stderr = await _run_skillhub_cmd(skillhub_bin, args, timeout=20)
        except TimeoutError:
            raise HTTPException(status_code=504, detail="skillhub rankings timed out") from None
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to run skillhub CLI: {exc}"
            ) from exc

    if rc != 0:
        raise HTTPException(
            status_code=502,
            detail=_skillhub_cli_failure_detail("rankings", stderr, locale=locale),
        )

    try:
        return json.loads(stdout)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502, detail=f"skillhub rankings returned invalid JSON: {exc}"
        ) from exc


@router.post("/agents/{agent_id}/skills/hub/install", status_code=201)
async def hub_install_skill(
    agent_id: str,
    body: HubInstallBody,
    as_user: int | None = None,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Install a SkillHub skill into the specified agent's workspace.

    Runs ``skillhub --dir <tmpdir> install <skill_name>``, then copies
    the resulting skill directory into the agent's backend via
    ``aupload_files``.
    """
    from fastapi import HTTPException  # noqa: PLC0415

    skill_name = body.skill_name.strip()
    if not skill_name or "/" in skill_name or skill_name.startswith("."):
        raise HTTPException(
            status_code=400, detail="skill_name is required and must not contain / or start with ."
        )

    ctx = await _ctx(agent_id, user=user, as_user=as_user, server=server)
    skillhub_bin = await _ensure_skillhub_cli()
    await _upgrade_skillhub_cli(skillhub_bin)

    with tempfile.TemporaryDirectory() as tmpdir:
        install_args = ["--dir", tmpdir, "install", skill_name]
        try:
            rc, _stdout, stderr = await _run_skillhub_cmd(
                skillhub_bin,
                install_args,
                timeout=120,
            )
        except TimeoutError:
            raise HTTPException(
                status_code=504, detail=f"skillhub install timed out for '{skill_name}'"
            ) from None
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Failed to run skillhub CLI: {exc}"
            ) from exc

        if (
            rc != 0
            and _skillhub_stderr_suggests_upgrade(stderr)
            and await _upgrade_skillhub_cli(skillhub_bin)
        ):
            try:
                rc, _stdout, stderr = await _run_skillhub_cmd(
                    skillhub_bin,
                    install_args,
                    timeout=120,
                )
            except TimeoutError:
                raise HTTPException(
                    status_code=504,
                    detail=f"skillhub install timed out for '{skill_name}'",
                ) from None
            except Exception as exc:
                raise HTTPException(
                    status_code=502, detail=f"Failed to run skillhub CLI: {exc}"
                ) from exc

        if rc != 0:
            err_msg = stderr.strip()
            mapped = _map_skillhub_install_error(err_msg, skill_name)
            if mapped is not None:
                raise mapped
            raise HTTPException(
                status_code=502,
                detail=_skillhub_cli_failure_detail("install", err_msg, locale="en"),
            )

        uploads: list[tuple[str, bytes]] = []
        skill_dir = os.path.join(tmpdir, skill_name)
        if not os.path.isdir(skill_dir):
            skill_dir = tmpdir
        for dirpath, _dirnames, filenames in os.walk(skill_dir):
            for fname in filenames:
                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, skill_dir)
                dest = f"skills/{skill_name}/{rel.replace(chr(92), '/')}"
                with open(fpath, "rb") as fh:
                    uploads.append((dest, fh.read()))

        if not uploads:
            raise HTTPException(
                status_code=502,
                detail=f"skillhub installed nothing for '{skill_name}'",
            )

        await ctx.workspace.aupload_many(uploads)

    if body.enable:
        disabled = _disabled_set(ctx.config)
        disabled.discard(skill_name)
        await _persist_disabled(server, agent_id, disabled)

    return {"installed": True, "name": skill_name, "enabled": body.enable}
