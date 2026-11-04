"""Unit tests for the secure-form vault storage slice (migration, repo, envelope, service)."""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

import pytest
from cryptography.fernet import InvalidToken

from octop.config import OctopConfig
from octop.infra.agents.secure_form.envelope import open_vault_fields
from octop.infra.agents.secure_form.vault_service import VaultService
from octop.infra.crypto.fernet import (
    PURPOSE_AGENT_SECRET,
    PURPOSE_VAULT_ITEM,
    decrypt_json,
    encrypt_str,
    get_fernet,
)
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.users import UserRepo
from octop.infra.db.repos.vault_items import (
    VAULT_ITEMS_MAX_PER_USER,
    VaultItemRow,
    VaultItemsRepo,
)
from octop.infra.db.services import build_shared_services
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.paths import PathLayout

LOGIN_FIELDS = {"text": "alice@example.com", "password": "hunter2"}


class VaultEnv(NamedTuple):
    db: SqlitePool
    user_id: int
    service: VaultService
    repo: VaultItemsRepo
    user_repo: UserRepo


@pytest.fixture
def env(tmp_path: Path) -> VaultEnv:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = SqlitePool(paths.db)
    run_migrations(db)
    shared = build_shared_services(db=db, paths=paths, config=OctopConfig())
    # vault_items.user_id is FK-bound to users(id) — seed the owner row.
    shared.repos.user_repo.create(username="owner", role="user")
    owner = shared.repos.user_repo.get_by_username("owner")
    assert owner is not None
    repo = VaultItemsRepo(db)
    return VaultEnv(
        db=db,
        user_id=owner.id,
        service=VaultService(repo=repo, secret_repo=shared.repos.secret_repo),
        repo=repo,
        user_repo=shared.repos.user_repo,
    )


def _open_blob(env: VaultEnv, vault_item_id: str, *, item_type: str = "login") -> dict[str, str]:
    row = env.repo.get(vault_item_id, user_id=env.user_id, include_blob=True)
    assert row is not None and row.fields_blob is not None
    return open_vault_fields(
        env.service.secret_repo,
        row_user_id=env.user_id,
        vault_item_id=vault_item_id,
        item_type=item_type,
        blob=row.fields_blob,
    )


def test_store_rotate_delete_list_roundtrip(env: VaultEnv) -> None:
    row = env.service.store_item(
        env.user_id,
        "login",
        "GitHub",
        "https://github.com",
        LOGIN_FIELDS,
        replace_confirmed=False,
    )
    assert isinstance(row, VaultItemRow)
    assert row.vault_item_id
    assert row.origin == "https://github.com"
    assert _open_blob(env, row.vault_item_id) == LOGIN_FIELDS

    listed = env.service.list_items(env.user_id)
    assert [item.vault_item_id for item in listed] == [row.vault_item_id]
    # Metadata-only list path never loads ciphertext.
    assert listed[0].fields_blob is None

    new_fields = {"text": "alice@example.com", "password": "n3w-pw"}
    rotated = env.service.store_item(
        env.user_id,
        "login",
        "GitHub",
        "https://github.com",
        new_fields,
        replace_confirmed=True,
    )
    assert isinstance(rotated, VaultItemRow)
    # Rotation reuses the row identity instead of minting a new one.
    assert rotated.vault_item_id == row.vault_item_id
    assert rotated.id == row.id
    assert _open_blob(env, row.vault_item_id) == new_fields

    env.service.delete_item(env.user_id, row.vault_item_id)
    assert env.service.list_items(env.user_id) == []
    with pytest.raises(OctopError) as missing:
        env.service.delete_item(env.user_id, row.vault_item_id)
    assert missing.value.code is ErrorCode.VAULT_ITEM_NOT_FOUND


