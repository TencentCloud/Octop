"""Synthesize SYSTEM / CONTEXT chunks from harness injection sources of truth."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from harness_agent.backends.workspace import DEFAULT_MEMORY_FILES

# Mirror harness ``SkillFilterMiddleware``: memory files are injected via
# ``BackendWorkspace.memory_paths(DEFAULT_MEMORY_FILES)``.
_MEMORY_SOURCE = "memory"


def memory_file_order() -> list[str]:
    """Workspace memory files harness injects into the system prompt."""
    return list(DEFAULT_MEMORY_FILES)


def filter_turn_skill_names(
    enabled_skills: Sequence[dict[str, str]],
    *,
    turn_skills: Sequence[str] | None,
    skills_filter_present: bool,
) -> list[str]:
    """Apply the same allow-list semantics as ``SkillFilterMiddleware``.

    * Filter key absent → all enabled skills (display ``name``).
    * Filter key present (even ``[]``) → keep skills whose name/slug intersects
      the allow-list (harness ``skill_identity_keys``).
    """
    out: list[str] = []
    seen: set[str] = set()
    allowed = {str(name) for name in (turn_skills or [])} if skills_filter_present else None
    for row in enabled_skills:
        name = str(row.get("name") or row.get("slug") or "").strip()
        if not name or name in seen:
            continue
        if allowed is not None:
            keys = {name}
            slug = str(row.get("slug") or "").strip()
            if slug:
                keys.add(slug)
            if not (keys & allowed):
                continue
        seen.add(name)
        out.append(name)
    return out


def build_turn_start_chunks(
    *,
    include_system: bool,
    system_prompt: str | None,
    workspace_files: Sequence[tuple[str, str]],
    skills: list[str] | None,
    mcp_servers: list[str] | None,
    skills_filter_present: bool = False,
) -> list[dict[str, Any]]:
    """Return projector-ready chunks aligned with harness injection.

    ``workspace_files`` must already be filtered to files harness would load
    (``DEFAULT_MEMORY_FILES`` ∩ exists ∩ non-empty). ``skills`` is the final
    enabled allow-list for this turn (or ``None`` to omit the skills row when
    the catalog could not be resolved). When ``skills_filter_present`` and
    ``skills == []``, emit an explicit ``(none)`` row so the ledger is not
    silently missing a real empty allow-list.
    """
    chunks: list[dict[str, Any]] = []
    prompt = (system_prompt or "").strip()
    if include_system and prompt:
        chunks.append(
            {
                "type": "system",
                "label": "Initial System Prompt",
                "content": prompt,
            }
        )

    for label, body in workspace_files:
        text = (body or "").strip()
        if not text:
            continue
        name = (label or "").strip() or "workspace"
        chunks.append(
            {
                "type": "context",
                "source": _MEMORY_SOURCE,
                "label": name,
                "content": text,
            }
        )

    if skills is not None:
        if skills:
            listing = "\n".join(f"- {name}" for name in skills)
        elif skills_filter_present:
            listing = "(none)"
        else:
            listing = ""
        if listing:
            chunks.append(
                {
                    "type": "context",
                    "source": "skills",
                    "label": "Available skills",
                    "content": listing,
                }
            )

    servers = [s.strip() for s in (mcp_servers or []) if isinstance(s, str) and s.strip()]
    if servers:
        listing = "\n".join(f"- {name}" for name in servers)
        chunks.append(
            {
                "type": "context",
                "source": "mcp",
                "label": "Connectors",
                "content": listing,
            }
        )

    return chunks
