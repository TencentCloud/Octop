"""Format HITL approval cards for IM channels."""

from __future__ import annotations

import json
import re
import string
from typing import Any

from octop.i18n import tool_display_name, tr
from octop.infra.utils.locale import Locale, normalize_locale

# Tool whose HITL interrupt is a question for the user rather than an approval.
ASK_USER_TOOL_NAME = "ask_user_question"

# Tool whose HITL interrupt collects a secret through the dashboard's masked
# card; IM channels only get a read-only notice.
REQUEST_SECRET_INPUT_TOOL_NAME = "request_secret_input"

# Tool whose HITL interrupt collects a multi-field secure form through the
# dashboard's modal; IM channels likewise only get a read-only notice.
# (Name duplicated from the tool module: importing the agents package here
# would cycle through its submit module, which imports this one.)
REQUEST_SECURE_FORM_TOOL_NAME = "request_secure_form"

# Option keys shown in IM cards: a) b) c) d)
_OPTION_KEYS = string.ascii_lowercase

# `1`, `a`, `1,3`, `a c`, `b、d` — a pure selection reply.
_SELECTION_RE = re.compile(r"^[0-9a-z]+(?:[,，、/\s]+[0-9a-z]+)*$")


def normalize_hitl_request(raw: Any) -> dict[str, Any]:
    """Unwrap LangGraph ``Interrupt`` envelopes so ``action_requests`` is top-level.

    LangGraph v2 streams interrupts as ``{"value": HITLRequest, "id": "..."}``
    (or a dict that still has ``value`` after ``model_dump``). Hosts that look
    for top-level ``action_requests`` would otherwise register an empty pause.
    """
    current: Any = raw
    for _ in range(3):
        if not isinstance(current, dict):
            return raw if isinstance(raw, dict) else {}
        if isinstance(current.get("action_requests"), list):
            return current
        nested = current.get("value")
        if isinstance(nested, dict):
            current = nested
            continue
        break
    return raw if isinstance(raw, dict) else {}


def _parse_action_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def parse_action_requests(raw: dict[str, Any]) -> list[dict[str, Any]]:
    requests = normalize_hitl_request(raw).get("action_requests")
    if not isinstance(requests, list):
        return []
    out: list[dict[str, Any]] = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "tool")
        args = _parse_action_args(item.get("args"))
        description = item.get("description")
        row: dict[str, Any] = {"name": name, "args": args}
        if isinstance(description, str) and description.strip():
            row["description"] = description.strip()
        out.append(row)
    return out


def parse_review_configs(raw: dict[str, Any]) -> list[dict[str, Any]] | None:
    configs = normalize_hitl_request(raw).get("review_configs")
    if not isinstance(configs, list):
        return None
    out = [c for c in configs if isinstance(c, dict)]
    return out or None


def is_ask_action_requests(action_requests: list[dict[str, Any]]) -> bool:
    """True when this HITL pause is an ``ask_user_question`` interrupt."""
    return any(isinstance(a, dict) and a.get("name") == ASK_USER_TOOL_NAME for a in action_requests)


def is_secret_input_action_requests(action_requests: list[dict[str, Any]]) -> bool:
    """True when this HITL pause collects a secret via the masked card."""
    return any(
        isinstance(a, dict) and a.get("name") == REQUEST_SECRET_INPUT_TOOL_NAME
        for a in action_requests
    )


def is_secure_form_action_requests(action_requests: list[dict[str, Any]]) -> bool:
    """True when this HITL pause collects a multi-field secure form."""
    return any(
        isinstance(a, dict) and a.get("name") == REQUEST_SECURE_FORM_TOOL_NAME
        for a in action_requests
    )


def is_sensitive_action_requests(action_requests: list[dict[str, Any]]) -> bool:
    """True when this pause collects user secrets (masked card or form).

    Such pauses are decided only through their dedicated submit flows — never
    the generic approval, slash, respond, or bypass paths.
    """
    return is_secret_input_action_requests(action_requests) or is_secure_form_action_requests(
        action_requests
    )


