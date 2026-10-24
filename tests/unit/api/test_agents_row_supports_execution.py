"""`_row_dict` must surface `supports_execution` so the dashboard can label
workspaces whose backend cannot host a shell (deepagents silently drops the
execute tool for object-storage / database backends — issue #1664)."""

from types import SimpleNamespace

from octop.api.routers.agents import _row_dict


def _row(config_json: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        agent_id="agent-1",
        user_id=None,
        name="agent",
        description=None,
        persona_mbti=None,
        default_model=None,
        system_prompt=None,
        last_state=None,
        last_error=None,
        config_json=config_json,
        icon=None,
        icon_url=None,
        template_name=None,
        icon_name=None,
        color=None,
        skill_package_ids=None,
        knowledge_base_ids=None,
        mcp_servers=None,
        published_expert_id=None,
        welcome_message=None,
        is_shared=0,
        kind="expert",
    )


def test_default_backend_supports_execution() -> None:
    payload = _row_dict(_row("{}"))
    assert payload["supports_execution"] is True


def test_named_object_storage_backend_does_not_support_execution() -> None:
    payload = _row_dict(_row('{"backend": {"type": "named", "name": "minio"}}'))
    assert payload["supports_execution"] is False


def test_docker_backend_supports_execution() -> None:
    payload = _row_dict(_row('{"backend": {"type": "docker", "image": "python:3.12-slim"}}'))
    assert payload["supports_execution"] is True
