"""OpenTelemetry metrics export (OTLP). Off unless an endpoint is configured."""

from __future__ import annotations

from octop.infra.telemetry.errors import error_code, exception_type
from octop.infra.telemetry.setup import (
    bind_active_agents,
    bind_agent_repo,
    bind_provider_repo,
    init_telemetry,
    is_active,
    record_agent_invocation,
    record_counter,
    record_first_token,
    record_http_request,
    record_inference_usage,
    record_turn_ended,
    record_turn_started,
    shutdown_telemetry,
)

__all__ = [
    "bind_active_agents",
    "bind_agent_repo",
    "bind_provider_repo",
    "error_code",
    "exception_type",
    "init_telemetry",
    "is_active",
    "record_agent_invocation",
    "record_counter",
    "record_first_token",
    "record_http_request",
    "record_inference_usage",
    "record_turn_ended",
    "record_turn_started",
    "shutdown_telemetry",
]
