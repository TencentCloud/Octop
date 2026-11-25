"""集群趋势：坏实例不该拖垮整批，空样本要能自动换一批。"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from octop.infra.cloud import tencent
from octop.infra.cloud.tencent import CloudCredential, query_cluster_trend


def _credential() -> CloudCredential:
    return CloudCredential(
        secret_id="AKIDtrend000000000",
        secret_key="sk",
        token="tk",
        expires_at=time.time() + 3600,
        access_token="at",
        access_expires_at=time.time() + 3600,
        refresh_token="rt",
        open_id="oid",
        site="cn",
    )


class _FakeMonitor:
    """按 instance_id 前缀决定：bad-* 报错，其余按 points 条数返回。"""

    def __init__(self, points: dict[str, int]) -> None:
        self.points = points
        self.calls: list[list[str]] = []

    def GetMonitorData(self, request: object) -> object:
        ids = [
            item["Dimensions"][0]["Value"]
            for item in request.Instances  # type: ignore[attr-defined]
        ]
        self.calls.append(ids)
        if any(instance_id.startswith("bad") for instance_id in ids):
            raise TencentCloudSDKException("InvalidParameterValue", "instance destroyed")
        data_points = []
        for instance_id in ids:
            count = self.points.get(instance_id, 0)
            if not count:
                continue
            stamps = [1_793_000_000 + index * 60 for index in range(count)]
            data_points.append(
                SimpleNamespace(
                    Dimensions=[SimpleNamespace(Name="InstanceId", Value=instance_id)],
                    Timestamps=stamps,
                    Values=[10.0 + index for index in range(count)],
                )
            )
        return SimpleNamespace(DataPoints=data_points)


def test_broken_instance_does_not_sink_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    monitor = _FakeMonitor({"good-a": 3, "good-b": 3})
    monkeypatch.setattr(tencent.monitor_client, "MonitorClient", lambda *_a, **_k: monitor)

    series = tencent._get_monitor_series(
        _credential(),
        region="ap-guangzhou",
        instance_ids=["good-a", "bad-x", "good-b"],
        metric="CpuUsage",
        start="2026-10-27T15:00:00+08:00",
        end="2026-10-27T16:00:00+08:00",
        period=60,
    )

    assert set(series) == {"good-a", "good-b"}
    # 整批失败后应二分降级，而不是整批丢弃
    assert any(len(call) < 3 for call in monitor.calls)


def test_trend_retries_next_batch_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    points = {f"ins-{index}": 0 for index in range(12)}
    points.update({f"ins-{index}": 61 for index in range(12, 24)})
    monitor = _FakeMonitor(points)
    monkeypatch.setattr(tencent.monitor_client, "MonitorClient", lambda *_a, **_k: monitor)

    targets = [{"region": "ap-guangzhou", "instance_id": f"ins-{index}"} for index in range(24)]
    trend = query_cluster_trend(
        _credential(), targets=targets, minutes=60, period=60, max_instances=12
    )

    assert len(trend["points"]) == 61
    assert trend["sampled"] >= 1
    assert trend["total"] == 24


def test_trend_keeps_sampling_until_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    # 前两批只有 2 个点（刚创建的实例），第三批才有完整 1 小时数据
    points = {f"ins-{index}": 2 for index in range(24)}
    points.update({f"ins-{index}": 61 for index in range(24, 36)})
    monitor = _FakeMonitor(points)
    monkeypatch.setattr(tencent.monitor_client, "MonitorClient", lambda *_a, **_k: monitor)

    targets = [{"region": "ap-guangzhou", "instance_id": f"ins-{index}"} for index in range(36)]
    trend = query_cluster_trend(
        _credential(), targets=targets, minutes=60, period=60, max_instances=12
    )

    assert len(trend["points"]) == 61
