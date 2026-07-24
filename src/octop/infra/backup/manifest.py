"""Backup archive manifest."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

MANIFEST_VERSION = 1


@dataclass
class AgentBackupEntry:
    agent_id: str
    name: str
    workspace_included: bool = True


@dataclass
class BackupManifest:
    manifest_version: int
    octop_version: str
    schema_version: int
    created_at: str
    home: str
    db_file: str = "db/octop.db"
    database_driver: str = "sqlite"
    database_dump_format: str = "sqlite_file"
    agents: list[AgentBackupEntry] = field(default_factory=list)
    includes_config: bool = True
    includes_env: bool = False

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "octop_version": self.octop_version,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "home": self.home,
            "db_file": self.db_file,
            "database_driver": self.database_driver,
            "database_dump_format": self.database_dump_format,
            "includes_config": self.includes_config,
            "includes_env": self.includes_env,
            "agents": [asdict(a) for a in self.agents],
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupManifest:
        agents_raw = data.get("agents") or []
        agents = [
            AgentBackupEntry(
                agent_id=str(row.get("agent_id", "")),
                name=str(row.get("name", "")),
                workspace_included=bool(row.get("workspace_included", True)),
            )
            for row in agents_raw
            if isinstance(row, dict)
        ]
        return cls(
            manifest_version=int(data.get("manifest_version", 0)),
            octop_version=str(data.get("octop_version", "")),
            schema_version=int(data.get("schema_version", 0)),
            created_at=str(data.get("created_at", "")),
            home=str(data.get("home", "")),
            db_file=str(data.get("db_file", "db/octop.db")),
            database_driver=str(data.get("database_driver", "sqlite")),
            database_dump_format=str(data.get("database_dump_format", "sqlite_file")),
            agents=agents,
            includes_config=bool(data.get("includes_config", True)),
            includes_env=bool(data.get("includes_env", False)),
        )

    @classmethod
    def load_text(cls, text: str) -> BackupManifest:
        data = json.loads(text)
        if not isinstance(data, dict):
            msg = "manifest must be a JSON object"
            raise ValueError(msg)
        return cls.from_dict(data)
