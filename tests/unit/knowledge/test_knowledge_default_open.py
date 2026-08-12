"""Unit tests for knowledge-base turn selection defaults."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.knowledge.default_open import merge_knowledge_base_ids


def test_merge_knowledge_base_ids_applies_only_visible_defaults_when_omitted() -> None:
    visible = [
        SimpleNamespace(id="default", default_open=True, shared=False),
        SimpleNamespace(id="optional", default_open=False, shared=False),
    ]

    assert merge_knowledge_base_ids(visible, None) == ["default"]
    assert merge_knowledge_base_ids(visible, []) == []
    assert merge_knowledge_base_ids(visible, ["optional", "unknown"]) == ["optional", "unknown"]


def test_merge_knowledge_base_ids_skips_shared_default_open() -> None:
    visible = [
        SimpleNamespace(id="mine", default_open=True, shared=False),
        SimpleNamespace(id="shared-default", default_open=True, shared=True),
    ]

    assert merge_knowledge_base_ids(visible, None) == ["mine"]
