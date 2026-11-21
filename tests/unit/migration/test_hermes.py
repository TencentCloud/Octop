"""Reading a Hermes Agent home into a migration plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from octop.infra.migration.hermes import find_hermes_home, read_hermes


def _home(tmp_path: Path, config: str = "", env: str = "") -> Path:
    home = tmp_path / ".hermes"
    home.mkdir()
    if config:
        (home / "config.yaml").write_text(config, encoding="utf-8")
    if env:
        (home / ".env").write_text(env, encoding="utf-8")
    return home


def _notes(plan: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(note.code, note.params) for note in plan.notes]


def _providers(plan: Any) -> list[tuple[str, str, str, str | None, tuple[str, ...]]]:
    return [(p.name, p.kind, p.base_url, p.api_key, p.models) for p in plan.providers]


def test_finds_the_home(tmp_path: Path) -> None:
    assert find_hermes_home({}, user_home=tmp_path) is None
    home = _home(tmp_path)
    assert find_hermes_home({}, user_home=tmp_path) == home
    other = tmp_path / "profile"
    other.mkdir()
    assert find_hermes_home({"HERMES_HOME": str(other)}) == other


def test_hosted_provider_takes_its_key_from_env(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        'model:\n  default: "anthropic/claude-opus-4.6"\n  provider: openrouter\n',
        "OPENROUTER_API_KEY=sk-or\n",
    )
    plan = read_hermes(home, env={})
    assert _providers(plan) == [
        (
            "openrouter",
            "openai",
            "https://openrouter.ai/api/v1",
            "sk-or",
            ("anthropic/claude-opus-4.6",),
        )
    ]
    assert plan.default_model == ("openrouter", "anthropic/claude-opus-4.6")


def test_plain_string_model_with_auto_provider_uses_the_first_key(tmp_path: Path) -> None:
    home = _home(tmp_path, "model: deepseek-chat\n", "DEEPSEEK_API_KEY=sk-ds\n")
    plan = read_hermes(home, env={})
    assert plan.default_model == ("deepseek", "deepseek-chat")
    assert plan.providers[0].api_key == "sk-ds"


def test_provider_aliases_map_to_octop_ids(tmp_path: Path) -> None:
    home = _home(tmp_path, "model:\n  default: kimi-k3\n  provider: kimi-coding\n")
    plan = read_hermes(home, env={"KIMI_API_KEY": "sk-kimi"})
    assert plan.default_model == ("moonshot", "kimi-k3")


def test_custom_base_url_becomes_one_compatible_provider(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        "model:\n  default: llama3\n  provider: custom\n  base_url: http://localhost:11434/v1\n",
    )
    plan = read_hermes(home, env={})
    assert _providers(plan) == [
        ("hermes-custom", "openai", "http://localhost:11434/v1", None, ("llama3",))
    ]
    assert plan.default_model == ("hermes-custom", "llama3")


def test_named_endpoints_in_both_formats(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        """
model:
  provider: custom:my-local
  default: qwen2.5-coder:32b
providers:
  my-local:
    api: http://localhost:8080/v1
    key_env: MY_LOCAL_KEY
    default_model: qwen2.5-coder:32b
    models:
      "qwen2.5-coder:7b": { context_length: 32000 }
  claude-proxy:
    base_url: https://claude.example.com
    api_key: sk-inline
    transport: anthropic_messages
  responses-only:
    api: https://r.example.com/v1
    transport: codex_responses
custom_providers:
  - name: legacy
    base_url: https://legacy.example.com/v1
    api_key: sk-legacy
    model: gpt-x
