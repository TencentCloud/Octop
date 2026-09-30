"""N 批（`T-CREDENTIAL-ECHO`）：★ 凭据回显掩码 + 读接口授权 + PATCH 三态 + Codex 登出真清。

★★ 全部用【自造串】（`DUMMY-*`）· ★ 不打印/不断言任何真实凭据值。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from octop.infra.agents.providers.codex_apply import CODEX_PROVIDER_NAME

_SECRET = "sk-DUMMY-NBATCH-KEY-0001"
_OVERWRITE = "sk-DUMMY-NBATCH-KEY-0002"
_VOICE_KEY = "AKID-DUMMY-NBATCH-VOICE-0003"
# ★ ≥20 位 base64/Fernet 形态（★ 密文/密钥都不该出现在响应体里）
_B64ISH = re.compile(r"[A-Za-z0-9_-]{20,}")


def _raw_api_key(services: Any, provider_id: int) -> str | None:
    with services.db.connect() as conn:
        cell = conn.execute(
            "SELECT api_key FROM providers WHERE id = ?", (provider_id,)
        ).fetchone()[0]
    if cell is None:
        return None
    return cell if isinstance(cell, str) else str(cell)


def _sha(text: str | None) -> str:
    return "" if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _assert_masked(body: Any) -> None:
    """★ 响应契约：★ 无 `api_key` 字段 ∧ 有布尔 `api_key_set` ∧ ★ 无 ≥20 位 base64 形态串。"""
    text = json.dumps(body, ensure_ascii=False)
    assert '"api_key"' not in text, text
    assert _B64ISH.search(text) is None, text
    items = body if isinstance(body, list) else [body]
    for item in items:
        assert isinstance(item["api_key_set"], bool), item


async def _regular_auth(c: Any, admin_auth: dict[str, str]) -> dict[str, str]:
    await c.post(
        "/api/users",
        headers=admin_auth,
        json={"username": "nbatch_regular", "password": "TestPass12", "role": "user"},
    )
    tok = (
        await c.post(
            "/api/auth/login", json={"username": "nbatch_regular", "password": "TestPass12"}
        )
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def test_read_endpoints_require_module_permission(env: Any) -> None:
    """★ 非授权方 = **403**（★ 非 404 ⇒ 不隐藏存在性）· ★ 有权限者仍 200。"""
    c, _, admin_auth = env
    user_auth = await _regular_auth(c, admin_auth)

    for path in ("/api/providers", "/api/voice/providers"):
        denied = await c.get(path, headers=user_auth)
        assert denied.status_code == 403, (path, denied.status_code)
        assert "FORBIDDEN" in denied.text, denied.text
        allowed = await c.get(path, headers=admin_auth)
        assert allowed.status_code == 200, (path, allowed.status_code)


async def test_provider_read_is_masked(env: Any) -> None:
    """★ 读接口：不回吐密钥 ⇒ 只回 `api_key_set`（★ 在解密后的值上判「非空」）。"""
    c, _, auth = env
    with_key = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "mask-a", "kind": "openai", "api_key": _SECRET},
    )
    without = await c.post(
        "/api/admin/providers", headers=auth, json={"name": "mask-b", "kind": "openai"}
    )
    assert with_key.status_code == 201 and without.status_code == 201
    assert with_key.json()["api_key_set"] is True
    assert without.json()["api_key_set"] is False

    listing = await c.get("/api/providers", headers=auth)
    body = listing.json()
    _assert_masked(body)
    assert _SECRET not in listing.text
    flags = {p["name"]: p["api_key_set"] for p in body}
    assert flags == {"mask-a": True, "mask-b": False}


async def test_write_responses_are_masked(env: Any) -> None:
    """★ POST/PATCH 响应同经 `_row_to_dict` ⇒ 写响应也不得回吐密钥（★ 单一出处闭合）。"""
    c, _, auth = env
    created = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "mask-c", "kind": "openai", "api_key": _SECRET},
    )
    assert created.status_code == 201
    _assert_masked(created.json())
    pid = created.json()["id"]
    patched = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"note": "n1"})
    assert patched.status_code == 200
    _assert_masked(patched.json())


async def test_voice_provider_read_is_masked(env: Any) -> None:
    """★ 语音列表同样掩码（★ 与 provider 同一契约）。"""
    c, srv, auth = env
    created = await c.post(
        "/api/admin/voice/providers",
        headers=auth,
        json={
            "name": "mask-voice",
            "kind": "openai",
            "capability": "tts",
            "api_key": _VOICE_KEY,
            "extra_json": json.dumps({"region": "cn"}),
        },
    )
    assert created.status_code == 201
    _assert_masked(created.json())
    assert created.json()["api_key_set"] is True
    listing = await c.get("/api/voice/providers", headers=auth)
    _assert_masked(listing.json())
    assert _VOICE_KEY not in listing.text


async def test_patch_tristate_keep_clear_overwrite(env: Any) -> None:
    """★★ 三态：字段**缺失** = 保留（★ 密文 sha 不变）· 显式 **null** = 清空 · 非空 = 覆盖。"""
    c, srv, auth = env
    created = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": "tri", "kind": "openai", "api_key": _SECRET},
    )
    pid = created.json()["id"]
    before = _raw_api_key(srv.services, pid)
    assert before is not None and _SECRET not in before  # ★ 落库即密文（base64 文本）

    kept = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"note": "only-note"})
    assert kept.status_code == 200
    after_keep = _raw_api_key(srv.services, pid)
    assert _sha(after_keep) == _sha(before), "★ 缺字段 ⇒ 必须保留（密文 sha 不变）"
    assert kept.json()["api_key_set"] is True

    cleared = await c.patch(f"/api/admin/providers/{pid}", headers=auth, json={"api_key": None})
    assert cleared.status_code == 200
    assert cleared.json()["api_key_set"] is False
    assert _raw_api_key(srv.services, pid) is None, "★ 显式 null ⇒ 必须真清空（写 NULL）"

    written = await c.patch(
        f"/api/admin/providers/{pid}", headers=auth, json={"api_key": _OVERWRITE}
    )
    assert written.status_code == 200
    assert written.json()["api_key_set"] is True
    raw = _raw_api_key(srv.services, pid)
    assert raw is not None and raw != before and _OVERWRITE not in raw
    assert srv.services.provider_repo.get(pid).api_key == _OVERWRITE  # ★ 解密后 == 新值


async def test_codex_logout_truly_clears_stored_key(env: Any) -> None:
    """★★ Codex 登出必须**真清 token**（★ 修 `providers.py` 旧「登出 no-op」缺陷）。"""
    c, srv, auth = env
    created = await c.post(
        "/api/admin/providers",
        headers=auth,
        json={"name": CODEX_PROVIDER_NAME, "kind": "openai", "api_key": _SECRET},
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    assert _raw_api_key(srv.services, pid) is not None

    out = await c.delete("/api/admin/providers/codex-oauth", headers=auth)
    assert out.status_code == 204, out.text
    assert _raw_api_key(srv.services, pid) is None, "★ 登出后 provider 行不得残留 access token"
