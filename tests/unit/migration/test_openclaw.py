"""Reading an OpenClaw home into a migration plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from octop.infra.migration.openclaw import find_openclaw_home, read_openclaw


def _home(tmp_path: Path, config: str | dict[str, Any] | None = None) -> Path:
    home = tmp_path / ".openclaw"
    (home / "workspace").mkdir(parents=True)
    if config is not None:
        text = config if isinstance(config, str) else json.dumps(config)
        (home / "openclaw.json").write_text(text, encoding="utf-8")
    return home


def _notes(plan: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(note.code, note.params) for note in plan.notes]


def test_finds_the_state_dir(tmp_path: Path) -> None:
    assert find_openclaw_home({}, user_home=tmp_path) is None
    legacy = tmp_path / ".clawdbot"
    legacy.mkdir()
    assert find_openclaw_home({}, user_home=tmp_path) == legacy
    current = tmp_path / ".openclaw"
    current.mkdir()
    assert find_openclaw_home({}, user_home=tmp_path) == current

    elsewhere = tmp_path / "state"
    elsewhere.mkdir()
    assert find_openclaw_home({"OPENCLAW_STATE_DIR": str(elsewhere)}) == elsewhere
    assert find_openclaw_home({"OPENCLAW_STATE_DIR": str(tmp_path / "missing")}) is None


def test_reads_custom_provider_and_default_model(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        """{
          // JSON5 on purpose
          env: { vars: { PROXY_KEY: "sk-proxy" } },
          models: { providers: {
            proxy: {
              baseUrl: "https://llm.example.com/v1",
              apiKey: "${PROXY_KEY}",
              models: [{ id: "qwen3-max" }, { id: "deepseek-v4" },],
            },
            claude: { baseUrl: "https://a.example.com", api: "anthropic-messages",
                      apiKey: { source: "env", id: "CLAUDE_KEY" } },
            vertex: { baseUrl: "https://v.example.com", api: "google-vertex" },
          } },
          agents: { defaults: { model: { primary: "proxy/qwen3-max" } } },
        }""",
    )
    plan = read_openclaw(home, env={"CLAUDE_KEY": "sk-claude"})

    assert [(p.name, p.kind, p.base_url, p.api_key, p.models) for p in plan.providers] == [
        ("proxy", "openai", "https://llm.example.com/v1", "sk-proxy", ("qwen3-max", "deepseek-v4")),
        ("claude", "anthropic", "https://a.example.com", "sk-claude", ()),
    ]
    assert plan.default_model == ("proxy", "qwen3-max")
    assert _notes(plan) == [("provider_unsupported", {"name": "vertex", "api": "google-vertex"})]


def test_builtin_provider_key_comes_from_the_state_env_file(tmp_path: Path) -> None:
    home = _home(tmp_path, {"agents": {"defaults": {"model": "anthropic/claude-opus-4-6"}}})
    (home / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-env\n", encoding="utf-8")

    plan = read_openclaw(home, env={})

    [provider] = plan.providers
    assert (provider.name, provider.kind, provider.api_key) == (
        "anthropic",
        "anthropic",
        "sk-ant-env",
    )
    assert provider.models == ("claude-opus-4-6",)
    assert plan.default_model == ("anthropic", "claude-opus-4-6")


def test_builtin_provider_key_falls_back_to_legacy_auth_profiles(tmp_path: Path) -> None:
    home = _home(tmp_path, {"agents": {"defaults": {"model": {"primary": "openrouter/x/y"}}}})
    profiles = home / "agents" / "main" / "agent" / "auth-profiles.json"
    profiles.parent.mkdir(parents=True)
    profiles.write_text(
        json.dumps(
            {
                "profiles": {
                    "openrouter:default": {
                        "type": "api_key",
                        "provider": "openrouter",
                        "key": "sk-or-profile",
                    },
                    "openai:personal": {"type": "oauth", "provider": "openai", "access": "tok"},
                }
            }
        ),
        encoding="utf-8",
    )

    plan = read_openclaw(home, env={})

    assert plan.providers[0].api_key == "sk-or-profile"
    assert plan.default_model == ("openrouter", "x/y")


def test_builtin_provider_without_a_key_is_reported(tmp_path: Path) -> None:
    home = _home(tmp_path, {"agents": {"defaults": {"model": "anthropic/claude-opus-4-6"}}})
    plan = read_openclaw(home, env={})
    assert plan.providers == []
    assert plan.default_model is None
    assert _notes(plan) == [("provider_key_missing", {"name": "anthropic"})]


def test_include_merges_files_and_siblings_win(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        '{ $include: ["./base.json5", "./missing.json5"], channels: { telegram: { botToken: "top" } } }',
    )
    (home / "base.json5").write_text(
        '{ channels: { telegram: { botToken: "base" }, discord: { token: "d-token" } } }',
        encoding="utf-8",
    )

    plan = read_openclaw(home, env={})

    assert [(c.kind, c.config) for c in plan.channels] == [
        ("telegram", {"bot_token": "top"}),
        ("discord", {"bot_token": "d-token"}),
    ]
    assert _notes(plan) == [("include_missing", {"path": str(home / "missing.json5")})]


def test_reads_workspace_files_and_both_skill_roots(tmp_path: Path) -> None:
    home = _home(tmp_path, {})
    workspace = home / "workspace"
    (workspace / "SOUL.md").write_text("soul", encoding="utf-8")
    (workspace / "memory.md").write_text("legacy lowercase memory", encoding="utf-8")
    (workspace / "BOOTSTRAP.md").write_text("first-run ritual", encoding="utf-8")
    (workspace / "memory").mkdir()
    (workspace / "memory" / "2026-11-09.md").write_text("daily", encoding="utf-8")
    for skill_dir in (
        workspace / "skills" / "weekly-report",
        home / "skills" / "research" / "web-digest",
        home / "skills" / "weekly-report",  # the workspace copy wins
        home / "skills" / ".hub" / "hidden",
    ):
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")

    plan = read_openclaw(home, env={})

    assert [(f.dest, f.source.read_text(encoding="utf-8")) for f in plan.files] == [
        ("SOUL.md", "soul"),
        ("MEMORY.md", "legacy lowercase memory"),
        ("memory/2026-11-09.md", "daily"),
    ]
    assert [(s.slug, s.source) for s in plan.skills] == [
        ("weekly-report", workspace / "skills" / "weekly-report"),
        ("web-digest", home / "skills" / "research" / "web-digest"),
    ]


def test_workspace_override_is_honoured(tmp_path: Path) -> None:
    custom = tmp_path / "elsewhere"
    custom.mkdir()
    (custom / "SOUL.md").write_text("soul", encoding="utf-8")
    home = _home(tmp_path, {"agents": {"defaults": {"workspace": str(custom)}}})
    assert [f.source for f in read_openclaw(home, env={}).files] == [custom / "SOUL.md"]


def test_mcp_servers_keep_stdio_and_streamable_http_only(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        {
            "mcp": {
                "servers": {
                    "fetch": {"command": "uvx", "args": ["mcp-server-fetch"], "env": {"K": "${V}"}},
                    "wiki docs": {
                        "url": "https://wiki.example.com/mcp",
                        "transport": "streamable-http",
                        "headers": {"Authorization": "Bearer ${WIKI_TOKEN}", "X": "${UNSET}"},
                        "enabled": False,
                    },
                    "legacy": {"url": "https://old.example.com/sse"},
                }
            }
        },
    )
    plan = read_openclaw(home, env={"V": "value", "WIKI_TOKEN": "tok"})

    assert [(m.name, m.spec) for m in plan.mcp_servers] == [
        (
            "fetch",
            {
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "env": {"K": "value"},
            },
        ),
        (
            "wiki-docs",
            {
                "transport": "streamable_http",
                "url": "https://wiki.example.com/mcp",
                "headers": {"Authorization": "Bearer tok", "X": "${UNSET}"},
                "enabled": False,
            },
        ),
    ]
    assert _notes(plan) == [("mcp_sse_unsupported", {"name": "legacy"})]


def test_channels_map_accounts_and_report_what_cannot_move(tmp_path: Path) -> None:
    home = _home(
        tmp_path,
        {
            "channels": {
                "telegram": {
                    "botToken": "t-main",
                    "accounts": {
                        "alerts": {"botToken": "t-alerts"},
                        "inherits": {"dmPolicy": "pairing"},
                    },
                },
                "feishu": {"accounts": {"main": {"appId": "cli_x", "appSecret": "s"}}},
                "qqbot": {"appId": "q", "clientSecret": {"source": "file", "id": "/x"}},
                "wecom": {"botId": "b", "secret": "w"},
                "slack": {"botToken": "xoxb"},
            }
        },
    )
    plan = read_openclaw(home, env={})

    assert [(c.kind, c.name, c.config) for c in plan.channels] == [
        ("telegram", "telegram", {"bot_token": "t-main"}),
        ("telegram", "telegram-alerts", {"bot_token": "t-alerts"}),
        ("feishu", "feishu-main", {"app_id": "cli_x", "app_secret": "s"}),
        ("wecom", "wecom", {"bot_id": "b", "secret": "w"}),
    ]
    assert _notes(plan) == [("channel_unsupported", {"name": "slack"})]


def test_extra_agents_and_cron_jobs_are_reported(tmp_path: Path) -> None:
    home = _home(tmp_path, {"agents": {"list": [{"id": "main"}, {"id": "work"}, {"id": "ops"}]}})
    (home / "cron").mkdir()
    (home / "cron" / "jobs.json").write_text('{"version": 1, "jobs": [{}, {}]}', encoding="utf-8")

    plan = read_openclaw(home, env={})

    assert _notes(plan) == [
        ("extra_agents", {"count": 2}),
        ("cron_not_migrated", {"count": 2}),
    ]


def test_missing_or_broken_config_still_reads_the_workspace(tmp_path: Path) -> None:
    home = _home(tmp_path)
    (home / "workspace" / "SOUL.md").write_text("soul", encoding="utf-8")
    plan = read_openclaw(home, env={})
    assert [f.dest for f in plan.files] == ["SOUL.md"]
    assert _notes(plan) == [("config_missing", {"path": str(home / "openclaw.json")})]

    (home / "openclaw.json").write_text("{ broken", encoding="utf-8")
    plan = read_openclaw(home, env={})
    assert [f.dest for f in plan.files] == ["SOUL.md"]
    assert [note.code for note in plan.notes] == ["config_unreadable"]
