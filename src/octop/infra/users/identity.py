"""User identity primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"


@dataclass
class User:
    id: int
    username: str
    role: Role
    display_name: str | None
    locale: str = "zh"
    permissions: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.display_name or self.username

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN
