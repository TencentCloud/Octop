"""Inbound bridge links stay distinct when several people share one peer account."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from octop.infra.bridge.ids import PROTOCOL_VERSION
from octop.infra.bridge.manager import BridgeManager, observe_ws_client_host
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.bridge_connections import BridgeConnectionRepo
from octop.infra.db.repos.users import UserRepo


class _HoldSocket:
    def __init__(self, hello: dict[str, object], *, client_host: str) -> None:
        self._hello = json.dumps(hello)
        self._opened = False
        self.sent: list[str] = []
        self.client = SimpleNamespace(host=client_host, port=40000)
        self.headers: dict[str, str] = {}
        self.hold = asyncio.Event()
        self.close_code: int | None = None

    async def receive_text(self) -> str:
        if not self._opened:
            self._opened = True
            return self._hello
        await self.hold.wait()
        raise RuntimeError("stop")

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_code = code
        self.hold.set()


def _hello(connection_id: str, *, display_name: str) -> dict[str, object]:
    return {
        "type": "hello",
        "protocol_version": PROTOCOL_VERSION,
        "connection_id": connection_id,
        "role": "initiator",
        "advertise_base_url": "http://127.0.0.1:8088",
        "advertise_username": "jubaoliang",
        "display_name": display_name,
    }


async def _wait_ack(sock: _HoldSocket) -> dict[str, object]:
    for _ in range(50):
        if sock.sent:
            payload = json.loads(sock.sent[0])
            assert isinstance(payload, dict)
            return payload
        await asyncio.sleep(0.02)
    raise AssertionError("no hello_ack")


def test_observe_ws_client_host_prefers_forwarded_when_peer_is_loopback() -> None:
    direct = SimpleNamespace(client=SimpleNamespace(host="203.0.113.8", port=1), headers={})
    assert observe_ws_client_host(direct) == "203.0.113.8"
    proxied = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1", port=1),
        headers={"x-forwarded-for": "10.0.0.4, 198.51.100.7"},
    )
    assert observe_ws_client_host(proxied) == "198.51.100.7"
    loopback = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1", port=1), headers={})
    assert observe_ws_client_host(loopback) == ""


@pytest.mark.asyncio
async def test_two_logins_to_same_account_stay_separate(tmp_path: Path) -> None:
    pool = SqlitePool(tmp_path / "octop.db")
    run_migrations(pool)
    users = UserRepo(pool)
    uid = users.create(username="jubaoliang", password_hash="x", role="admin")
    repo = BridgeConnectionRepo(pool)
    mgr = BridgeManager(
        bridge_repo=repo,
        secret_repo=SimpleNamespace(),
        user_repo=users,
        advertise_base_url="https://demo.octop.chat",
    )
    owner = SimpleNamespace(id=uid, username="jubaoliang")
    first = _HoldSocket(_hello("CIDAAA", display_name="内网"), client_host="203.0.113.8")
    second = _HoldSocket(_hello("CIDBBB", display_name="内网"), client_host="198.51.100.7")

    task_a = asyncio.create_task(mgr.accept_inbound(websocket=first, user=owner))
    ack_a = await _wait_ack(first)
    task_b = asyncio.create_task(mgr.accept_inbound(websocket=second, user=owner))
    ack_b = await _wait_ack(second)

    assert ack_a["connection_id"] == "CIDAAA"
    assert ack_b["connection_id"] == "CIDBBB"
    assert first.close_code is None
    assert mgr._sessions["CIDAAA"] is not None
    assert mgr._sessions["CIDBBB"] is not None

    rows = {row.connection_id: row for row in repo.list_for_owner(uid)}
    assert set(rows) == {"CIDAAA", "CIDBBB"}
    assert rows["CIDAAA"].display_name == "203.0.113.8"
    assert rows["CIDBBB"].display_name == "198.51.100.7"
    assert rows["CIDAAA"].peer_client_host == "203.0.113.8"
    assert rows["CIDBBB"].peer_username == "jubaoliang"

    renamed = repo.update_settings("CIDAAA", display_name="家里的机器", notes=None)
    assert renamed is not None and renamed.display_name == "家里的机器"

    again = _HoldSocket(_hello("CIDAAA", display_name="云端改名"), client_host="203.0.113.8")
    task_again = asyncio.create_task(mgr.accept_inbound(websocket=again, user=owner))
    ack_again = await _wait_ack(again)
    await asyncio.sleep(0)
    assert ack_again["connection_id"] == "CIDAAA"
    kept = repo.get("CIDAAA")
    assert kept is not None
    assert kept.display_name == "家里的机器"
    assert kept.status == "connected"
    other = repo.get("CIDBBB")
    assert other is not None and other.display_name == "198.51.100.7"
    live_a = mgr._sessions.get("CIDAAA")
    live_b = mgr._sessions.get("CIDBBB")
    assert live_a is not None and not live_a.closed
    assert live_b is not None and not live_b.closed

    for sock in (first, second, again):
        sock.hold.set()
    await asyncio.gather(task_a, task_b, task_again)
