"""list_instances / list_regions: 并发拉取 + 短缓存。"""

from __future__ import annotations

import time

import pytest

from octop.infra.cloud import tencent
from octop.infra.cloud.tencent import CloudCredential, list_instances, list_regions


def _credential(secret_id: str = "AKIDcatalog000000") -> CloudCredential:
    return CloudCredential(
        secret_id=secret_id,
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
def clean_caches() -> None:
    tencent._INSTANCE_CACHE.clear()
    tencent._REGION_CACHE.clear()


def test_instances_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_region(_credential: CloudCredential, region: str) -> list[dict[str, object]]:
        calls.append(region)
        return [{"instance_id": f"ins-{region}", "region": region}]

    monkeypatch.setattr(tencent, "_list_region_instances", fake_region)
    regions = ["ap-guangzhou", "ap-beijing"]

    first = list_instances(_credential(), regions)
    second = list_instances(_credential(), regions)

    assert len(first["instances"]) == 2
    assert first["cached"] is False
    assert second["cached"] is True
    assert len(calls) == 2  # 第二轮没有再多打地域


def test_instances_nocache_refetches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_region(_credential: CloudCredential, region: str) -> list[dict[str, object]]:
        calls.append(region)
        return []

    monkeypatch.setattr(tencent, "_list_region_instances", fake_region)
    list_instances(_credential(), ["ap-guangzhou"])
    list_instances(_credential(), ["ap-guangzhou"], nocache=True)

    assert len(calls) == 2


def test_instances_fetched_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow_region(_credential: CloudCredential, region: str) -> list[dict[str, object]]:
        time.sleep(0.2)
        return []

    monkeypatch.setattr(tencent, "_list_region_instances", slow_region)
    regions = [f"ap-region-{index}" for index in range(8)]

    started = time.perf_counter()
    list_instances(_credential(), regions)
    elapsed = time.perf_counter() - started

    # 串行需要 1.6s；并发上限 8 个 worker 应接近 0.2~0.5s
    assert elapsed < 0.9, f"地域拉取没有并发，耗时 {elapsed:.2f}s"


def test_instances_empty_regions_skips_api() -> None:
    result = list_instances(_credential(), [])
    assert result["instances"] == []
    assert result["cached"] is False


def test_cache_keyed_by_account(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_region(_credential: CloudCredential, region: str) -> list[dict[str, object]]:
        return [{"instance_id": "x", "region": region}]

    monkeypatch.setattr(tencent, "_list_region_instances", fake_region)
    list_instances(_credential("AKID-a"), ["ap-guangzhou"])
    other = list_instances(_credential("AKID-b"), ["ap-guangzhou"])

    assert other["cached"] is False


def test_regions_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    class FakeResponse:
        RegionSet = [
            type(
                "R",
                (),
                {"Region": "ap-guangzhou", "RegionName": "广州", "RegionState": "AVAILABLE"},
            )()
        ]

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def DescribeRegions(self, _request: object) -> FakeResponse:
            calls.append(1)
            return FakeResponse()

    monkeypatch.setattr(tencent.cvm_client, "CvmClient", FakeClient)
    regions = list_regions(_credential())
    again = list_regions(_credential())

    assert regions == [{"id": "ap-guangzhou", "name": "广州"}]
    assert again == regions
    assert len(calls) == 1


def test_one_region_failure_does_not_blank_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
        TencentCloudSDKException,
    )

    class FakeClient:
        def __init__(self, _cred, region: str, _profile: object) -> None:
            self.region = region

        def DescribeInstances(self, _request: object) -> object:
            if self.region == "ap-broken":
                raise TencentCloudSDKException("RequestLimitExceeded")
            return type(
                "R",
                (),
                {
                    "InstanceSet": [
                        type(
                            "I",
                            (),
                            {
                                "InstanceId": f"ins-{self.region}",
                                "InstanceName": "n",
                                "Placement": None,
                                "InstanceState": "RUNNING",
                                "OsName": "linux",
                                "PrivateIpAddresses": ["10.0.0.1"],
                                "PublicIpAddresses": [],
                                "CreatedTime": "",
                                "CPU": 2,
                                "Memory": 4,
                            },
                        )()
                    ],
                    "TotalCount": 1,
                },
            )()

    monkeypatch.setattr(tencent.cvm_client, "CvmClient", FakeClient)
    monkeypatch.setattr(tencent.time, "sleep", lambda _s: None)

    result = list_instances(_credential(), ["ap-guangzhou", "ap-broken"])

    assert [row["instance_id"] for row in result["instances"]] == ["ins-ap-guangzhou"]
