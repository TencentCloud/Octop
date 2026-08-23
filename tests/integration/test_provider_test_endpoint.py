"""tests/integration/test_provider_test_endpoint.py — provider probe."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


async def test_provider_test_ok(env_with_provider_record: Any) -> None:
    c, _srv, auth, pid = env_with_provider_record

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=MagicMock(content="pong"))

    with patch(
        "octop.infra.agents.providers.probe.build_probe_chat_model", return_value=fake_model
    ):
        r = await c.post(f"/api/admin/providers/{pid}/test", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert isinstance(body["latency_ms"], int)


async def test_provider_test_failure(env_with_provider_record: Any) -> None:
    c, _srv, auth, pid = env_with_provider_record

    def boom(*_a: Any, **_kw: Any) -> Any:
        raise RuntimeError("auth failed")

    with patch("octop.infra.agents.providers.probe.build_probe_chat_model", side_effect=boom):
        r = await c.post(f"/api/admin/providers/{pid}/test", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert "auth failed" in body["error"]


async def test_provider_test_missing_provider(env_with_provider_record: Any) -> None:
    c, _srv, auth, _pid = env_with_provider_record
    r = await c.post("/api/admin/providers/99999/test", headers=auth)
    assert r.status_code == 404


async def test_provider_test_embedding_skips_chat_probe(
    env_with_provider_record: Any,
) -> None:
    c, _srv, auth, pid = env_with_provider_record

    async def fake_probe(
        row: Any,
        *,
        model_id: str | None = None,
        embedding: bool | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        assert embedding is True
        assert model_id == "text-embedding-3-small"
        return {"ok": True, "latency_ms": 12}

    with patch(
        "octop.api.routers.providers.probe_provider_row",
        new=AsyncMock(side_effect=fake_probe),
    ):
        r = await c.post(
            f"/api/admin/providers/{pid}/test",
            headers=auth,
            json={"model_id": "text-embedding-3-small", "embedding": True},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["latency_ms"] == 12
