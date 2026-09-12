"""Unit tests for knowledge-base turn selection defaults."""

from __future__ import annotations

from types import SimpleNamespace

from octop.infra.knowledge.default_open import (
    merge_knowledge_base_ids,
    stamp_turn_knowledge_config,
)


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


def test_merge_knowledge_base_ids_unions_agent_default_ids() -> None:
    visible = [
        SimpleNamespace(id="default", owner_user_id=1, default_open=True, shared=False),
        SimpleNamespace(id="agent-kb", owner_user_id=1, default_open=False, shared=False),
        SimpleNamespace(id="other", owner_user_id=1, default_open=False, shared=False),
    ]
    assert merge_knowledge_base_ids(
        visible,
        None,
        owner_user_id=1,
        agent_default_ids=["agent-kb", "missing"],
    ) == ["default", "agent-kb"]


def test_merge_knowledge_base_ids_falls_back_when_agent_defaults_invisible() -> None:
    visible = [
        SimpleNamespace(id="default", owner_user_id=1, default_open=True, shared=False),
    ]
    assert merge_knowledge_base_ids(
        visible,
        None,
        owner_user_id=1,
        agent_default_ids=["gone"],
    ) == ["default"]


def test_merge_knowledge_base_ids_unions_visible_extra_ids() -> None:
    visible = [
        SimpleNamespace(id="default", owner_user_id=1, default_open=True, shared=False),
        SimpleNamespace(id="expert-pick", owner_user_id=1, default_open=False, shared=False),
    ]

    assert merge_knowledge_base_ids(
        visible,
        None,
        owner_user_id=1,
        extra_ids=["expert-pick", "gone", ""],
    ) == ["default", "expert-pick"]
    assert (
        merge_knowledge_base_ids(
            visible,
            [],
            owner_user_id=1,
            extra_ids=["expert-pick"],
        )
        == []
    )


def test_stamp_turn_knowledge_config_writes_catalog() -> None:
    visible = [
        SimpleNamespace(
            id="expert-pick",
            owner_user_id=1,
            default_open=False,
            name="Policies",
            description="Refund rules",
        ),
    ]
    request: dict = {}
    selected = stamp_turn_knowledge_config(
        request,
        visible_bases=visible,
        explicit_ids=None,
        owner_user_id=1,
        extra_ids=["expert-pick", "gone"],
        is_admin=False,
        locale="zh",
    )
    assert selected == ["expert-pick"]
    configurable = request["configurable"]
    assert configurable["knowledge_base_ids"] == ["expert-pick"]
    assert configurable["knowledge_base_catalog"] == [
        {"id": "expert-pick", "name": "Policies", "description": "Refund rules"}
    ]
    assert configurable["user_is_admin"] is False
    assert configurable["locale"] == "zh"
