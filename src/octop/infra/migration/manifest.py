"""Shared manifest model for the LightClaw → Octop migration export archive."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

SUPPORTED_FORMAT_VERSION = "1"


class ExportManifest(BaseModel):
    """Content of ``manifest.json`` inside the migration archive."""

    format: str = SUPPORTED_FORMAT_VERSION
    source: str = "lightclaw"
    agent_name: str = ""
    agent_description: str = ""
    active_provider: str = ""
    active_model: str = ""
    providers_count: int = 0
    cron_jobs_count: int = 0
    uploads_count: int = 0
    workspace_files: list[str] = Field(default_factory=list)
    memory_files: list[str] = Field(default_factory=list)
    sessions_index_included: bool = False
    messages_db_included: bool = False
    env_keys: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
