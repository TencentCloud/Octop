"""Tiered DOM output builder for AI-friendly page state representation."""

from __future__ import annotations

import json
from typing import Any, Literal

from octop_browser.dom.refs import RefCache

DOMLevel = Literal["minimal", "interactive", "full", "structured"]

_INTERACTIVE_TAGS = frozenset(
    ["button", "input", "select", "textarea", "a", "label", "form"]
)
_STRUCTURAL_TAGS = frozenset(
    [
        "header",
        "nav",
        "main",
        "footer",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "table",
    ]
)
_INTERACTIVE_ROLES = frozenset(
    [
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "menuitem",
        "option",
        "switch",
        "tab",
        "searchbox",
    ]
)
_SKIP_TAGS = frozenset(
    [
        "script",
        "style",
        "meta",
        "link",
        "noscript",
        "svg",
        "path",
        "head",
        "html",
        "#document",
    ]
)

_CONTEXT_TAGS = frozenset({"iframe", "frame"})


def _attrs_to_dict(attrs: list[str]) -> dict[str, str]:
    """Convert CDP flat attributes list ['key','val',...] to dict."""
    return dict(zip(attrs[::2], attrs[1::2])) if attrs else {}


def _node_text(node: dict[str, Any]) -> str:
    """Return the direct text content of a node (first text child only)."""
    for child in node.get("children", []):
        if child.get("nodeName") == "#text":
            val: str = child.get("nodeValue", "")
            return val.strip()
    return ""


def _subtree_text(node: dict[str, Any], limit: int = 300) -> str:
    parts: list[str] = []

    def walk(n: dict[str, Any]) -> None:
        if len(" ".join(parts)) > limit:
            return
        if n.get("nodeName") == "#text":
            val = str(n.get("nodeValue", "")).strip()
            if val:
                parts.append(val)
        for c in n.get("children", []):
            walk(c)

    walk(node)
    return " ".join(parts).strip()[:limit]


def _selector_candidates(tag: str, attrs: dict[str, str]) -> list[str]:
    out: list[str] = []
    for key in ("data-testid", "data-test", "data-cy"):
        if attrs.get(key):
            out.append(f'[{key}="{attrs[key]}"]')
    if attrs.get("id"):
        out.append(f"#{attrs['id']}")
    if attrs.get("name"):
        out.append(f'{tag}[name="{attrs["name"]}"]')
    if attrs.get("aria-label"):
        out.append(f'{tag}[aria-label="{attrs["aria-label"]}"]')
    if attrs.get("type"):
        out.append(f'{tag}[type="{attrs["type"]}"]')
    return list(dict.fromkeys(out))


def _context_selector(tag: str, attrs: dict[str, str]) -> str:
    if attrs.get("id"):
        return f"{tag}#{attrs['id']}"
    if attrs.get("name"):
        return f'{tag}[name="{attrs["name"]}"]'
    for key in ("data-testid", "data-test", "data-cy"):
        if attrs.get(key):
            return f'{tag}[{key}="{attrs[key]}"]'
    return tag


def _make_ref(tag: str, counter: dict[str, int]) -> str:
    prefix = {
        "input": "inp",
        "button": "btn",
        "a": "lnk",
        "select": "sel",
        "textarea": "txt",
    }.get(tag, tag[:3])
    idx = counter.get(prefix, 0)
    counter[prefix] = idx + 1
    return f"{prefix}_{idx}"


