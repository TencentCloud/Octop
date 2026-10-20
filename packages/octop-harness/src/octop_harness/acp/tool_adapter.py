"""Render ACP client events as plain text for LangChain tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _render_status_event(event: dict[str, Any]) -> str | None:
    status = str(event.get("status") or "unknown")
    if status == "run_finished":
        return None
    summary = str(event.get("summary") or "").strip()
    if status == "agent_thinking":
        return summary or "agent thinking..."
    parts = [f"[status] {status}"]
    if summary:
        parts.append(summary)
    return "\n".join(parts)


def render_event_text(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "").lower()
    if event_type == "text":
        text = str(event.get("text") or "").strip()
        return f"[assistant]\n{text}" if text else None
    if event_type.startswith("tool_"):
        kind = str(event.get("kind") or "").strip()
        detail = str(event.get("detail") or event.get("title") or "").strip()
        return f"[tool_call] {kind} ({detail})" if kind and detail else None
    if event_type == "status":
        return _render_status_event(event)
    if event_type == "permission_request":
        return _render_permission_event(event)
    if event_type == "error":
        message_text = str(event.get("message") or "Unknown error")
        return f"[error] {message_text}" if message_text else None
    return None


def format_permission_required(suspended: Any) -> str:
    title = str(getattr(suspended, "summary", None) or getattr(suspended, "tool_name", None) or "permission request")
    lines = [f"[permission_required] {title}", "Choose an option id and call acp_runner(action='respond', ...):"]
    for opt in getattr(suspended, "options", []) or []:
        if not isinstance(opt, dict):
            continue
        name = str(opt.get("title") or opt.get("name") or opt.get("optionId") or "option")
        option_id = str(opt.get("optionId") or opt.get("option_id") or "")
        lines.append(f"- {name}" + (f" (id={option_id})" if option_id else ""))
    return "\n".join(lines)


def format_close_response(*, runner_name: str, closed: bool) -> str:
    if closed:
        return f"Closed ACP session for runner '{runner_name}'."
    return f"No open ACP session for runner '{runner_name}'."


def format_final_response(
    *,
    runner_name: str,
    execution_cwd: Path,
    final_event: dict[str, Any] | None,
) -> str:
    header = f"runner: {runner_name} working directory: {execution_cwd}"
    if final_event and str(final_event.get("type") or "").lower() == "text":
        text = str(final_event.get("text") or "").strip()
        if text:
            return f"{header}\n\n[assistant]\n{text}"
    if final_event and str(final_event.get("type") or "").lower() == "error":
        return f"{header}\n\n[error] {final_event.get('message', 'Unknown error')}"
    return f"{header}\n\n(no assistant text returned)"


def _render_permission_event(event: dict[str, Any]) -> str:
    title = str(event.get("title") or event.get("reason") or "permission request")
    options = event.get("options") or []
    rendered: list[str] = []
    for opt in options:
        if isinstance(opt, dict):
            name = str(opt.get("title") or opt.get("name") or opt.get("optionId") or "option")
            option_id = str(opt.get("optionId") or opt.get("option_id") or "")
            rendered.append(f"{name} ({option_id})" if option_id else name)
    lines = [f"[permission_request] {title}"]
    if rendered:
        lines.append(f"options: {', '.join(rendered)}")
    return "\n".join(lines)
