"""Unit tests for knowledge-base turn selection defaults."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.knowledge.default_open import merge_knowledge_base_ids


def test_merge_knowledge_base_ids_applies_only_visible_defaults_when_omitted() -> None:
    visible = [
        SimpleNamespace(id="default", owner_user_id=1, default_open=True, shared=False),
        SimpleNamespace(id="optional", owner_user_id=1, default_open=False, shared=False),
    ]

    assert merge_knowledge_base_ids(visible, None, owner_user_id=1) == ["default"]
    assert merge_knowledge_base_ids(visible, [], owner_user_id=1) == []
    assert merge_knowledge_base_ids(visible, ["optional", "unknown"], owner_user_id=1) == [
        "optional",
        "unknown",
    ]


def test_merge_knowledge_base_ids_default_open_only_for_owner() -> None:
    visible = [
        SimpleNamespace(id="mine", owner_user_id=1, default_open=True, shared=False),
        SimpleNamespace(id="shared-default", owner_user_id=2, default_open=True, shared=True),
        SimpleNamespace(id="shared-opt", owner_user_id=2, default_open=False, shared=True),
    ]

    assert merge_knowledge_base_ids(visible, None, owner_user_id=1) == ["mine"]
    assert merge_knowledge_base_ids(visible, None, owner_user_id=2) == ["shared-default"]
