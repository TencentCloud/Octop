"""Care settings survive upgrades, round trips and writes from older dashboards."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from octop.api.deps import current_user, get_server
from octop.api.routers.proactive_care import router
from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.proactive_care_config import ProactiveCareConfig, ProactiveCareConfigRepo
from octop.infra.db.repos.users import UserRepo


def test_generation_config_upgrade_keeps_existing_schedule(tmp_path):
    db = SqlitePool(tmp_path / "care.db")
    run_migrations(db)
    user_id = UserRepo(db).create(username="user", password_hash="h", role="admin")
    AgentRepo(db).create(agent_id="expert", user_id=user_id, name="bot")
    repo = ProactiveCareConfigRepo(db)
    repo.upsert(ProactiveCareConfig(agent_id="expert", min_interval_hours=9))
    with db.transaction() as conn:
        conn.execute("UPDATE _schema_version SET version = 26")
        for column in ("model_ref", "reasoning_effort", "generation_timeout_seconds"):
            conn.execute(f"ALTER TABLE proactive_care_config DROP COLUMN {column}")
    run_migrations(db)
    run_migrations(db)
    assert repo.get("expert") == ProactiveCareConfig(agent_id="expert", min_interval_hours=9)
    assert repo.list_enabled() == [repo.get("expert")]


def test_generation_config_api(tmp_path):
    db = SqlitePool(tmp_path / "care.db")
    run_migrations(db)
    user_id = UserRepo(db).create(username="user", password_hash="h", role="admin")
    rows = AgentRepo(db)
    rows.create(agent_id="expert", user_id=user_id, name="bot")
    repo = ProactiveCareConfigRepo(db)
    server = MagicMock()
    server.services.repos.proactive_care_config_repo = repo
    registry = server.app_runtime.agent_registry
    registry.get_row.side_effect = rows.get
    registry.configured_default_model_ref.return_value = "provider/main"
    registry.providers.is_model_ref_usable.side_effect = lambda ref: (
        ref in {"provider/main", "provider/fast"}
    )
    registry.model_ref_allowed_for_user.return_value = True
    registry.providers.get_model_reasoning_capability.return_value = {
        "toggle": True,
        "efforts": ["low"],
    }
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_server] = lambda: server
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=user_id, is_admin=True)
    client = TestClient(app)
    path = "/agents/expert/proactive-care"

    defaults = client.get(path).json()
    assert defaults["default_model_ref"] == "provider/main"
    assert defaults["model_ref"] is None
    assert defaults["reasoning_effort"] == "auto"
    assert defaults["generation_timeout_seconds"] == 30
    saved = {
        "model_ref": "provider/fast",
        "reasoning_effort": "disabled",
        "generation_timeout_seconds": 90,
    }
    assert client.put(path, json=saved).status_code == 200
    assert client.put(path, json={"min_interval_hours": 9}).status_code == 200
    restored = client.get(path).json()
    assert {key: restored[key] for key in saved} == saved
    assert restored["min_interval_hours"] == 9
    assert repo.list_enabled() == [repo.get("expert")]
    for timeout in (0, -1, 3601, 0.5, True):
        assert client.put(path, json={"generation_timeout_seconds": timeout}).status_code == 422
    assert client.put(path, json={"reasoning_effort": "not-an-effort"}).status_code == 422
    assert client.put(path, json={"model_ref": "missing/model"}).status_code == 400
    assert client.get(path).json() == restored
    response = client.put(path, json={"model_ref": None, "reasoning_effort": "low"})
    assert response.status_code == 200
    assert response.json()["model_ref"] is None
    assert response.json()["reasoning_effort"] == "low"
    registry.providers.get_model_reasoning_capability.assert_called_with("provider/main")
    assert server.app_runtime.proactive_scheduler.reschedule.call_count == 3
