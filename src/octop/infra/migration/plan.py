"""What a migration found in another assistant's home, before anything is written."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProviderImport:
    name: str
    kind: str  # Octop provider kind: "openai" (compatible) or "anthropic"
    base_url: str
    api_key: str | None
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileImport:
    """One workspace file. ``content`` wins over ``source`` when the text was converted."""

    dest: str
    source: Path
    content: str | None = None


@dataclass(frozen=True)
class SkillImport:
    slug: str
    source: Path


@dataclass(frozen=True)
class McpImport:
    name: str
    spec: dict[str, Any]


@dataclass(frozen=True)
class ChannelImport:
    kind: str
    name: str
    config: dict[str, Any]


@dataclass(frozen=True)
class Note:
    """Something the reader could not carry over; the CLI words it per locale."""

    code: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MigrationPlan:
    source: str
    home: Path
    providers: list[ProviderImport] = field(default_factory=list)
    default_model: tuple[str, str] | None = None  # (provider name, model id)
    files: list[FileImport] = field(default_factory=list)
    skills: list[SkillImport] = field(default_factory=list)
    mcp_servers: list[McpImport] = field(default_factory=list)
    channels: list[ChannelImport] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)

    def note(self, code: str, **params: Any) -> None:
        self.notes.append(Note(code, params))
