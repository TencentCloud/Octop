"""The best-effort host read must not raise for a malformed path."""

from __future__ import annotations

import asyncio

from octop.infra.gateway.media.backend_files import _read_host_file_bytes


def test_a_nul_byte_path_is_a_miss_not_an_exception():
    # Path.read_bytes raises ValueError("embedded null byte") for this, not OSError.
    assert asyncio.run(_read_host_file_bytes("/tmp/definitely\x00missing")) is None


def test_a_missing_file_is_a_miss():
    assert asyncio.run(_read_host_file_bytes("/tmp/definitely-not-here-12345")) is None
