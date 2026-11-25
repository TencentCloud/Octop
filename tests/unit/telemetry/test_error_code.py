"""``octop.error.code``: the specific Octop error behind a generic exception type."""

from __future__ import annotations

import enum

import pytest

from octop.infra.errors import ErrorCode, OctopError
from octop.infra.gateway.process.usage_record import TurnMeter
from octop.infra.metrics import Metrics
from octop.infra.telemetry import error_code
from tests.support.otel import active_telemetry, metric_points


def test_error_code_reads_the_octop_error_code() -> None:
    assert error_code(OctopError(ErrorCode.TOKEN_QUOTA_EXCEEDED, "over")) == "TOKEN_QUOTA_EXCEEDED"


class _IntCode(Exception):
    code = 404


class _Other(enum.Enum):
    A = 1


class _EnumIntCode(Exception):
    code = _Other.A


@pytest.mark.parametrize(
    "exc", [None, ValueError("x"), _IntCode(), _EnumIntCode(), KeyboardInterrupt()]
)
def test_error_code_is_blank_for_everything_else(exc: BaseException | None) -> None:
    assert error_code(exc) == ""


def test_counters_carry_error_code_and_drop_blank() -> None:
    m = Metrics()
    with active_telemetry() as reader:
        m.inc("stream_errors_total", error_type="octop.infra.errors.OctopError", error_code="X_Y")
        m.inc("cron_errors_total", error_type="ValueError", error_code="")
        (stream,) = metric_points(reader, "octop.stream.errors")
        (cron,) = metric_points(reader, "octop.cron.errors")
    assert stream.attributes["octop.error.code"] == "X_Y"
    assert stream.attributes["error.type"] == "octop.infra.errors.OctopError"
    assert "octop.error.code" not in cron.attributes


def test_failed_turn_duration_carries_error_code() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        meter.start()
        meter.finish(OctopError(ErrorCode.TOKEN_QUOTA_EXCEEDED, "over"))
        (point,) = metric_points(reader, "gen_ai.invoke_agent.duration")
    assert point.attributes["error.type"] == "octop.infra.errors.OctopError"
    assert point.attributes["octop.error.code"] == "TOKEN_QUOTA_EXCEEDED"


def test_non_octop_failure_has_no_error_code() -> None:
    with active_telemetry() as reader:
        meter = TurnMeter("a1")
        meter.finish(TimeoutError("slow"))
        (point,) = metric_points(reader, "gen_ai.invoke_agent.duration")
    assert point.attributes["error.type"] == "TimeoutError"
    assert "octop.error.code" not in point.attributes