def test_transplanted_blob_is_rejected(env: VaultEnv) -> None:
    first = env.service.store_item(
        env.user_id, "login", "A", None, LOGIN_FIELDS, replace_confirmed=False
    )
    second = env.service.store_item(
        env.user_id, "login", "B", None, LOGIN_FIELDS, replace_confirmed=False
    )
    donor = env.repo.get(first.vault_item_id, user_id=env.user_id, include_blob=True)
    assert donor is not None and donor.fields_blob is not None
    with pytest.raises(OctopError) as exc:
        open_vault_fields(
            env.service.secret_repo,
            row_user_id=env.user_id,
            vault_item_id=second.vault_item_id,
            item_type="login",
            blob=donor.fields_blob,
        )
    assert exc.value.code is ErrorCode.SECRET_REQUEST_INVALID
    # The bind also pins the owning user.
    with pytest.raises(OctopError) as other_user:
        open_vault_fields(
            env.service.secret_repo,
            row_user_id=env.user_id + 999,
            vault_item_id=first.vault_item_id,
            item_type="login",
            blob=donor.fields_blob,
        )
    assert other_user.value.code is ErrorCode.SECRET_REQUEST_INVALID


def test_cap_256_then_rotation_is_cap_exempt(env: VaultEnv) -> None:
    for i in range(VAULT_ITEMS_MAX_PER_USER):
        env.service.store_item(
            env.user_id,
            "login",
            f"item-{i:03d}",
            None,
            LOGIN_FIELDS,
            replace_confirmed=False,
        )
    assert len(env.service.list_items(env.user_id)) == VAULT_ITEMS_MAX_PER_USER

    with pytest.raises(OctopError) as exc:
        env.service.store_item(
            env.user_id, "login", "overflow", None, LOGIN_FIELDS, replace_confirmed=False
        )
    assert exc.value.code is ErrorCode.VAULT_CAP_EXCEEDED
    assert env.repo.find_by_title(user_id=env.user_id, item_type="login", title="overflow") is None

    new_fields = {"text": "alice@example.com", "password": "rotated"}
    rotated = env.service.store_item(
        env.user_id, "login", "item-000", None, new_fields, replace_confirmed=True
    )
    first = env.repo.find_by_title(user_id=env.user_id, item_type="login", title="item-000")
    assert first is not None
    assert rotated.vault_item_id == first.vault_item_id
    assert _open_blob(env, first.vault_item_id) == new_fields
    # Rotation replaced a row; the count did not grow.
    assert len(env.service.list_items(env.user_id)) == VAULT_ITEMS_MAX_PER_USER


