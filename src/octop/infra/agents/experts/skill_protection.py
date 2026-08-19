"""Guards for skills shipped by experts published with hidden skill details.

When an expert is published with ``allow_skill_details = False``, users who
install it may *use* its skills but must not view or modify their content.
The restriction is stamped into the installed agent's config at install time
(``skill_details_restricted`` + ``protected_skills``) so enforcement survives
the expert later being refreshed or unpublished.

The publishing user (and admins) stay exempt: they can always inspect skills
of experts they published.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from octop.infra.db.repos.published_experts import PublishedExpertRow
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User

RESTRICTED_CONFIG_KEY = "skill_details_restricted"
PROTECTED_SKILLS_KEY = "protected_skills"
PUBLISHED_EXPERT_ID_KEY = "published_expert_id"


def protected_slugs_from_config(config: dict[str, Any] | None) -> frozenset[str]:
    """Return the skill slugs an installed agent must keep opaque."""
    if not isinstance(config, dict) or not config.get(RESTRICTED_CONFIG_KEY):
        return frozenset()
    raw = config.get(PROTECTED_SKILLS_KEY)
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(slug) for slug in raw if slug)


def snapshot_protected_skill_slugs(snapshot_dir: Path) -> list[str]:
    """List ``skills/<slug>/`` directories present in a published snapshot."""
    skills_root = snapshot_dir / "skills"
    if not skills_root.is_dir():
        return []
    return sorted(
        entry.name
        for entry in skills_root.iterdir()
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    )


def _is_exempt(config: dict[str, Any], user: User, services: Any) -> bool:
    """The expert's publisher and admins may always view skill details."""
    if user.is_admin:
        return True
    expert_id = config.get(PUBLISHED_EXPERT_ID_KEY)
    if not expert_id or services is None:
        return False
    row: PublishedExpertRow | None = services.published_expert_repo.get(str(expert_id))
    return row is not None and str(user.id) == row.created_by


def _restricted(config: dict[str, Any] | None) -> bool:
    return isinstance(config, dict) and bool(config.get(RESTRICTED_CONFIG_KEY))


def skill_details_protected(
    config: dict[str, Any] | None,
    *,
    user: User,
    services: Any,
    slug: str,
) -> bool:
    """Return True when *slug* must stay opaque for this user."""
    if not _restricted(config):
        return False
    if slug not in protected_slugs_from_config(config):
        return False
    return not _is_exempt(config if isinstance(config, dict) else {}, user, services)


def assert_skill_details_visible(
    config: dict[str, Any] | None,
    *,
    user: User,
    services: Any,
    slug: str,
) -> None:
    """Raise ``SKILL_DETAILS_PROTECTED`` when the user may not view/modify *slug*."""
    if skill_details_protected(config, user=user, services=services, slug=slug):
        raise OctopError(
            ErrorCode.SKILL_DETAILS_PROTECTED,
            f"skill {slug!r} details are protected by the expert publisher",
            details={"slug": slug},
        )


def assert_workspace_path_allowed(
    config: dict[str, Any] | None,
    *,
    user: User,
    services: Any,
    rel_path: str,
) -> None:
    """Guard raw workspace file access (read/write/move/delete/download).

    *rel_path* is workspace-relative with forward slashes (``skills/a/b.md``).
    Blocking the whole ``skills`` root as well prevents deleting / moving the
    tree out from under the protected skills.
    """
    if not _restricted(config):
        return
    parts = PurePosixPath(rel_path.strip().replace("\\", "/").lstrip("/")).parts
    if not parts or parts[0] != "skills":
        return
    protected = protected_slugs_from_config(config)
    if not protected:
        return
    cfg = config if isinstance(config, dict) else {}
    if (len(parts) == 1 or (len(parts) > 1 and parts[1] in protected)) and not _is_exempt(
        cfg, user, services
    ):
        raise OctopError(
            ErrorCode.SKILL_DETAILS_PROTECTED,
            "workspace skill files are protected by the expert publisher",
            details={"path": rel_path},
        )
