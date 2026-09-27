"""Project management domain — lifecycle, KB binding, permissions, task board."""

from __future__ import annotations

from octop.infra.projects.service import (
    PROJECT_ACTIONS,
    PROJECT_ARCHIVE,
    PROJECT_CONFIRM,
    PROJECT_MANAGE_CONFIG,
    PROJECT_MANAGE_MEMBERS,
    PROJECT_READ,
    PROJECT_WRITE,
    ProjectActor,
    ProjectService,
)

__all__ = [
    "PROJECT_ACTIONS",
    "PROJECT_ARCHIVE",
    "PROJECT_CONFIRM",
    "PROJECT_MANAGE_CONFIG",
    "PROJECT_MANAGE_MEMBERS",
    "PROJECT_READ",
    "PROJECT_WRITE",
    "ProjectActor",
    "ProjectService",
]
