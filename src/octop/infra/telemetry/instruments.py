"""Instrument names, attribute keys and the instrument container."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from opentelemetry.metrics import CallbackOptions, Counter, Histogram, Meter, Observation

# --- GenAI semantic conventions (semantic-conventions-genai v0.1.0, Development) ---
# Keep every convention-defined name in this block.
USAGE_INPUT_TOKENS = "gen_ai.client.inference.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.client.inference.usage.output_tokens"
USAGE_CACHE_READ_TOKENS = "gen_ai.client.inference.usage.cache_read.input_tokens"
USAGE_CACHE_WRITE_TOKENS = "gen_ai.client.inference.usage.cache_write.input_tokens"
USAGE_REASONING_TOKENS = "gen_ai.client.inference.usage.reasoning.output_tokens"
OPERATION_INPUT_TOKENS = "gen_ai.client.inference.operation.input_tokens"
OPERATION_OUTPUT_TOKENS = "gen_ai.client.inference.operation.output_tokens"
INVOKE_AGENT_DURATION = "gen_ai.invoke_agent.duration"

ATTR_OPERATION_NAME = "gen_ai.operation.name"
ATTR_PROVIDER_NAME = "gen_ai.provider.name"
ATTR_TOKEN_MODALITY = "gen_ai.token.modality"
ATTR_REQUEST_MODEL = "gen_ai.request.model"
ATTR_RESPONSE_MODEL = "gen_ai.response.model"
ATTR_AGENT_ID = "gen_ai.agent.id"
ATTR_AGENT_NAME = "gen_ai.agent.name"
ATTR_ERROR_TYPE = "error.type"
OPERATION_CHAT = "chat"
OPERATION_INVOKE_AGENT = "invoke_agent"
MODALITY_UNKNOWN = "unknown"

# --- Octop-specific (non-spec) names ---
ATTR_SOURCE = "octop.usage.source"
ATTR_CHANNEL_TYPE = "octop.channel.type"
AGENTS_ACTIVE = "octop.agent.active"

# ``Metrics`` field name -> (instrument name, unit)
COUNTER_NAMES: dict[str, tuple[str, str]] = {
    "messages_total": ("octop.messages", "{message}"),
    "stream_errors_total": ("octop.stream.errors", "{error}"),
    "cron_runs_total": ("octop.cron.runs", "{run}"),
    "cron_errors_total": ("octop.cron.errors", "{error}"),
}

# ``Metrics.inc`` keyword label -> metric attribute key
COUNTER_LABELS: dict[str, str] = {
    "channel_type": ATTR_CHANNEL_TYPE,
    "error_type": ATTR_ERROR_TYPE,
}

# Recommended bucket boundaries for ``gen_ai.invoke_agent.duration`` (seconds).
INVOKE_AGENT_DURATION_BUCKETS: list[float] = [
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
    30,
    60,
    120,
    300,
    600,
    1800,
    3600,
    7200,
    21600,
    43200,
    86400,
]

# Recommended bucket boundaries for ``gen_ai.client.inference.operation.*_tokens``.
TOKEN_BUCKETS: list[float] = [
    1,
    4,
    16,
    64,
    256,
    1024,
    4096,
    16384,
    65536,
    262144,
    1048576,
    4194304,
    16777216,
    67108864,
]


@dataclass(frozen=True)
class Instruments:
    usage_input: Counter
    usage_output: Counter
    usage_cache_read: Counter
    usage_cache_write: Counter
    usage_reasoning: Counter
    operation_input: Histogram
    operation_output: Histogram
    agent_duration: Histogram
    counters: dict[str, Counter]


def build_instruments(meter: Meter, active_agents: Callable[[], int]) -> Instruments:
    """Create every instrument on *meter*; the gauge reads *active_agents* on collect."""

    def _observe_active_agents(_options: CallbackOptions) -> Iterable[Observation]:
        try:
            yield Observation(int(active_agents()))
        except Exception:  # noqa: BLE001 - a gauge callback must never break collection
            return

    meter.create_observable_gauge(
        AGENTS_ACTIVE,
        callbacks=[_observe_active_agents],
        unit="{agent}",
        description="Enabled agents.",
    )

    def _counter(name: str, description: str) -> Counter:
        return meter.create_counter(name, unit="{token}", description=description)

    return Instruments(
        usage_input=_counter(
            USAGE_INPUT_TOKENS, "The number of input (prompt) tokens used, including cached tokens."
        ),
        usage_output=_counter(
            USAGE_OUTPUT_TOKENS,
            "The number of output (completion) tokens used, including reasoning tokens.",
        ),
        usage_cache_read=_counter(
            USAGE_CACHE_READ_TOKENS,
            "The number of input tokens served from a provider-managed cache.",
        ),
        usage_cache_write=_counter(
            USAGE_CACHE_WRITE_TOKENS,
            "The number of input tokens written to a provider-managed cache.",
        ),
        usage_reasoning=_counter(
            USAGE_REASONING_TOKENS, "The number of output tokens used for reasoning."
        ),
        operation_input=meter.create_histogram(
            OPERATION_INPUT_TOKENS,
            unit="{token}",
            description="The number of input (prompt) tokens used per inference operation.",
            explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
        ),
        operation_output=meter.create_histogram(
            OPERATION_OUTPUT_TOKENS,
            unit="{token}",
            description="The number of output (completion) tokens used per inference operation.",
            explicit_bucket_boundaries_advisory=TOKEN_BUCKETS,
        ),
        agent_duration=meter.create_histogram(
            INVOKE_AGENT_DURATION,
            unit="s",
            description="The end-to-end duration of a single agent invocation (one turn).",
            explicit_bucket_boundaries_advisory=INVOKE_AGENT_DURATION_BUCKETS,
        ),
        counters={
            field: meter.create_counter(name, unit=unit, description=f"Octop {field}.")
            for field, (name, unit) in COUNTER_NAMES.items()
        },
    )
