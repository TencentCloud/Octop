"""tests/integration/test_user_avatars.py"""

from __future__ import annotations

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_user_with_portrait(c, auth, username: str) -> int:
    created = await c.post(
        "/api/users",
        headers=auth,
        json={"username": username, "password": "TestPass12", "role": "user"},
    )
    assert created.status_code == 201, created.text
    user_id = int(created.json()["id"])
    uploaded = await c.post(
        f"/api/users/{user_id}/avatar",
        headers=auth,
        files={"file": ("avatar.png", _PNG, "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    return user_id


async def test_both_delete_paths_remove_the_portrait(env):
    """Batch delete must drop the portrait file, like the single delete does."""
    c, srv, auth = env
    avatars = srv.services.paths.user_avatars_dir
    batch_id = await _create_user_with_portrait(c, auth, "portrait_batch")
    single_id = await _create_user_with_portrait(c, auth, "portrait_single")
    assert list(avatars.glob(f"{batch_id}.*")), "upload stored no portrait"
    assert list(avatars.glob(f"{single_id}.*")), "upload stored no portrait"

    batched = await c.post(
        "/api/users/batch",
        headers=auth,
        json={"user_ids": [batch_id], "action": "delete"},
    )
    assert batched.status_code == 200, batched.text
    assert batched.json()["succeeded"] == 1
    assert not list(avatars.glob(f"{batch_id}.*")), "batch delete left an orphan portrait"

    single = await c.delete(f"/api/users/{single_id}", headers=auth)
    assert single.status_code == 204, single.text
    assert not list(avatars.glob(f"{single_id}.*")), "single delete left an orphan portrait"
