"""Octop infrastructure — all domain logic and utilities.

Sub-packages:
    agents   — agent factory, runtime, manager, MBTI personas, expert templates
    channels — IM channels, processor, slash commands
    cron     — CronJob, CronManager, trigger parsing
    db       — SqlitePool, SQL migrations, Repo classes, RepoBundle
    users    — User/Role/UserToken identity, manager, password

Top-level modules:
    config          — OctopConfig from env vars
    errors          — project-wide exception hierarchy
    server          — OctopServer process orchestrator
    shared          — SharedServices DI container
    paths           — filesystem layout helpers (~/.octop/...)
    ulid            — monotonic ULID generator
    metrics         — process-wide thread-safe in-memory counters
    ollama_manager  — Ollama local model manager
"""

from __future__ import annotations
