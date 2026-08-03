#!/usr/bin/env python3
"""Simulate subscription creation and learning-delivery decisions.

Routing model (v2): the platform ``cronjob_create`` tool binds the cron job to
the *current* conversation session and delivers to whatever channel that session
uses (WeChat / QQ / dashboard / CLI / …). There is no longer a WeChat-only gate:
any session may create tasks, and the platform auto-routes delivery. This file
keeps a decision simulator so the package's intent stays testable.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass

TASKS = (
    "daily_guideline_learning",
    "guideline_update_reminder",
    "insurance_policy_learning",
)


@dataclass(frozen=True)
class SessionContext:
    current_session_key: str = ""
    existing_task_session_keys: tuple[str, ...] = ()


def _normalize_selection(selection: Iterable[str] | str) -> list[str]:
    if selection == "all":
        return list(TASKS)
    if selection == "none":
        return []
    return [task for task in selection if task in TASKS]


def can_create_task_from_current_session(context: SessionContext) -> bool:
    """The platform cron tool binds the current session; any session qualifies."""
    return bool(context.current_session_key)


def decide(
    selection: Iterable[str] | str,
    context: SessionContext,
) -> dict[str, object]:
    """All selected tasks are created on the current session (auto-routed).

    Daily guideline learning is created via generic cron with the weak-dedup
    protocol; it does not require a receipt-capable adapter to be *created* —
    it simply reports "no enabled track" until the user selects a guideline.
    """
    selected = _normalize_selection(selection)
    can_create = can_create_task_from_current_session(context)
    if not selected:
        return {
            "status": "registered_only",
            "selected_tasks": [],
            "create_tasks": [],
            "note": "未选择任何任务，仅保留登记档案。",
        }
    if not can_create:
        return {
            "status": "no_session",
            "selected_tasks": selected,
            "create_tasks": [],
            "note": "缺少当前会话标识，无法绑定 cron；请在一个有效会话中创建。",
        }
    return {
        "status": "enabled",
        "selected_tasks": selected,
        "create_tasks": list(selected),
        "delivery_channel": "auto (当前会话通道)",
        "note": (
            "平台自动绑定当前会话通道投递；每日指南学习用通用 cron + 弱投递防重规程，"
            "选定指南轨道前不随机推送。"
        ),
    }


def decide_learning_delivery(
    *,
    scheduled_run: bool = False,
    explicit_formal_start: bool = False,
    preview_requested: bool = False,
    guideline_just_selected: bool = False,
    receipt_capable_adapter: bool = False,
    claimed: bool = False,
    transport_ack: bool = False,
) -> dict[str, object]:
    if preview_requested:
        return {
            "mode": "preview",
            "send_formal_content": False,
            "advance_progress": False,
            "create_delivery_ledger": False,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": False,
        }
    formal_requested = scheduled_run or explicit_formal_start
    if guideline_just_selected and not explicit_formal_start:
        return {
            "mode": "configuration",
            "send_formal_content": False,
            "advance_progress": False,
            "create_delivery_ledger": False,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": True,
        }
    if not formal_requested:
        return {
            "mode": "configuration",
            "send_formal_content": False,
            "advance_progress": False,
            "create_delivery_ledger": False,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": False,
        }
    # Generic cron (no receipt-capable adapter): weak-dedup protocol allows
    # sending formal content with per-logical-date dedup, but cannot confirm
    # delivery or advance learning state on its own.
    if not receipt_capable_adapter:
        return {
            "mode": "weak_delivery",
            "send_formal_content": True,
            "advance_progress": False,
            "create_delivery_ledger": True,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": False,
            "note": "通用 cron 弱投递：按逻辑日期去重后发送，不代表送达回执，不推进学习状态。",
        }
    if not claimed:
        return {
            "mode": "awaiting_claim",
            "send_formal_content": False,
            "advance_progress": False,
            "create_delivery_ledger": True,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": False,
        }
    return {
        "mode": "formal_accepted" if transport_ack else "dispatching",
        "send_formal_content": True,
        "advance_progress": transport_ack,
        "create_delivery_ledger": True,
        "manual_trigger_cron": False,
        "stop_after_guideline_selection": False,
    }


def _run_scenarios() -> list[dict[str, object]]:
    scenarios = [
        (
            "all_tasks_from_any_session_auto_route",
            "all",
            SessionContext(current_session_key="user:dashboard:alice"),
            {"status": "enabled", "create_count": 3},
        ),
        (
            "single_task_from_weixin_session",
            ["insurance_policy_learning"],
            SessionContext(current_session_key="user:weixin:alice"),
            {"status": "enabled", "create_count": 1},
        ),
        (
            "daily_learning_from_cli_session",
            ["daily_guideline_learning"],
            SessionContext(current_session_key="user:cli:bob"),
            {"status": "enabled", "create_count": 1},
        ),
        (
            "no_task_selected",
            "none",
            SessionContext(current_session_key="user:weixin:alice"),
            {"status": "registered_only", "create_count": 0},
        ),
    ]
    results = []
    for name, selection, context, expected in scenarios:
        result = decide(selection, context)
        result["scenario"] = name
        result["ok"] = (
            result["status"] == expected["status"]
            and len(result["create_tasks"]) == expected["create_count"]
        )
        results.append(result)
    delivery_scenarios = [
        (
            "preview_does_not_create_ledger",
            {"preview_requested": True},
            {"mode": "preview", "advance_progress": False, "create_delivery_ledger": False},
        ),
        (
            "selection_waits_for_schedule",
            {"guideline_just_selected": True},
            {"mode": "configuration", "advance_progress": False, "stop_after_guideline_selection": True},
        ),
        (
            "generic_scheduled_run_uses_weak_dedup",
            {"scheduled_run": True},
            {"mode": "weak_delivery", "advance_progress": False, "create_delivery_ledger": True, "send_formal_content": True},
        ),
        (
            "receipt_adapter_advances_only_after_ack",
            {"scheduled_run": True, "receipt_capable_adapter": True, "claimed": True, "transport_ack": True},
            {"mode": "formal_accepted", "advance_progress": True, "create_delivery_ledger": True},
        ),
    ]
    for name, kwargs, expected in delivery_scenarios:
        result = decide_learning_delivery(**kwargs)
        result["scenario"] = name
        result["ok"] = all(result[key] == value for key, value in expected.items())
        results.append(result)
    return results


def main() -> int:
    results = _run_scenarios()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
