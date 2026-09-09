"""Plan brief artifact for Plan → Craft handoff (#616 P5)."""

from __future__ import annotations

from typing import Any

# Minimal HumanMessage text when the dashboard sends plan_brief with no chat bubble.
# Full plan lives in the system hint; this only gives the model a user-turn trigger.
PLAN_EXECUTE_USER_TRIGGER = "Execute the approved plan now."


def format_plan_brief(*, summary: str = "", todos: list[dict[str, Any]] | None = None) -> str:
    """Serialize an approved plan into a Craft-turn brief (markdown)."""
    lines: list[str] = ["## Approved plan", ""]
    text = (summary or "").strip()
    if text:
        lines.extend([text, ""])
    items = todos or []
    if items:
        lines.append("### Steps")
        for idx, raw in enumerate(items, start=1):
            if isinstance(raw, str):
                content = raw.strip()
            elif isinstance(raw, dict):
                content = str(
                    raw.get("content") or raw.get("text") or raw.get("title") or ""
                ).strip()
            else:
                content = ""
            if not content:
                continue
            status = ""
            if isinstance(raw, dict) and raw.get("status"):
                status = f" ({raw['status']})"
            lines.append(f"{idx}. {content}{status}")
        lines.append("")
    lines.append("Execute this plan now.")
    return "\n".join(lines).strip() + "\n"


def parse_plan_brief_steps(brief: str) -> list[str]:
    """Extract numbered step lines from a brief produced by :func:`format_plan_brief`."""
    steps: list[str] = []
    for line in (brief or "").splitlines():
        stripped = line.strip()
        if len(stripped) >= 3 and stripped[0].isdigit() and ". " in stripped[:6]:
            _, _, rest = stripped.partition(". ")
            content = rest.strip()
            if content:
                steps.append(content)
    return steps
