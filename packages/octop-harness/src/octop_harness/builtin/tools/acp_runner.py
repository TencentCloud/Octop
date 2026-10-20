"""Built-in tool: ``acp_runner`` — delegate work to external ACP agent runtimes."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool
from langgraph.config import get_config

from octop_harness.acp.models import ACPConfig
from octop_harness.acp.service import ACPService, get_acp_service, init_acp_service
from octop_harness.acp.tool_adapter import (
    format_close_response,
    format_final_response,
    format_permission_required,
    render_event_text,
)
from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

ActionName = Literal["list", "status", "start", "message", "respond", "close"]


def build_acp_runner_tool(*, service_key: str, config: ACPConfig, workspace_dir: Path) -> Any:
    """Return the ``acp_runner`` tool bound to a specific agent instance."""

    @tool
    async def acp_runner(
        action: str,
        runner: str = "",
        message: str = "",
        cwd: str = "",
        max_runtime: float | None = 300,
    ) -> str:
        """Delegate tasks to an external ACP-compatible coding agent runtime.

        Use this tool to collaborate with configured external agents such as
        OpenCode, CodeBuddy, Qwen Code, Claude Code, or Codex.

        Workflow:
        1. ``action='list'`` — show enabled runners and session states.
        2. ``action='start', runner='...', message='...'`` — open a new session.
        3. ``action='message', runner='...', message='...'`` — continue the session.
        4. When ``[permission_required]`` appears, ask the user which option to pick,
           then ``action='respond', runner='...', message='<exact option id>'``.
        5. ``action='close', runner='...'`` — close the session.

        Args:
            action: One of list, status, start, message, respond, close.
            runner: Runner name (e.g. opencode, codebuddy, qwen_code). Not required for list.
            message: Task text for start/message, or exact permission option id for respond.
            cwd: Working directory override (defaults to agent workspace).
            max_runtime: Max seconds for one turn (default 300). None disables timeout.
        """
        action_name = str(action or "").strip().lower()
        runner_name = str(runner or "").strip()
        message_text = str(message or "")
        execution_cwd = _resolve_execution_cwd(cwd, workspace_dir)

        validation_error = _validate_action_inputs(
            action_name=action_name,
            runner_name=runner_name,
            message_text=message_text,
        )
        if validation_error:
            return validation_error

        if action_name == "list":
            return await _format_runner_list(config, service_key)

        if action_name == "status":
            return await _format_status(config, service_key, runner_name)

        if action_name == "close":
            try:
                thread_id = _thread_id_from_config()
            except ValueError as exc:
                return f"Error: {exc}"
            service = _get_service(service_key, config)
            existing = await service.get_session(thread_id, runner_name)
            await service.close_thread_session(thread_id=thread_id, runner=runner_name)
            return format_close_response(
                runner_name=runner_name,
                closed=existing is not None,
            )

        timeout_seconds, timeout_error = _parse_timeout(max_runtime)
        if timeout_error:
            return timeout_error

        return await _run_streaming_action(
            service_key=service_key,
            config=config,
            action_name=action_name,
            runner_name=runner_name,
            message_text=message_text,
            execution_cwd=execution_cwd,
            timeout_seconds=timeout_seconds,
        )

    return acp_runner


def _get_service(service_key: str, config: ACPConfig) -> ACPService:
    service = get_acp_service(service_key)
    if service is None:
        service = init_acp_service(service_key, config)
    return service


def _thread_id_from_config() -> str:
    cfg = get_config().get("configurable") or {}
    thread_id = cfg.get("thread_id")
    if not thread_id:
        raise ValueError(
            "acp_runner requires configurable.thread_id; this tool can only run inside a bound chat thread",
        )
    return str(thread_id)


def _resolve_execution_cwd(cwd: str, workspace_dir: Path) -> Path:
    cwd_text = cwd.strip()
    if not cwd_text:
        return workspace_dir.resolve()
    candidate = Path(cwd_text).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_dir / candidate
    return candidate.resolve()


def _validate_action_inputs(
    *,
    action_name: str,
    runner_name: str,
    message_text: str,
) -> str | None:
    allowed = {"list", "status", "start", "message", "respond", "close"}
    if action_name not in allowed:
        return "Error: action must be one of: list, status, start, message, respond, close."
    if action_name not in {"list", "status"} and not runner_name:
        return "Error: runner is empty."
    if action_name in {"message", "respond"} and not message_text:
        if action_name == "message":
            return "Error: message is empty. Use action='start' to begin a new conversation."
        return "Error: message is empty. For respond, pass the exact permission option id."
    return None


def _parse_timeout(max_runtime: float | None) -> tuple[float | None, str | None]:
    if max_runtime is None:
        return None, None
    try:
        timeout_seconds = float(max_runtime)
    except (TypeError, ValueError):
        return None, "Error: max_runtime must be a number in seconds."
    if timeout_seconds <= 0:
        return None, "Error: max_runtime must be greater than 0."
    return timeout_seconds, None


def _enabled_runners(config: ACPConfig) -> list[str]:
    return config.enabled_runner_names()


async def _format_runner_list(config: ACPConfig, service_key: str) -> str:
    runners = _enabled_runners(config)
    if not runners:
        return "No enabled ACP runners are configured."
    try:
        thread_id = _thread_id_from_config()
    except ValueError:
        thread_id = ""
    service = _get_service(service_key, config) if thread_id else None
    lines = ["Available external ACP runners:"]
    for name in runners:
        details: list[str] = []
        if service is not None:
            session = await service.get_session(thread_id, name)
            if session is not None and session.process.returncode is None:
                details.append("session: open")
            pending = await service.get_pending_permission(thread_id=thread_id, runner=name)
            if pending is not None:
                details.append("task: permission_required")
        lines.append(f"- {name}" + (f" ({', '.join(details)})" if details else ""))
    return "\n".join(lines)


async def _format_status(config: ACPConfig, service_key: str, runner_name: str) -> str:
    if runner_name:
        if runner_name not in config.runners:
            return f"Error: runner '{runner_name}' is not configured."
        if not config.runners[runner_name].enabled:
            return f"Error: runner '{runner_name}' is disabled."
    else:
        return await _format_runner_list(config, service_key)

    try:
        thread_id = _thread_id_from_config()
    except ValueError as exc:
        return f"Error: {exc}"

    service = _get_service(service_key, config)
    session = await service.get_session(thread_id, runner_name)
    pending = await service.get_pending_permission(thread_id=thread_id, runner=runner_name)
    state = "closed"
    if session is not None and session.process.returncode is None:
        state = "waiting_for_permission" if pending is not None else "open"
    lines = [f"runner: {runner_name}", f"session: {state}"]
    if pending is not None:
        lines.append("")
        lines.append(format_permission_required(pending))
    return "\n".join(lines)


async def _run_streaming_action(
    *,
    service_key: str,
    config: ACPConfig,
    action_name: str,
    runner_name: str,
    message_text: str,
    execution_cwd: Path,
    timeout_seconds: float | None,
) -> str:
    if runner_name not in config.runners or not config.runners[runner_name].enabled:
        enabled = ", ".join(_enabled_runners(config)) or "(none)"
        return f"Error: runner '{runner_name}' is not available. Enabled runners: {enabled}."

    service = _get_service(service_key, config)
    try:
        thread_id = _thread_id_from_config()
    except ValueError as exc:
        return f"Error: {exc}"

    if action_name == "start":
        existing = await service.get_session(thread_id, runner_name)
        if existing is not None and existing.process.returncode is None:
            return f"Error: an ACP session for runner '{runner_name}' is already open. Use action='message' instead."

    chunks: list[str] = []
    final_event: dict[str, Any] | None = None

    async def on_message(payload: dict[str, Any], _is_last: bool) -> None:
        nonlocal final_event
        text = render_event_text(payload)
        if text:
            chunks.append(text)
        if str(payload.get("type") or "").lower() == "text":
            final_event = payload

    async def execute() -> dict[str, Any]:
        if action_name == "respond":
            bound = await service.get_session(thread_id, runner_name)
            if bound is None:
                raise ValueError(
                    f"no bound ACP session found for runner '{runner_name}' in current thread",
                )
            pending = await service.get_pending_permission(thread_id=thread_id, runner=runner_name)
            if pending is None:
                raise ValueError(
                    f"current ACP session for runner '{runner_name}' is not waiting for permission",
                )
            return await service.resume_permission(
                acp_session_id=bound.acp_session_id,
                option_id=message_text.strip(),
                on_message=on_message,
            )

        restart = action_name == "start"
        require_existing = action_name == "message"
        prompt = message_text or ("hi" if action_name == "start" else "")
        return await service.run_turn(
            thread_id=thread_id,
            runner=runner_name,
            prompt_blocks=[{"type": "text", "text": prompt}],
            cwd=str(execution_cwd),
            on_message=on_message,
            restart=restart,
            require_existing=require_existing,
        )

    try:
        if timeout_seconds is None:
            result = await execute()
        else:
            result = await asyncio.wait_for(execute(), timeout=timeout_seconds)
    except TimeoutError:
        await service.cancel_turn(thread_id=thread_id, runner=runner_name)
        return (
            f"ACP turn for runner '{runner_name}' reached max_runtime and was interrupted. "
            "The session remains open; continue with action='message'."
        )
    except ImportError as exc:
        return f"ACP support not installed: {exc}. Install octop-harness with the [acp] extra."
    except ValueError as exc:
        return f"Error: {exc}"
    except DEFENSIVE_OP_ERRORS as exc:
        return f"ACP execution error: {exc}"

    body = "\n\n".join(chunks).strip()
    if result.get("status") == "permission_required":
        suspended = result.get("suspended_permission")
        permission_text = format_permission_required(suspended) if suspended is not None else ""
        return "\n\n".join(part for part in (body, permission_text) if part) or "Permission required."

    return body or format_final_response(
        runner_name=runner_name,
        execution_cwd=execution_cwd,
        final_event=result.get("event") if isinstance(result.get("event"), dict) else final_event,
    )
