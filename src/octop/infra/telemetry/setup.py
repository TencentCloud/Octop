"""OpenTelemetry provider lifecycle (private provider; never the OTel global)."""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote

from octop.infra.telemetry.agent_names import AgentNameResolver, AgentNameSource
from octop.infra.telemetry.instruments import (
    ATTR_AGENT_ID,
    ATTR_AGENT_NAME,
    ATTR_ERROR_CODE,
    ATTR_ERROR_TYPE,
    ATTR_HTTP_METHOD,
    ATTR_HTTP_ROUTE,
    ATTR_HTTP_STATUS,
    ATTR_OPERATION_NAME,
    ATTR_PROVIDER_NAME,
    ATTR_REQUEST_MODEL,
    ATTR_RESPONSE_MODEL,
    ATTR_SOURCE,
    ATTR_TOKEN_MODALITY,
    ATTR_URL_SCHEME,
    COUNTER_LABELS,
    MODALITY_UNKNOWN,
    OPERATION_CHAT,
    OPERATION_INVOKE_AGENT,
    Instruments,
    build_instruments,
)
from octop.infra.telemetry.providers import ProviderNameResolver, ProviderSource

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import MetricReader
    from opentelemetry.sdk.resources import Resource

logger = logging.getLogger(__name__)

_DEFAULT_SERVICE_NAME = "octop"
_SHUTDOWN_TIMEOUT_MS = 5000
_ENDPOINT_VARS = ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")

_provider: MeterProvider | None = None
_instruments_state: Instruments | None = None
_agent_names: AgentNameResolver | None = None
_provider_names: ProviderNameResolver | None = None
_active_agents: Callable[[], int] | None = None


def _instruments() -> Instruments | None:
    return _instruments_state


def is_active() -> bool:
    return _provider is not None


def octop_version() -> str:
    from octop import __version__  # noqa: PLC0415

    return __version__


def _unsupported_config(env: Mapping[str, str]) -> str | None:
    """Return why *env* asks for something this build cannot export, else ``None``."""
    exporters = [v.strip().lower() for v in env.get("OTEL_METRICS_EXPORTER", "").split(",")]
    exporters = [v for v in exporters if v]
    if exporters and exporters != ["otlp"] and exporters != ["none"]:
        return f"OTEL_METRICS_EXPORTER={env['OTEL_METRICS_EXPORTER']!r} (only otlp or none)"
    for name in ("OTEL_EXPORTER_OTLP_METRICS_PROTOCOL", "OTEL_EXPORTER_OTLP_PROTOCOL"):
        protocol = (env.get(name) or "").strip().lower()
        if protocol and protocol != "http/protobuf":
            return f"{name}={env[name]!r} (only http/protobuf)"
    return None


def _parse_resource_attributes(raw: str) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for pair in raw.split(","):
        key, sep, value = pair.partition("=")
        if sep and key.strip():
            attributes[key.strip()] = unquote(value.strip())
    return attributes


def _build_resource(env: Mapping[str, str]) -> Resource:
    """Env wins over the ``octop`` default (explicit attributes override SDK env detectors)."""
    from opentelemetry.sdk.resources import Resource  # noqa: PLC0415

    attributes = _parse_resource_attributes(env.get("OTEL_RESOURCE_ATTRIBUTES", ""))
    service_name = (
        env.get("OTEL_SERVICE_NAME") or attributes.get("service.name") or _DEFAULT_SERVICE_NAME
    )
    attributes["service.name"] = service_name
    attributes.setdefault("service.version", octop_version())
    return Resource.create(attributes)


