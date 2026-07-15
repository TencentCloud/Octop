"""Live connectivity probes for bundled token / api_key connectors.

Each connector is probed with REAL credentials through the very same
:func:`octop.infra.connectors.probe.probe_connector` the dashboard calls when a
user adds / verifies a connector — so a green probe means the real key reaches
the real upstream MCP endpoint.

Credentials come from the repo-root ``.env`` (loaded by
``tests/live/conftest.py`` via python-dotenv) or from CI GitHub Secrets. A
connector is probed only when ALL of its env vars are present; otherwise that
single case auto-skips, so CI stays green for connectors you hold no key for.

Excluded by design (need interactive / real-account auth):
  * notion       — oauth2, requires browser authorization
  * qq-mail      — imap_app_password, requires a real mailbox + auth code

Run locally::

    uv run pytest tests/live/test_connector_probe.py -m live -v
"""

from __future__ import annotations

import asyncio

import pytest
from tests.support.secrets import require_env

from octop.config import OctopConfig
from octop.infra.connectors.builder import validate_create_credentials
from octop.infra.connectors.catalog import get_catalog_entry
from octop.infra.connectors.probe import probe_connector

pytestmark = pytest.mark.live


# kind -> mapping of MCP credential payload key -> env var name.
# `personal_token` connectors map their value to ``token``; `api_key`
# connectors map to ``api_key``. Extra fields (IMA, Lexiang) are added too.
_CONNECTOR_CASES: dict[str, dict[str, str]] = {
    "tencent-docs": {"token": "CONNECTOR_TENCENT_DOCS_TOKEN"},
    "tencent-meeting": {"token": "CONNECTOR_TENCENT_MEETING_TOKEN"},
    "tencent-weiyun": {"token": "CONNECTOR_TENCENT_WEIYUN_TOKEN"},
    "youdao-note": {"token": "CONNECTOR_YOUDAO_NOTE_TOKEN"},
    "tencent-news": {"api_key": "CONNECTOR_TENCENT_NEWS_TOKEN"},
    "wechat-reading": {"api_key": "CONNECTOR_WECHAT_READING_TOKEN"},
    "qq-music": {"api_key": "CONNECTOR_QQ_MUSIC_TOKEN"},
    "fliggy": {"api_key": "CONNECTOR_FLIGGY_TOKEN"},
    "baidu-map": {"api_key": "CONNECTOR_BAIDU_MAP_TOKEN"},
    "ctrip-wendao": {"api_key": "CONNECTOR_CTRIP_WENDAO_TOKEN"},
    "meituan-travel": {"api_key": "CONNECTOR_MEITUAN_TRAVEL_TOKEN"},
    "yuandian": {"api_key": "CONNECTOR_YUANDIAN_TOKEN"},
    "tencent-ima": {
        "api_key": "CONNECTOR_TENCENT_IMA_TOKEN",
        "client_id": "CONNECTOR_TENCENT_IMA_CLIENT_ID",
    },
    "tencent-lexiang": {
        "api_key": "CONNECTOR_TENCENT_LEXIANG_TOKEN",
        "company_from": "CONNECTOR_TENCENT_LEXIANG_COMPANY_FROM",
    },
}


@pytest.mark.parametrize("kind", sorted(_CONNECTOR_CASES))
def test_connector_probe_with_real_credentials(kind: str) -> None:
    """Probe a real connector with real credentials via the product code path."""
    mapping = _CONNECTOR_CASES[kind]
    creds: dict[str, str] = {}
    for payload_key, env_name in mapping.items():
        creds[payload_key] = require_env(env_name)

    entry = get_catalog_entry(kind)
    assert entry is not None, f"catalog missing connector {kind}"

    # Enforce format rules (wrk-/qmk- prefixes, client_id / company_from
    # presence, ...) and normalize into the canonical credential payload.
    try:
        payload = validate_create_credentials(kind, creds)
    except ValueError as exc:
        pytest.fail(f"{kind} credential format invalid: {exc}")

    config = OctopConfig()
    result = asyncio.run(probe_connector(entry, payload, instance_id=f"live-{kind}", config=config))
    if result.get("ok"):
        return
    # A connection/network failure (e.g. the CI runner cannot reach the
    # upstream MCP host, or a proxy drops the SSE stream) is an environment
    # limitation, not a product defect — skip rather than turn the build red.
    # An auth/format failure, by contrast, means the credential is genuinely
    # bad and must fail loudly.
    if result.get("error_type") == "connection":
        pytest.skip(
            f"{kind} probe failed due to a network/connection issue "
            f"(not a credential problem): {result.get('error')}"
        )
    pytest.fail(f"{kind} probe failed: {result}")
