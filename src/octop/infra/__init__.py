"""Octop infrastructure — domain logic and utilities.

Sub-packages (see ``AGENTS.md`` §5 for ownership boundaries):
    agents      — AgentManager, providers, settings, workspace, threads, experts, …
    auth        — captcha + SSO
    backend     — storage backend resolution / probe
    backup      — system / workspace / chat backup
    browser     — local browser environment setup
    connectors  — connector catalog, OAuth, MCP builder
    cron        — scheduled jobs
    db          — pools, migrations, repos, SharedServices
    desktop     — remote desktop capture / input
    gateway     — IM / dashboard ingress, threads, slash, media, HITL
    history     — versioned messages, trajectory, turn projection
    knowledge   — knowledge bases
    mobile      — Android remote
    proactive   — proactive care scheduler
    setup       — first-run wizard, OS service, TLS, self-update
    skills      — skill packages + SkillHub HTTP client
    users       — identity and UserManager
    utils       — leaf helpers (paths, ulid, locale, …)
    voice       — STT / TTS

Top-level modules:
    errors   — OctopError / ErrorCode
    metrics  — in-process counters
    server   — OctopServer process orchestrator
"""

from __future__ import annotations