def _make_reader() -> MetricReader:
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (  # noqa: PLC0415
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader  # noqa: PLC0415

    return PeriodicExportingMetricReader(OTLPMetricExporter())


def _read_active_agents() -> int:
    fn = _active_agents
    return int(fn()) if fn is not None else 0


def bind_agent_repo(source: AgentNameSource | None) -> None:
    """Bind (or clear, with ``None``) the agents repo used to resolve ``gen_ai.agent.name``."""
    global _agent_names
    _agent_names = AgentNameResolver(source) if source is not None else None


def bind_provider_repo(source: ProviderSource | None) -> None:
    """Bind (or clear) the providers repo used to resolve ``gen_ai.provider.name``."""
    global _provider_names
    _provider_names = ProviderNameResolver(source) if source is not None else None


def bind_active_agents(fn: Callable[[], int] | None) -> None:
    """Bind (or clear) the callable behind the ``octop.agent.active`` gauge."""
    global _active_agents
    _active_agents = fn


def _positive(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def record_counter(name: str, n: int = 1, **labels: str) -> None:
    """Add *n* to the counter for a ``Metrics`` field name. No-op when inactive or unknown.

    ``labels`` use the ``COUNTER_LABELS`` keywords (``channel_type``, ``error_type``);
    blank or unknown ones are dropped.
    """
    instruments = _instruments_state
    if instruments is None:
        return
    counter = instruments.counters.get(name)
    if counter is None:
        return
    attributes = {COUNTER_LABELS[k]: v for k, v in labels.items() if v and k in COUNTER_LABELS}
    with contextlib.suppress(Exception):
        counter.add(n, attributes)


def _agent_attributes(agent_id: str, source: str, operation: str) -> dict[str, str]:
    attributes: dict[str, str] = {ATTR_OPERATION_NAME: operation, ATTR_SOURCE: source}
    if agent_id:
        attributes[ATTR_AGENT_ID] = agent_id
    resolver = _agent_names
    name = resolver.name_for(agent_id) if resolver is not None else ""
    if name:
        attributes[ATTR_AGENT_NAME] = name
    return attributes


def record_agent_invocation(
    *,
    agent_id: str,
    source: str,
    duration_s: float,
    error_type: str = "",
    error_code: str = "",
) -> None:
    """Record one agent turn's wall-clock duration. No-op when inactive; never raises."""
    instruments = _instruments_state
    if instruments is None or not duration_s >= 0:
        return
    try:
        attributes = _agent_attributes(agent_id, source, OPERATION_INVOKE_AGENT)
        if error_type:
            attributes[ATTR_ERROR_TYPE] = error_type
        if error_code:
            attributes[ATTR_ERROR_CODE] = error_code
        instruments.agent_duration.record(duration_s, attributes)
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        return


_HTTP_METHODS = frozenset(
    {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)


def record_http_request(
    *,
    method: str,
    scheme: str,
    duration_s: float,
    route: str = "",
    status_code: int | None = None,
    error_type: str = "",
) -> None:
    """Record one HTTP server request. ``route`` is the route *template* (never the raw path).

    Unknown methods collapse to ``_OTHER``; blank/unknown route, status and error are
    omitted. No-op when inactive; never raises.
    """
    instruments = _instruments_state
    if instruments is None or not duration_s >= 0:
        return
    try:
        upper = method.upper()
        attributes: dict[str, Any] = {
            ATTR_HTTP_METHOD: upper if upper in _HTTP_METHODS else "_OTHER",
            ATTR_URL_SCHEME: scheme or "http",
        }
        if route:
            attributes[ATTR_HTTP_ROUTE] = route
        if status_code is not None:
            attributes[ATTR_HTTP_STATUS] = int(status_code)
        if error_type:
            attributes[ATTR_ERROR_TYPE] = error_type
        instruments.http_duration.record(duration_s, attributes)
    except Exception:  # noqa: BLE001 - telemetry must never break a request
        return


def record_turn_started(agent_id: str, source: str) -> dict[str, str] | None:
    """Count one in-flight turn; return the attributes to hand back to ``record_turn_ended``.

    ``None`` when telemetry is inactive. The attributes are captured once so the
    matching decrement lands on the same series even if the agent is renamed mid-turn.
    """
    instruments = _instruments_state
    if instruments is None:
        return None
    try:
        attributes = _agent_attributes(agent_id, source, OPERATION_INVOKE_AGENT)
        instruments.turn_active.add(1, attributes)
        return attributes
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        return None


def record_turn_ended(attributes: dict[str, str] | None) -> None:
    """Undo ``record_turn_started``. No-op for ``None``; never raises."""
    instruments = _instruments_state
    if instruments is None or attributes is None:
        return
    try:
        instruments.turn_active.add(-1, attributes)
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        return


def record_first_token(*, agent_id: str, source: str, latency_s: float) -> None:
    """Record time from turn start to the first visible text token. Never raises."""
    instruments = _instruments_state
    if instruments is None or not latency_s >= 0:
        return
    try:
        attributes = _agent_attributes(agent_id, source, OPERATION_INVOKE_AGENT)
        instruments.turn_first_token.record(latency_s, attributes)
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        return


def record_inference_usage(
    *,
    agent_id: str,
    source: str,
    provider: str,
    request_model: str,
    response_model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> None:
    """Record one model call's token usage. No-op when inactive; never raises.

    ``provider`` is the Octop provider name (mapped to ``gen_ai.provider.name``);
    empty values omit the matching attribute.
    """
    instruments = _instruments_state
    if instruments is None:
        return
    try:
        attributes = _agent_attributes(agent_id, source, OPERATION_CHAT)
        resolver = _provider_names
        provider_name = resolver.name_for(provider) if resolver is not None else provider
        if provider_name:
            attributes[ATTR_PROVIDER_NAME] = provider_name
        if request_model:
            attributes[ATTR_REQUEST_MODEL] = request_model
        if response_model:
            attributes[ATTR_RESPONSE_MODEL] = response_model
        counted = {**attributes, ATTR_TOKEN_MODALITY: MODALITY_UNKNOWN}
        for counter, count in (
            (instruments.usage_input, input_tokens),
            (instruments.usage_output, output_tokens),
            (instruments.usage_cache_read, cache_read_tokens),
            (instruments.usage_cache_write, cache_write_tokens),
        ):
            if _positive(count):
                counter.add(count, counted)
        if _positive(reasoning_tokens):
            instruments.usage_reasoning.add(reasoning_tokens, attributes)
        for histogram, count in (
            (instruments.operation_input, input_tokens),
            (instruments.operation_output, output_tokens),
        ):
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
                histogram.record(count, attributes)
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        return


def init_telemetry(
    *,
    environ: Mapping[str, str] | None = None,
    reader: MetricReader | None = None,
) -> bool:
    """Start metric export when configured. Returns True iff telemetry is active."""
    global _provider, _instruments_state
    if _provider is not None:
        return True
    env = os.environ if environ is None else environ
    if env.get("OTEL_SDK_DISABLED", "").strip().lower() == "true":
        return False
    if [v.strip().lower() for v in env.get("OTEL_METRICS_EXPORTER", "").split(",")] == ["none"]:
        return False
    unsupported = _unsupported_config(env)
    if unsupported is not None:
        logger.warning("OpenTelemetry metrics disabled: unsupported %s", unsupported)
        return False
    has_endpoint = any((env.get(name) or "").strip() for name in _ENDPOINT_VARS)
    if reader is None and not has_endpoint:
        return False
    provider: MeterProvider | None = None
    try:
        from opentelemetry.sdk.metrics import MeterProvider  # noqa: PLC0415

        metric_reader = reader if reader is not None else _make_reader()
        provider = MeterProvider(metric_readers=[metric_reader], resource=_build_resource(env))
        instruments = build_instruments(
            provider.get_meter("octop", version=octop_version()), _read_active_agents
        )
    except Exception as exc:  # noqa: BLE001 - a bad OTEL_* value must not stop Octop booting
        logger.warning("OpenTelemetry metrics disabled: invalid configuration (%s)", exc)
        if provider is not None:
            with contextlib.suppress(Exception):
                provider.shutdown(timeout_millis=_SHUTDOWN_TIMEOUT_MS)
        return False
    _instruments_state = instruments
    _provider = provider
    return True


def shutdown_telemetry() -> None:
    """Flush and stop the provider, then clear all state. Safe when inactive."""
    global _provider, _instruments_state, _agent_names, _provider_names, _active_agents
    provider, _provider = _provider, None
    _instruments_state = None
    try:
        if provider is not None:
            # ``shutdown`` performs a final export (which still reads the bindings);
            # bound the wait so a dead collector cannot stall ``octop`` shutdown for
            # the exporter's full retry window.
            with contextlib.suppress(Exception):
                provider.shutdown(timeout_millis=_SHUTDOWN_TIMEOUT_MS)
    finally:
        _agent_names = None
        _provider_names = None
        _active_agents = None
