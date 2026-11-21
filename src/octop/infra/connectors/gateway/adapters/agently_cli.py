"""Agent Mail CLI gateway with isolated credentials and two-phase writes."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from octop.i18n import tr
from octop.infra.connectors.gateway.cli_dirs import resolve_cli_config_key
from octop.infra.connectors.gateway.cli_runner import resolve_binary, run_cli
from octop.infra.utils.paths import PathLayout

_KIND = "agently-cli"
_MAX_FILE = 10 * 1024 * 1024
_TEXT: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": 1024 * 1024}
_BOOL = {"type": "boolean"}
_FILTERS: dict[str, Any] = {
    "dir": {"type": "string", "enum": ["inbox", "sent", "trash", "spam"]},
    "after": _TEXT,
    "before": _TEXT,
    "cursor": _TEXT,
    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    "has_attachments": _BOOL,
    "is_unread": _BOOL,
}
_WRITE: dict[str, Any] = {
    "body": _TEXT,
    "body_format": {"type": "string", "enum": ["plain", "html"]},
    "cc": _TEXT,
    "bcc": _TEXT,
    "attachments": _TEXT,
    "confirmation_token": _TEXT,
}
# Only these commands/flags are exposed. No raw argv, --confirmed, or body-file.
_COMMANDS: dict[str, tuple[list[str], dict[str, Any], list[str]]] = {
    "agently_me": (["+me"], {}, []),
    "agently_list": (["message", "+list"], _FILTERS, []),
    "agently_read": (["message", "+read"], {"id": _TEXT}, ["id"]),
    "agently_search": (
        ["message", "+search"],
        {
            **_FILTERS,
            "q": _TEXT,
            "from": _TEXT,
            "to": _TEXT,
            "search_in": {
                "type": "string",
                "enum": ["SEARCH_IN_ALL", "SEARCH_IN_SUBJECT", "SEARCH_IN_CONTENT"],
            },
        },
        [],
    ),
    "agently_send": (
        ["message", "+send"],
        {
            **_WRITE,
            "to": _TEXT,
            "subject": {**_TEXT, "maxLength": 4096},
            "body_format": {"type": "string", "enum": ["plain", "html", "markdown"]},
        },
        ["to", "subject", "body"],
    ),
    "agently_reply": (
        ["message", "+reply"],
        {**_WRITE, "id": _TEXT, "reply_all": _BOOL},
        ["id", "body"],
    ),
    "agently_forward": (
        ["message", "+forward"],
        {**_WRITE, "id": _TEXT, "to": _TEXT, "include_attachments": _BOOL},
        ["id", "to"],
    ),
    "agently_trash": (
        ["message", "+trash"],
        {"id": _TEXT, "confirmation_token": _TEXT},
        ["id"],
    ),
    "agently_delete": (
        ["message", "+delete"],
        {"id": _TEXT, "confirmation_token": _TEXT},
        ["id"],
    ),
    "agently_upload": (
        ["attachment", "+upload"],
        {
            "filename": {**_TEXT, "maxLength": 200},
            "content_base64": {**_TEXT, "maxLength": ((_MAX_FILE + 2) // 3) * 4},
        },
        ["filename", "content_base64"],
    ),
    "agently_download": (["attachment", "+download"], {"msg": _TEXT, "att": _TEXT}, ["msg", "att"]),
}
_WRITES = {"agently_send", "agently_reply", "agently_forward", "agently_trash", "agently_delete"}
_WRITES_ALLOWED: ContextVar[bool] = ContextVar("agently_writes_allowed", default=True)


@contextmanager
def write_scope(*, allowed: bool) -> Iterator[None]:
    """Allow or reject Agent Mail write tools for the current task."""
    token = _WRITES_ALLOWED.set(allowed)
    try:
        yield
    finally:
        _WRITES_ALLOWED.reset(token)


def writes_allowed() -> bool:
    return _WRITES_ALLOWED.get()


def write_tool_names(mcp_server_name: str) -> list[str]:
    from octop.infra.agents.plugins.plugin_tool_names import sanitize_plugin_tool_name

    used: set[str] = set()
    return [
        sanitize_plugin_tool_name(f"{mcp_server_name}_{name}", used=used)
        for name in sorted(_WRITES)
    ]


def _confirm_when(req: Any) -> bool:
    tool_call = getattr(req, "tool_call", None) or {}
    raw_args = tool_call.get("args") if isinstance(tool_call, dict) else {}
    token = raw_args.get("confirmation_token") if isinstance(raw_args, dict) else None
    return isinstance(token, str) and bool(token.strip())


def write_interrupt_on(mcp_server_names: list[str]) -> dict[str, Any]:
    """Always interrupt the confirm call, even when global HITL is off."""
    entry: dict[str, Any] = {"allowed_decisions": ["approve", "reject"], "when": _confirm_when}
    return {name: dict(entry) for server in mcp_server_names for name in write_tool_names(server)}


def list_tools() -> list[dict[str, Any]]:
    tools = []
    for name, (_, properties, required) in _COMMANDS.items():
        description = (
            tr(f"connector.agently.tools.{name}") + " " + tr("connector.agently.untrusted")
        )
        if name in _WRITES:
            description += " " + tr("connector.agently.confirmation")
        fields = {key: dict(value) for key, value in properties.items()}
        for key in ("to", "cc", "bcc"):
            if key in fields and name in _WRITES:
                fields[key]["description"] = tr("connector.agently.recipients")
        if "attachments" in fields:
            fields["attachments"]["description"] = tr("connector.agently.attachment_handles")
        tools.append(
            {
                "name": name,
                "description": description,
                "inputSchema": {
                    "type": "object",
                    "properties": fields,
                    "required": required,
                    "additionalProperties": False,
                },
            }
        )
    return tools


def prepare_env(creds: dict[str, Any]) -> dict[str, str]:
    key = resolve_cli_config_key(creds)
    config_dir = PathLayout.from_env().connector_cli_instance_dir(_KIND, key).resolve()
    env = {key: value for key, value in os.environ.items() if not key.startswith("AGENTLY_")}
    # CLI 1.0.18 forces workspace=default when CONFIG_DIR is set, while keychain
    # ignores that directory. Native workspaces isolate both config and keychain.
    env["AGENTLY_WORKSPACE"] = "octop-" + hashlib.sha256(str(config_dir).encode()).hexdigest()[:24]
    return env


def _run(creds: dict[str, Any], command: list[str], *, cwd: Path | None = None) -> dict[str, Any]:
    locale = str(creds.get("_locale") or "en")
    try:
        raw = run_cli(
            [resolve_binary(_KIND), *command],
            env=prepare_env(creds),
            cwd=str(cwd) if cwd is not None else None,
            timeout_s=60,
        )
    except (OSError, ValueError):
        # CLI errors can contain instructions to bypass this gateway using the shell.
        raise ValueError(tr("connector.agently.command_failed", locale)) from None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(tr("connector.agently.invalid_output", locale)) from None
    if (
        isinstance(payload, dict)
        and command[-1:] == ["--dry-run"]
        and isinstance(payload.get("calls"), list)
    ):
        return {"ok": True, "data": payload}
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        raise ValueError(tr("connector.agently.command_failed", locale))
    return payload


def read_auth_status(creds: dict[str, Any]) -> dict[str, Any]:
    data = _run(creds, ["auth", "status"]).get("data")
    if not isinstance(data, dict) or not isinstance(data.get("logged_in"), bool):
        raise ValueError(tr("connector.agently.invalid_output", str(creds.get("_locale") or "en")))
    return data


def probe_credentials(creds: dict[str, Any]) -> None:
    data = read_auth_status(creds)
    if not data["logged_in"] or data.get("token_status") == "expired":
        raise ValueError(tr("connector.agently.login_required", str(creds.get("_locale") or "en")))


def _validate(name: str, args: dict[str, Any]) -> None:
    if name not in _COMMANDS or not isinstance(args, dict):
        raise ValueError(tr("connector.agently.invalid_arguments"))
    _, fields, required = _COMMANDS[name]
    if args.keys() - fields.keys() or any(key not in args for key in required):
        raise ValueError(tr("connector.agently.invalid_arguments"))
    for key, value in args.items():
        spec = fields[key]
        typ = {"string": str, "integer": int, "boolean": bool}[spec["type"]]
        valid = type(value) is typ
        if valid and typ is str:
            valid = "\0" not in value and spec.get("minLength", 0) <= len(value) <= spec.get(
                "maxLength", 1024 * 1024
            )
        if valid and typ is int:
            valid = spec.get("minimum", 0) <= value <= spec.get("maximum", 50)
        if "enum" in spec:
            valid = valid and value in spec["enum"]
        if not valid:
            raise ValueError(tr("connector.agently.invalid_arguments"))


def _attachment_file(root: Path, handle: str) -> Path:
    # Opaque handles never select arbitrary host or credential files.
    if not re.fullmatch(r"[a-zA-Z0-9_-]+/[^/\\]+", handle):
        raise ValueError(tr("connector.agently.invalid_attachment"))
    file = root / handle
    if not file.resolve().is_relative_to(root.resolve()) or file.is_symlink() or not file.is_file():
        raise ValueError(tr("connector.agently.invalid_attachment"))
    if file.stat().st_size > _MAX_FILE:
        raise ValueError(tr("connector.agently.invalid_attachment"))
    return file


def _upload(creds: dict[str, Any], args: dict[str, Any], root: Path) -> dict[str, Any]:
    filename = args["filename"]
    if filename in {".", ".."} or any(ch in filename for ch in "/\\:\r\n"):
        raise ValueError(tr("connector.agently.invalid_attachment"))
    try:
        content = base64.b64decode(args["content_base64"], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError(tr("connector.agently.invalid_attachment")) from exc
    if not content or len(content) > _MAX_FILE:
        raise ValueError(tr("connector.agently.invalid_attachment"))
    folder = Path(tempfile.mkdtemp(dir=root))
    try:
        file = folder / filename
        file.write_bytes(content)
        payload = _run(creds, ["attachment", "+upload", f"--file=./{filename}"], cwd=folder)
        payload["file"] = file.relative_to(root).as_posix()
        return payload
    except Exception:
        shutil.rmtree(folder)
        raise


def _download(creds: dict[str, Any], args: dict[str, Any], root: Path) -> dict[str, Any]:
    folder = Path(tempfile.mkdtemp(dir=root))
    try:
        payload = _run(
            creds,
            [
                "attachment",
                "+download",
                f"--msg={args['msg']}",
                f"--att={args['att']}",
                "--output=.",
            ],
            cwd=folder,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError(tr("connector.agently.invalid_output"))
        # Use actual files, never trust an upstream saved_to path to read host files.
        files = list(folder.iterdir())
        if len(files) != 1:
            raise ValueError(tr("connector.agently.invalid_attachment"))
        file = _attachment_file(root, files[0].relative_to(root).as_posix())
        data.pop("saved_to", None)
        payload["file"] = file.relative_to(root).as_posix()
        payload["content_base64"] = base64.b64encode(file.read_bytes()).decode("ascii")
        return payload
    except Exception:
        shutil.rmtree(folder)
        raise


def _purge_expired_confirmations(folder: Path) -> None:
    if not folder.is_dir():
        return
    now = time.time()
    for path in folder.iterdir():
        if not path.is_file() or not re.fullmatch(r"[0-9a-f]{48}", path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if float(data.get("expires") or 0) < now:
                path.unlink()
        except (OSError, TypeError, ValueError):
            continue


def _write(
    creds: dict[str, Any], name: str, args: dict[str, Any], command: list[str], root: Path
) -> dict[str, Any]:
    # Upstream confirmation is optional, including for permanent deletion. Always
    # preview locally; consume the instance-bound approval before any real write.
    locale = str(creds.get("_locale") or "en")
    if not writes_allowed():
        raise ValueError(tr("connector.agently.write_not_allowed", locale))
    parameters = {key: value for key, value in args.items() if key != "confirmation_token"}
    folder = root.parent / "confirmations"
    token = args.get("confirmation_token")
    if token is None:
        _run(creds, [*command, "--dry-run"], cwd=root)
        folder.mkdir(mode=0o700, exist_ok=True)
        _purge_expired_confirmations(folder)
        token = secrets.token_hex(24)
        with os.fdopen(
            os.open(folder / token, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            "w",
            encoding="utf-8",
        ) as file:
            json.dump({"tool": name, "args": parameters, "expires": time.time() + 300}, file)
        summary = {"action": name.removeprefix("agently_"), **parameters}
        if "id" in summary:
            summary["message_id"] = summary.pop("id")
        for field in ("to", "cc", "bcc"):
            if field in summary:
                summary[field] = [item.strip() for item in summary[field].split(",")]
        summary["attachment_count"] = len(parameters.get("attachments", "").splitlines())
        return {
            "ok": True,
            "data": {
                "confirmation_required": True,
                "confirmation_token": token,
                "expires_in": 300,
                "summary": summary,
            },
        }
    if not re.fullmatch(r"[0-9a-f]{48}", token):
        raise ValueError(tr("connector.agently.invalid_arguments"))
    path = folder / token
    try:
        approval = json.loads(path.read_text(encoding="utf-8"))
        if (
            approval["tool"] != name
            or approval["args"] != parameters
            or approval["expires"] < time.time()
        ):
            raise ValueError
        path.unlink()  # Atomic claim: replay/concurrent confirmation cannot write twice.
    except (OSError, ValueError, KeyError):
        raise ValueError(tr("connector.agently.invalid_arguments")) from None
    payload = _run(creds, command, cwd=root)
    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise ValueError(tr("connector.agently.invalid_output"))
    if data.get("confirmation_required") is True:
        upstream_token = data.get("confirmation_token")
        if not isinstance(upstream_token, str) or not upstream_token or "\0" in upstream_token:
            raise ValueError(tr("connector.agently.invalid_output"))
        payload = _run(creds, [*command, f"--confirmation-token={upstream_token}"], cwd=root)
        confirmed_data = payload.get("data")
        if (
            not isinstance(confirmed_data, dict)
            or confirmed_data.get("confirmation_required") is True
        ):
            raise ValueError(tr("connector.agently.invalid_output"))
    return payload


def call_tool(creds: dict[str, Any], name: str, args: dict[str, Any]) -> str:
    _validate(name, args)
    root = (
        PathLayout.from_env().ensure_connector_cli_instance_dir(
            _KIND, resolve_cli_config_key(creds)
        )
        / "attachments"
    )
    root.mkdir(exist_ok=True)
    if name == "agently_upload":
        payload = _upload(creds, args, root)
    elif name == "agently_download":
        payload = _download(creds, args, root)
    else:
        command = list(_COMMANDS[name][0])
        for key, value in args.items():
            if key == "confirmation_token":
                continue
            flag = key.replace("_", "-")
            if key == "attachments":
                handles = value.splitlines()
                if len(handles) > 50:
                    raise ValueError(tr("connector.agently.invalid_attachment"))
                for handle in handles:
                    file = _attachment_file(root, handle)
                    command.append(f"--attachment=./{file.relative_to(root).as_posix()}")
            elif key in {"to", "cc", "bcc"} and name in _WRITES:
                recipients = [item.strip() for item in value.split(",")]
                if not all(recipients):
                    raise ValueError(tr("connector.agently.invalid_arguments"))
                command.extend(f"--{flag}={item}" for item in recipients)
            elif isinstance(value, bool):
                if value:
                    command.append(f"--{flag}")
            else:
                command.append(f"--{flag}={value}")
        payload = (
            _write(creds, name, args, command, root)
            if name in _WRITES
            else _run(creds, command, cwd=root)
        )
    # Keep the raw response (including security warnings and confirmation summaries)
    # inside an explicitly untrusted data envelope.
    return json.dumps(
        {"notice": tr("connector.agently.untrusted"), "result": payload}, ensure_ascii=False
    )
