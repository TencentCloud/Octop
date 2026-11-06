"""Built-in tool: ``request_secret_file``.

Like ``ask_user_question``, the real implementation is the human — the
dashboard renders a dedicated secret card and the browser submits the
credential straight to an authenticated API, which writes it into the agent's
auth directory. The model only passes *metadata* (path + prompt) and only
receives a filled / cancelled / failed status — never the secret.

The function body is the fail-safe fallback for runs without an interactive
HITL channel (cron, headless IM). It must never block or collect input.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.tools import StructuredTool
from pydantic import Field

from octop.infra.agents.secret_file.paths import REQUEST_SECRET_FILE_TOOL

# Returned when no interactive channel is attached. Phrased as an instruction
# so the model recovers instead of retrying.
HEADLESS_FALLBACK = (
    "No interactive credential card is available in this run. Do not call "
    "request_secret_file again. Tell the user which file inside the agent auth "
    "directory they must create manually, then stop and wait."
)

_PATH_HELP = (
    "File name or path RELATIVE to the agent's auth directory, e.g. "
    "'hr.token' or 'feishu/app.token' (skill docs may also write it as "
    "'auth/hr.token'). Absolute host paths, '~', '..' segments, other agents' "
    "directories and shared HOME locations are rejected. NEVER put the "
    "credential itself into any argument. For a CLI requiring '~/.example/credentials', "
    "use 'cli-home/.example/credentials'; for XDG config use "
    "'cli-home/.config/example/config.json'."
)

_PROMPT_HELP = (
    "Short user-facing explanation of what this credential is for and how to "
    "obtain it (e.g. where to copy the token from). Shown on the fill-in card."
)

_DESCRIPTION = (
    "Ask the user to securely provide a credential file (token / key / cookie) "
    "that a skill or CLI needs. Pauses the turn and shows a secure input card; "
    "the user types the secret, the browser submits it directly to the server, "
    "and the server writes it into this agent's private auth directory "
    "(POSIX 0600/0700). You only learn whether the file was filled or "
    "cancelled, plus the final path — the secret itself is never visible to "
    "you, so never ask the user to paste it into the chat instead. "
    "Request one credential at a time; wait for filled or cancelled before asking for another. "
    "After the card reports filled, run the skill's own verification command "
    "(e.g. `whoami`) using the returned path. Prefer the CLI's credential-file or "
    "config-dir option. On the default local shell, if it requires a user HOME, "
    'run only that CLI with `env HOME="$OCTOP_CLI_HOME" '
    'XDG_CONFIG_HOME="$OCTOP_CLI_HOME/.config" <cli> ...`; also map its XDG '
    "data/state/cache directories there if used. Never change the platform HOME "
    "or put a secret into the command."
)


def build_secret_file_tools() -> list[Any]:
    """Return the ``request_secret_file`` host tool (mounted per agent)."""

    async def request_secret_file(
        path: Annotated[str, Field(description=_PATH_HELP, max_length=200)],
        prompt: Annotated[str, Field(description=_PROMPT_HELP, max_length=500)],
        title: Annotated[
            str | None,
            Field(description="Optional 1-5 word card title.", max_length=60),
        ] = None,
    ) -> str:
        del path, prompt, title  # The human answers on behalf of this tool.
        return HEADLESS_FALLBACK

    return [
        StructuredTool.from_function(
            coroutine=request_secret_file,
            name=REQUEST_SECRET_FILE_TOOL,
            description=_DESCRIPTION,
        ),
    ]


__all__ = ["HEADLESS_FALLBACK", "build_secret_file_tools"]
