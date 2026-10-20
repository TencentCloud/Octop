"""Turn raw browser events into semantic replay steps."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from octop_browser.record.models import SemanticStep, StepsDocument
from octop_browser.record.url_filter import is_replayable_page_url

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _name(target: dict[str, Any] | None) -> str:
    if not target:
        return ""
    return str(
        target.get("accessibleName")
        or target.get("name")
        or target.get("label")
        or target.get("placeholder")
        or target.get("nameAttr")
        or target.get("id")
        or target.get("text")
        or ""
    ).strip()


def _event_target_id(event: dict[str, Any] | None) -> str:
    if not event:
        return ""
    target_id = event.get("targetId")
    if isinstance(target_id, str) and target_id:
        return target_id
    page = event.get("page")
    if isinstance(page, dict):
        page_target_id = page.get("targetId")
        if isinstance(page_target_id, str) and page_target_id:
            return page_target_id
    return ""


def _compact_target(
    target: dict[str, Any] | None, target_id: str = ""
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if target_id:
        out["targetId"] = target_id
    if not target:
        return out
    for src, dst in (
        ("tag", "tag"),
        ("role", "role"),
        ("type", "type"),
        ("accessibleName", "name"),
        ("name", "name"),
        ("label", "label"),
        ("placeholder", "placeholder"),
        ("id", "id"),
        ("nameAttr", "nameAttr"),
        ("text", "text"),
        ("testId", "testId"),
    ):
        val = target.get(src)
        if val and dst not in out:
            out[dst] = val
    selectors = target.get("selectorCandidates")
    if isinstance(selectors, list) and selectors:
        out["selectorCandidates"] = [str(s) for s in selectors[:5]]
    if target.get("xpath"):
        out["xpath"] = target.get("xpath")
    if target.get("bbox"):
        out["bbox"] = target.get("bbox")
    for key in ("framePath", "shadowPath"):
        value = target.get(key)
        if isinstance(value, list) and value:
            out[key] = [str(v) for v in value]
    return out


def _target_key(target: dict[str, Any] | None) -> str:
    if not target:
        return ""
    parts = [
        str(target.get("role", "")),
        _name(target).lower(),
        str(target.get("nameAttr", "")),
        str(target.get("id", "")),
    ]
    return "|".join(parts)


def _same_target(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if not a or not b:
        return False
    if _target_key(a) and _target_key(a) == _target_key(b):
        return True
    a_sel = set(a.get("selectorCandidates") or [])
    b_sel = set(b.get("selectorCandidates") or [])
    return bool(a_sel & b_sel)


def _step_id(n: int) -> str:
    return f"step_{n:03d}"


def _looks_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value.strip()))


def _stable_input_name(target: dict[str, Any] | None, hay: str) -> str:
    for key in ("nameAttr", "id", "placeholder", "label", "name"):
        raw = str((target or {}).get(key) or "").strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
        if slug and not slug.isdigit():
            return slug[:40]
    raw = re.sub(r"[^a-z0-9]+", "_", hay.strip())
    return raw.strip("_")[:40] or "value"


def _var_for(
    target: dict[str, Any] | None, value: str, used: set[str]
) -> tuple[str, dict[str, Any]]:
    hay = " ".join(
        str((target or {}).get(k, ""))
        for k in ("accessibleName", "name", "label", "placeholder", "nameAttr", "id")
    ).lower()
    search_hints = {
        str((target or {}).get(k, "")).strip().lower()
        for k in ("nameAttr", "id", "placeholder", "accessibleName", "name", "label")
    }
    if value.startswith("{{") and value.endswith("}}"):
        base = "sensitive_value"
        kind = "secret"
        example = ""
    elif "email" in hay or _looks_email(value):
        base = "email"
        kind = "email"
        example = value
    elif (
        "search" in hay
        or "query" in hay
        or "百度" in hay
        or "搜" in hay
        or bool(
            search_hints & {"q", "wd", "word", "query", "search", "keyword", "keywords"}
        )
    ):
        base = "query"
        kind = "string"
        example = value
    elif "date" in hay:
        base = "date"
        kind = "date"
        example = value
    else:
        base = _stable_input_name(target, hay)
        kind = "string"
        example = value
    name = base
    idx = 2
    while name in used:
        name = f"{base}_{idx}"
        idx += 1
    used.add(name)
    info: dict[str, Any] = {"name": name, "kind": kind, "required": True}
    if example:
        info["example"] = example
    return f"{{{{{name}}}}}", info


def _same_fill_step(step: SemanticStep, target: dict[str, Any], value: str) -> bool:
    return (
        step.kind == "fill"
        and step.value == value
        and _same_target(step.target, target)
    )


def _target_tag(target: dict[str, Any] | None) -> str:
    return str((target or {}).get("tag") or "").strip().lower()


def _target_type(target: dict[str, Any] | None) -> str:
    return str((target or {}).get("type") or "").strip().lower()


def _target_role(target: dict[str, Any] | None) -> str:
    return str((target or {}).get("role") or "").strip().lower()


def _is_select_target(target: dict[str, Any] | None) -> bool:
    return _target_tag(target) == "select" or _target_role(target) == "combobox"


def _is_checkable_target(target: dict[str, Any] | None) -> bool:
    role = _target_role(target)
    typ = _target_type(target)
    return role in {"checkbox", "radio", "switch"} or typ in {"checkbox", "radio"}


def _checked_value(event: dict[str, Any]) -> str:
    checked = event.get("checked")
    if isinstance(checked, bool):
        return "true" if checked else "false"
    value = str(event.get("value", "")).strip().lower()
    return "false" if value in {"", "0", "false", "off", "unchecked"} else "true"


def _value_step(
    event: dict[str, Any],
    *,
    target: dict[str, Any],
    raw_target: dict[str, Any] | None,
) -> SemanticStep:
    if _is_checkable_target(raw_target or target):
        return SemanticStep(
            id="",
            kind="set_checked",
            target=target,
            value=_checked_value(event),
            description=f"Set {_name(raw_target) or 'checkbox'} checked",
        )
    if _is_select_target(raw_target or target):
        return SemanticStep(
            id="",
            kind="select",
            target=target,
            value=str(event.get("value", "")),
            description=f"Select {_name(raw_target) or 'option'}",
        )
    return SemanticStep(
        id="",
        kind="fill",
        target=target,
        value=str(event.get("value", "")),
        description=f"Fill {_name(raw_target) or 'field'}",
    )


def _path_hint(url: str | None) -> str | None:
    if not url:
        return None
    try:
        path = urlsplit(url).path
        if path and path != "/":
            bits = [p for p in path.split("/") if p]
            if bits:
                return "/" + bits[-1]
    except ValueError:
        return None
    return None


def _page_url(event: dict[str, Any]) -> str:
    page = event.get("page")
    if isinstance(page, dict) and page.get("url"):
        return str(page["url"])
    return str(event.get("urlAfter") or event.get("url") or "")


def _is_blank_page_click(event: dict[str, Any]) -> bool:
    if event.get("kind") != "click":
        return False
    url = _page_url(event)
    if url != "about:blank":
        return False
    target = event.get("target")
    if not isinstance(target, dict):
        return False
    tag = str(target.get("tag") or "").lower()
    xpath = str(target.get("xpath") or "")
    return tag in {"body", "html"} or xpath in {"/html", "/html/body[1]"}


def _is_low_signal_result_click(event: dict[str, Any]) -> bool:
    """Return true for clicks on large, non-interactive result/content blocks.

    Search result pages and weather cards often emit a click against a generic
    ``div`` containing hundreds of characters. Replaying those clicks is
    unstable and usually irrelevant: the durable user intent is the preceding
    search/navigation, not selecting a dynamic result area.
    """
    if event.get("kind") != "click":
        return False
    target = event.get("target")
    if not isinstance(target, dict):
        return False
    role = str(target.get("role") or "").strip().lower()
    tag = str(target.get("tag") or "").strip().lower()
    if role in {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "menuitem",
        "option",
        "tab",
        "switch",
    }:
        return False
    if tag in {"button", "a", "input", "textarea", "select", "label"}:
        return False
    text = _name(target) or str(target.get("text") or "")
    if len(text) >= 160:
        return True
    selectors = target.get("selectorCandidates")
    return bool(
        tag in {"div", "section", "article", "main", "body", ""}
        and isinstance(selectors, list)
        and selectors
        and all("nth-of-type" in str(s) for s in selectors)
    )


def _scroll_position(event: dict[str, Any]) -> dict[str, float]:
    raw = event.get("scroll")
    if not isinstance(raw, dict):
        return {"x": 0.0, "y": 0.0}

    def as_float(value: object) -> float:
        try:
            return float(value) if isinstance(value, (int, float, str)) else 0.0
        except (TypeError, ValueError):
            return 0.0

    return {"x": as_float(raw.get("x")), "y": as_float(raw.get("y"))}


class SemanticProcessor:
    def __init__(self, recording_id: str, events: list[dict[str, Any]]) -> None:
        self.recording_id = recording_id
        self.events = sorted(events, key=lambda e: int(e.get("seq", 0)))

    def process(self) -> StepsDocument:
        useful = self._filter_events(self.events)
        start_url = self._start_url(useful)
        steps = self._build_steps(useful, start_url)
        steps, inputs = self._infer_variables(steps)
        steps = self._attach_navigation_expectations(steps)
        verification = self._verification(steps)
        return StepsDocument(
            recordingId=self.recording_id,
            startUrl=start_url,
            inputs=inputs,
            steps=steps,
            verification=verification,
        )

    def _filter_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {
            "recorder_installed",
            "page_opened",
            "click",
            "dblclick",
            "input",
            "change",
            "keydown",
            "submit",
            "scroll",
            "navigation",
            "history.pushState",
            "history.replaceState",
            "popstate",
            "hashchange",
        }
        return [e for e in events if e.get("kind") in allowed]

    def _start_url(self, events: list[dict[str, Any]]) -> str:
        for e in events:
            if e.get("kind") == "recorder_installed":
                seq = int(e.get("seq", 0))
                # addScriptToEvaluateOnNewDocument also fires after a recorded
                # navigation. A late installer event describes the destination
                # page, not the workflow's starting page.
                if seq > 1:
                    continue
                page = e.get("page")
                if isinstance(page, dict) and page.get("url"):
                    return str(page["url"])
                if e.get("url"):
                    return str(e["url"])
        for e in events:
            page = e.get("page")
            if isinstance(page, dict) and page.get("url"):
                return str(page["url"])
            if e.get("url"):
                return str(e["url"])
            if e.get("urlAfter"):
                return str(e["urlAfter"])
        return ""

    def _build_steps(
        self, events: list[dict[str, Any]], start_url: str
    ) -> list[SemanticStep]:
        steps: list[SemanticStep] = []
        initial_target_id = self._initial_target_id(events, start_url)
        known_targets: set[str] = {initial_target_id} if initial_target_id else set()
        if start_url:
            steps.append(
                SemanticStep(
                    id=_step_id(1),
                    kind="open",
                    url=start_url,
                    description=f"Open {start_url}",
                )
            )
        i = 0
        while i < len(events):
            e = events[i]
            kind = str(e.get("kind", ""))
            if kind == "click":
                if _is_low_signal_result_click(e):
                    i += 1
                    continue
                nxt = events[i + 1] if i + 1 < len(events) else None
                if (
                    _is_blank_page_click(e)
                    and nxt
                    and nxt.get("kind")
                    in {"navigation", "history.pushState", "history.replaceState"}
                ):
                    # A click on the empty about:blank body usually means the
                    # user/agent focused the address bar or otherwise caused an
                    # immediate navigation outside page DOM. There is no stable
                    # element to replay inside the blank document, so model it
                    # as an explicit navigation instead of an unmatchable body
                    # click.
                    url = str(nxt.get("urlAfter") or nxt.get("url") or "")
                    if url:
                        steps.append(
                            SemanticStep(
                                id=_step_id(len(steps) + 1),
                                kind="navigate",
                                url=url,
                                description=f"Navigate to {url}",
                            )
                        )
                        i += 2
                        continue
                if (
                    nxt
                    and nxt.get("kind") in {"input", "change"}
                    and _same_target(e.get("target"), nxt.get("target"))
                ):
                    target = _compact_target(
                        nxt.get("target"), _event_target_id(nxt) or _event_target_id(e)
                    )
                    step = _value_step(
                        nxt,
                        target=target,
                        raw_target=nxt.get("target")
                        if isinstance(nxt.get("target"), dict)
                        else None,
                    )
                    step.id = _step_id(len(steps) + 1)
                    steps.append(step)
                    i += 2
                    continue
                target = _compact_target(e.get("target"), _event_target_id(e))
                label = (
                    target.get("name")
                    or target.get("text")
                    or target.get("role")
                    or "element"
                )
                steps.append(
                    SemanticStep(
                        id=_step_id(len(steps) + 1),
                        kind="click",
                        target=target,
                        description=f"Click {label}",
                    )
                )
            elif kind in {"input", "change"}:
                raw_target = e.get("target")
                target = _compact_target(raw_target, _event_target_id(e))
                value = str(e.get("value", ""))
                if any(_same_fill_step(prev, target, value) for prev in steps):
                    i += 1
                    continue
                step = _value_step(
                    e,
                    target=target,
                    raw_target=raw_target if isinstance(raw_target, dict) else None,
                )
                step.id = _step_id(len(steps) + 1)
                steps.append(step)
            elif kind == "keydown" and e.get("key"):
                steps.append(
                    SemanticStep(
                        id=_step_id(len(steps) + 1),
                        kind="press",
                        key=str(e.get("key")),
                        target=_compact_target(e.get("target"), _event_target_id(e)),
                        description=f"Press {e.get('key')}",
                    )
                )
            elif kind == "scroll":
                nxt = events[i + 1] if i + 1 < len(events) else None
                if nxt and _is_low_signal_result_click(nxt):
                    i += 1
                    continue
                pos = _scroll_position(e)
                if pos["x"] or pos["y"]:
                    steps.append(
                        SemanticStep(
                            id=_step_id(len(steps) + 1),
                            kind="scroll_to",
                            target={"targetId": _event_target_id(e)}
                            if _event_target_id(e)
                            else None,
                            value=f"{pos['x']:.3f},{pos['y']:.3f}",
                            description=f"Scroll to y={pos['y']:.0f}",
                        )
                    )
            elif kind == "page_opened":
                url = str(e.get("url") or e.get("urlAfter") or "")
                target_id = _event_target_id(e)
                if is_replayable_page_url(url):
                    duplicate_of_previous = (
                        steps
                        and steps[-1].url == url
                        and steps[-1].kind in {"open", "navigate", "new_tab"}
                    )
                    if (
                        target_id
                        and target_id not in known_targets
                        and not duplicate_of_previous
                    ):
                        steps.append(
                            SemanticStep(
                                id=_step_id(len(steps) + 1),
                                kind="new_tab",
                                url=url,
                                target={"targetId": target_id} if target_id else None,
                                description=f"Open new tab {url}",
                            )
                        )
                    if target_id:
                        known_targets.add(target_id)
            elif kind in {
                "navigation",
                "history.pushState",
                "history.replaceState",
                "popstate",
                "hashchange",
            }:
                url = str(e.get("urlAfter") or e.get("url") or "")
                if url and url != start_url and is_replayable_page_url(url):
                    duplicate_of_previous = (
                        steps
                        and steps[-1].url == url
                        and steps[-1].kind in {"open", "navigate", "new_tab"}
                    )
                    if not duplicate_of_previous:
                        if (
                            i + 1 < len(events)
                            and events[i + 1].get("kind") == "recorder_installed"
                        ):
                            nxt_url = str(
                                events[i + 1].get("url") or _page_url(events[i + 1])
                            )
                            if nxt_url == url:
                                i += 1
                        target_id = _event_target_id(e)
                        if target_id and target_id not in known_targets:
                            steps.append(
                                SemanticStep(
                                    id=_step_id(len(steps) + 1),
                                    kind="new_tab",
                                    url=url,
                                    target={"targetId": target_id},
                                    description=f"Open new tab {url}",
                                )
                            )
                            known_targets.add(target_id)
                            i += 1
                            continue
                        steps.append(
                            SemanticStep(
                                id=_step_id(len(steps) + 1),
                                kind="navigate",
                                url=url,
                                target={"targetId": target_id} if target_id else None,
                                description=f"Navigate to {url}",
                            )
                        )
            i += 1
        return steps

    def _initial_target_id(self, events: list[dict[str, Any]], start_url: str) -> str:
        if not start_url:
            return ""
        for event in events:
            target_id = _event_target_id(event)
            if not target_id:
                continue
            if _page_url(event) == start_url:
                return target_id
        # Some older/raw evidence events did not include targetId on click/input
        # records, but the following navigation on the same page did. In that
        # case the first target-bearing event is the best available proxy for
        # the initial page, not proof that a new tab was opened.
        for event in events:
            target_id = _event_target_id(event)
            if target_id and event.get("kind") != "page_opened":
                return target_id
        return ""

    def _infer_variables(
        self, steps: list[SemanticStep]
    ) -> tuple[list[SemanticStep], list[dict[str, Any]]]:
        used: set[str] = set()
        inputs: list[dict[str, Any]] = []
        for step in steps:
            if step.kind in {"fill", "select"} and step.value:
                var, info = _var_for(step.target, step.value, used)
                step.value = var
                inputs.append(info)
        return steps, inputs

    def _attach_navigation_expectations(
        self, steps: list[SemanticStep]
    ) -> list[SemanticStep]:
        result: list[SemanticStep] = []
        for step in steps:
            if (
                step.kind == "navigate"
                and result
                and result[-1].kind in {"click", "press", "submit"}
            ):
                prev = result[-1]
                expect = dict(prev.expect or {})
                expect["urlAfter"] = step.url
                hint = _path_hint(step.url)
                if hint:
                    expect["urlContains"] = hint
                prev.expect = expect
                continue
            result.append(step)
        result = self._coalesce_scrolls(result)
        for idx, step in enumerate(result, start=1):
            step.id = _step_id(idx)
        return result

    def _coalesce_scrolls(self, steps: list[SemanticStep]) -> list[SemanticStep]:
        result: list[SemanticStep] = []
        pending: SemanticStep | None = None
        for step in steps:
            if step.kind == "scroll_to":
                pending = step
                continue
            if pending is not None:
                result.append(pending)
                pending = None
            result.append(step)
        if pending is not None:
            result.append(pending)
        return result

    def _verification(self, steps: list[SemanticStep]) -> list[dict[str, Any]]:
        for step in reversed(steps):
            if step.expect and step.expect.get("urlContains"):
                return [{"type": "url_contains", "value": step.expect["urlContains"]}]
        return []
