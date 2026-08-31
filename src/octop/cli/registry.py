"""CLI command registry for lazy loading."""

from __future__ import annotations

# command name -> (relative module path, attribute name, short help)
COMMANDS: dict[str, tuple[str, str, str]] = {
    "init": (".commands.init", "init", "Bootstrap an Octop server install."),
    "run": (".commands.run", "run", "Run octop-server in the foreground."),
    "service": (
        ".commands.service",
        "service",
        "System service lifecycle (start/stop/restart/status).",
    ),
    "config": (".commands.config", "config_group", "CLI defaults (pinned user/agent)."),
    "user": (".commands.user", "user", "User management commands (admin only)."),
    "agent": (".commands.agent", "agent", "Agent lifecycle commands."),
    "chats": (".commands.chats", "chats", "Chat REPL and session management."),
    "channel": (".commands.channel", "channel", "Channel management commands."),
    "cron": (".commands.cron", "cron", "Cron job management commands."),
    "provider": (".commands.provider", "provider", "Provider management (admin write)."),
    "models": (".commands.models", "models", "Provider presets and resolved models."),
    "skills": (".commands.skills", "skills", "Per-agent skill enable/disable."),
    "admin": (".commands.admin", "admin", "Admin commands."),
    "version": (".commands.version", "version", "Show the installed octop version."),
    "completion": (".commands.completion", "completion", "Shell completion utilities."),
    "update": (".commands.update", "update", "Check for and install a newer Octop release."),
    "clean": (".commands.clean", "clean", "Remove CLI state or wipe all of ~/.octop."),
    "backup": (".commands.backup", "backup", "Export and restore Octop backups."),
    "acp": (".commands.acp", "acp_cmd", "Run Octop agent as ACP server (stdio)."),
    "plugin": (".commands.plugin", "plugin", "Install and manage plugins."),
}
