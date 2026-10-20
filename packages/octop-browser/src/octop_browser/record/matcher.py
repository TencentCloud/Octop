"""Target matching for replay."""

from __future__ import annotations

import json
from typing import Any


def _norm(v: object) -> str:
    return str(v or "").strip().lower()


def _elements(dom_content: str) -> list[dict[str, Any]]:
    data = json.loads(dom_content)
    els = data.get("elements", [])
    return els if isinstance(els, list) else []


def match_target(target: dict[str, Any], dom_content: str) -> tuple[str | None, str]:
    elements = _elements(dom_content)
    target_selectors = set(target.get("selectorCandidates") or [])
    target_name = _norm(target.get("name") or target.get("label") or target.get("text"))
    target_role = _norm(target.get("role"))
    target_id = _norm(target.get("id"))
    target_name_attr = _norm(target.get("nameAttr"))

    best: tuple[int, str | None, str] = (0, None, "")
    for el in elements:
        score = 0
        why: list[str] = []
        el_ref = el.get("ref")
        el_selectors = set(el.get("selectorCandidates") or [])
        if target_selectors and el_selectors & target_selectors:
            score += 80
            why.append("selector")
        if target_id and _norm(el.get("id")) == target_id:
            score += 70
            why.append("id")
        if target_name_attr and _norm(el.get("nameAttr")) == target_name_attr:
            score += 60
            why.append("nameAttr")
        if target_role and _norm(el.get("role")) == target_role:
            score += 25
            why.append("role")
        el_name = _norm(
            el.get("accessibleName")
            or el.get("name")
            or el.get("label")
            or el.get("text")
            or el.get("placeholder")
        )
        if target_name and el_name == target_name:
            score += 50
            why.append("name")
        elif target_name and target_name in el_name:
            score += 20
            why.append("partial-name")
        if score > best[0]:
            best = (score, str(el_ref) if el_ref else None, "+".join(why))
    if best[0] >= 45:
        return best[1], best[2]
    return None, "not-found"
