"""query_metrics: 延迟补偿窗口 + 短缓存 + 并发取数。"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest

from octop.infra.cloud import tencent
from octop.infra.cloud.tencent import CloudCredential, query_metrics

CST = timezone(timedelta(hours=8))


def _credential() -> CloudCredential:
    return CloudCredential(
        secret_id="AKIDcache0000000000",
        secret_key="sk",
        token="tk",
        expires_at=time.time() + 3600,
        access_token="at",
        access_expires_at=time.time() + 3600,
        refresh_token="rt",
        open_id="oid",
        site="cn",
    )


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    tencent._METRIC_CACHE.clear()


def test_monitor_pairs_skip_nulls() -> None:
    assert tencent._monitor_pairs([10, 20, 30, 40], [1.5, None, "bad", 4]) == [
        (10, 1.5),
        (40, 4.0),
    ]
    assert tencent._monitor_pairs([10], [None]) == []


def test_time_window_applies_lag() -> None:
    start, end = tencent._time_window(60, tencent.METRIC_LAG_S)
    parsed_end = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S%z")
    parsed_start = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S%z")

    drift = (datetime.now(CST) - parsed_end).total_seconds()
    assert 110 <= drift <= 130, f"窗口末端应回退约 120s，实际 {drift:.0f}s"
    assert (parsed_end - parsed_start).total_seconds() == pytest.approx(3600, abs=2)


def test_cache_hit_skips_second_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(*_args: object, key: str, **_kwargs: object):
        calls.append(key)
        return key, [{"t": int(time.time()), "v": 1.0}]

    monkeypatch.setattr(tencent, "_fetch_metric_series", fake_fetch)
    kwargs = {"region": "ap-guangzhou", "instance_id": "ins-cache", "minutes": 60, "period": 60}

    first = query_metrics(_credential(), **kwargs)
    second = query_metrics(_credential(), **kwargs)

    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == len(tencent._METRICS)  # 只打了一轮
    assert set(first["series"]) == set(tencent._METRICS)


def test_nocache_bypasses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(*_args: object, key: str, **_kwargs: object):
        calls.append(key)
        return key, []

    monkeypatch.setattr(tencent, "_fetch_metric_series", fake_fetch)
    kwargs = {"region": "ap-guangzhou", "instance_id": "ins-nocache", "minutes": 60, "period": 60}

    query_metrics(_credential(), **kwargs)
    query_metrics(_credential(), nocache=True, **kwargs)

    assert len(calls) == len(tencent._METRICS) * 2


def test_expired_cache_refetches(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_args: object, key: str, **_kwargs: object):
        return key, []

    monkeypatch.setattr(tencent, "_fetch_metric_series", fake_fetch)
    kwargs = {"region": "ap-guangzhou", "instance_id": "ins-ttl", "minutes": 60, "period": 60}
    query_metrics(_credential(), **kwargs)

    stamp, payload = next(iter(tencent._METRIC_CACHE.values()))
    tencent._METRIC_CACHE[next(iter(tencent._METRIC_CACHE))] = (
        stamp - tencent.METRIC_CACHE_TTL_S - 1,
        payload,
    )

    again = query_metrics(_credential(), **kwargs)
    assert again["cached"] is False


def test_cache_is_per_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_args: object, key: str, instance_id: str = "", **_kwargs: object):
        return key, [{"t": 1, "v": float(len(instance_id))}]

    monkeypatch.setattr(tencent, "_fetch_metric_series", fake_fetch)
    a = query_metrics(_credential(), region="ap-guangzhou", instance_id="ins-a")
    b = query_metrics(_credential(), region="ap-guangzhou", instance_id="ins-b")

    assert a["instance_id"] == "ins-a"
    assert b["instance_id"] == "ins-b"
    assert b["cached"] is False


def test_cache_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(*_args: object, key: str, **_kwargs: object):
        return key, []

    monkeypatch.setattr(tencent, "_fetch_metric_series", fake_fetch)
    for index in range(tencent.METRIC_CACHE_MAX + 8):
        query_metrics(_credential(), region="ap-guangzhou", instance_id=f"ins-{index}")

    assert len(tencent._METRIC_CACHE) <= tencent.METRIC_CACHE_MAX
