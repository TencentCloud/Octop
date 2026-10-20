"""Built-in tool: ``browser_use``.

Thin wrapper around :func:`octop_browser.browser_tool` exposing it as a
LangChain async ``@tool``. ``octop-browser`` drives Chrome via the
Chrome DevTools Protocol with profile-based login persistence -- see
https://pypi.org/project/octop-browser/ for the underlying API.

``octop-browser`` ships as a required dependency of
``octop-harness``, so ``browser_use`` is always available as a
default tool. Chrome or Chromium must be present at runtime for the
tool to actually drive a browser; missing-binary errors are surfaced
back to the model as a JSON envelope rather than raising. The lazy
``ImportError`` branch below is kept defensive in case a downstream
packager strips the dependency.

Two ergonomic features are layered on top of the raw ``browser_tool``
output:

1. **Per-profile action history.** Each call appends ``{action, success}``
   to a ring buffer keyed by ``profile`` (size 50, last 20 surfaced). The
   buffer is embedded in every JSON payload as ``action_history`` /
   ``total_actions_in_session``, giving the LLM enough self-context to
   notice "I just clicked this button three times in a row" without a
   separate middleware. The buffer is in-process only; it resets on agent
   restart and is intentionally not persisted (cheap, transient,
   per-session).

2. **Multimodal screenshot result.** Successful ``screenshot`` calls
   return a list of LangChain content blocks --
   ``[image_block, text_block]`` -- so multimodal-capable models receive
   the PNG inline alongside a short summary (path, size, dimensions, page
   url/title). All other actions and any failure still return a JSON
   string for stable downstream parsing.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from langchain_core.tools import tool
from pydantic import Field

from octop_harness.backends.utils import DEFENSIVE_OP_ERRORS

# ---- per-profile action history (ring buffer) ------------------------------

_HISTORY_MAX = 50
_HISTORY_WINDOW = 20
_history: dict[str, list[dict[str, Any]]] = {}
_TAB_LINE_RE = re.compile(r"^\[(?P<tab_id>[^\]]+)\]\s+.*?\s—\s(?P<url>\S.*)$")


def _record_history(profile: str, action: str, success: bool) -> int:
    """Append an entry to the profile's history; return the post-append size."""
    bucket = _history.setdefault(profile, [])
    bucket.append({"action": action, "success": success})
    if len(bucket) > _HISTORY_MAX:
        del bucket[: len(bucket) - _HISTORY_MAX]
    return len(bucket)


def _history_payload(profile: str) -> dict[str, Any]:
    bucket = _history.get(profile, [])
    return {
        "action_history": bucket[-_HISTORY_WINDOW:],
        "total_actions_in_session": len(bucket),
    }


def _reset_history_for_tests() -> None:
    """Clear the in-process history. Test-only helper."""
    _history.clear()


# ---- result formatting -----------------------------------------------------


def _missing_dependency_error() -> str:
    return (
        "Error: browser_use requires the 'octop-browser' package. "
        "It is normally installed as a default dependency of "
        "octop-harness; reinstall the package, or run "
        "`pip install octop-browser` directly. Chrome/Chromium must "
        "also be available at runtime."
    )


