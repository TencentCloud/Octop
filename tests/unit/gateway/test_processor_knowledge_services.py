"""GlobalProcessor knowledge services must carry provider_repo for remote embeds."""

from __future__ import annotations

from unittest.mock import MagicMock

from octop.infra.gateway.process.processor import GlobalProcessor
from octop.infra.gateway.slash.dispatcher import SlashDispatcher


def test_processor_knowledge_services_include_provider_repo() -> None:
    provider_repo = object()
    processor = GlobalProcessor(
        agent_manager=MagicMock(),
        thread_registry=MagicMock(),
        audit_repo=MagicMock(),
        agent_repo=MagicMock(),
        user_repo=MagicMock(),
        connector_repo=MagicMock(),
        knowledge_repo=MagicMock(),
        settings_repo=MagicMock(),
        provider_repo=provider_repo,
        dispatcher=SlashDispatcher(),
    )

    assert processor._knowledge_services is not None
    assert processor._knowledge_services.provider_repo is provider_repo
