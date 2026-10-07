"""Provision a user with private copies of an administrator's experts."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlsplit

from octop.infra.agents.experts.avatar import (
    bind_workspace_avatar_icon_url,
    public_portrait_icon_url,
)
from octop.infra.agents.experts.catalog import (
    read_workspace_manifest_bytes,
    seed_expert_directory,
)
from octop.infra.agents.experts.publish import (
    PublishedExpertSnapshotMeta,
    export_agent_workspace_to_dir,
)
from octop.infra.agents.manager import AgentCreateSpec, AgentManager
from octop.infra.agents.settings.profile import (
    parse_config_json,
    parse_id_list_json,
    strip_profile_config,
)
from octop.infra.backend.resolver import resolve_agent_backend_spec
from octop.infra.db.services import SharedServices
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.users.identity import User
from octop.infra.users.manager import UserManager
from octop.infra.users.resource_policy import raise_if_backend_outside_user_root

logger = logging.getLogger(__name__)

_PRIVATE_KEY_NAMES = frozenset({"id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"})
_PRIVATE_KEY_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})
_INLINE_SECRET_MARKERS = (
    "password",
    "secret",
    "token",
    "credential",
    "api_key",
    "access_key",
    "private_key",
    "environment",
    "authorization",
    "headers",
)


def _reject_unsafe(reason: str) -> None:
    raise OctopError(
        ErrorCode.EXPERT_PUSH_UNSAFE,
        "expert cannot be safely copied with its current backend or files",
        details={"reason": reason},
    )


def _backend_leaves(spec: Any) -> list[dict[str, Any]]:
    if isinstance(spec, str):
        return [{"type": spec}]
    if not isinstance(spec, dict):
        return []
    if spec.get("type") == "composite":
        leaves = _backend_leaves(spec.get("default"))
        routes = spec.get("routes")
        if isinstance(routes, dict):
            for route in routes.values():
                leaves.extend(_backend_leaves(route))
        return leaves
    return [spec]


def _assert_no_inline_credentials(spec: dict[str, Any]) -> None:
    for key, value in spec.items():
        if not value:
            continue
        normalized = key.lower().replace("-", "_")
        if normalized in {"dsn", "connection_string"} or any(
            marker in normalized for marker in _INLINE_SECRET_MARKERS
        ):
            _reject_unsafe("inline_backend_credential")
        if (
            isinstance(value, str)
            and "://" in value
            and normalized
            in {
                "endpoint",
                "endpoint_url",
                "url",
                "host",
            }
        ):
            parsed = urlsplit(value)
            if parsed.username or parsed.password:
                _reject_unsafe("inline_backend_credential")


def _assert_safe_backend(raw: Any, resolved: Any, source_workspace: Path) -> None:
    source_workspace = source_workspace.resolve()
    if any(leaf.get("type") == "docker" for leaf in _backend_leaves(resolved)) and not (
        isinstance(resolved, dict) and resolved.get("type") == "docker"
    ):
        _reject_unsafe("docker_not_agent_scoped")
    for leaf in _backend_leaves(raw):
        if leaf.get("type") != "named":
            _assert_no_inline_credentials(leaf)

    for leaf in _backend_leaves(resolved):
        kind = str(leaf.get("type") or "").lower()
        if kind in {"filesystem", "local_shell"} and leaf.get("root_dir"):
            root = Path(str(leaf["root_dir"])).expanduser().resolve()
            if root.is_relative_to(source_workspace):
                _reject_unsafe("source_workspace_root")
        if kind == "opensandbox":
            _reject_unsafe("opensandbox_seed_unsupported")
        if kind != "docker":
            continue
        if str(leaf.get("sandbox_scope") or "agent").strip().lower() != "agent":
            _reject_unsafe("docker_scope")
        if any(
            leaf.get(key)
            for key in (
                "agent_id",
                "container_name",
                "sandbox_id",
                "username",
                "workspace_path",
                "root_dir",
                "volumes",
                "environment",
                "environment_file",
            )
        ):
            _reject_unsafe("docker_shared_workspace")


def _assert_safe_snapshot_files(paths: list[str]) -> None:
    for path in paths:
        name = Path(path).name.lower()
        if name in _PRIVATE_KEY_NAMES or any(name.endswith(ext) for ext in _PRIVATE_KEY_SUFFIXES):
            _reject_unsafe("private_key_file")


def _assert_safe_agent_settings(config: dict[str, Any]) -> None:
    memory = config.get("memory")
    if isinstance(memory, dict) and isinstance(memory.get("backend"), dict):
        _assert_no_inline_credentials(memory["backend"])
    plugins = config.get("plugins")
    if isinstance(plugins, dict):
        for plugin in plugins.values():
            if not isinstance(plugin, dict) or not isinstance(plugin.get("tools"), dict):
                continue
            for tool in plugin["tools"].values():
                if isinstance(tool, dict) and tool.get("config"):
                    _reject_unsafe("plugin_tool_credentials")
    acp = config.get("acp")
    if isinstance(acp, dict) and acp.get("runners"):
        _reject_unsafe("legacy_acp_credentials")


def _profile_ids(source: Any, config: dict[str, Any], key: str) -> list[str]:
    stored = parse_id_list_json(getattr(source, key))
    if stored is not None:
        return stored
    legacy = config.get(key)
    return [str(item) for item in legacy if str(item).strip()] if isinstance(legacy, list) else []


def _remove_owner_context(snapshot_dir: Path) -> None:
    """Keep the template manifest consistent after dropping the owner's USER.md."""
    (snapshot_dir / "USER.md").unlink(missing_ok=True)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    prompt_files = manifest_data.get("prompt_files")
    if isinstance(prompt_files, list) and "USER.md" in prompt_files:
        manifest_data["prompt_files"] = [path for path in prompt_files if path != "USER.md"]
        manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False), encoding="utf-8")


