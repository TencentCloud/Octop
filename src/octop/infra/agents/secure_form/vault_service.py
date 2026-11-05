"""Storage service for the user vault (secure-form destination)."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from octop.infra.agents.secure_form.envelope import (
    filter_vault_fields,
    open_vault_fields,
    reveal_vault_fields,
    seal_vault_fields,
)
from octop.infra.crypto.fernet import PURPOSE_VAULT_ITEM, get_fernet
from octop.infra.db.repos.secrets import SecretRepo
from octop.infra.db.repos.vault_items import (
    VAULT_ITEMS_MAX_PER_USER,
    VaultItemRow,
    VaultItemsRepo,
)
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.ulid import new_ulid

logger = logging.getLogger(__name__)


@dataclass
class VaultService:
    """Encrypt, store, rotate, and delete user-scoped vault items.

    Crypto mirrors the agent-secret flow: a Fernet key bootstrapped in the
    ``secrets`` table under ``PURPOSE_VAULT_ITEM``, with the envelope bound to
    the row identity so a transplanted blob cannot decrypt.
    """

    repo: VaultItemsRepo
    secret_repo: SecretRepo

    def store_item(
        self,
        user_id: int,
        item_type: str,
        title: str,
        origin: str | None,
        fields: Mapping[str, str],
        *,
        replace_confirmed: bool,
        conn: Any | None = None,
    ) -> VaultItemRow:
        """Insert or rotate one vault item as a single serialized unit.

        Per-user serialization: SQLite serializes on the pool's single-writer
        lock; PostgreSQL takes ``pg_advisory_xact_lock(user_id)`` so the title
        lookup, the cap guard, and the write share one transaction. An
        injected ``conn`` (the secure-form submit unit) is used as-is.
        """
        storable = filter_vault_fields(item_type, fields)
        if not storable:
            # An empty credential must never be minted, whatever the caller
            # passed or forgot to filter.
            raise OctopError(
                ErrorCode.SECURE_FORM_FIELD_INVALID,
                f"no vault-storable fields for item_type {item_type!r}",
            )
        # Warm the purpose key before the write unit: SecretRepo.get_or_create
        # opens its own transaction, which cannot nest inside one on SQLite.
        # With an injected conn the unit is already open, so the owner of that
        # transaction is expected to have warmed the key beforehand.
        get_fernet(self.secret_repo, PURPOSE_VAULT_ITEM)

        def run(c: Any) -> VaultItemRow:
            existing = self.repo.find_by_title(
                user_id=user_id, item_type=item_type, title=title, conn=c
            )
            if existing is None:
                return self._insert(
                    c,
                    user_id=user_id,
                    item_type=item_type,
                    title=title,
                    origin=origin,
                    fields=storable,
                )
            if not replace_confirmed:
                raise OctopError(
                    ErrorCode.VAULT_REPLACE_REQUIRED,
                    f"a {item_type} item titled {title!r} already exists",
                    details={"existing_vault_item_id": existing.vault_item_id},
                )
            return self._rotate(c, existing=existing, fields=storable, origin=origin)

        if conn is not None:
            return run(conn)
        db = self.repo.db
        with db.transaction() as own:
            if db.dialect == "postgresql":
                # Transaction-scoped: released with this unit's COMMIT/ROLLBACK.
                own.execute("SELECT pg_advisory_xact_lock(?)", (user_id,))
            return run(own)

    def list_items(self, user_id: int) -> list[VaultItemRow]:
        """Metadata-only listing (no ciphertext, no values)."""
        return self.repo.list_for_user(user_id)

    def revealed_fields(self, row: VaultItemRow) -> dict[str, str]:
        """Decrypt one listed row and keep only user-revealable field types.

        Listing surfaces that show non-sensitive values back to the owning
        user (the vault page's username/contact line) decrypt per row here;
        the envelope module filters to ``VAULT_REVEALABLE_FIELD_TYPES`` so a
        password or card value can never leave storage through this path. An
        unreadable envelope degrades to an empty reveal so one corrupted row
        cannot fail the whole list.
        """
        full = self.repo.get(row.vault_item_id, user_id=row.user_id, include_blob=True)
        if full is None or full.fields_blob is None:
            return {}
        try:
            opened = open_vault_fields(
                self.secret_repo,
                row_user_id=row.user_id,
                vault_item_id=row.vault_item_id,
                item_type=row.item_type,
                blob=full.fields_blob,
            )
        except Exception:
            # OctopError covers tamper/missing-key cases; decrypt can also
            # raise from the crypto layer — either way degrade this row only.
            logger.warning(
                "vault reveal skipped (envelope unreadable) user=%s item=%s",
                row.user_id,
                row.vault_item_id,
            )
            return {}
        return reveal_vault_fields(opened)

    def check_insert_capacity(self, user_id: int) -> None:
        """Raise ``VAULT_CAP_EXCEEDED`` when the user is at the insert cap.

        Pre-claim submit check (cheap); rotation is never cap-guarded, so this
        is only consulted when no colliding item exists. The cap-guarded
        INSERT remains the authoritative guard inside the write unit.
        """
        if len(self.repo.list_for_user(user_id)) >= VAULT_ITEMS_MAX_PER_USER:
            raise OctopError(
                ErrorCode.VAULT_CAP_EXCEEDED,
                "user already has the maximum number of vault items",
            )

    def delete_item(self, user_id: int, vault_item_id: str) -> None:
        if not self.repo.delete(vault_item_id, user_id):
            raise OctopError(ErrorCode.VAULT_ITEM_NOT_FOUND, "vault item not found")
        logger.info("vault item deleted user=%s item=%s", user_id, vault_item_id)

    def _insert(
        self,
        conn: Any,
        *,
        user_id: int,
        item_type: str,
        title: str,
        origin: str | None,
        fields: Mapping[str, str],
    ) -> VaultItemRow:
        # The id is minted before sealing: the envelope bind must carry the
        # exact identity the row will be stored under.
        vault_item_id = new_ulid()
        blob = seal_vault_fields(
            self.secret_repo,
            user_id=user_id,
            vault_item_id=vault_item_id,
            item_type=item_type,
            fields=fields,
        )
        if not self.repo.insert_new(
            conn,
            vault_item_id=vault_item_id,
            user_id=user_id,
            item_type=item_type,
            title=title,
            origin=origin,
            fields_blob=blob,
        ):
            raise OctopError(
                ErrorCode.VAULT_CAP_EXCEEDED,
                "user already has the maximum number of vault items",
            )
        logger.info("vault item stored user=%s item=%s type=%s", user_id, vault_item_id, item_type)
        stored = self.repo.find_by_title(
            user_id=user_id, item_type=item_type, title=title, conn=conn
        )
        assert stored is not None, "vault insert lost the row"
        return stored

    def _rotate(
        self,
        conn: Any,
        *,
        existing: VaultItemRow,
        fields: Mapping[str, str],
        origin: str | None,
    ) -> VaultItemRow:
        # Rotation reuses the existing row identity: a freshly minted id would
        # fail the envelope bind check on read and destroy the item.
        blob = seal_vault_fields(
            self.secret_repo,
            user_id=existing.user_id,
            vault_item_id=existing.vault_item_id,
            item_type=existing.item_type,
            fields=fields,
        )
        updated = self.repo.rotate_by_identity(
            conn,
            vault_item_id=existing.vault_item_id,
            fields_blob=blob,
            origin=origin,
        )
        if updated != 1:
            # The row vanished mid-flight; never insert a new row bound to a
            # dead identity — the caller re-derives instead.
            raise OctopError(
                ErrorCode.VAULT_REPLACE_REQUIRED,
                "the vault item changed while replacing it",
                details={"existing_vault_item_id": existing.vault_item_id},
            )
        logger.info("vault item rotated user=%s item=%s", existing.user_id, existing.vault_item_id)
        stored = self.repo.find_by_title(
            user_id=existing.user_id,
            item_type=existing.item_type,
            title=existing.title,
            conn=conn,
        )
        assert stored is not None, "vault rotate lost the row"
        return stored
