"""Storage service for chat-collected agent secret slots."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.secret_input.slots import (
    AGENT_SECRET_MAX_SLOTS,
    AGENT_SECRET_MAX_VALUE_CHARS,
    normalize_slot_name,
)
from octop.infra.crypto.fernet import PURPOSE_AGENT_SECRET, decrypt_str, encrypt_str
from octop.infra.db.repos._base import now_ts
from octop.infra.db.repos.agent_secrets import AgentSecretRow, AgentSecretsRepo
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)


@dataclass
class AgentSecretService:
    """Encrypt, store, decrypt, and delete per-agent secret slots.

    Crypto mirrors the connector credential flow: the Fernet key is bootstrapped
    in the ``secrets`` table under ``PURPOSE_AGENT_SECRET`` with no external
    master-key configuration.
    """

    repo: AgentSecretsRepo
    secret_repo: SecretRepo

    def store_slot(
        self,
        *,
        agent_id: str,
        user_id: int,
        slot_name: str,
        value: str,
        display_name: str | None = None,
    ) -> AgentSecretRow:
        """Encrypt *value* and upsert the slot. Never log the value itself."""
        slot = normalize_slot_name(slot_name)
        if slot is None:
            raise OctopError(
                ErrorCode.SECRET_SLOT_INVALID,
                f"invalid secret slot name: {slot_name!r}",
            )
        # Stored verbatim — a password may legitimately contain spaces; only
        # an entirely blank payload is rejected.
        if not value.strip():
            raise OctopError(
                ErrorCode.SECRET_SLOT_INVALID,
                "secret value must not be blank",
            )
        if len(value) > AGENT_SECRET_MAX_VALUE_CHARS:
            raise OctopError(
                ErrorCode.SECRET_SLOT_INVALID,
                f"secret value exceeds {AGENT_SECRET_MAX_VALUE_CHARS} characters",
            )
        existing = self.repo.list_for_agent(agent_id)
        known = {row.slot_name for row in existing}
        if slot not in known and len(existing) >= AGENT_SECRET_MAX_SLOTS:
            raise OctopError(
                ErrorCode.SECRET_SLOT_INVALID,
                f"agent already has {AGENT_SECRET_MAX_SLOTS} secret slots",
            )
        blob = encrypt_str(self.secret_repo, PURPOSE_AGENT_SECRET, value)
        try:
            row = self.repo.upsert_slot(
                agent_id=agent_id,
                user_id=user_id,
                slot_name=slot,
                display_name=display_name or slot,
                secret_blob=blob,
            )
        except Exception:
            logger.exception("agent secret slot write failed agent=%s slot=%s", agent_id, slot)
            raise OctopError(
                ErrorCode.SECRET_WRITE_FAILED,
                "failed to persist the secret slot",
            ) from None
        logger.info(
            "agent secret slot stored agent=%s slot=%s rotated=%s",
            agent_id,
            slot,
            slot in known,
        )
        return row

    def store_slots_in_unit(
        self,
        conn: Any,
        *,
        agent_id: str,
        user_id: int,
        values: Mapping[str, str],
        display_names: Mapping[str, str] | None = None,
    ) -> None:
        """Encrypt and upsert several slots on a caller-owned connection.

        The secure-form submit unit writes all mapped env slots plus the vault
        item plus the audit row inside ONE transaction; this method only
        encrypts and delegates to the connection-injecting repo write. Slot
        names arrive already normalized; values already passed the secure-form
        pre-claim validation. The purpose key must be warm before the owning
        transaction opens (SQLite cannot nest the bootstrap).
        """
        entries: list[tuple[str, str | None, bytes]] = []
        for slot_name, value in values.items():
            slot = normalize_slot_name(slot_name)
            if slot is None:
                raise OctopError(
                    ErrorCode.SECRET_SLOT_INVALID,
                    f"invalid secret slot name: {slot_name!r}",
                )
            if not value.strip():
                raise OctopError(
                    ErrorCode.SECRET_SLOT_INVALID,
                    f"secret value for slot {slot} must not be blank",
                )
            if len(value) > AGENT_SECRET_MAX_VALUE_CHARS:
                raise OctopError(
                    ErrorCode.SECRET_SLOT_INVALID,
                    f"secret value for slot {slot} exceeds "
                    f"{AGENT_SECRET_MAX_VALUE_CHARS} characters",
                )
            label = (display_names or {}).get(slot) or slot
            entries.append(
                (slot, label, encrypt_str(self.secret_repo, PURPOSE_AGENT_SECRET, value))
            )
        self.repo.upsert_slots(conn, agent_id=agent_id, user_id=user_id, entries=entries)
        logger.info(
            "agent secret slots stored agent=%s slots=%s",
            agent_id,
            ",".join(sorted(slot for slot, _n, _b in entries)),
        )

    def decrypt_env(self, agent_id: str) -> dict[str, str]:
        """All slot values for *agent_id* as an env mapping (decrypting read)."""
        out: dict[str, str] = {}
        try:
            rows = self.repo.list_for_agent(agent_id, include_blob=True)
        except Exception:
            logger.exception("agent secret slot list failed agent=%s", agent_id)
            return out
        for row in rows:
            if not row.secret_blob:
                continue
            try:
                out[row.slot_name] = decrypt_str(
                    self.secret_repo, PURPOSE_AGENT_SECRET, row.secret_blob
                )
            except Exception:
                logger.exception(
                    "agent secret slot decrypt failed agent=%s slot=%s (skipping)",
                    agent_id,
                    row.slot_name,
                )
        return out

    def list_slots(self, agent_id: str) -> list[AgentSecretRow]:
        """Metadata-only listing (no ciphertext, no values)."""
        return self.repo.list_for_agent(agent_id)

    def delete_slot(self, agent_id: str, secret_id: str) -> bool:
        deleted = self.repo.delete(agent_id, secret_id)
        if deleted:
            logger.info(
                "agent secret slot deleted agent=%s secret_id=%s at=%d",
                agent_id,
                secret_id,
                now_ts(),
            )
        return deleted


__all__ = ["AgentSecretService"]