@asynccontextmanager
async def _temporary_snapshot_dir() -> AsyncIterator[Path]:
    temporary = await asyncio.to_thread(TemporaryDirectory, prefix="octop-user-experts-")
    try:
        yield Path(temporary.name)
    finally:
        await asyncio.to_thread(temporary.cleanup)


async def create_user_with_experts(
    *,
    user_manager: UserManager,
    registry: AgentManager,
    services: SharedServices,
    actor: User,
    source_agent_ids: list[str],
    user_fields: dict[str, Any],
    policy_kwargs: dict[str, Any],
) -> User:
    """Create an account and copy selected experts, or remove it if provisioning fails."""
    if source_agent_ids and not actor.is_admin:
        raise OctopError(ErrorCode.FORBIDDEN, "only administrators can push experts")
    if len(source_agent_ids) != len(set(source_agent_ids)):
        raise OctopError(ErrorCode.FORBIDDEN, "duplicate source expert", status=400)

    sources = []
    for agent_id in source_agent_ids:
        row = registry.get_row(agent_id)
        if row is None:
            raise OctopError(ErrorCode.AGENT_NOT_FOUND, "source expert not found")
        if row.user_id != actor.id or row.kind != "expert":
            raise OctopError(ErrorCode.FORBIDDEN, "source expert must be owned by administrator")
        source_config = parse_config_json(row.config_json)
        _assert_safe_agent_settings(source_config)
        backend = source_config.get("backend")
        try:
            resolved_backend = resolve_agent_backend_spec(
                backend, repo=services.storage_backend_repo
            )
        except ValueError:
            _reject_unsafe("unresolvable_backend")
        await asyncio.to_thread(
            _assert_safe_backend,
            backend,
            resolved_backend,
            registry.resolve_workspace_dir(agent_id, persist_if_missing=False),
        )
        sources.append((row, source_config, resolved_backend))

    if not sources:
        user = await user_manager.create(**user_fields)
        try:
            await user_manager.set_resource_policy(user.username, **policy_kwargs)
        except (Exception, asyncio.CancelledError):
            await user_manager.remove(user.username)
            raise
        return user

    async with _temporary_snapshot_dir() as temporary:
        snapshots: list[Path] = []
        for index, (source, _, _) in enumerate(sources):
            workspace = registry.workspace_for_agent(source.agent_id)
            if workspace is None:
                raise OctopError(ErrorCode.AGENT_NOT_FOUND, "source expert workspace not found")
            snapshot_dir = temporary / str(index)
            manifest = await read_workspace_manifest_bytes(workspace)
            metadata = (
                None
                if manifest is not None
                else PublishedExpertSnapshotMeta(
                    name=source.name,
                    description=source.description or "",
                    icon_name=source.icon_name or source.icon,
                    color=source.color,
                    label_zh=source.name,
                    label_en=source.name,
                    welcome_message_zh=source.welcome_message or "",
                    welcome_message_en=source.welcome_message or "",
                )
            )
            exported = await export_agent_workspace_to_dir(
                workspace=workspace,
                dest=snapshot_dir,
                metadata=metadata,
                manifest_id=source.agent_id,
            )
            _assert_safe_snapshot_files(exported)
            # USER.md describes the source owner's personal context, not the expert.
            await asyncio.to_thread(_remove_owner_context, snapshot_dir)
            snapshots.append(snapshot_dir)

        user = await user_manager.create(**user_fields)
        try:
            await user_manager.set_resource_policy(user.username, **policy_kwargs)
            for (source, source_config, resolved_backend), snapshot_dir in zip(
                sources, snapshots, strict=True
            ):
                package_ids = _profile_ids(source, source_config, "skill_package_ids")
                knowledge_ids = _profile_ids(source, source_config, "knowledge_base_ids")
                mcp_servers = _profile_ids(source, source_config, "mcp_servers")
                config = strip_profile_config(source_config)
                config.pop("workspace_dir", None)
                config.pop("system_files_path", None)
                memory = config.get("memory")
                if isinstance(memory, dict):
                    memory_backend = memory.get("backend")
                    if (
                        isinstance(memory_backend, dict)
                        and str(memory_backend.get("type") or "sqlite").lower() == "sqlite"
                    ):
                        config["memory"] = {
                            **memory,
                            "backend": {k: v for k, v in memory_backend.items() if k != "db_path"},
                        }
                backend = config.get("backend")
                raise_if_backend_outside_user_root(
                    services.user_policy_repo, user.id, resolved_backend
                )
                if package_ids:
                    package_ids = registry.validate_skill_package_ids(package_ids)
                    registry.assert_backend_supports_skill_packages(backend)
                knowledge_ids = registry.validate_knowledge_base_ids(user.id, knowledge_ids)
                mcp_servers = registry.validate_mcp_servers(user.id, mcp_servers)

                async def seed_copy(
                    created_row: Any, workspace: Any, snapshot: Path = snapshot_dir
                ) -> None:
                    await seed_expert_directory(expert_dir=snapshot, workspace=workspace)
                    await bind_workspace_avatar_icon_url(registry, created_row.agent_id, workspace)

                await registry.create(
                    AgentCreateSpec(
                        name=source.name,
                        user_id=user.id,
                        description=source.description,
                        persona_mbti=source.persona_mbti,
                        default_model=source.default_model,
                        system_prompt=source.system_prompt,
                        config=config,
                        icon=source.icon,
                        icon_name=source.icon_name,
                        icon_url=public_portrait_icon_url(source.icon_url),
                        color=source.color,
                        template_name=source.template_name,
                        seed_template=False,
                        skill_package_ids=package_ids,
                        published_expert_id=source.published_expert_id,
                        knowledge_base_ids=knowledge_ids,
                        mcp_servers=mcp_servers,
                        welcome_message=source.welcome_message,
                    ),
                    defer_bootstrap=False,
                    workspace_initializer=seed_copy,
                )
        except (Exception, asyncio.CancelledError):
            for row in registry.list_agents(user.id):
                try:
                    await registry.delete(row.agent_id)
                except Exception:
                    logger.exception("failed to remove incomplete pushed expert %s", row.agent_id)
            await user_manager.remove(user.username)
            raise
        return user
