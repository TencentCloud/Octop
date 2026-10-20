"""Tests for cos_spec_to_s3_compat and S3 spec alias normalization."""

from __future__ import annotations

import pytest

from octop_harness.backends.s3_backend import (
    S3Config,
    cos_spec_to_s3_compat,
    normalize_s3_spec_kwargs,
)


def test_cos_spec_to_s3_compat() -> None:
    spec = {
        "type": "cos",
        "bucket": "b-125",
        "region": "ap-guangzhou",
        "secret_id": "AKID",
        "secret_key": "SECRET",
        "prefix": "agents/",
    }
    out = cos_spec_to_s3_compat(spec)
    assert out is not None
    assert out["type"] == "s3"
    assert out["bucket"] == "b-125"
    assert out["endpoint_url"] == "https://cos.ap-guangzhou.myqcloud.com"
    assert out["prefix"] == "agents/"


def test_cos_spec_to_s3_compat_non_cos() -> None:
    assert cos_spec_to_s3_compat({"type": "filesystem", "root_dir": "/tmp"}) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"s3_force_path_style": True}, {"addressing_style": "path"}),
        ({"force_path_style": True}, {"addressing_style": "path"}),
        ({"path_style": True}, {"addressing_style": "path"}),
        ({"path_style": False}, {"addressing_style": "virtual"}),
        (
            {"path_style": True, "addressing_style": "virtual"},
            {"addressing_style": "virtual"},
        ),
        ({"bucket": "b"}, {"bucket": "b"}),
    ],
)
def test_normalize_s3_spec_kwargs(raw: dict[str, object], expected: dict[str, object]) -> None:
    out = normalize_s3_spec_kwargs(raw)
    for alias in ("s3_force_path_style", "force_path_style", "path_style"):
        assert alias not in out
    assert out == expected


def test_s3_config_from_kwargs_translates_path_style() -> None:
    config = S3Config.from_kwargs(
        bucket="b",
        access_key_id="AK",
        secret_access_key="SK",
        s3_force_path_style=True,
        previewable=True,
    )
    assert config.addressing_style == "path"
    assert config.extra == {"previewable": True}
