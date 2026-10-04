"""The plugins namespace must honour the local shadow short-circuit too.

``_local_bridge_shadow_response`` documents that ``history-migration`` "is a
local-archive concern and must not hop the bridge", and it is reached through
``TunnelTarget.agent_rest``. Both URL shapes resolve a bridge agent id —
``/api/agents/bridge:...`` and ``/api/plugins/agents/bridge:...`` — but only the
first one fills ``agent_rest``, so the plugins shape skips the short-circuit and
tunnels a request the docstring says must stay local.

The existing ``test_resolve_agents_and_plugins_path`` asserts ``remote_path`` for
both shapes but never ``agent_rest``, which is exactly why this slipped through.
"""

from __future__ import annotations

import pytest

from octop.api.middleware.bridge_proxy import resolve_tunnel_target
from octop.infra.errors import ErrorCode, OctopError

AGENTS = "/api/agents/bridge:cid1:aid1"
PLUGINS = "/api/plugins/agents/bridge:cid1:aid1"


@pytest.mark.parametrize(
    ("base", "rest"),
    [
        (AGENTS, "/history-migration/status"),
        (PLUGINS, "/history-migration/status"),
    ],
)
def test_both_namespaces_carry_agent_rest(base: str, rest: str) -> None:
    """``agent_rest`` is the only switch the local short-circuit reads."""
    target = resolve_tunnel_target(f"{base}{rest}")
    assert target is not None, f"unresolved: {base}{rest}"
    assert target.agent_rest == rest, f"agent_rest lost for the {base} namespace"


@pytest.mark.parametrize("base", [AGENTS, PLUGINS])
def test_both_namespaces_resolve_regular_sub_paths(base: str) -> None:
    """Control: ordinary sub-paths keep working in both shapes."""
    target = resolve_tunnel_target(f"{base}/tools")
    assert target is not None
    assert target.agent_rest == "/tools"
    assert target.remote_path.endswith("/tools")


def test_history_migration_status_is_answered_locally_in_both_namespaces() -> None:
    """The behaviour the docstring promises, driven through the middleware helper."""
    from octop.api.middleware.bridge_proxy import _local_bridge_shadow_response

    for base in (AGENTS, PLUGINS):
        target = resolve_tunnel_target(f"{base}/history-migration/status")
        assert target is not None
        assert target.agent_rest, f"{base} would tunnel a local-archive request"
        local = _local_bridge_shadow_response(method="GET", rest=target.agent_rest or "")
        assert local is not None, f"{base} did not answer locally"
        assert local.status_code == 200


def test_history_migration_writes_are_refused_locally_in_both_namespaces() -> None:
    """Control: the refusal path is also local, not a bridge round-trip."""
    from octop.api.middleware.bridge_proxy import _local_bridge_shadow_response

    for base in (AGENTS, PLUGINS):
        target = resolve_tunnel_target(f"{base}/history-migration/start")
        assert target is not None
        assert target.agent_rest, f"{base} would forward a local-archive write"
        with pytest.raises(OctopError) as exc_info:
            _local_bridge_shadow_response(method="POST", rest=target.agent_rest or "")
        assert exc_info.value.code == ErrorCode.BRIDGE_REMOTE_UNSUPPORTED


def test_agent_id_is_unwrapped_consistently() -> None:
    """Control: the plugins shape keeps rewriting the agent id like its sibling."""
    agents = resolve_tunnel_target(f"{AGENTS}/tools")
    plugins = resolve_tunnel_target(f"{PLUGINS}/tools")
    assert agents is not None and plugins is not None
    assert agents.ref.remote_agent_id == plugins.ref.remote_agent_id == "aid1"
    assert agents.ref.connection_id == plugins.ref.connection_id == "cid1"