def test_check_insert_capacity_pre_claim_guard(
    env: VaultEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    import octop.infra.agents.secure_form.vault_service as vault_service_module

    env.service.check_insert_capacity(env.user_id)  # empty vault: fine
    env.service.store_item(
        env.user_id, "login", "GitHub", None, LOGIN_FIELDS, replace_confirmed=False
    )
    monkeypatch.setattr(vault_service_module, "VAULT_ITEMS_MAX_PER_USER", 1)
    with pytest.raises(OctopError) as exc:
        env.service.check_insert_capacity(env.user_id)
    assert exc.value.code is ErrorCode.VAULT_CAP_EXCEEDED


def test_replace_requires_confirmation(env: VaultEnv) -> None:
    row = env.service.store_item(
        env.user_id, "login", "GitHub", None, LOGIN_FIELDS, replace_confirmed=False
    )
    with pytest.raises(OctopError) as exc:
        env.service.store_item(
            env.user_id,
            "login",
            "GitHub",
            None,
            {"text": "a", "password": "b"},
            replace_confirmed=False,
        )
    assert exc.value.code is ErrorCode.VAULT_REPLACE_REQUIRED
    assert exc.value.details["existing_vault_item_id"] == row.vault_item_id
    # The refusal left the stored envelope untouched.
    assert _open_blob(env, row.vault_item_id) == LOGIN_FIELDS

    rotated = env.service.store_item(
        env.user_id,
        "login",
        "GitHub",
        None,
        {"text": "a", "password": "b"},
        replace_confirmed=True,
    )
    assert rotated.vault_item_id == row.vault_item_id
    assert _open_blob(env, row.vault_item_id) == {"text": "a", "password": "b"}


def test_item_type_allowlist_filters_envelope_fields(env: VaultEnv) -> None:
    card_fields = {
        "card_number": "4242424242424242",
        "card_exp": "12/29",
        "card_cvv": "123",
        "text": "billing address",
    }
    row = env.service.store_item(
        env.user_id, "card", "My card", None, card_fields, replace_confirmed=False
    )
    opened = _open_blob(env, row.vault_item_id, item_type="card")
    # Exactly the card allow-list survives: cvv and the billing text never
    # enter the envelope.
    assert set(opened) == {"card_number", "card_exp"}
    assert opened["card_number"] == "4242424242424242"
    assert opened["card_exp"] == "12/29"

    with pytest.raises(OctopError) as exc:
        env.service.store_item(
            env.user_id,
            "card",
            "CVV only",
            None,
            {"card_cvv": "123"},
            replace_confirmed=False,
        )
    assert exc.value.code is ErrorCode.SECURE_FORM_FIELD_INVALID
    assert env.repo.find_by_title(user_id=env.user_id, item_type="card", title="CVV only") is None


def test_user_delete_cascades_vault_items(env: VaultEnv) -> None:
    row = env.service.store_item(
        env.user_id, "login", "GitHub", None, LOGIN_FIELDS, replace_confirmed=False
    )
    env.user_repo.delete(env.user_id)
    assert env.repo.get(row.vault_item_id, user_id=env.user_id) is None
    assert env.service.list_items(env.user_id) == []


def test_rotate_preserves_origin_when_omitted(env: VaultEnv) -> None:
    env.service.store_item(
        env.user_id,
        "login",
        "GitHub",
        "https://github.com",
        LOGIN_FIELDS,
        replace_confirmed=False,
    )
    kept = env.service.store_item(
        env.user_id, "login", "GitHub", None, LOGIN_FIELDS, replace_confirmed=True
    )
    assert kept.origin == "https://github.com"
    replaced = env.service.store_item(
        env.user_id,
        "login",
        "GitHub",
        "https://example.com",
        LOGIN_FIELDS,
        replace_confirmed=True,
    )
    assert replaced.origin == "https://example.com"


def test_injected_connection_rolls_back_with_the_owner_transaction(env: VaultEnv) -> None:
    # The unit owner warms the purpose key before opening the shared
    # transaction: a cold bootstrap inside it would nest transactions on
    # SQLite (SecretRepo.get_or_create opens its own).
    get_fernet(env.service.secret_repo, PURPOSE_VAULT_ITEM)

    with pytest.raises(RuntimeError), env.db.transaction() as conn:
        env.service.store_item(
            env.user_id,
            "login",
            "A",
            None,
            LOGIN_FIELDS,
            replace_confirmed=False,
            conn=conn,
        )
        env.service.store_item(
            env.user_id,
            "login",
            "B",
            None,
            LOGIN_FIELDS,
            replace_confirmed=False,
            conn=conn,
        )
        raise RuntimeError("forced rollback")
    assert env.service.list_items(env.user_id) == []

    with env.db.transaction() as conn:
        env.service.store_item(
            env.user_id,
            "login",
            "A",
            None,
            LOGIN_FIELDS,
            replace_confirmed=False,
            conn=conn,
        )
        env.service.store_item(
            env.user_id,
            "login",
            "B",
            None,
            LOGIN_FIELDS,
            replace_confirmed=False,
            conn=conn,
        )
    assert sorted(item.title for item in env.service.list_items(env.user_id)) == ["A", "B"]


def test_vault_purpose_key_is_separate_from_agent_secrets(env: VaultEnv) -> None:
    row = env.service.store_item(
        env.user_id, "login", "GitHub", None, LOGIN_FIELDS, replace_confirmed=False
    )
    stored = env.repo.get(row.vault_item_id, user_id=env.user_id, include_blob=True)
    assert stored is not None and stored.fields_blob is not None
    # The agent-secret purpose key cannot open a vault envelope...
    with pytest.raises(InvalidToken):
        decrypt_json(env.service.secret_repo, PURPOSE_AGENT_SECRET, stored.fields_blob)
    # ...and the vault purpose cannot open an agent-secret blob.
    agent_blob = encrypt_str(env.service.secret_repo, PURPOSE_AGENT_SECRET, "slot-value")
    with pytest.raises(InvalidToken):
        decrypt_json(env.service.secret_repo, PURPOSE_VAULT_ITEM, agent_blob)
