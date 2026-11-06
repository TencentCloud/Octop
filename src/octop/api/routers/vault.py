"""User vault item management (list with non-sensitive reveals, create, delete)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.agents.secret_input.validation import validate_manual_vault_item
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class VaultItemOut(BaseModel):
    """One vault item's metadata plus its revealable (non-secret) values.

    Secret field values (passwords, card data) are never included in any
    response; ``fields`` carries only types the envelope module marks
    revealable (plain ``text``).
    """

    vault_item_id: str
    item_type: str = Field(description="login / card / contact.")
    title: str
    origin: str | None = Field(
        default=None, description="Agent-declared site origin, not verified."
    )
    fields: dict[str, str] = Field(
        default_factory=dict,
        description="Revealable values keyed by field type (text only); "
        "secret types are never returned.",
    )
    created_at: int
    updated_at: int = Field(description="Changes on rotation, so silent rotation stays visible.")


class VaultItemsOut(BaseModel):
    items: list[VaultItemOut]


class VaultItemFieldIn(BaseModel):
    """One typed field of a manually created item."""

    id: str = Field(description="Field id: [a-z0-9_]{1,32}, unique within the item.")
    label: str | None = Field(
        default=None,
        description="Optional display label (validated, not persisted).",
    )
    type: str = Field(description="Field type; must be storable for item_type.")
    value: str = Field(description="Field value, validated against its type's shape.")


class VaultItemCreateBody(BaseModel):
    """Manual creation payload for one vault item (owner-scoped)."""

    item_type: str = Field(description="login / card / contact.")
    title: str = Field(description="Unique title for this item type (1-120 chars).")
    origin: str | None = Field(
        default=None, description="Optional http(s) origin, normalized server-side."
    )
    fields: list[VaultItemFieldIn] = Field(description="1 to 8 typed fields.")


def _item_out(row: Any, revealed: dict[str, str]) -> VaultItemOut:
    return VaultItemOut(
        vault_item_id=row.vault_item_id,
        item_type=row.item_type,
        title=row.title,
        origin=row.origin,
        fields=revealed,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/vault/items",
    response_model=VaultItemsOut,
    summary="List vault items",
)
async def list_vault_items(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> VaultItemsOut:
    """Encrypted vault items for the current user with non-sensitive reveals.

    The list query itself never selects ciphertext; the service re-reads and
    decrypts each row (page sizes are small) and keeps only revealable field
    types — usernames and contact text come back, passwords and card data
    never do. No admin listing exists, and no support path reads values.
    """
    vault = server.services.vault_service
    rows = vault.list_items(user.id)
    return VaultItemsOut(items=[_item_out(row, vault.revealed_fields(row)) for row in rows])


@router.post(
    "/vault/items",
    response_model=VaultItemOut,
    summary="Create a vault item",
)
async def create_vault_item(
    body: VaultItemCreateBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> VaultItemOut:
    """Manually create one vault item for the current user (owner-only).

    Validation mirrors the secure-form submit shapes (origin grammar,
    per-item-type field pairing, title and value lengths, per-type value
    shapes); values are sealed into the envelope exactly once and never
    echoed. A title collision answers 409 ``VAULT_REPLACE_REQUIRED`` (manual
    creation never rotates silently). The audit row carries ids only.
    """
    vault = server.services.vault_service
    title, origin, values = validate_manual_vault_item(
        body.item_type,
        body.title,
        body.origin,
        [field.model_dump() for field in body.fields],
    )
    try:
        row = vault.store_item(
            user.id,
            body.item_type,
            title,
            origin,
            values,
            replace_confirmed=False,
        )
    except OctopError as err:
        if err.code is ErrorCode.VAULT_REPLACE_REQUIRED:
            # Conflict semantics on the management surface; the chat submit
            # path keeps the 422 family for its replace/retry flow.
            err.status = 409
        raise
    server.services.audit_repo.write(
        actor=user.username,
        action="vault.create",
        target=row.vault_item_id,
    )
    return _item_out(row, vault.revealed_fields(row))


@router.delete(
    "/vault/items/{vault_item_id}",
    summary="Delete a vault item",
)
async def delete_vault_item(
    vault_item_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, bool]:
    """Delete one vault item (owner or admin).

    Metadata-only handling throughout: the delete never reads or decrypts the
    stored fields. The audit row carries the item id only.
    """
    vault = server.services.vault_service
    item = vault.repo.get(vault_item_id, user_id=user.id)
    if item is None and user.is_admin:
        # Admins may remove any user's item; the id still never leaks whether
        # it exists for a non-owner.
        item = vault.repo.find_by_id(vault_item_id)
    if item is None:
        raise OctopError(ErrorCode.VAULT_ITEM_NOT_FOUND, f"vault item {vault_item_id!r} not found")
    vault.delete_item(item.user_id, vault_item_id)
    server.services.audit_repo.write(
        actor=user.username,
        action="vault.delete",
        target=vault_item_id,
    )
    return {"deleted": True}
