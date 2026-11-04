"""User vault item management (metadata only — values are never returned)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from octop.api.deps import current_user, get_server
from octop.infra.errors import ErrorCode, OctopError

router = APIRouter()


class VaultItemOut(BaseModel):
    """One vault item's metadata. Ciphertext and values are never included."""

    vault_item_id: str
    item_type: str = Field(description="login / card / contact.")
    title: str
    origin: str | None = Field(
        default=None, description="Agent-declared site origin, not verified."
    )
    created_at: int
    updated_at: int = Field(description="Changes on rotation, so silent rotation stays visible.")


class VaultItemsOut(BaseModel):
    items: list[VaultItemOut]


@router.get(
    "/vault/items",
    response_model=VaultItemsOut,
    summary="List vault items",
)
async def list_vault_items(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> VaultItemsOut:
    """Encrypted vault items for the current user, metadata only.

    No admin listing exists: the list query never selects ciphertext, and no
    support path reads or decrypts values.
    """
    rows = server.services.vault_service.list_items(user.id)
    return VaultItemsOut(
        items=[
            VaultItemOut(
                vault_item_id=row.vault_item_id,
                item_type=row.item_type,
                title=row.title,
                origin=row.origin,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
    )


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
