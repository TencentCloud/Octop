"""CronJobRepo mcp_servers persistence."""

from __future__ import annotations

from pathlib import Path

from octop.infra.db.migrate import run_migrations
from octop.infra.db.pool import SqlitePool
from octop.infra.db.repos.agents import AgentRepo
from octop.infra.db.repos.cron import CronJobRepo
from octop.infra.db.repos.users import UserRepo


def test_cron_mcp_servers_roundtrip(tmp_path: Path) -> None:
    db = SqlitePool(tmp_path / "x.db")
    run_migrations(db)
    UserRepo(db).create(username="u", password_hash="h", role="user")
    AgentRepo(db).create(agent_id="a1", user_id=1, name="bot")
    repo = CronJobRepo(db)

    cid = repo.create(
        cron_id="j1",
        agent_id="a1",
        user_id=1,
        trigger="interval:60",
        prompt="hi",
        session_key="a1:cron:j1:dm",
        mcp_servers=["github__1", "feishu__2"],
    )
    row = repo.get(cid)
    assert row is not None
    assert row.mcp_servers == ["github__1", "feishu__2"]
    assert row.to_public_dict()["mcp_servers"] == ["github__1", "feishu__2"]

    repo.update(cid, mcp_servers=["only_one"])
    row2 = repo.get(cid)
    assert row2 is not None
    assert row2.mcp_servers == ["only_one"]

    cid2 = repo.create(
        cron_id="j2",
        agent_id="a1",
        user_id=1,
        trigger="interval:60",
        prompt="bye",
        session_key="a1:cron:j2:dm",
    )
    row3 = repo.get(cid2)
    assert row3 is not None
    assert row3.mcp_servers == []