""",
        "MY_LOCAL_KEY=local-key\n",
    )
    plan = read_hermes(home, env={})

    assert _providers(plan) == [
        ("legacy", "openai", "https://legacy.example.com/v1", "sk-legacy", ("gpt-x",)),
        (
            "my-local",
            "openai",
            "http://localhost:8080/v1",
            "local-key",
            ("qwen2.5-coder:32b", "qwen2.5-coder:7b"),
        ),
        ("claude-proxy", "anthropic", "https://claude.example.com", "sk-inline", ()),
    ]
    assert plan.default_model == ("my-local", "qwen2.5-coder:32b")
    assert _notes(plan) == [
        ("provider_unsupported", {"name": "responses-only", "api": "codex_responses"})
    ]


@pytest.mark.parametrize(
    ("config", "note"),
    [
        (
            "model:\n  default: m\n  provider: anthropic\n",
            ("provider_key_missing", {"name": "anthropic"}),
        ),
        (
            "model:\n  default: m\n  provider: openai-codex\n",
            ("provider_unsupported", {"name": "openai-codex", "api": "built-in"}),
        ),
    ],
)
def test_models_that_cannot_move_are_reported(
    tmp_path: Path, config: str, note: tuple[str, dict[str, str]]
) -> None:
    plan = read_hermes(_home(tmp_path, config), env={})
    assert plan.providers == []
    assert plan.default_model is None
    assert _notes(plan) == [note]


def test_persona_and_memory_files(tmp_path: Path) -> None:
    home = _home(tmp_path)
    (home / "SOUL.md").write_text("soul", encoding="utf-8")
    (home / "memories").mkdir()
    (home / "memories" / "MEMORY.md").write_text(
        "Dev machine runs Fedora\n§\nDeploys go through staging\nfirst\n§\n\n", encoding="utf-8"
    )
    (home / "memories" / "USER.md").write_text("Prefers brief answers\n", encoding="utf-8")

    plan = read_hermes(home, env={})

    assert [(f.dest, f.content) for f in plan.files] == [
        ("SOUL.md", None),
        ("MEMORY.md", "Dev machine runs Fedora\n\nDeploys go through staging\nfirst\n"),
        ("USER.md", "Prefers brief answers\n"),
    ]


@pytest.mark.parametrize("manifest", ["deploy-k8s:abc123\n", '{"deploy-k8s": "abc123"}'])
def test_bundled_skills_are_left_behind(tmp_path: Path, manifest: str) -> None:
    home = _home(tmp_path)
    for rel in ("productivity/meeting-notes", "devops/deploy-k8s", ".hub/quarantine/bad"):
        skill = home / "skills" / rel
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (home / "skills" / ".bundled_manifest").write_text(manifest, encoding="utf-8")

    plan = read_hermes(home, env={})

    assert [s.slug for s in plan.skills] == ["meeting-notes"]


def test_mcp_servers(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        """
mcp_servers:
  filesystem:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/srv"]
    enabled: false
  remote_api:
    url: https://mcp.example.com/mcp
    headers:
      Authorization: "Bearer ${env:EXAMPLE_TOKEN}"
      X-Team: "${TEAM}"
  events:
    url: https://sse.example.com/sse
    transport: sse
""",
        "EXAMPLE_TOKEN=tok\n",
    )
    plan = read_hermes(home, env={})

    assert [(m.name, m.spec) for m in plan.mcp_servers] == [
        (
            "filesystem",
            {
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/srv"],
                "enabled": False,
            },
        ),
        (
            "remote_api",
            {
                "transport": "streamable_http",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer tok", "X-Team": "${TEAM}"},
            },
        ),
    ]
    assert _notes(plan) == [("mcp_sse_unsupported", {"name": "events"})]


def test_channels_come_from_env_and_cron_is_reported(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        env=(
            "TELEGRAM_BOT_TOKEN=tg\nFEISHU_APP_ID=cli_x\nFEISHU_APP_SECRET=fs\n"
            "DINGTALK_CLIENT_ID=only-half\nSLACK_BOT_TOKEN=xoxb\n"
        ),
    )
    (home / "cron").mkdir()
    (home / "cron" / "jobs.json").write_text('{"jobs": [{"id": "a"}]}', encoding="utf-8")

    plan = read_hermes(home, env={})

    assert [(c.kind, c.name, c.config) for c in plan.channels] == [
        ("telegram", "telegram", {"bot_token": "tg"}),
        ("feishu", "feishu", {"app_id": "cli_x", "app_secret": "fs"}),
    ]
    assert _notes(plan) == [
        ("config_missing", {"path": str(home / "config.yaml")}),
        ("channel_unsupported", {"name": "slack"}),
        ("cron_not_migrated", {"count": 1}),
    ]


def test_broken_yaml_is_reported_not_raised(tmp_path: Path) -> None:
    plan = read_hermes(_home(tmp_path, "model: [unclosed\n"), env={})
    assert [note.code for note in plan.notes] == ["config_unreadable"]
