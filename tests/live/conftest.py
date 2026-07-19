"""Fixtures for live tests that call real LLM endpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from octop.config import OctopConfig
from octop.infra.agents.experts.catalog import ExpertCatalog, default_library_root
from octop.infra.agents.manager import AgentManager
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import DBPool
from octop.infra.db.services import build_shared_services
from octop.infra.utils.paths import PathLayout

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


def _load_env_file() -> None:
    if not _ENV_FILE.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE, override=False)
    except ImportError:
        pass


@pytest.fixture(autouse=True, scope="session")
def _load_live_env() -> None:
    """Load the repo-root ``.env`` only while live tests run.

    Loading at import time (previously a module-level call) leaked real
    credentials into ``os.environ`` for the entire pytest session, polluting
    unrelated unit tests such as ``test_config`` that assume a clean env for
    their defaults. Scoping the load to this autouse session fixture confines
    it to live tests, which are deselected by ``-m "not live"``.
    """
    _load_env_file()


@dataclass(frozen=True)
class LiveOpenAIConfig:
    provider_name: str
    api_key: str
    base_url: str
    model_id: str

    @property
    def default_model(self) -> str:
        return f"{self.provider_name}/{self.model_id}"


@pytest.fixture(scope="session")
def live_openai_config() -> LiveOpenAIConfig:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    model_id = os.environ.get("OPENAI_MODEL_NAME", "").strip()
    if not api_key or not base_url or not model_id:
        pytest.skip("Set OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL_NAME in .env")
    return LiveOpenAIConfig(
        provider_name="openai-live",
        api_key=api_key,
        base_url=base_url,
        model_id=model_id,
    )


def _seed_live_provider(services: object, cfg: LiveOpenAIConfig) -> None:
    repos = services.repos  # type: ignore[attr-defined]
    existing = repos.provider_repo.get_by_name(cfg.provider_name)
    if existing is not None:
        repos.provider_repo.delete(existing.id)
    repos.provider_repo.create(
        name=cfg.provider_name,
        kind="openai",
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        models_json=json.dumps(
            [{"id": cfg.model_id, "name": cfg.model_id, "enabled": True, "input": ["text"]}],
        ),
    )


@pytest.fixture
async def live_agent_manager(
    tmp_path: Path,
    live_openai_config: LiveOpenAIConfig,
) -> AsyncIterator[AgentManager]:
    paths = PathLayout(tmp_path / ".octop")
    paths.ensure_root()
    db = DBPool(paths.db)
    run_migrations(db)
    services = build_shared_services(db=db, paths=paths, config=OctopConfig())
    _seed_live_provider(services, live_openai_config)

    catalog = ExpertCatalog(default_library_root())
    catalog.refresh()

    manager = AgentManager(
        repos=services.repos,
        paths=services.paths,
        expert_catalog=catalog,
    )
    await manager.boot()
    try:
        yield manager
    finally:
        await manager.shutdown()
