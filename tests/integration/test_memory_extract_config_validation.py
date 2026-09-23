"""``PUT .../memory/extract-config`` must not accept non-finite seconds.

The route documents that "seconds are clamped to safe bounds", but
``_coerce_seconds`` decides with ``<`` / ``>``, and both comparisons are False
for ``NaN``. Pydantic accepts ``NaN`` / ``Infinity`` in a JSON body for a bare
``float`` field, so the value escapes the clamp and is persisted:

* ``agents.config_json`` is written with ``json.dumps`` (``allow_nan=True``), so
  the column stops being valid JSON (RFC 8259 has no ``NaN`` literal);
* the response and every later ``GET`` report ``null`` instead, so the stored
  setting is silently lost even though the request returned 200.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

_URL = "/api/agents/{aid}/memory/extract-config"


async def _put_raw(
    client: httpx.AsyncClient, auth: dict[str, str], aid: str, raw: str
) -> httpx.Response:
    headers = {**auth, "content-type": "application/json"}
    return await client.put(_URL.format(aid=aid), headers=headers, content=raw.encode())


def _strict_loads(text: str) -> Any:
    """``json.loads`` that rejects the non-standard ``NaN`` / ``Infinity`` tokens."""

    def _reject(constant: str) -> Any:
        raise AssertionError(f"config_json is not valid JSON: bare {constant!r} literal")

    return json.loads(text, parse_constant=_reject)


@pytest.mark.asyncio
async def test_put_rejects_nan_interval_seconds(env_with_main_agent: Any) -> None:
    client, _srv, auth, aid = env_with_main_agent
    resp = await _put_raw(client, auth, aid, '{"extract_interval_seconds": NaN}')
    assert resp.status_code == 400, resp.text

    # Nothing persisted: the stored default survives the rejected write.
    after = await client.get(_URL.format(aid=aid), headers=auth)
    assert after.status_code == 200, after.text
    assert after.json()["extract_interval_seconds"] == 21600.0


@pytest.mark.asyncio
async def test_put_rejects_nan_idle_seconds(env_with_main_agent: Any) -> None:
    client, _srv, auth, aid = env_with_main_agent
    resp = await _put_raw(client, auth, aid, '{"extract_idle_seconds": NaN}')
    assert resp.status_code == 400, resp.text

    after = await client.get(_URL.format(aid=aid), headers=auth)
    assert after.json()["extract_idle_seconds"] == 300.0


@pytest.mark.asyncio
async def test_put_rejects_infinite_seconds(env_with_main_agent: Any) -> None:
    """``Infinity`` is finite-clamped to 7 days today; an out-of-range ask is a
    client error, not a silent rewrite of what the user typed."""
    client, _srv, auth, aid = env_with_main_agent
    resp = await _put_raw(client, auth, aid, '{"extract_interval_seconds": Infinity}')
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_rejected_write_leaves_config_json_valid(env_with_main_agent: Any) -> None:
    client, srv, auth, aid = env_with_main_agent
    await _put_raw(client, auth, aid, '{"extract_interval_seconds": NaN}')

    row = srv.services.agent_repo.get(aid)
    _strict_loads(row.config_json or "{}")
