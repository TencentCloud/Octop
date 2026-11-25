"""Persisted marker that the first-run wizard has finished."""

from __future__ import annotations

from typing import Any

SETUP_WIZARD_COMPLETED_KEY = "setup_wizard_completed"


def setup_wizard_completed(settings_repo: Any) -> bool:
    """Return True once ``finish`` or a later boot has closed the wizard."""
    return bool(settings_repo.get(SETUP_WIZARD_COMPLETED_KEY) == "1")


def mark_setup_wizard_completed(settings_repo: Any, tokens: Any) -> None:
    """Record completion and drop every in-memory wizard token."""
    settings_repo.set(SETUP_WIZARD_COMPLETED_KEY, "1")
    tokens.clear()


def seal_setup_wizard_if_installed(server: Any) -> None:
    """Close the wizard on boot when this install already has users.

    A single-admin install stays at user count 1 after the first admin is
    created, so a count check cannot tell a mid-wizard request from a
    finished install. Sealing on boot closes leftover tokens without blocking
    ``finish`` in the same process that just created the admin.
    """
    user_manager = server.user_manager
    services = server.services
    if user_manager is None or services is None or user_manager.count() == 0:
        return
    if setup_wizard_completed(services.settings_repo):
        return
    mark_setup_wizard_completed(services.settings_repo, server.wizard_tokens)
