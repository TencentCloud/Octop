"""Generate Codex/Claude-style SKILL.md files from steps."""

from __future__ import annotations

import re

from octop_browser.record.models import StepsDocument


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "recorded-browser-workflow"


def _md_escape(value: str) -> str:
    return value.replace("`", "\\`")


class SkillGenerator:
    def __init__(self, steps: StepsDocument, skill_name: str | None = None) -> None:
        self.steps = steps
        self.skill_name = _slug(skill_name or self._infer_name())

    def _infer_name(self) -> str:
        if self.steps.start_url:
            return (
                "recorded-"
                + re.sub(r"^https?://", "", self.steps.start_url).split("/")[0]
            )
        return "recorded-browser-workflow"

    def generate(self) -> str:
        title = self.skill_name.replace("-", " ").title()
        inputs = self._inputs_md()
        workflow = self._workflow_md()
        verification = self._verification_md()
        start_url = _md_escape(self.steps.start_url)
        target_hint = (
            "Always take a fresh `octop-browser dom-tree --level structured` snapshot "
            "before clicking or filling if the page may have changed."
        )
        privacy_note = (
            "Do not log passwords, tokens, one-time codes, cookies, session values, "
            "or other secrets. Keep recorded values as variables when possible."
        )
        return (
            f"""---
name: {self.skill_name}
description: Use this skill to replay the recorded browser workflow from {start_url or "the recorded start page"}.
allowed-tools: Bash
---

# {title}

## When to use

Use this skill when the user asks to repeat the recorded browser workflow. Provide any required inputs listed below.

## Required inputs

{inputs}

## Workflow

{workflow}

## Target matching guidance

When locating elements, prefer this order:

1. `data-testid`, `data-test`, or `data-cy`.
2. Role plus visible or accessible name.
3. Label text or placeholder.
4. Stable CSS selector from the recording.
5. Coordinates only as a last resort.

{target_hint}

## Verification

{verification}

## Error handling

- If an element cannot be found, refresh the DOM snapshot and search for a semantically equivalent label or button.
- If a submit button is disabled, check required fields.
- If the page layout has changed significantly, stop and report the blocker instead of clicking random coordinates.

## Privacy notes

{privacy_note}

## Recording reference

- Recording ID: `{self.steps.recording_id}`
- Start URL: `{start_url}`
""".rstrip()
            + "\n"
        )

    def _inputs_md(self) -> str:
        if not self.steps.inputs:
            return "- No variable inputs were detected. Confirm with the user before replaying if values should change."
        lines = []
        for item in self.steps.inputs:
            name = item.get("name", "value")
            kind = item.get("kind", "string")
            example = item.get("example")
            suffix = f" Example: `{_md_escape(str(example))}`." if example else ""
            lines.append(f"- `{name}` ({kind}): required.{suffix}")
        return "\n".join(lines)

    def _workflow_md(self) -> str:
        lines = []
        for idx, step in enumerate(self.steps.steps, start=1):
            if step.kind == "open":
                lines.append(
                    f"{idx}. Open `{_md_escape(step.url or self.steps.start_url)}`."
                )
            elif step.kind == "fill":
                target = (
                    (step.target or {}).get("name")
                    or (step.target or {}).get("label")
                    or "the recorded field"
                )
                lines.append(
                    f"{idx}. Fill `{_md_escape(str(target))}` with `{_md_escape(step.value or '')}`."
                )
            elif step.kind == "select":
                target = (
                    (step.target or {}).get("name")
                    or (step.target or {}).get("label")
                    or "the recorded select"
                )
                lines.append(
                    f"{idx}. Select `{_md_escape(str(target))}` with `{_md_escape(step.value or '')}`."
                )
            elif step.kind == "set_checked":
                target = (
                    (step.target or {}).get("name")
                    or (step.target or {}).get("label")
                    or "the recorded checkbox"
                )
                lines.append(
                    f"{idx}. Set `{_md_escape(str(target))}` checked to `{_md_escape(step.value or '')}`."
                )
            elif step.kind == "click":
                target = (
                    (step.target or {}).get("name")
                    or (step.target or {}).get("text")
                    or "the recorded element"
                )
                extra = ""
                if step.expect and step.expect.get("urlContains"):
                    extra = f" Wait until the URL contains `{_md_escape(str(step.expect['urlContains']))}`."
                lines.append(f"{idx}. Click `{_md_escape(str(target))}`.{extra}")
            elif step.kind == "press":
                lines.append(f"{idx}. Press `{_md_escape(step.key or '')}`.")
            elif step.kind == "navigate":
                lines.append(f"{idx}. Navigate to `{_md_escape(step.url or '')}`.")
            elif step.kind == "new_tab":
                lines.append(
                    f"{idx}. Open a new tab at `{_md_escape(step.url or '')}`."
                )
            elif step.kind == "scroll_to":
                parts = (step.value or "0,0").split(",", 1)
                y = parts[1] if len(parts) > 1 else "0"
                lines.append(f"{idx}. Scroll to vertical position `{_md_escape(y)}`.")
            else:
                lines.append(f"{idx}. {step.description or step.kind}.")
        return (
            "\n".join(lines)
            or "1. No steps were detected; inspect the recording before use."
        )

    def _verification_md(self) -> str:
        if not self.steps.verification:
            return "No reliable verification condition was inferred. Confirm the expected success state with the user."
        lines = []
        for item in self.steps.verification:
            if item.get("type") == "url_contains":
                lines.append(
                    f"- The URL contains `{_md_escape(str(item.get('value', '')))}`."
                )
            else:
                lines.append(f"- `{_md_escape(str(item))}`")
        return "\n".join(lines)
