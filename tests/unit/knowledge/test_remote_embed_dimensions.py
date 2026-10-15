"""A remote embedding response must have one nonzero width for every item."""

from __future__ import annotations

import pytest

from octop.infra.knowledge import embed


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _Client:
    def __init__(self, widths):
        self._widths = widths

    def post(self, url, headers=None, json=None):  # noqa: A002 - mirrors httpx
        batch = json["input"]
        data = [{"embedding": [0.1] * self._widths.pop(0)} for _ in batch]
        return _Resp({"data": data})


def _run(widths, texts):
    return embed._embed_remote_batched(
        client=_Client(widths),
        base="https://embed.invalid",
        headers={},
        model="m",
        texts=texts,
    )


def test_mixed_widths_within_one_batch_are_rejected():
    with pytest.raises(RuntimeError):
        _run([2, 3], ["a", "b"])


def test_mixed_widths_across_batches_are_rejected():
    texts = [f"t{i}" for i in range(21)]  # one more than the batch limit
    with pytest.raises(RuntimeError):
        _run([2] * 20 + [3], texts)


def test_empty_vectors_are_rejected():
    with pytest.raises(RuntimeError):
        _run([0, 0], ["a", "b"])


def test_uniform_widths_still_pass_through_in_order():
    vectors = _run([3, 3], ["a", "b"])

    assert [len(vector) for vector in vectors] == [3, 3]
