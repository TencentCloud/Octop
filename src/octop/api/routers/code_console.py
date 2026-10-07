"""Code console API — human-facing gateway over ACP runners.

Exposes the same ``harness_agent.acp.service.ACPService`` used by the
``acp_runner`` agent tool, but as a first-class HTTP surface so the dashboard
"Code" page can drive external coding agents (OpenCode / CodeBuddy / …)
directly: list runners, open sessions, stream turns, answer permission
requests, cancel and close.

S3: session metadata and turn events are persisted (SQLite/Postgres via the
shared pool). Process-local ACP conversations remain in memory; after a
restart, sessions are marked ``interrupted`` at startup and the next prompt
replays textual history into a fresh CLI process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from octop.api.deps import current_user, get_server
from octop.infra.coding.event_sink import EventSink
from octop.infra.coding.policy_engine import PolicyEngine
from octop.infra.coding.runtime_manager import RuntimeManager
from octop.infra.coding.session_manager import SessionManager
from octop.infra.coding.worktree_manager import WorktreeManager

logger = logging.getLogger(__name__)

router = APIRouter()

# --- Direct (non-ACP) transport ------------------------------------
# harness_agent.acp drops agent_thought_chunk updates, so the Code Console
# drives the coding CLIs itself (same binaries, own stdio JSON-RPC client).
# ACP stays intact for agents; set OCTOP_CODE_DRIVER=acp to use it here too.
_DIRECT_AGENTS: dict[str, Any] = {}


def _driver_mode() -> str:
    return (os.environ.get("OCTOP_CODE_DRIVER") or "direct").strip().lower()


def _use_sandbox() -> bool:
    """Run the coding CLI inside a throw-away sandbox container.

    Defaults to ``False``: the CLIs are installed in the Octop image, and
    running them in-place removes container cold-start latency and keeps
    the session workspace on the persistent volume.
    """
    raw = (os.environ.get("OCTOP_CODE_SANDBOX") or "0").strip().lower()
    return raw in ("1", "true", "yes", "on")

_SERVICE_KEY = "code-console"
_DEFAULT_CWD = "/data/.octop/code-workspace"
_FLUSH_TIMEOUT = 2.0

# Uploads accepted by POST /code/sessions/{id}/files.
_UPLOAD_MAX_BYTES = 2 * 1024 * 1024
_UPLOAD_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".json", ".yaml",
    ".yml", ".toml", ".ini", ".conf", ".py", ".js", ".ts", ".tsx", ".sh",
    ".sql", ".html", ".css", ".xml", ".diff", ".patch",
}
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\-]{0,63}$")

# Built-in per-runner model catalog; can be overridden per user via the
# ``code_models:user:<id>`` settings key (JSON map runner -> [{id,label}]).
_DEFAULT_MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "codex": [
        {"id": "deepseek-chat", "label": "DeepSeek Chat"},
        {"id": "deepseek-reasoner", "label": "DeepSeek Reasoner"},
    ],
}
# Env vars on the runner config that carry its default model (display only).
_RUNNER_MODEL_ENV = {
    "codebuddy": "CODEBUDDY_MODEL",
    "opencode": "OPENCODE_MODEL",
}

# codex-rs core prepends this notice to agent text when the model slug is not
# in its built-in metadata table (every third-party model). It is pure noise
# for users — model context window is supplied explicitly via config.toml —
# so strip it from streamed/final text events.
_RUNNER_NOTICE_RE = re.compile(
    r"\s*Model metadata for `[^`]*` not found\. "
    r"Defaulting to fallback metadata; this can degrade performance and cause issues\."
)


def _strip_runner_notices(text: Any) -> Any:
    if isinstance(text, str):
        return _RUNNER_NOTICE_RE.sub("", text).lstrip()
    return text


# Process-local ACP runtime cache: session_id -> rec. Source of truth is the DB.
_sessions: dict[str, dict[str, Any]] = {}
_streams: dict[str, asyncio.Queue] = {}
_state_lock = asyncio.Lock()

# Process-local persistence components (initialised on first request).
_sm: SessionManager | None = None
_sink: EventSink | None = None
_runtime_mgr: RuntimeManager | None = None
_worktree_mgr: WorktreeManager | None = None
_components_lock = asyncio.Lock()
_recovered = False
_reaper_started = False

# Strong refs for fire-and-forget tasks (the loop only weak-refs tasks).
_background: set[asyncio.Task[None]] = set()


class NewSessionBody(BaseModel):
    runner: str = ""
    cwd: str = ""
    repo_path: str = ""
    model: str = ""


class PromptBody(BaseModel):
    text: str = ""
    option_id: str = ""
    attachments: list[str] = []


def _registry(server: Any) -> Any:
    assert server.app_runtime is not None
    return server.app_runtime.agent_registry


def _acp_config(server: Any, user_id: int):
    from harness_agent.acp.models import ACPConfig

    registry = _registry(server)
    runners = registry.acp_settings.load_runners(user_id)
    return ACPConfig.from_dict({"runners": runners})


def _service(server: Any, user_id: int):
    from harness_agent.acp.service import get_acp_service, init_acp_service

    service = get_acp_service(_SERVICE_KEY)
    if service is None:
        service = init_acp_service(_SERVICE_KEY, _acp_config(server, user_id))
    return service


_IDLE_TIMEOUT_S = 30 * 60       # 30 minutes idle -> reclaim sandbox
_MAX_CONCURRENT_SANDBOXES = 10
_REAPER_INTERVAL_S = 60


async def _reap_idle_sandboxes() -> None:
    """Background task: reclaim idle sandboxes and enforce concurrency cap."""
    global _runtime_mgr, _sm
    while True:
        try:
            if _runtime_mgr is not None and _sm is not None:
                active = _runtime_mgr._repo.list_active()  # noqa: SLF001
                now = time.time()
                # 1) reclaim idle sandboxes (session not updated recently)
                for rt in active:
                    srow = _sm.get(rt.session_id)
                    if srow is None:
                        _runtime_mgr.destroy(rt.session_id)
                        continue
                    idle = now - (srow.updated_at or srow.created_at or now)
                    if idle > _IDLE_TIMEOUT_S and srow.status not in ("running", "awaiting_permission"):
                        logger.info("reaping idle sandbox for session %s (idle %.0fs)", rt.session_id, idle)
                        _runtime_mgr.destroy(rt.session_id)
                # 2) enforce concurrency cap: destroy oldest idle beyond limit
                still_active = _runtime_mgr._repo.list_active()  # noqa: SLF001
                if len(still_active) > _MAX_CONCURRENT_SANDBOXES:
                    still_active.sort(key=lambda r: r.created_at)
                    for rt in still_active[: len(still_active) - _MAX_CONCURRENT_SANDBOXES]:
                        logger.info("concurrency cap: destroying sandbox for %s", rt.session_id)
                        _runtime_mgr.destroy(rt.session_id)
        except Exception:  # noqa: BLE001
            logger.exception("sandbox reaper tick failed")
        await asyncio.sleep(_REAPER_INTERVAL_S)


async def _components(server: Any):
    global _sm, _sink, _runtime_mgr, _worktree_mgr, _recovered, _reaper_started
    if _sm is not None and _sink is not None and _runtime_mgr is not None and _worktree_mgr is not None:
        return _sm, _sink, _runtime_mgr, _worktree_mgr
    async with _components_lock:
        if _sm is None or _sink is None or _runtime_mgr is None or _worktree_mgr is None:
            repos = server.services
            _sm = SessionManager(repos.coding_session_repo, repos.agent_event_repo)
            _sink = EventSink(repos.agent_event_repo)
            _sink.start()
            _runtime_mgr = RuntimeManager(repos.runtime_repo)
            _worktree_mgr = WorktreeManager(repos.worktree_repo)
            if not _reaper_started:
                asyncio.create_task(_reap_idle_sandboxes())
                _reaper_started = True
            if not _recovered:
                try:
                    n = _sm.recover_on_startup()
                    if n:
                        logger.info("coding startup recovery: %d active sessions -> interrupted", n)
                except Exception:  # noqa: BLE001
                    logger.exception("coding startup recovery failed")
                _recovered = True
    return _sm, _sink, _runtime_mgr, _worktree_mgr


async def aclose_sink() -> None:
    if _sink is not None:
        await _sink.aclose(flush_timeout=_FLUSH_TIMEOUT)


def _is_admin(user: Any) -> bool:
    return getattr(user, "role", "") == "admin" or bool(getattr(user, "is_admin", False))


def _resolve_cwd(raw: str) -> str:
    candidate = (raw or "").strip()
    if not candidate:
        return _DEFAULT_CWD
    if not os.path.isdir(candidate):
        raise HTTPException(status_code=400, detail=f"cwd does not exist: {candidate}")
    return candidate


def _safe_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"type": "raw", "text": str(payload)}
    out: dict[str, Any] = {}
    for key, value in payload.items():
        try:
            json.dumps(value)
            out[key] = value
        except TypeError:
            out[key] = str(value)
    return out


def _register_runner_secrets(sink: EventSink, service: Any, runner: str) -> None:
    """Best-effort: teach the sink every env value configured for a runner."""
    try:
        runner_cfg = service.config.runners.get(runner)
        env = getattr(runner_cfg, "env", None) if runner_cfg is not None else None
        if isinstance(env, dict):
            for value in env.values():
                if isinstance(value, str) and value:
                    sink.register_secret(value)
    except Exception:  # noqa: BLE001 - secret registration must never break a turn
        logger.debug("secret registration failed for runner %s", runner, exc_info=True)


async def _flush_sink(sink: EventSink) -> None:
    try:
        await asyncio.wait_for(sink.flush_idle(), timeout=_FLUSH_TIMEOUT)
    except TimeoutError:
        logger.warning("event sink flush exceeded %.1fs", _FLUSH_TIMEOUT)


async def _load_owned(server: Any, session_id: str, user: Any):
    sm, _sink, _rt_mgr, _wt_mgr = await _components(server)
    row = sm.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not sm.can_access(row, user_id=user.id, is_admin=_is_admin(user)):
        raise HTTPException(status_code=403, detail="forbidden")
    return sm, row


def _runtime_rec(row: Any) -> dict[str, Any]:
    """Rebuild the process-local ACP runtime record from a persisted row."""
    rec = _sessions.get(row.session_id)
    if rec is None:
        rec = {
            "runner": row.runner,
            "cwd": row.cwd,
            "user_id": row.user_id,
            "started": False,
            "replay_done": True,  # default: no replay unless history exists
        }
        if row.turns > 0:
            rec["replay_done"] = False
        _sessions[row.session_id] = rec
    return rec


# --------------------------------------------------------------------------- #
# Runner / session metadata
# --------------------------------------------------------------------------- #


@router.get("/code/runners", summary="List enabled ACP runners")
async def list_runners(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    cfg = _acp_config(server, user.id)
    names = cfg.enabled_runner_names()
    items = []
    for name in names:
        runner = cfg.runners[name]
        items.append(
            {
                "name": name,
                "command": runner.command,
                "args": list(runner.args),
                "trusted": bool(runner.trusted),
                "tool_parse_mode": runner.tool_parse_mode,
                "env_keys": sorted(runner.env.keys()),
            }
        )
    return {"runners": items, "default_cwd": _DEFAULT_CWD}


@router.get("/code/models", summary="List selectable models per runner")
async def list_models(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the per-runner model catalog.

    Combines the built-in defaults with any runner default exposed through its
    environment and an optional per-user override (``code_models:user:<id>``).
    """
    cfg = _acp_config(server, user.id)
    settings_repo = server.services.settings_repo
    raw = settings_repo.get(f"code_models:user:{user.id}")
    try:
        override = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        override = {}

    catalog: dict[str, list[dict[str, str]]] = {}
    for name in cfg.enabled_runner_names():
        runner = cfg.runners[name]
        items = [dict(m) for m in _DEFAULT_MODEL_CATALOG.get(name, [])]
        env_model = (runner.env or {}).get(_RUNNER_MODEL_ENV.get(name, ""))
        if env_model and not any(m["id"] == env_model for m in items):
            items.append({"id": env_model, "label": env_model})
        for m in override.get(name, []) or []:
            mid = str(m.get("id", ""))
            label = str(m.get("label", "")) or mid
            if mid and not any(x["id"] == mid for x in items):
                items.append({"id": mid, "label": label})
        catalog[name] = items
    return {"models": catalog}