class DOMBuilder:
    """
    Converts a raw CDP DOM tree into one of four output levels.

    Args:
        dom: The CDP ``DOM.getDocument`` root node dict.
        url: Current page URL.
        title: Current page title.
        ref_cache: A ``RefCache`` instance to populate with ref→node_id mappings.
    """

    def __init__(
        self,
        dom: dict[str, Any],
        url: str,
        title: str,
        ref_cache: RefCache,
    ) -> None:
        self._dom = dom
        self._url = url
        self._title = title
        self._ref_cache = ref_cache

    def build(self, level: DOMLevel = "interactive") -> str:
        """Build and return the DOM representation at the requested level."""
        ref_counter: dict[str, int] = {}
        interactive: list[dict[str, Any]] = []
        structural: list[str] = []

        self._walk(
            self._dom,
            interactive,
            structural,
            ref_counter,
            depth=0,
            frame_path=[],
            shadow_path=[],
        )

        if level == "minimal":
            return self._build_minimal(len(interactive))
        if level == "interactive":
            return self._build_interactive(interactive)
        if level == "full":
            return self._build_full(interactive, structural)
        if level == "structured":
            return self._build_structured(interactive)
        raise ValueError(f"Unknown DOM level: {level!r}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _walk(
        self,
        node: dict[str, Any],
        interactive: list[dict[str, Any]],
        structural: list[str],
        counter: dict[str, int],
        depth: int,
        frame_path: list[str],
        shadow_path: list[str],
    ) -> None:
        tag = node.get("nodeName", "").lower()
        if tag in ("#text", "#comment"):
            return
        if tag in _SKIP_TAGS:
            # Still recurse into #document
            for child in node.get("children", []):
                self._walk(
                    child,
                    interactive,
                    structural,
                    counter,
                    depth,
                    frame_path,
                    shadow_path,
                )
            return

        attrs = _attrs_to_dict(node.get("attributes", []))
        next_frame_path = frame_path
        if tag in _CONTEXT_TAGS:
            next_frame_path = [*frame_path, _context_selector(tag, attrs)]
        role = attrs.get("role", "")
        aria_label = attrs.get("aria-label", "")
        is_interactive = tag in _INTERACTIVE_TAGS or role in _INTERACTIVE_ROLES
        # Anchor must have href to count as interactive
        if tag == "a" and not attrs.get("href"):
            is_interactive = False

        if is_interactive:
            ref = _make_ref(tag, counter)
            self._ref_cache.store(ref, node["nodeId"])
            interactive.append(
                {
                    "ref": ref,
                    "tag": tag,
                    "type": attrs.get("type", ""),
                    "role": role or tag,
                    "label": aria_label or attrs.get("label", ""),
                    "placeholder": attrs.get("placeholder", ""),
                    "text": _subtree_text(node) or _node_text(node),
                    "accessibleName": aria_label
                    or attrs.get("aria-labelledby", "")
                    or attrs.get("label", "")
                    or attrs.get("placeholder", "")
                    or _subtree_text(node),
                    "id": attrs.get("id", ""),
                    "nameAttr": attrs.get("name", ""),
                    "testId": attrs.get("data-testid", "")
                    or attrs.get("data-test", "")
                    or attrs.get("data-cy", ""),
                    "selectorCandidates": _selector_candidates(tag, attrs),
                    "href": attrs.get("href", ""),
                    "node_id": node["nodeId"],
                    "attrs": attrs,
                    "depth": depth,
                    "framePath": frame_path,
                    "shadowPath": shadow_path,
                }
            )
        elif tag in _STRUCTURAL_TAGS:
            text = _node_text(node)
            indent = "  " * depth
            structural.append(f"{indent}<{tag}>{(' ' + text) if text else ''}")

        for child in node.get("children", []):
            self._walk(
                child,
                interactive,
                structural,
                counter,
                depth + 1,
                next_frame_path,
                shadow_path,
            )
        content_document = node.get("contentDocument")
        if isinstance(content_document, dict):
            self._walk(
                content_document,
                interactive,
                structural,
                counter,
                depth + 1,
                next_frame_path,
                shadow_path,
            )
        for shadow_root in node.get("shadowRoots") or []:
            if isinstance(shadow_root, dict):
                host_selector = _context_selector("", attrs) or tag
                self._walk(
                    shadow_root,
                    interactive,
                    structural,
                    counter,
                    depth + 1,
                    frame_path,
                    [*shadow_path, host_selector],
                )

    def _build_minimal(self, interactive_count: int) -> str:
        return (
            f'Page: {self._url} | "{self._title}"\n'
            f"Interactive elements: {interactive_count} | Scroll: yes"
        )

    def _build_interactive(self, interactive: list[dict[str, Any]]) -> str:
        lines = [
            f'Page: {self._url} | "{self._title}"',
            f"Interactive elements ({len(interactive)}):",
        ]
        for el in interactive:
            tag = el["tag"]
            ref = el["ref"]
            if tag == "input":
                type_part = f"[{el['type'] or 'text'}]"
                label_part = ""
                if el["placeholder"]:
                    label_part = f' placeholder="{el["placeholder"]}"'
                elif el["label"]:
                    label_part = f' label="{el["label"]}"'
                lines.append(f"  [ref={ref}] input{type_part}{label_part}")
            elif tag == "button":
                text = el["text"] or el["label"] or ""
                lines.append(f'  [ref={ref}] button "{text}"')
            elif tag == "a":
                text = el["text"] or el["label"] or el["href"]
                lines.append(f'  [ref={ref}] a "{text}"')
            elif tag == "select":
                label = el["label"] or el["placeholder"] or ""
                lines.append(f'  [ref={ref}] select "{label}"')
            elif tag == "textarea":
                placeholder = el["placeholder"] or ""
                lines.append(f'  [ref={ref}] textarea placeholder="{placeholder}"')
            else:
                label = el["text"] or el["label"] or ""
                lines.append(f'  [ref={ref}] {tag} "{label}"')
        return "\n".join(lines)

    def _build_full(
        self, interactive: list[dict[str, Any]], structural: list[str]
    ) -> str:
        parts = [f'Page: {self._url} | "{self._title}"\n']
        if structural:
            parts.extend(structural)
            parts.append("")
        if interactive:
            parts.append(f"Interactive elements ({len(interactive)}):")
            for el in interactive:
                ref = el["ref"]
                tag = el["tag"]
                attrs_str = ""
                if el["type"]:
                    attrs_str += f" type={el['type']}"
                if el["placeholder"]:
                    attrs_str += f' placeholder="{el["placeholder"]}"'
                text = el["text"] or el["label"]
                text_str = f" {text}" if text else ""
                parts.append(f"  <{tag} ref={ref}{attrs_str}>{text_str}")
        return "\n".join(parts)

    def _build_structured(self, interactive: list[dict[str, Any]]) -> str:
        elements = []
        for el in interactive:
            entry: dict[str, Any] = {
                "ref": el["ref"],
                "tag": el["tag"],
                "role": el["role"],
                "node_id": el["node_id"],
            }
            if el["type"]:
                entry["type"] = el["type"]
            if el["label"]:
                entry["label"] = el["label"]
            if el.get("accessibleName"):
                entry["accessibleName"] = el["accessibleName"]
                entry["name"] = el["accessibleName"]
            if el["placeholder"]:
                entry["placeholder"] = el["placeholder"]
            if el["text"]:
                entry["text"] = el["text"]
            if el.get("id"):
                entry["id"] = el["id"]
            if el.get("nameAttr"):
                entry["nameAttr"] = el["nameAttr"]
            if el.get("testId"):
                entry["testId"] = el["testId"]
            if el.get("selectorCandidates"):
                entry["selectorCandidates"] = el["selectorCandidates"]
            if el.get("framePath"):
                entry["framePath"] = el["framePath"]
            if el.get("shadowPath"):
                entry["shadowPath"] = el["shadowPath"]
            if el["href"]:
                entry["href"] = el["href"]
            elements.append(entry)
        data: dict[str, Any] = {
            "url": self._url,
            "title": self._title,
            "elements": elements,
        }
        return json.dumps(data, indent=2, ensure_ascii=False)