def extract_secure_form_summary(
    action_requests: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Read-only facts about a secure-form pause for the IM notice card.

    Field values are never present (the pause only carries the schema), and
    IM renders nothing interactive — just what the form is about and where it
    must be filled.
    """
    for action in action_requests:
        if not isinstance(action, dict) or action.get("name") != REQUEST_SECURE_FORM_TOOL_NAME:
            continue
        args = action.get("args")
        if not isinstance(args, dict):
            args = {}
        fields = args.get("fields")
        routing = args.get("routing")
        return {
            "title": str(args.get("title") or "").strip() or None,
            "prompt": str(args.get("prompt") or "").strip(),
            "field_count": len(fields) if isinstance(fields, list) else 0,
            "routing_kind": (
                str(routing.get("kind") or "").strip() if isinstance(routing, dict) else ""
            ),
        }
    return None


def extract_secret_input_request(
    action_requests: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Normalized ``request_secret_input`` args for the matching pause, if any."""
    for action in action_requests:
        if not isinstance(action, dict) or action.get("name") != REQUEST_SECRET_INPUT_TOOL_NAME:
            continue
        args = action.get("args")
        if not isinstance(args, dict):
            args = {}
        return {
            "slot": str(args.get("slot") or "").strip(),
            "prompt": str(args.get("prompt") or "").strip(),
            "title": str(args.get("title") or "").strip() or None,
        }
    return None


def extract_questions(action_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pull the normalized ``questions`` list out of an ask action request."""
    for action in action_requests:
        if not isinstance(action, dict) or action.get("name") != ASK_USER_TOOL_NAME:
            continue
        args = action.get("args")
        if not isinstance(args, dict):
            continue
        raw = args.get("questions")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except ValueError:
                continue
            raw = parsed
        if not isinstance(raw, list):
            continue
        return [q for q in raw if isinstance(q, dict)]
    return []


def _options_of(question: dict[str, Any]) -> list[dict[str, Any]]:
    raw = question.get("options")
    if not isinstance(raw, list):
        return []
    return [o for o in raw if isinstance(o, dict)]


def _format_args(args: dict[str, Any], *, limit: int = 400) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False, indent=2)
    except TypeError:
        text = str(args)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def format_hitl_card(
    record_action_requests: list[dict[str, Any]],
    *,
    pending_id: str,
    locale: str | Locale,
) -> str:
    """Render the IM card for a paused turn (approval, question, secret, or form)."""
    if is_secret_input_action_requests(record_action_requests):
        return format_secret_input_card(
            record_action_requests,
            pending_id=pending_id,
            locale=locale,
        )
    if is_secure_form_action_requests(record_action_requests):
        return format_secure_form_card(
            record_action_requests,
            pending_id=pending_id,
            locale=locale,
        )
    if is_ask_action_requests(record_action_requests):
        return format_ask_card(
            extract_questions(record_action_requests),
            pending_id=pending_id,
            locale=locale,
        )
    loc = normalize_locale(str(locale))
    lines = [
        tr("slash.hitl.card_title", loc),
        "",
        tr("slash.hitl.card_intro", loc),
        "",
    ]
    for idx, action in enumerate(record_action_requests, start=1):
        name = str(action.get("name") or "tool")
        label = tool_display_name(name, loc)
        args = action.get("args")
        if not isinstance(args, dict):
            args = {}
        args_text = _format_args(args)
        lines.append(tr("slash.hitl.action_line", loc, index=idx, name=label))
        if args_text.strip() and args_text.strip() != "{}":
            lines.append(f"```\n{args_text}\n```")
        desc = action.get("description")
        if isinstance(desc, str) and desc.strip():
            lines.append(desc.strip())
        lines.append("")
    lines.extend(
        [
            tr("slash.hitl.card_footer", loc),
            tr("slash.hitl.card_pending_id", loc, pending_id=pending_id),
        ]
    )
    return "\n".join(lines).strip()


def format_ask_card(
    questions: list[dict[str, Any]],
    *,
    pending_id: str,
    locale: str | Locale,
    question_index: int = 0,
) -> str:
    """Render one ``ask_user_question`` item as a plain-text IM card.

    IM clients do not provide the dashboard's interactive multi-question card.
    Showing one item at a time also lets letter/number replies map unambiguously
    to the visible option list.
    """
    loc = normalize_locale(str(locale))
    lines = [tr("slash.ask.card_title", loc), ""]
    total = len(questions)
    if total == 0:
        lines.extend(
            [
                tr("slash.ask.open_hint", loc),
                "",
                tr("slash.ask.card_footer", loc),
                tr("slash.ask.card_pending_id", loc, pending_id=pending_id),
            ]
        )
        return "\n".join(lines).strip()

    current = min(max(question_index, 0), total - 1)
    if total > 1:
        lines.extend(
            [
                tr("slash.ask.progress", loc, current=current + 1, total=total),
                "",
            ]
        )

    question = questions[current]
    idx = current + 1
    text = str(question.get("question") or "").strip()
    header = question.get("header")
    if isinstance(header, str) and header.strip():
        lines.append(
            tr(
                "slash.ask.question_line_headed",
                loc,
                index=idx,
                header=header.strip(),
                question=text,
            )
        )
    else:
        lines.append(tr("slash.ask.question_line", loc, index=idx, question=text))
    lines.append("")
    options = _options_of(question)
    for opt_idx, option in enumerate(options):
        if opt_idx >= len(_OPTION_KEYS):
            break
        label = str(option.get("label") or "").strip()
        description = str(option.get("description") or "").strip()
        opt = _OPTION_KEYS[opt_idx]
        if description:
            lines.append(
                tr(
                    "slash.ask.option_line_desc",
                    loc,
                    opt=opt,
                    label=label,
                    description=description,
                )
            )
        else:
            lines.append(tr("slash.ask.option_line", loc, opt=opt, label=label))
        # A blank paragraph is preserved by plain-text IM clients such as Weixin,
        # while a single newline may be collapsed into one dense line.
        lines.append("")
    if not options:
        lines.append(tr("slash.ask.open_hint", loc))
        lines.append("")
    elif question.get("multi_select"):
        lines.append(tr("slash.ask.multi_hint", loc))
        lines.append("")
    lines.extend(
        [
            tr("slash.ask.card_footer", loc),
            tr("slash.ask.card_pending_id", loc, pending_id=pending_id),
        ]
    )
    return "\n".join(lines).strip()


def format_secret_input_card(
    action_requests: list[dict[str, Any]],
    *,
    pending_id: str,
    locale: str | Locale,
) -> str:
    """Render the read-only IM notice for a secret-input pause.

    IM clients cannot host the masked card, and secrets must never travel
    through an IM conversation — the user is pointed at the dashboard.
    """
    loc = normalize_locale(str(locale))
    request = extract_secret_input_request(action_requests) or {}
    slot = request.get("slot") or "—"
    prompt = request.get("prompt") or ""
    lines = [tr("slash.secret_input.card_title", loc), ""]
    if prompt:
        lines.append(prompt)
        lines.append("")
    lines.append(tr("slash.secret_input.slot_line", loc, slot=slot))
    lines.append("")
    lines.extend(
        [
            tr("slash.secret_input.card_footer", loc),
            tr("slash.secret_input.card_pending_id", loc, pending_id=pending_id),
        ]
    )
    return "\n".join(lines).strip()


def format_secure_form_card(
    action_requests: list[dict[str, Any]],
    *,
    pending_id: str,
    locale: str | Locale,
) -> str:
    """Render the read-only IM notice for a secure-form pause.

    Same contract as the secret-input notice: the modal cannot open in IM and
    the values must never travel through the conversation, so the card only
    points at the dashboard and waits for its submit (or the pause TTL).
    """
    loc = normalize_locale(str(locale))
    summary = extract_secure_form_summary(action_requests) or {}
    lines = [tr("slash.secure_form.card_title", loc), ""]
    prompt = str(summary.get("prompt") or "")
    if prompt:
        lines.append(prompt)
        lines.append("")
    lines.append(tr("slash.secure_form.fields_line", loc, count=summary.get("field_count") or 0))
    routing_key = {
        "env": "slash.secure_form.routing_env",
        "vault": "slash.secure_form.routing_vault",
    }.get(str(summary.get("routing_kind") or ""))
    if routing_key:
        lines.append(tr(routing_key, loc))
    lines.append("")
    lines.extend(
        [
            tr("slash.secure_form.card_footer", loc),
            tr("slash.secure_form.card_pending_id", loc, pending_id=pending_id),
        ]
    )
    return "\n".join(lines).strip()


def _resolve_selection(token: str, options: list[dict[str, Any]]) -> str | None:
    """Map one reply token (``a`` / ``1``) to an option label, if it matches."""
    if not options:
        return None
    index: int | None = None
    if token.isdigit():
        index = int(token) - 1
    elif len(token) == 1 and token in _OPTION_KEYS:
        index = _OPTION_KEYS.index(token)
    if index is None or not (0 <= index < len(options)):
        return None
    label = str(options[index].get("label") or "").strip()
    return label or None


def parse_ask_reply(
    text: str,
    questions: list[dict[str, Any]],
    *,
    locale: str | Locale,
) -> str:
    """Turn a plain IM reply into the ``respond`` message sent back to the model.

    Selection shorthands (``a``, ``2``, ``a,c``) are expanded to their option
    labels so the model sees the semantic choice rather than an index. Anything
    else is forwarded verbatim — free-form answers, counter-proposals and even
    topic switches are all valid replies, and the model handles them better than
    any parser could.
    """
    loc = normalize_locale(str(locale))
    stripped = text.strip()
    # Shorthand selection only makes sense against a single option list.
    if len(questions) == 1:
        options = _options_of(questions[0])
        candidate = stripped.lower()
        if options and _SELECTION_RE.match(candidate):
            tokens = [t for t in re.split(r"[,，、/\s]+", candidate) if t]
            labels = [_resolve_selection(t, options) for t in tokens]
            picked = [label for label in labels if label]
            if picked and len(picked) == len(tokens):
                if not questions[0].get("multi_select") and len(picked) > 1:
                    picked = picked[:1]
                return tr("slash.ask.answered_prefix", loc) + "; ".join(picked)

    return stripped


__all__ = [
    "ASK_USER_TOOL_NAME",
    "REQUEST_SECRET_INPUT_TOOL_NAME",
    "REQUEST_SECURE_FORM_TOOL_NAME",
    "extract_questions",
    "extract_secret_input_request",
    "extract_secure_form_summary",
    "format_ask_card",
    "format_hitl_card",
    "format_secret_input_card",
    "format_secure_form_card",
    "is_ask_action_requests",
    "is_secret_input_action_requests",
    "is_secure_form_action_requests",
    "is_sensitive_action_requests",
    "normalize_hitl_request",
    "parse_action_requests",
    "parse_ask_reply",
    "parse_review_configs",
]