def _envelope(
    *,
    action: str,
    profile: str,
    success: bool,
    content: Any,
    error: str | None,
    metrics: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> str:
    """Build the standard JSON envelope returned for non-screenshot actions."""
    payload: dict[str, Any] = {
        "tool": "browser_use",
        "action": action,
        "profile": profile,
        "success": success,
        "content": content,
        "error": error,
        "metrics": metrics or {},
        "metadata": metadata,
        **_history_payload(profile),
    }
    return json.dumps(payload, ensure_ascii=False)


def _screenshot_blocks(
    *,
    profile: str,
    saved_path: str,
    metrics: dict[str, Any],
    metadata: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build ``[image_block, text_block]`` for a successful screenshot.

    The image block follows the same shape as :func:`send_file_to_user`'s output
    so multimodal-aware models (Claude 3.5+, GPT-4o, Gemini) consume it
    directly.
    """
    abs_path = Path(saved_path).expanduser().absolute()
    image_block: dict[str, Any] = {
        "type": "image",
        "source": {
            "type": "url",
            "url": abs_path.as_uri(),
            "media_type": "image/png",
        },
        "filename": abs_path.name,
        "path": str(abs_path),
    }

    md = metadata or {}
    size_kb = metrics.get("screenshot_size_kb")
    width = md.get("width")
    height = md.get("height")
    full_page = bool(md.get("full_page"))
    page_url = str(md.get("url") or "")
    page_title = str(md.get("title") or "")

    qualifiers: list[str] = []
    if size_kb:
        qualifiers.append(f"{size_kb} KB")
    if width and height:
        qualifiers.append(f"{width}x{height}")
    if full_page:
        qualifiers.append("full_page")
    summary = f"Screenshot saved to {abs_path}"
    if qualifiers:
        summary += " (" + ", ".join(qualifiers) + ")"
    lines = [summary]
    if page_title:
        lines.append(f"page_title: {page_title}")
    if page_url:
        lines.append(f"page_url: {page_url}")

    history = _history_payload(profile)
    recent = ", ".join(f"{e['action']}{'' if e['success'] else '!'}" for e in history["action_history"])
    if recent:
        lines.append(f"recent_actions ({history['total_actions_in_session']}): {recent}")

    text_block: dict[str, Any] = {"type": "text", "text": "\n".join(lines)}
    return [image_block, text_block]


# ---- helpers ---------------------------------------------------------------


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Project a octop_browser ``ToolResult`` into a plain dict."""
    metrics = getattr(result, "metrics", None)
    metrics_dict: dict[str, Any] = {}
    if metrics is not None:
        metrics_dict = {
            "duration_ms": getattr(metrics, "duration_ms", 0),
            "estimated_tokens": getattr(metrics, "estimated_tokens", 0),
            "dom_nodes_scanned": getattr(metrics, "dom_nodes_scanned", 0),
            "screenshot_size_kb": getattr(metrics, "screenshot_size_kb", 0),
        }
    return {
        "success": bool(getattr(result, "success", False)),
        "content": getattr(result, "content", ""),
        "error": getattr(result, "error", None),
        "metrics": metrics_dict,
        "metadata": getattr(result, "metadata", None),
    }


def _iter_listed_tabs(
    content: Any,
    metadata: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """Return ``(tab_id, url)`` pairs from ``list_tabs`` output.

    Newer octop-browser versions expose structured tab data in metadata;
    prefer that over parsing the human-readable content because page titles can
    contain the same dash separator used in the fallback text format.
    """
    raw_tabs = (metadata or {}).get("tabs")
    if isinstance(raw_tabs, list):
        tabs_from_metadata: list[tuple[str, str]] = []
        for item in raw_tabs:
            if not isinstance(item, dict):
                continue
            tab_id = item.get("tab_id") or item.get("id")
            url = item.get("url")
            if isinstance(tab_id, str) and isinstance(url, str):
                tabs_from_metadata.append((tab_id, url.strip()))
        if tabs_from_metadata:
            return tabs_from_metadata

    tabs: list[tuple[str, str]] = []
    for raw_line in str(content or "").splitlines():
        match = _TAB_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        tabs.append((match.group("tab_id"), match.group("url").strip()))
    return tabs


def _canonical_url_parts(raw_url: str) -> tuple[str, str, str, str] | None:
    """Return comparable URL parts, or ``None`` for non-HTTP(S) values."""
    try:
        parsed = urlsplit(raw_url.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query_pairs = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    return (
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        urlencode(query_pairs, doseq=True),
    )


def _urls_match_requested_open(requested_url: str, existing_url: str) -> bool:
    """Whether an existing tab satisfies an agent request to open a URL.

    Exact canonical URL matches are reused. Additionally, a request for a
    site's root (for example ``https://weibo.com/``) may be satisfied by a
    same-host redirect/login URL that Chrome already has open.
    """
    requested = _canonical_url_parts(requested_url)
    existing = _canonical_url_parts(existing_url)
    if requested is None or existing is None:
        return False
    if requested == existing:
        return True
    req_scheme, req_host, req_path, req_query = requested
    ex_scheme, ex_host, _, _ = existing
    return req_scheme == ex_scheme and req_host == ex_host and req_path == "/" and not req_query


def _synthetic_reuse_result(
    *,
    action: str,
    tab_id: str,
    requested_url: str,
    matched_url: str,
) -> Any:
    """Build a ToolResult-like object without importing octop_browser models."""
    return SimpleNamespace(
        success=True,
        content=f"Reused existing tab {tab_id} for {requested_url}",
        error=None,
        metrics=SimpleNamespace(
            action=action,
            duration_ms=0,
            estimated_tokens=0,
            dom_nodes_scanned=0,
            screenshot_size_kb=0,
        ),
        metadata={
            "reused_existing_tab": True,
            "tab_id": tab_id,
            "requested_url": requested_url,
            "matched_url": matched_url,
        },
    )


async def _maybe_reuse_open_tab(
    browser_tool: Any,
    *,
    action: str,
    profile: str,
    url: str,
) -> Any | None:
    """Switch to an already-open matching tab instead of opening duplicates.

    This is intentionally implemented in the high-level agent wrapper rather
    than the lower-level ``octop_browser`` API: raw browser automation keeps
    precise ``navigate`` / ``new_tab`` semantics, while chat usage gets
    idempotent "open this site" behavior that survives LLM retries.
    """
    listed = _result_to_dict(await browser_tool(action="list_tabs", profile=profile))
    if not listed["success"]:
        return None
    for tab_id, existing_url in _iter_listed_tabs(
        listed["content"],
        listed["metadata"],
    ):
        if not _urls_match_requested_open(url, existing_url):
            continue
        switched = _result_to_dict(await browser_tool(action="switch_tab", profile=profile, tab_id=tab_id))
        if switched["success"]:
            return _synthetic_reuse_result(
                action=action,
                tab_id=tab_id,
                requested_url=url,
                matched_url=existing_url,
            )
    return None


# ---- action normalization & validation ---------------------------------------

_ACTION_ALIASES: dict[str, str] = {
    "goto": "navigate",
    "snapshot": "screenshot",
    "scroll_down": "scroll",
    "scroll_up": "scroll",
    # Docs sometimes say "start" to bootstrap Chrome — list_tabs lazily opens a session.
    "start": "list_tabs",
}


def _normalize_action(action: str) -> tuple[str, str]:
    """Return ``(normalized_action, original_action)``."""
    return _ACTION_ALIASES.get(action, action), action


def _coalesce_url(
    url: str,
    *,
    target_url: str = "",
    href: str = "",
    query: str = "",
    link: str = "",
    address: str = "",
) -> str:
    for value in (url, target_url, href, query, link, address):
        if value and value.strip():
            return value.strip()
    return ""


def _kwargs_from_candidates(candidates: dict[str, Any]) -> dict[str, Any]:
    """Drop unset optional fields — empty strings and ``None`` are omitted."""
    out: dict[str, Any] = {}
    for key, value in candidates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        out[key] = value
    return out


def _validate_action_params(action: str, kwargs: dict[str, Any]) -> str | None:
    """Return a human-readable error when required kwargs are missing."""
    if action == "navigate" and not kwargs.get("url"):
        return "navigate requires a non-empty `url` (e.g. https://example.com). Pass the full destination URL."
    if action == "click" and not kwargs.get("ref") and not kwargs.get("selector"):
        return "click requires `ref` (from dom_tree) or `selector`."
    if action == "type" and not kwargs.get("text"):
        return "type requires `text` to insert."
    if action == "eval_js" and not kwargs.get("expression"):
        return "eval_js requires `expression` JavaScript to run."
    if action in ("switch_tab", "close_tab") and not kwargs.get("tab_id"):
        return f"{action} requires `tab_id` from list_tabs."
    return None


@tool
async def browser_use(
    action: Annotated[str, Field(description="Browser action, e.g. navigate, screenshot, dom_tree, click.")],
    *,
    profile: Annotated[
        str,
        Field(default="default", description="Browser profile for cookie persistence."),
    ] = "default",
    url: Annotated[
        str,
        Field(
            default="",
            description="Required when action is navigate or new_tab. Full URL starting with https://.",
        ),
    ] = "",
    ref: Annotated[str, Field(default="", description="Element ref from dom_tree, for click/type/hover.")] = "",
    selector: Annotated[str, Field(default="", description="CSS selector fallback for click.")] = "",
    text: Annotated[str, Field(default="", description="Text to type when action is type.")] = "",
    level: Annotated[
        str,
        Field(default="", description="dom_tree detail: minimal, interactive, full, or structured."),
    ] = "",
    direction: Annotated[str, Field(default="", description="Scroll direction: up or down.")] = "",
    amount: Annotated[int | None, Field(default=None, description="Scroll distance in pixels.")] = None,
    expression: Annotated[str, Field(default="", description="JavaScript for eval_js.")] = "",
    tab_id: Annotated[str, Field(default="", description="Tab id from list_tabs for switch_tab/close_tab.")] = "",
    full_page: Annotated[bool | None, Field(default=None, description="Screenshot full scrollable page.")] = None,
    crop: Annotated[bool | None, Field(default=None, description="Crop screenshot to ref element.")] = None,
    path: Annotated[str, Field(default="", description="Output path for screenshot.")] = "",
    kill: Annotated[
        bool | None,
        Field(
            default=None,
            description="For close_session only: also terminate the local Chrome process.",
        ),
    ] = None,
    target_url: Annotated[str, Field(default="", description="Alias for url.")] = "",
    href: Annotated[str, Field(default="", description="Alias for url.")] = "",
    query: Annotated[str, Field(default="", description="Alias for url when opening a page.")] = "",
    link: Annotated[str, Field(default="", description="Alias for url.")] = "",
    address: Annotated[str, Field(default="", description="Alias for url.")] = "",
) -> str | list[dict[str, Any]]:
    """Drive a Chrome browser via the Chrome DevTools Protocol.

    Use this when the user asks you to "open a website", "click a button",
    "fill a form", "scrape a page", or otherwise interact with a real
    browser. Login state is persisted per ``profile`` -- call once with
    ``profile="work"`` to log in interactively, and every later call with
    the same profile will reuse those cookies.

    The ``action`` parameter selects what to do; only the kwargs relevant
    to that action are read, the rest are ignored. Omit unused fields or
    leave them as empty strings.

    Supported actions (most useful subset):

    - ``"navigate"`` (alias: ``"goto"``) -- go to ``url`` (required). In chat
      usage, if the same URL/site is already open in another tab, this tool
      switches to that tab instead of opening a duplicate.
    - ``"dom_tree"`` -- return a token-efficient view of the page. Set
      ``level`` to ``"minimal"`` (~50 tokens), ``"interactive"``
      (~200-500, default), ``"full"`` (~1000-3000), or ``"structured"``
      (JSON). Each interactive element gets a stable ``ref`` like
      ``btn_2`` you can reuse in later actions.
    - ``"click"`` -- click by ``ref`` (preferred) or ``selector``.
    - ``"type"`` -- type ``text`` into the focused / ref'd field.
    - ``"scroll"`` (aliases: ``"scroll_down"``, ``"scroll_up"``) -- scroll the page;
      ``direction`` is ``"up"`` or ``"down"``, ``amount`` is pixels.
    - ``"hover"`` -- hover over the element identified by ``ref``.
    - ``"screenshot"`` (alias: ``"snapshot"``) -- capture the current page. Returns a multimodal
      block list (image + summary text) so vision-capable models see the
      PNG inline. ``full_page=True`` captures beyond the viewport (use
      sparingly; modern pages produce huge images).
    - ``"eval_js"`` -- evaluate ``expression`` in the page and return
      the result.
    - ``"go_back"`` / ``"go_forward"`` / ``"reload"`` -- history
      navigation.
    - ``"new_tab"`` / ``"switch_tab"`` / ``"close_tab"`` /
      ``"list_tabs"`` -- tab management. ``new_tab`` accepts ``url`` and also
      reuses an already-open matching tab instead of opening duplicates;
      ``switch_tab`` / ``close_tab`` accept ``tab_id``.
    - ``"close_session"`` -- close the Chrome session for ``profile``. Set
      ``kill=True`` to also terminate the local Chrome process while keeping
      its profile and login state on disk.

    Returns:
        For ``screenshot`` on success: a list of LangChain multimodal
        content blocks ``[image_block, text_block]``. For everything
        else (and any failure) a JSON string with ``success``, ``content``,
        ``error``, ``metrics``, ``metadata``, and the rolling
        ``action_history`` / ``total_actions_in_session`` for this
        ``profile``. Plain-text error if ``octop-browser`` is not
        installed.
    """
    try:
        from octop_browser import browser_tool
    except ImportError:
        return _missing_dependency_error()

    normalized, original = _normalize_action(action)
    url = _coalesce_url(
        url,
        target_url=target_url,
        href=href,
        query=query,
        link=link,
        address=address,
    )
    if original == "scroll_down" and not direction:
        direction = "down"
    elif original == "scroll_up" and not direction:
        direction = "up"

    candidates: dict[str, Any] = {
        "url": url,
        "ref": ref,
        "selector": selector,
        "text": text,
        "level": level,
        "direction": direction,
        "amount": amount,
        "expression": expression,
        "tab_id": tab_id,
        "full_page": full_page,
        "crop": crop,
        "path": path,
        "kill": kill,
    }
    kwargs = _kwargs_from_candidates(candidates)

    param_err = _validate_action_params(normalized, kwargs)
    if param_err:
        _record_history(profile, original, success=False)
        return _envelope(
            action=original,
            profile=profile,
            success=False,
            content="",
            error=param_err,
            metrics=None,
            metadata=None,
        )

    try:
        result: Any | None = None
        if normalized in {"navigate", "new_tab"} and url:
            result = await _maybe_reuse_open_tab(
                browser_tool,
                action=normalized,
                profile=profile,
                url=url,
            )
        if result is None:
            result = await browser_tool(action=normalized, profile=profile, **kwargs)
    except DEFENSIVE_OP_ERRORS as exc:
        # ``browser_tool`` is meant to fail-soft and return a ToolResult,
        # but defend against unexpected exceptions so the LLM still gets a
        # well-formed envelope and the action is recorded.
        _record_history(profile, original, success=False)
        return _envelope(
            action=original,
            profile=profile,
            success=False,
            content="",
            error=f"{type(exc).__name__}: {exc}",
            metrics=None,
            metadata=None,
        )

    parsed = _result_to_dict(result)
    _record_history(profile, original, success=parsed["success"])

    # Multimodal screenshot block on success only -- failures fall through
    # to the JSON envelope so the error is visible.
    if normalized == "screenshot" and parsed["success"]:
        saved_path = parsed["content"] if isinstance(parsed["content"], str) else ""
        if saved_path and os.path.isfile(saved_path):
            return _screenshot_blocks(
                profile=profile,
                saved_path=saved_path,
                metrics=parsed["metrics"],
                metadata=parsed["metadata"],
            )
        # Fallthrough to JSON if the file isn't there for some reason.

    return _envelope(
        action=original,
        profile=profile,
        success=parsed["success"],
        content=parsed["content"],
        error=parsed["error"],
        metrics=parsed["metrics"],
        metadata=parsed["metadata"],
    )
