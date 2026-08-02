#!/usr/bin/env python3
"""Simulate safe WeChat subscription and learning-delivery decisions."""

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
class WeixinContext:
    current_session_key: str = ""
    existing_task_session_keys: tuple[str, ...] = ()
    weixin_channel_bound: bool = False
    qr_binding_confirmed: bool = False


def _normalize_selection(selection: Iterable[str] | str) -> list[str]:
    if selection == "all":
        return list(TASKS)
    if selection == "none":
        return []
    return [task for task in selection if task in TASKS]


def has_weixin_binding(context: WeixinContext) -> bool:
    if ":weixin:" in context.current_session_key:
        return True
    if any(":weixin:" in key for key in context.existing_task_session_keys):
        return True
    return context.weixin_channel_bound or context.qr_binding_confirmed


def can_create_weixin_task_from_current_session(context: WeixinContext) -> bool:
    """Current cron tools bind the current session and cannot target another one."""
    return ":weixin:" in context.current_session_key


def decide(
    selection: Iterable[str] | str,
    context: WeixinContext,
    *,
    receipt_capable_delivery_adapter: bool = False,
) -> dict[str, object]:
    selected = _normalize_selection(selection)
    bound = has_weixin_binding(context)
    can_create = can_create_weixin_task_from_current_session(context)
    blocked_daily = (
        ["daily_guideline_learning"]
        if "daily_guideline_learning" in selected and not receipt_capable_delivery_adapter
        else []
    )
    creatable = [task for task in selected if task not in blocked_daily]
    if not selected:
        return {
            "status": "registered_only",
            "selected_tasks": [],
            "create_tasks": [],
            "prompt_binding": False,
        }
    if not can_create:
        return {
            "status": "pending_weixin_session",
            "selected_tasks": selected,
            "create_tasks": [],
            "pending_platform_adapter_tasks": blocked_daily,
            "prompt_binding": not bound,
            "note": "当前 cron 工具不能从 Dashboard 或 CLI 选择另一个已绑定微信会话。",
        }
    if not creatable:
        return {
            "status": "pending_delivery_adapter",
            "selected_tasks": selected,
            "create_tasks": [],
            "pending_platform_adapter_tasks": blocked_daily,
            "prompt_binding": False,
            "note": "每日指南学习不能使用 generic agent cron，需平台回执型投递适配器。",
        }
    return {
        "status": "enabled_partial" if blocked_daily else "enabled",
        "selected_tasks": selected,
        "create_tasks": creatable,
        "pending_platform_adapter_tasks": blocked_daily,
        "prompt_binding": False,
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
    if not receipt_capable_adapter:
        return {
            "mode": "blocked",
            "send_formal_content": False,
            "advance_progress": False,
            "create_delivery_ledger": False,
            "manual_trigger_cron": False,
            "stop_after_guideline_selection": False,
            "note": "普通 agent cron 没有通道回执且会直接外发，不能创建每日指南学习任务。",
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
            "all_tasks_from_weixin_session",
            "all",
            WeixinContext(current_session_key="user:weixin:alice"),
            {"status": "enabled_partial", "create_count": 2, "prompt_binding": False},
        ),
        (
            "dashboard_with_old_weixin_task_cannot_retarget",
            ["insurance_policy_learning"],
            WeixinContext(
                current_session_key="user:dashboard:alice",
                existing_task_session_keys=("user:weixin:alice",),
            ),
            {"status": "pending_weixin_session", "create_count": 0, "prompt_binding": False},
        ),
        (
            "dashboard_without_weixin_proof",
            ["daily_guideline_learning"],
            WeixinContext(current_session_key="user:dashboard:alice"),
            {"status": "pending_weixin_session", "create_count": 0, "prompt_binding": True},
        ),
        (
            "no_task_selected",
            "none",
            WeixinContext(current_session_key="user:weixin:alice"),
            {"status": "registered_only", "create_count": 0, "prompt_binding": False},
        ),
    ]
    results = []
    for name, selection, context, expected in scenarios:
        result = decide(selection, context)
        result["scenario"] = name
        result["ok"] = (
            result["status"] == expected["status"]
            and len(result["create_tasks"]) == expected["create_count"]
            and result["prompt_binding"] is expected["prompt_binding"]
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
            "generic_scheduled_run_is_blocked",
            {"scheduled_run": True},
            {"mode": "blocked", "advance_progress": False, "create_delivery_ledger": False},
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
