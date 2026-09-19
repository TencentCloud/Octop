"""Sports scores via TheSportsDB free API key 3."""

from __future__ import annotations

import json
from typing import Any

import httpx
from harness_agent.plugins import PluginContext

_BASE = "https://www.thesportsdb.com/api/v1/json/3"
_EPL_LEAGUE = "4328"


def _payload(data: dict[str, Any], text: str) -> str:
    return json.dumps(
        {"octop_ui": {"renderer": "sports_scores_list", "version": 1}, "data": data, "text": text},
        ensure_ascii=False,
    )


def _map_event(row: dict[str, Any]) -> dict[str, Any]:
    home = str(row.get("strHomeTeam") or "")
    away = str(row.get("strAwayTeam") or "")
    score = f"{row.get('intHomeScore', '-')} - {row.get('intAwayScore', '-')}"
    return {
        "event": str(row.get("strEvent") or f"{home} vs {away}"),
        "home": home,
        "away": away,
        "score": score,
        "date": str(row.get("dateEvent") or row.get("strDate") or ""),
    }


async def sports_scores(league: str = "soccer", query: str = "") -> str:
    """Past league events or search by query. Default league EPL (4328)."""
    q = (query or "").strip()
    league_key = (league or "soccer").strip().lower()
    league_id = _EPL_LEAGUE if league_key in {"soccer", "epl", "4328"} else _EPL_LEAGUE
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            if q:
                resp = client.get(f"{_BASE}/searchevents.php", params={"e": q})
            else:
                resp = client.get(f"{_BASE}/eventspastleague.php", params={"id": league_id})
            resp.raise_for_status()
            body = resp.json()
    except Exception as exc:
        return _payload({"items": [], "error": str(exc)}, f"赛况获取失败：{exc}")
    rows = body.get("event") or body.get("events") or []
    if isinstance(rows, dict):
        rows = [rows]
    items = [_map_event(r) for r in rows if isinstance(r, dict)][:20]
    if not items:
        return _payload({"items": [], "silent": True, "query": q}, "")
    lines = [f"{e['date']} {e['home']} {e['score']} {e['away']}" for e in items[:8]]
    text = f"赛况 {len(items)} 场\n" + "\n".join(lines)
    return _payload({"items": items, "league": league_id, "query": q}, text)


def setup(ctx: PluginContext) -> None:
    ctx.tool(
        "sports_scores",
        sports_scores,
        description="足球赛况。query 非空则搜索赛事；否则返回英超(id 4328)近期比赛。",
    )