@router.get("/code/sessions", summary="List code console sessions")
async def list_sessions(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    sm, _sink, _rt_mgr, _wt_mgr = await _components(server)
    rows = sm.list_visible(user_id=user.id, is_admin=_is_admin(user))
    items = []
    for row in rows:
        view = sm.runtime_view(row, streaming=row.session_id in _streams)
        items.append(view)
    items.sort(key=lambda x: x["created_at"] or 0, reverse=True)
    return {"sessions": items}


@router.post("/code/sessions", summary="Open a code console session")
async def create_session(
    body: NewSessionBody,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    cfg = _acp_config(server, user.id)
    runner = (body.runner or "").strip()
    if not runner:
        enabled = cfg.enabled_runner_names()
        if enabled:
            runner = enabled[0]
    if not runner or runner not in cfg.runners or not cfg.runners[runner].enabled:
        raise HTTPException(status_code=400, detail=f"runner '{runner}' is not enabled")
    model = (body.model or "").strip()
    if model and not _MODEL_ID_RE.match(model):
        raise HTTPException(status_code=400, detail=f"invalid model id '{model}'")
    cwd = _resolve_cwd(body.cwd)
    os.makedirs(cwd, exist_ok=True)
    sm, _sink, rt_mgr, wt_mgr = await _components(server)
    row = sm.create_session(user_id=user.id, runner=runner, cwd=cwd)

    # S5: bind a git worktree when a repository path is supplied.
    repo_path = (body.repo_path or "").strip()
    worktree_path = cwd
    if repo_path:
        try:
            wt = wt_mgr.create(session_id=row.session_id, repository_path=repo_path)
            worktree_path = wt.path
        except ValueError as exc:
            sm.close(row.session_id)
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("worktree creation failed")
            sm.close(row.session_id)
            raise HTTPException(status_code=500, detail=f"worktree creation failed: {exc}")

    # Persist the per-session model choice (applied when the sandbox starts).
    if model:
        sm._sessions.set_meta(row.session_id, {"model": model})  # noqa: SLF001

    # Eagerly boot the sandbox in the background so the first prompt does not
    # pay the container cold-start cost (boot ~3s; lazy path still retries).
    async def _prestart() -> None:
        try:
            await asyncio.to_thread(
                rt_mgr.create,
                session_id=row.session_id,
                worktree_path=worktree_path,
                runner=runner,
                model=model or None,
            )
        except Exception:  # noqa: BLE001 - first prompt falls back to lazy start
            logger.exception("eager sandbox prestart failed for %s", row.session_id)

    task = asyncio.create_task(_prestart())
    _background.add(task)
    task.add_done_callback(_background.discard)

    return {
        "id": row.session_id,
        "runner": row.runner,
        "model": model or None,
        "cwd": worktree_path,
        "status": row.status,
    }


@router.get("/code/sessions/{session_id}", summary="Get a code console session")
async def get_session(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    sm, row = await _load_owned(server, session_id, user)
    return sm.runtime_view(row, streaming=session_id in _streams)


@router.delete("/code/sessions/{session_id}", summary="Close a code console session")
async def close_session(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    try:
        sm, row = await _load_owned(server, session_id, user)
        rec = _sessions.get(session_id)
        try:
            service = _service(server, row.user_id)
            await service.close_thread_session(thread_id=session_id, runner=f"{row.runner}__sandbox__{session_id}")
            # Clean up the per-session sandbox runner config.
            service.config.runners.pop(f"{row.runner}__sandbox__{session_id}", None)
        except (Exception, asyncio.CancelledError):  # noqa: BLE001 - best effort teardown
            # close_thread_session awaits the pending prompt_task; closing a
            # session whose turn is suspended on a permission cancels it,
            # raising CancelledError (a BaseException in py3.8+). Treat as OK.
            logger.exception("close ACP session failed for %s", session_id)
        sm.close(session_id)
        async with _state_lock:
            _sessions.pop(session_id, None)
            _streams.pop(session_id, None)
        # S4/S5: tear down sandbox container and worktree.
        _sm2, _sink2, rt_mgr, wt_mgr = await _components(server)
        direct_agent = _DIRECT_AGENTS.pop(session_id, None)
        if direct_agent is not None:
            try:
                await direct_agent.close()
            except Exception:  # noqa: BLE001
                logger.debug("direct agent close failed", exc_info=True)
        if _use_sandbox():
            try:
                rt_mgr.destroy(session_id)
            except Exception:  # noqa: BLE001
                logger.debug("runtime destroy failed", exc_info=True)
        else:
            logger.debug("sandbox disabled; skipping runtime destroy")
        try:
            wt_mgr.remove(session_id)
        except Exception:  # noqa: BLE001
            logger.exception("worktree remove failed for %s", session_id)
        if rec is not None:
            sink = _sink2
            sink.submit(session_id, "session_closed", {"reason": "user_closed"})
            await _flush_sink(sink)
        return {"closed": True}
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("close_session unhandled error for %s", session_id)
        raise HTTPException(status_code=500, detail="failed to close session")


# --------------------------------------------------------------------------- #
# Event history (T7)
# --------------------------------------------------------------------------- #


@router.get("/code/sessions/{session_id}/events", summary="Replay persisted turn events")
async def list_events(
    session_id: str,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    sm, _row = await _load_owned(server, session_id, user)
    events = sm.list_events(session_id, after_seq=after_seq, limit=limit)
    return {
        "session_id": session_id,
        "events": [
            {
                "seq": e.seq,
                "ts": e.ts,
                "kind": e.kind,
                "payload": e.payload,
                "turn_id": e.turn_id,
                "is_error": bool(e.is_error),
            }
            for e in events
        ],
    }


# --------------------------------------------------------------------------- #
# Turn execution
# --------------------------------------------------------------------------- #


def _permission_view(suspended: Any) -> dict[str, Any]:
    if suspended is None:
        return {}
    data = suspended.payload if hasattr(suspended, "payload") else suspended
    options = getattr(suspended, "options", None) or []
    view: dict[str, Any] = {
        "runner": getattr(suspended, "runner", ""),
        "tool_name": getattr(suspended, "tool_name", ""),
        "tool_kind": getattr(suspended, "tool_kind", ""),
        "title": "",
        "options": [],
    }
    if isinstance(data, dict):
        view["title"] = str(data.get("title") or data.get("summary") or "")
        view["detail"] = str(data.get("description") or data.get("detail") or "")
        raw_options = data.get("options") or []
        if isinstance(raw_options, list):
            for opt in raw_options:
                if isinstance(opt, dict):
                    view["options"].append(
                        {
                            "id": str(opt.get("id") or opt.get("optionId") or ""),
                            "name": str(opt.get("name") or opt.get("label") or opt.get("id") or ""),
                            "kind": str(opt.get("kind") or ""),
                        }
                    )
    for opt in options:
        if isinstance(opt, dict):
            oid = str(opt.get("id") or opt.get("optionId") or "")
            if oid and all(o["id"] != oid for o in view["options"]):
                view["options"].append(
                    {"id": oid, "name": str(opt.get("name") or oid), "kind": str(opt.get("kind") or "")}
                )
    view["raw"] = _safe_payload(data if isinstance(data, dict) else {})
    return view


def _render_attachments(
    row: Any,
    wt_mgr: WorktreeManager,
    names: list[str],
    *,
    per_file_bytes: int = 64 * 1024,
    total_bytes: int = 128 * 1024,
) -> str:
    """Build a prompt block inlining previously uploaded text files."""
    if not names:
        return ""
    wt = wt_mgr.get(row.session_id)
    base = wt.path if wt is not None else row.cwd
    sections: list[str] = []
    budget = total_bytes
    for rel in names:
        rel = str(rel).lstrip("/").replace("\\", "/")
        if not rel or rel.startswith("..") or os.path.isabs(rel) or ".." in rel.split("/"):
            continue
        full = os.path.normpath(os.path.join(base, rel))
        if not full.startswith(os.path.normpath(base) + os.sep) or not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as fh:
                content = fh.read(per_file_bytes + 1)
        except OSError:
            continue
        truncated = len(content) > per_file_bytes
        content = content[:per_file_bytes]
        budget -= len(content)
        if budget < 0:
            break
        sections.append(
            f"--- 附件: {rel}"
            + ("（过长，已截断）" if truncated else "")
            + f" ---\n{content}"
        )
    if not sections:
        return ""
    return (
        "以下是本轮附带的项目文件（相对工作区路径，请用文件工具读取完整内容）：\n"
        + "\n\n".join(sections)
    )


def _ensure_sandbox_runner(
    *,
    service: Any,
    rt_mgr: RuntimeManager,
    wt_mgr: WorktreeManager,
    row: Any,
    session_id: str,
) -> str:
    """Ensure a sandbox container + per-session ACP runner exist.

    Returns the runner name to pass to the ACP service. The runner command is
    rewritten to ``docker exec -i <container> <orig>`` so the coding CLI runs
    inside the sandbox. The worktree (or session cwd) is bind-mounted at
    ``/workspace`` inside the container.
    """
    from harness_agent.acp.models import ACPRunnerConfig

    session_runner = f"{row.runner}__sandbox__{session_id}"
    base = service.config.runners.get(row.runner)
    if base is None:
        raise HTTPException(status_code=400, detail=f"runner '{row.runner}' not configured")

    # Determine the workspace path to mount (worktree if bound, else cwd).
    wt = wt_mgr.get(session_id)
    worktree_path = wt.path if wt is not None else row.cwd

    model = str((row.meta or {}).get("model") or "").strip()
    rt_row = rt_mgr.create(
        session_id=session_id,
        worktree_path=worktree_path,
        runner=row.runner,
        model=model or None,
    )
    container_name = rt_mgr._container_name(session_id)  # noqa: SLF001

    if session_runner not in service.config.runners:
        exec_args = ["exec", "-i"]
        env = dict(base.env)
        # Env-driven runners honour the per-session model as an override.
        model_env = _RUNNER_MODEL_ENV.get(row.runner)
        if model_env and model:
            env[model_env] = model
        for k, v in env.items():
            exec_args += ["-e", f"{k}={v}"]
        exec_args += [container_name, base.command, *base.args]
        service.config.runners[session_runner] = ACPRunnerConfig(
            enabled=True,
            command="docker",
            args=exec_args,
            env={},  # env already baked into docker exec -e flags
            trusted=base.trusted,
            tool_parse_mode=base.tool_parse_mode,
            stdio_buffer_limit_bytes=base.stdio_buffer_limit_bytes,
        )
    return session_runner


async def _apply_policy(
    *,
    service: Any,
    policy: PolicyEngine,
    approval_repo: Any,
    session_runner: str,
    session_id: str,
    turn_id: str,
    result: dict[str, Any],
    on_message: Any,
    sink: EventSink,
    user_id: int,
) -> dict[str, Any]:
    """Evaluate policy on a suspended permission request.

    * ``allow`` — auto-pick the affirmative option and resume.
    * ``deny``  — auto-pick the negative option and resume.
    * ``ask``   — persist an approval record and leave it for the user.
    """
    suspended = result.get("suspended_permission")
    if suspended is None:
        return result

    tool_name = getattr(suspended, "tool_name", "") or ""
    tool_kind = getattr(suspended, "tool_kind", "") or ""
    decision = policy.evaluate(tool_name=tool_name, tool_kind=tool_kind)
    action = decision["action"]

    # Persist an audit record of this permission request.
    payload = {
        "tool_name": tool_name,
        "tool_kind": tool_kind,
        "policy_action": action,
        "policy_reason": decision["reason"],
    }
    approval = approval_repo.create(
        request_id=f"apr_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        turn_id=turn_id,
        tool_name=tool_name,
        tool_kind=decision["tool_kind"],
        payload=payload,
    )

    if action == "ask":
        sink.submit(
            session_id, "policy_ask",
            {"approval_id": approval.id, "reason": decision["reason"]},
            turn_id=turn_id,
        )
        return result  # surface to user unchanged

    # auto allow / deny: pick the matching option and resume.
    options = getattr(suspended, "options", None) or []
    target = None
    keywords = ("allow", "approve", "yes", "accept") if action == "allow" \
        else ("deny", "reject", "no", "cancel")
    for opt in options:
        if isinstance(opt, dict):
            name = str(opt.get("name") or opt.get("label") or opt.get("id") or "").lower()
            if any(k in name for k in keywords):
                target = str(opt.get("id") or opt.get("optionId") or "")
                break
    if not target and options:
        target = str(options[0].get("id") or options[0].get("optionId") or "")

    if not target:
        sink.submit(session_id, "policy_error",
                    {"text": f"no option to auto-{action} permission"}, turn_id=turn_id)
        return result

    sink.submit(
        session_id, f"policy_{action}",
        {"approval_id": approval.id, "option_id": target, "reason": decision["reason"]},
        turn_id=turn_id,
    )
    try:
        conv = await service.get_session(session_id, session_runner)
        if conv is None or not getattr(conv, "acp_session_id", None):
            return result
        resumed = await service.resume_permission(
            acp_session_id=conv.acp_session_id,
            option_id=target,
            on_message=on_message,
        )
        approval_repo.resolve(approval.id, target, user_id)
        return resumed
    except Exception:  # noqa: BLE001
        logger.exception("policy auto-%s resume failed for %s", action, session_id)
        return result


async def _run_turn(
    *,
    server: Any,
    sm: SessionManager,
    sink: EventSink,
    rt_mgr: RuntimeManager,
    wt_mgr: WorktreeManager,
    approval_repo: Any,
    row: Any,
    rec: dict[str, Any],
    session_id: str,
    body: PromptBody,
    queue: asyncio.Queue,
) -> None:
    service = _service(server, row.user_id)
    if _driver_mode() == "direct" and not _use_sandbox():
        # Drive the CLI installed in this container; no sandbox container.
        session_runner = row.runner
    else:
        session_runner = _ensure_sandbox_runner(
            service=service, rt_mgr=rt_mgr, wt_mgr=wt_mgr, row=row, session_id=session_id,
        )
    _register_runner_secrets(sink, service, session_runner)
    policy = PolicyEngine(server.services.settings_repo, row.user_id)
    turn_id = uuid.uuid4().hex

    if _driver_mode() == "direct":
        await _run_turn_direct(
            sm=sm, sink=sink, rt_mgr=rt_mgr, wt_mgr=wt_mgr,
            approval_repo=approval_repo, row=row, rec=rec, session_id=session_id,
            body=body, queue=queue, service=service, session_runner=session_runner,
            policy=policy, turn_id=turn_id,
        )
        return

    async def on_message(payload: Any, _is_last: bool) -> None:
        safe = _safe_payload(payload)
        if safe.get("type") == "text":
            safe["text"] = _strip_runner_notices(safe.get("text"))
        await queue.put(safe)
        kind = str(safe.get("type") or "agent_update")
        sink.submit(session_id, kind, safe, turn_id=turn_id)

    try:
        # ---- permission resume branch (existing in-memory conversation) ----
        if body.option_id:
            bound = await service.get_session(session_id, session_runner)
            if bound is None:
                sink.submit(
                    session_id, "turn_error", {"text": "no active ACP session"},
                    turn_id=turn_id, is_error=True,
                )
                await queue.put({"type": "error", "text": "no active ACP session"})
                await queue.put({"__final__": True, "status": "error"})
                return
            sink.submit(
                session_id, "permission_resolved",
                {"option_id": body.option_id.strip()}, turn_id=turn_id,
            )
            result = await service.resume_permission(
                acp_session_id=bound.acp_session_id,
                option_id=body.option_id.strip(),
                on_message=on_message,
            )
            await _finalize(sm, sink, queue, session_id, turn_id, result)
            return

        # ---- normal prompt branch ----
        prompt_text = body.text or ""
        sink.submit(session_id, "user_prompt", {"type": "user_prompt", "text": prompt_text},
                    turn_id=turn_id)
        sm.bump_turns(session_id)
        sm.mark_running(session_id)

        # Restart recovery: process restarted (no in-memory ACP conversation)
        # but persisted history exists -> recreate CLI context from text replay.
        effective_text = prompt_text
        if not rec.get("replay_done", True) and not rec.get("started"):
            prefix = sm.build_replay_prefix(session_id)
            if prefix:
                effective_text = f"{prefix}\n\n[当前消息]\n{prompt_text}"
                logger.info("session %s: replaying text history into fresh CLI", session_id)
        rec["replay_done"] = True

        # S7: inline uploaded files (already stored under uploads/) as a
        # context block so the agent need not guess where to find them.
        attachment_block = _render_attachments(row, wt_mgr, body.attachments)
        if attachment_block:
            effective_text = f"{effective_text}\n\n{attachment_block}".strip()

        first_turn = not rec.get("started")
        rec["started"] = True

        async def _turn(restart: bool) -> dict[str, Any]:
            return await service.run_turn(
                thread_id=session_id,
                runner=session_runner,
                prompt_blocks=[{"type": "text", "text": effective_text}],
                cwd=row.cwd,
                on_message=on_message,
                restart=restart,
                require_existing=not restart,
            )

        try:
            result = await _turn(first_turn)
        except Exception as exc:  # noqa: BLE001 - binding lost retry, then surface
            lost = "no bound ACP session" in str(exc) or "no longer active" in str(exc)
            if first_turn or not lost:
                rec["started"] = False if lost else rec.get("started", False)
                raise
            logger.warning("ACP binding lost for %s, restarting session", session_id)
            result = await _turn(True)

        # ---- S6 policy pre-judgement on permission requests ----
        if result.get("status") == "permission_required":
            result = await _apply_policy(
                service=service,
                policy=policy,
                approval_repo=approval_repo,
                session_runner=session_runner,
                session_id=session_id,
                turn_id=turn_id,
                result=result,
                on_message=on_message,
                sink=sink,
                user_id=row.user_id,
            )

        # Capture ACP session id for diagnostics when available.
        try:
            conv = await service.get_session(session_id, session_runner)
            if conv is not None and getattr(conv, "acp_session_id", None):
                sm.bind_acp(session_id, conv.acp_session_id)
        except Exception:  # noqa: BLE001
            pass

        await _finalize(sm, sink, queue, session_id, turn_id, result)
    except Exception as exc:  # noqa: BLE001 - surface to the UI stream
        logger.exception("ACP turn failed for session %s", session_id)
        sm.mark_idle(session_id)
        sink.submit(session_id, "turn_error", {"text": str(exc)},
                    turn_id=turn_id, is_error=True)
        await _flush_sink(sink)
        await queue.put({"__final__": True, "status": "error", "text": str(exc)})


async def _run_turn_direct(
    *,
    sm: Any,
    sink: Any,
    rt_mgr: Any,
    wt_mgr: Any,
    approval_repo: Any,
    row: Any,
    rec: dict[str, Any],
    session_id: str,
    body: Any,
    queue: asyncio.Queue,
    service: Any,
    session_runner: str,
    policy: Any,
    turn_id: str,
) -> None:
    """Drive the coding CLI directly (no ACP) so thoughts reach the UI."""
    from octop.infra.coding.direct_agent import DirectAgent, permission_view

    cfg = service.config.runners.get(session_runner)
    if cfg is None:
        raise RuntimeError(f"runner {session_runner!r} is not configured")
    command = [cfg.command, *list(cfg.args or [])]
    env = dict(getattr(cfg, "env", None) or {})

    agent = _DIRECT_AGENTS.get(session_id)
    if agent is None:
        agent = DirectAgent(command=command, cwd=row.cwd, env=env, runner=row.runner)
        try:
            await agent.start()
        except Exception as exc:  # noqa: BLE001
            logger.exception("direct agent start failed for %s", session_id)
            sm.mark_idle(session_id)
            sink.submit(session_id, "turn_error", {"text": str(exc)},
                        turn_id=turn_id, is_error=True)
            await _flush_sink(sink)
            await queue.put({"__final__": True, "status": "error", "text": str(exc)})
            return
        _DIRECT_AGENTS[session_id] = agent
    rec["queue"] = queue

    buffer: dict[str, str] = {"text": ""}

    async def on_event(payload: dict[str, Any]) -> None:
        safe = _safe_payload(payload)
        kind = str(safe.get("type") or "agent_update")
        if kind == "text":
            safe["text"] = _strip_runner_notices(safe.get("text"))
        if kind == "text_delta":
            buffer["text"] += str(safe.get("text") or "")
        await queue.put(safe)
        sink.submit(session_id, kind, safe, turn_id=turn_id)

    async def on_permission(params: dict[str, Any]) -> str:
        view = permission_view(params)
        tool_name = str(view.get("tool_name") or "")
        tool_kind = str(view.get("tool_kind") or "")
        decision = policy.evaluate(tool_name=tool_name, tool_kind=tool_kind)
        action = decision["action"]
        options = list(view.get("options") or [])
        approval = approval_repo.create(
            request_id=f"apr_{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            turn_id=turn_id,
            tool_name=tool_name,
            tool_kind=decision["tool_kind"],
            payload={
                "tool_name": tool_name,
                "tool_kind": tool_kind,
                "policy_action": action,
                "policy_reason": decision["reason"],
                "options": options,
            },
        )
        if action in ("allow", "deny"):
            keywords = ("allow", "approve", "yes", "accept") if action == "allow" \
                else ("deny", "reject", "no", "cancel")
            target = ""
            for opt in options:
                name = str(opt.get("name") or "").lower()
                if any(k in name for k in keywords):
                    target = str(opt.get("id") or "")
                    break
            if not target and options:
                target = str(options[0].get("id") or "")
            sink.submit(session_id, f"policy_{action}",
                        {"approval_id": approval.id, "option_id": target,
                         "reason": decision["reason"]}, turn_id=turn_id)
            if target:
                approval_repo.resolve(approval.id, target, row.user_id)
                return target
            return str(options[0].get("id") or "") if options else ""

        sink.submit(session_id, "permission_request", view, turn_id=turn_id)
        await _flush_sink(sink)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        rec["pending_perm"] = fut
        await queue.put({
            "__final__": True,
            "status": "permission_required",
            "permission": view,
        })
        chosen = await fut
        approval_repo.resolve(approval.id, str(chosen), row.user_id)
        return str(chosen)

    text = body.text or ""
    if not rec.get("replay_done", True) and not rec.get("started"):
        prefix = sm.build_replay_prefix(session_id)
        if prefix:
            text = f"{prefix}\n\n[当前消息]\n{text}"
    rec["replay_done"] = True
    rec["started"] = True

    attachment_block = _render_attachments(row, wt_mgr, body.attachments)
    if attachment_block:
        text = f"{text}\n\n{attachment_block}".strip()

    sink.submit(session_id, "user_prompt",
                {"type": "user_prompt", "text": body.text or ""}, turn_id=turn_id)
    sm.bump_turns(session_id)
    sm.mark_running(session_id)

    try:
        result = await agent.prompt(text, on_event=on_event, on_permission=on_permission)
    except Exception as exc:  # noqa: BLE001
        logger.exception("direct turn failed for %s", session_id)
        sm.mark_idle(session_id)
        sink.submit(session_id, "turn_error", {"text": str(exc)},
                    turn_id=turn_id, is_error=True)
        await _flush_sink(sink)
        await queue.put({"__final__": True, "status": "error", "text": str(exc)})
        return

    final_text = (buffer["text"] or "").strip()
    if final_text:
        sink.submit(session_id, "agent_message",
                    {"type": "text", "text": final_text}, turn_id=turn_id)
    stop = str(result.get("stopReason") or result.get("stop_reason") or "")
    status = "cancelled" if stop == "cancelled" else "completed"
    sm.mark_idle(session_id)
    sink.submit(session_id, "turn_final", {"status": status}, turn_id=turn_id)
    await _flush_sink(sink)
    payload: dict[str, Any] = {"__final__": True, "status": status}
    if final_text:
        payload["event"] = {"type": "text", "text": final_text}
    await queue.put(payload)


async def _attach_generator(queue: asyncio.Queue, session_id: str) -> Any:
    """Stream the remainder of a suspended (permission) turn."""
    try:
        while True:
            item = await queue.get()
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            if item.get("__final__"):
                break
    finally:
        _streams.pop(session_id, None)


async def _finalize(
    sm: SessionManager,
    sink: EventSink,
    queue: asyncio.Queue,
    session_id: str,
    turn_id: str,
    result: dict[str, Any],
) -> None:
    status = result.get("status", "completed")
    payload: dict[str, Any] = {"__final__": True, "status": status}

    event = result.get("event")
    if isinstance(event, dict):
        if event.get("type") == "text":
            event = dict(event)
            event["text"] = _strip_runner_notices(event.get("text"))
        payload["event"] = _safe_payload(event)
        text = event.get("text")
        if event.get("type") == "text" and isinstance(text, str) and text.strip():
            sink.submit(session_id, "agent_message", _safe_payload(event), turn_id=turn_id)
    elif event is not None:
        payload["event"] = {"type": "raw", "text": str(event)}

    if status == "permission_required":
        suspended = result.get("suspended_permission")
        permission = _permission_view(suspended)
        payload["permission"] = permission
        sink.submit(session_id, "permission_request", permission, turn_id=turn_id)
        sink.submit(session_id, "turn_final", {"status": status}, turn_id=turn_id)
        sm.mark_awaiting(session_id)
    elif status == "cancelled":
        sink.submit(session_id, "turn_cancelled", {"status": status}, turn_id=turn_id)
        sm.mark_idle(session_id)
    else:
        sink.submit(session_id, "turn_final", {"status": status}, turn_id=turn_id)
        sm.mark_idle(session_id)

    await _flush_sink(sink)
    await queue.put(payload)


@router.post("/code/sessions/{session_id}/prompt", summary="Stream a turn (SSE)")
async def stream_turn(
    session_id: str,
    body: PromptBody = Body(...),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
):
    sm, row = await _load_owned(server, session_id, user)
    if row.status == "closed":
        raise HTTPException(status_code=409, detail="session is closed")
    if session_id in _streams:
        raise HTTPException(status_code=409, detail="a turn is already streaming for this session")
    if not body.option_id and not (body.text or "").strip():
        raise HTTPException(status_code=400, detail="prompt text is required")

    rec = _runtime_rec(row)
    _, sink, rt_mgr, wt_mgr = await _components(server)
    if body.option_id and rec.get("pending_perm") is not None and rec.get("queue") is not None:
        fut = rec["pending_perm"]
        if not fut.done():
            fut.set_result(body.option_id.strip())
            return StreamingResponse(
                _attach_generator(rec["queue"], session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

    approval_repo = server.services.approval_repo
    queue: asyncio.Queue = asyncio.Queue()
    _streams[session_id] = queue
    task = asyncio.create_task(
        _run_turn(
            server=server, sm=sm, sink=sink, rt_mgr=rt_mgr, wt_mgr=wt_mgr,
            approval_repo=approval_repo,
            row=row, rec=rec, session_id=session_id, body=body, queue=queue,
        )
    )

    async def generator():
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("__final__"):
                    break
        finally:
            _streams.pop(session_id, None)
            if not task.done():
                task.cancel()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/code/sessions/{session_id}/cancel", summary="Cancel the running turn")
async def cancel_turn(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    _sm, row = await _load_owned(server, session_id, user)
    session_runner = f"{row.runner}__sandbox__{session_id}"
    agent = _DIRECT_AGENTS.get(session_id)
    if agent is not None:
        try:
            await agent.cancel()
            return {"cancelled": True}
        except Exception:  # noqa: BLE001
            logger.exception("direct cancel failed for %s", session_id)
            return {"cancelled": False}
    try:
        service = _service(server, row.user_id)
        ok = await service.cancel_turn(thread_id=session_id, runner=session_runner)
    except Exception:  # noqa: BLE001
        logger.exception("cancel failed for %s", session_id)
        ok = False
    return {"cancelled": bool(ok)}


@router.get("/code/sessions/{session_id}/patch", summary="Export worktree diff patch")
async def export_patch(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    """Return the unified diff of all changes in the session's worktree.

    Used by the Code page review surface before the user closes the session
    (keep / commit / discard).
    """
    _sm, _row = await _load_owned(server, session_id, user)
    _, _sink, _rt_mgr, wt_mgr = await _components(server)
    patch = wt_mgr.diff_patch(session_id)
    return {"session_id": session_id, "patch": patch}


@router.get("/code/sessions/{session_id}/files", summary="List workspace files")
async def list_session_files(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    query: str = Query("", description="optional substring filter"),
    limit: int = Query(300, ge=1, le=2000),
) -> dict[str, Any]:
    """List files in the session workspace so the composer can '@'-mention them."""
    _sm, row = await _load_owned(server, session_id, user)
    _, _sink, _rt_mgr, wt_mgr = await _components(server)
    wt = wt_mgr.get(session_id)
    base_dir = wt.path if wt is not None else row.cwd

    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
        ".next", ".cache", ".mypy_cache", ".pytest_cache", ".ruff_cache", "uploads",
    }
    needle = (query or "").strip().lower()
    found: list[dict[str, str]] = []
    try:
        for root, dirs, files in os.walk(base_dir):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), base_dir)
                if needle and needle not in rel.lower():
                    continue
                found.append({"name": name, "path": rel})
                if len(found) >= limit:
                    raise StopIteration
    except StopIteration:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("workspace scan failed for %s: %s", session_id, exc)

    found.sort(key=lambda item: item["path"])
    return {"cwd": base_dir, "files": found[:limit]}


@router.post("/code/sessions/{session_id}/files", summary="Upload files into the session worktree")
async def upload_session_files(
    session_id: str,
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
    files: list[UploadFile] = File(..., description="Text files to place under uploads/"),
) -> dict[str, Any]:
    """Persist uploaded planning/spec files into the session worktree.

    Files land under ``uploads/`` and are referenced by their relative path in
    the next prompt's ``attachments``; the agent reads them with its tools.
    """
    _sm, row = await _load_owned(server, session_id, user)
    _, _sink, _rt_mgr, wt_mgr = await _components(server)
    wt = wt_mgr.get(session_id)
    base_dir = wt.path if wt is not None else row.cwd
    upload_dir = os.path.join(base_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    saved: list[dict[str, Any]] = []
    for up in files:
        name = os.path.basename(up.filename or "").strip()
        if not _SAFE_NAME_RE.match(name):
            raise HTTPException(status_code=400, detail=f"invalid file name: {name!r}")
        ext = os.path.splitext(name)[1].lower()
        if ext not in _UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"file type not allowed: {ext}")
        data = await up.read(_UPLOAD_MAX_BYTES + 1)
        if len(data) > _UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=413, detail=f"file too large (max {_UPLOAD_MAX_BYTES} bytes)")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail=f"binary file not supported: {name}") from None
        with open(os.path.join(upload_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        saved.append({"name": name, "path": f"uploads/{name}", "size": len(data)})
    return {"files": saved}


# --------------------------------------------------------------------------- #
# S6 approval endpoints
# --------------------------------------------------------------------------- #


class ResolveApprovalBody(BaseModel):
    option_id: str = ""
    decision: str = ""  # "allow" | "deny" — informational, the option_id drives the harness


@router.get("/code/approvals", summary="List pending approval requests")
async def list_approvals(
    session_id: str = Query("", description="filter by session"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    sm, _sink, _rt_mgr, _wt_mgr = await _components(server)
    approval_repo = server.services.approval_repo
    rows = approval_repo.list_pending(session_id=session_id or None)
    # filter to sessions the user can access
    visible = []
    for a in rows:
        row = sm.get(a.session_id)
        if row is not None and sm.can_access(row, user_id=user.id, is_admin=_is_admin(user)):
            visible.append({
                "id": a.id,
                "request_id": a.request_id,
                "session_id": a.session_id,
                "turn_id": a.turn_id,
                "tool_name": a.tool_name,
                "tool_kind": a.tool_kind,
                "payload": a.payload,
                "created_at": a.created_at,
            })
    return {"approvals": visible}


@router.post("/code/approvals/{approval_id}/resolve", summary="Resolve an approval request")
async def resolve_approval(
    approval_id: int,
    body: ResolveApprovalBody = Body(...),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    sm, _sink, _rt_mgr, _wt_mgr = await _components(server)
    approval_repo = server.services.approval_repo
    approval = approval_repo.get_by_id(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="approval not found")
    row = sm.get(approval.session_id)
    if row is None or not sm.can_access(row, user_id=user.id, is_admin=_is_admin(user)):
        raise HTTPException(status_code=403, detail="forbidden")

    option_id = (body.option_id or "").strip()
    if not option_id:
        raise HTTPException(status_code=400, detail="option_id is required")

    # Best-effort: resume the suspended permission in the harness.
    resumed = False
    sink = _sink
    turn_id = approval.turn_id

    async def _on_resume_message(payload: Any, _is_last: bool) -> None:
        safe = _safe_payload(payload)
        if safe.get("type") == "text":
            safe["text"] = _strip_runner_notices(safe.get("text"))
        kind = str(safe.get("type") or "agent_update")
        sink.submit(approval.session_id, kind, safe, turn_id=turn_id)

    try:
        service = _service(server, row.user_id)
        session_runner = f"{row.runner}__sandbox__{approval.session_id}"
        conv = await service.get_session(approval.session_id, session_runner)
        acp_sid = getattr(conv, "acp_session_id", None) if conv is not None else None
        if conv is not None and acp_sid:
            await service.resume_permission(
                acp_session_id=acp_sid, option_id=option_id,
                on_message=_on_resume_message,
            )
            resumed = True
    except Exception:  # noqa: BLE001
        logger.exception("resume permission failed for approval %s", approval_id)

    approval_repo.resolve(approval.id, option_id, user.id)
    return {"resolved": True, "resumed": resumed, "id": approval.id}


@router.get("/code/policy", summary="Get the effective permission policy matrix")
async def get_policy(
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> dict[str, Any]:
    policy = PolicyEngine(server.services.settings_repo, user.id)
    return {"matrix": policy.matrix()}
