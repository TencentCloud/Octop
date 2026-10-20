"""Tests for :class:`~octop_harness.backends.cos.CosBackend` delete helpers."""

from __future__ import annotations

import secrets
from unittest.mock import MagicMock

import pytest

from octop_harness.backends.cos_backend import CosBackend, CosConfig


def _test_credential() -> str:
    """Return a non-production credential value for configuration tests."""
    return secrets.token_urlsafe(24)


@pytest.fixture
def cos_backend() -> CosBackend:
    config = CosConfig(
        bucket="bucket-1250000000",
        region="ap-guangzhou",
        secret_id=_test_credential(),
        secret_key=_test_credential(),
        prefix="agent/ws",
    )
    client = MagicMock()
    backend = CosBackend(config, client=client)
    return backend


class TestCosDeletePath:
    def test_delete_path_single_object(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(  # type: ignore[method-assign]
            return_value={"content": "x", "encoding": "utf-8"}
        )
        cos_backend.delete_path("/notes.md")
        cos_backend._client.delete_object.assert_called_once()

    def test_delete_path_prefix_when_not_a_file(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(return_value=None)  # type: ignore[method-assign]
        cos_backend.delete_prefix = MagicMock(return_value=2)  # type: ignore[method-assign]
        cos_backend.delete_path("/nested")
        cos_backend.delete_prefix.assert_called_once_with("/nested")

    def test_delete_path_missing_raises(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(return_value=None)  # type: ignore[method-assign]
        cos_backend.delete_prefix = MagicMock(return_value=0)  # type: ignore[method-assign]
        with pytest.raises(FileNotFoundError):
            cos_backend.delete_path("/missing.txt")


class TestCosMovePath:
    def test_move_path_single_object(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(  # type: ignore[method-assign]
            side_effect=[None, {"content": "x", "encoding": "utf-8"}]
        )
        cos_backend._prefix_has_objects = MagicMock(return_value=False)  # type: ignore[method-assign]
        cos_backend._copy_object = MagicMock()  # type: ignore[method-assign]
        cos_backend.delete_object = MagicMock()  # type: ignore[method-assign]
        cos_backend.move_path("/src.md", "/dest.md")
        cos_backend._copy_object.assert_called_once_with("/src.md", "/dest.md")
        cos_backend.delete_object.assert_called_once_with("/src.md")

    def test_move_path_prefix(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(return_value=None)  # type: ignore[method-assign]
        cos_backend._prefix_has_objects = MagicMock(return_value=False)  # type: ignore[method-assign]
        cos_backend._move_prefix = MagicMock(return_value=2)  # type: ignore[method-assign]
        cos_backend.move_path("/nested", "/other")
        cos_backend._move_prefix.assert_called_once_with("/nested", "/other")

    def test_move_path_missing_raises(self, cos_backend: CosBackend) -> None:
        cos_backend._get_file_data = MagicMock(return_value=None)  # type: ignore[method-assign]
        cos_backend._prefix_has_objects = MagicMock(return_value=False)  # type: ignore[method-assign]
        cos_backend._move_prefix = MagicMock(return_value=0)  # type: ignore[method-assign]
        with pytest.raises(FileNotFoundError):
            cos_backend.move_path("/missing", "/dest")
