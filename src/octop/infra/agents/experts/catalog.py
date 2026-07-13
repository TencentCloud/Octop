"""Expert catalog — bundled "scene templates" inherited from finnie.

An *expert* is metadata in ``manifest.json`` plus files on disk under
``library/<id>/``. At seed time files (including a copy of ``manifest.json``)
are written into the agent workspace. ``prompt_files`` in the manifest is
metadata for the dashboard only — persona text is read from the workspace.

Templates are discovered at server start by :class:`ExpertCatalog`.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from harness_agent.backends.workspace import BackendWorkspace

from octop.infra.agents.manager import AgentCreateSpec

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
"""Expert template / agent-workspace welcome metadata filename."""


@dataclass(frozen=True)
class ExpertQuickPrompt:
    """One quick-start card shown on the chat welcome screen."""

    title_zh: str
    title_en: str
    description_zh: str
    description_en: str
    prompt_zh: str
    prompt_en: str
    color: str = "#e8f4ff"
    icon_name: str | None = None


@dataclass(frozen=True)
class ExpertSummary:
    """Lightweight view used by ``GET /api/experts``."""

    id: str
    label_zh: str
    label_en: str
    description_zh: str
    description_en: str
    welcome_message_zh: str = ""
    welcome_message_en: str = ""
    icon_name: str | None = None
    color: str | None = None
    quick_prompts: tuple[ExpertQuickPrompt, ...] = ()


@dataclass(frozen=True)
class Expert:
    """Full expert: summary + on-disk seed inventory (paths only, no eager bodies)."""

    summary: ExpertSummary
    files: list[str] = field(default_factory=list)
    """Workspace-relative paths discovered under the expert directory (excl. manifest)."""
    prompt_files: list[str] = field(default_factory=list)
    """Persona markdown filenames declared in the manifest (dashboard hint)."""
    quick_prompts: tuple[ExpertQuickPrompt, ...] = ()


def discover_seed_paths(expert_dir: Path) -> list[str]:
    """Return sorted workspace-relative paths for every file under *expert_dir*."""
    if not expert_dir.is_dir():
        return []
    paths: list[str] = []
    for fpath in sorted(expert_dir.rglob("*")):
        if not fpath.is_file():
            continue
        rel = fpath.relative_to(expert_dir)
        if rel.as_posix() == MANIFEST_FILENAME:
            continue
        paths.append(rel.as_posix())
    return paths


def preview_file_paths(expert: Expert) -> list[str]:
    """Paths shown in the create-from-expert drawer: ``prompt_files`` + ``skills/``."""
    paths = list(expert.prompt_files)
    paths.extend(f for f in expert.files if f.startswith("skills/"))
    return paths


async def seed_expert_directory(
    *,
    expert_dir: Path,
    workspace: BackendWorkspace,
    seed_paths: list[str] | None = None,
) -> int:
    """Upload expert template files into *workspace*, including ``manifest.json``.

    ``seed_paths`` / :func:`discover_seed_paths` omit the library manifest so
    catalog ``Expert.files`` stays seed-content only; this helper always
    copies ``manifest.json`` when present (chat welcome source of truth).
    """
    paths = seed_paths if seed_paths is not None else discover_seed_paths(expert_dir)
    pairs: list[tuple[str, bytes]] = []
    for rel in paths:
        fpath = expert_dir / rel
        if not fpath.is_file():
            continue
        pairs.append((rel.lstrip("/"), fpath.read_bytes()))
    manifest_path = expert_dir / MANIFEST_FILENAME
    if manifest_path.is_file():
        pairs.append((MANIFEST_FILENAME, manifest_path.read_bytes()))
    if not pairs:
        return 0
    await workspace.aupload_many(pairs)
    return len(pairs)


def _quick_prompt_api_dict(prompt: ExpertQuickPrompt) -> dict[str, Any]:
    return {
        "title": {"zh": prompt.title_zh, "en": prompt.title_en},
        "description": {"zh": prompt.description_zh, "en": prompt.description_en},
        "prompt": {"zh": prompt.prompt_zh, "en": prompt.prompt_en},
        "color": prompt.color,
        "icon_name": prompt.icon_name,
    }


def welcome_payload_from_manifest_data(data: dict[str, Any]) -> dict[str, Any]:
    """Build dashboard welcome payload from workspace or library ``manifest.json``."""
    wm = data.get("welcome_message")
    return {
        "welcome_message": {
            "zh": _coerce_label(wm, "zh"),
            "en": _coerce_label(wm, "en"),
        },
        "quick_prompts": [_quick_prompt_api_dict(p) for p in _parse_quick_prompts(data)],
    }


def welcome_payload_from_expert(expert: Expert) -> dict[str, Any]:
    """Welcome fields from an in-memory catalog expert."""
    summary = expert.summary
    return {
        "welcome_message": {
            "zh": summary.welcome_message_zh,
            "en": summary.welcome_message_en,
        },
        "quick_prompts": [_quick_prompt_api_dict(p) for p in expert.quick_prompts],
    }


def welcome_payload_has_content(payload: dict[str, Any]) -> bool:
    wm = payload.get("welcome_message")
    if isinstance(wm, dict) and (wm.get("zh") or wm.get("en")):
        return True
    prompts = payload.get("quick_prompts")
    return isinstance(prompts, list) and len(prompts) > 0


def default_welcome_payload(catalog: ExpertCatalog | None = None) -> dict[str, Any]:
    """Last-resort welcome: prefer bundled ``general-assistant``, else a small built-in set."""
    if catalog is not None:
        expert = catalog.get("general-assistant")
        if expert is not None:
            payload = welcome_payload_from_expert(expert)
            if welcome_payload_has_content(payload):
                return payload
    return {
        "welcome_message": {
            "zh": "说出你的想法，我来帮忙",
            "en": "Tell me what you need — I'll help",
        },
        "quick_prompts": [
            {
                "title": {"zh": "总结内容", "en": "Summarize"},
                "description": {
                    "zh": "粘贴文字，提炼要点和结论",
                    "en": "Paste text and extract key points",
                },
                "prompt": {
                    "zh": "请帮我总结以下内容，提炼核心要点：\n\n",
                    "en": "Please summarize the following and extract the key points:\n\n",
                },
                "color": "#e8f4ff",
                "icon_name": "file-text",
            },
            {
                "title": {"zh": "随便问问", "en": "Ask anything"},
                "description": {
                    "zh": "有任何问题都可以直接问我",
                    "en": "Ask me anything",
                },
                "prompt": {
                    "zh": "我有一个问题想请教你：",
                    "en": "I have a question for you:",
                },
                "color": "#eef2ff",
                "icon_name": "message-square",
            },
        ],
    }


async def read_workspace_manifest_welcome(
    workspace: BackendWorkspace,
) -> dict[str, Any] | None:
    """Parse ``manifest.json`` from an agent workspace, if present and valid."""
    text = await workspace.aread_text(MANIFEST_FILENAME)
    if not text or not str(text).strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("workspace manifest.json is not valid JSON")
        return None
    if not isinstance(data, dict):
        return None
    payload = welcome_payload_from_manifest_data(data)
    return payload if welcome_payload_has_content(payload) else None


def read_text_file_contents(expert_dir: Path, paths: list[str]) -> list[dict[str, str]]:
    """Read UTF-8 text files for API preview; skip unreadable/binary paths."""
    out: list[dict[str, str]] = []
    for rel in paths:
        fpath = expert_dir / rel
        if not fpath.is_file():
            continue
        try:
            text = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        out.append({"name": rel, "content": text})
    return out


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("expert manifest %s unreadable: %s", path, exc)
        return None


def _coerce_label(node: dict[str, Any] | str | None, fallback: str) -> str:
    if isinstance(node, dict):
        return str(node.get(fallback) or node.get("zh") or node.get("en") or "")
    if isinstance(node, str):
        return node
    return ""


def _parse_quick_prompts(data: dict[str, Any]) -> tuple[ExpertQuickPrompt, ...]:
    raw = data.get("quick_prompts")
    if not isinstance(raw, list):
        return ()
    out: list[ExpertQuickPrompt] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            ExpertQuickPrompt(
                title_zh=_coerce_label(item.get("title"), "zh"),
                title_en=_coerce_label(item.get("title"), "en"),
                description_zh=_coerce_label(item.get("description"), "zh"),
                description_en=_coerce_label(item.get("description"), "en"),
                prompt_zh=_coerce_label(item.get("prompt"), "zh"),
                prompt_en=_coerce_label(item.get("prompt"), "en"),
                color=str(item.get("color") or "#e8f4ff"),
                icon_name=item.get("icon_name") if item.get("icon_name") else None,
            ),
        )
    return tuple(out)


class ExpertCatalog:
    """Loads expert templates from a directory tree.

    Construction is cheap (it only validates the root); :meth:`refresh`
    walks the directory and populates the in-memory cache. Tests can
    point ``library_root`` at a fixture directory.
    """

    def __init__(self, library_root: Path) -> None:
        self._root = library_root
        self._experts: dict[str, Expert] = {}

    @property
    def root(self) -> Path:
        return self._root

    def expert_dir(self, expert_id: str) -> Path:
        return self._root / expert_id

    def read_file_contents(
        self,
        expert_id: str,
        *,
        paths: list[str] | None = None,
    ) -> list[dict[str, str]]:
        """Lazy-read text file bodies for ``GET /api/experts/{id}`` preview."""
        expert = self.get(expert_id)
        if expert is None:
            return []
        rels = paths if paths is not None else expert.files
        return read_text_file_contents(self.expert_dir(expert_id), rels)

    def refresh(self) -> None:
        """Re-scan the library directory; quietly skip malformed entries."""
        out: dict[str, Expert] = {}
        if not self._root.exists():
            self._experts = {}
            return
        for entry in sorted(self._root.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / MANIFEST_FILENAME
            if not manifest_path.exists():
                continue
            data = _read_manifest(manifest_path)
            if not isinstance(data, dict):
                continue
            ex_id = str(data.get("id") or entry.name)
            prompt_files = [str(f) for f in (data.get("prompt_files") or [])]
            seed_paths = discover_seed_paths(entry)
            summary = ExpertSummary(
                id=ex_id,
                label_zh=_coerce_label(data.get("label"), "zh"),
                label_en=_coerce_label(data.get("label"), "en"),
                description_zh=_coerce_label(data.get("description"), "zh"),
                description_en=_coerce_label(data.get("description"), "en"),
                welcome_message_zh=_coerce_label(data.get("welcome_message"), "zh"),
                welcome_message_en=_coerce_label(data.get("welcome_message"), "en"),
                icon_name=data.get("icon_name"),
                color=data.get("color"),
                quick_prompts=_parse_quick_prompts(data),
            )
            out[ex_id] = Expert(
                summary=summary,
                files=seed_paths,
                prompt_files=prompt_files,
                quick_prompts=summary.quick_prompts,
            )
        self._experts = out
        logger.info("expert catalog loaded: %d templates", len(out))

    def list_summaries(self) -> list[ExpertSummary]:
        summaries = [e.summary for e in self._experts.values() if e.summary.id != "default"]
        summaries.sort(key=lambda s: (0 if s.id == "general-assistant" else 1, s.id))
        return summaries

    def get(self, expert_id: str) -> Expert | None:
        return self._experts.get(expert_id)


def default_library_root() -> Path:
    """Return the in-package library directory."""
    return Path(__file__).parent / "library"


def resolve_expert_agent_name(
    expert: Expert,
    expert_id: str,
    *,
    locale: str,
    override: str | None = None,
) -> str:
    if override:
        return override
    if locale == "zh":
        return expert.summary.label_zh or expert.summary.label_en or expert_id
    return expert.summary.label_en or expert.summary.label_zh or expert_id


def expert_agent_config(expert_id: str, expert: Expert, **extra: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {
        "expert_id": expert_id,
        "icon_name": expert.summary.icon_name,
        "color": expert.summary.color,
    }
    cfg.update(extra)
    return cfg


def build_create_spec_from_expert(
    *,
    expert_id: str,
    expert: Expert,
    user_id: int,
    name: str | None = None,
    description: str | None = None,
    locale: str = "zh",
    default_model: str | None = None,
    config_extra: dict[str, Any] | None = None,
    agent_id: str | None = None,
    icon: str | None = None,
) -> AgentCreateSpec:
    """Build :class:`AgentCreateSpec` for ``AgentManager.create`` from a catalog entry."""
    resolved_name = resolve_expert_agent_name(expert, expert_id, locale=locale, override=name)
    if description:
        resolved_description = description
    elif locale == "zh":
        resolved_description = (
            expert.summary.description_zh
            or expert.summary.label_zh
            or expert.summary.description_en
            or expert.summary.label_en
        )
    else:
        resolved_description = (
            expert.summary.description_en
            or expert.summary.label_en
            or expert.summary.description_zh
            or expert.summary.label_zh
        )
    return AgentCreateSpec(
        agent_id=agent_id,
        name=resolved_name,
        user_id=user_id,
        description=resolved_description,
        default_model=default_model,
        config=expert_agent_config(expert_id, expert, **(config_extra or {})),
        icon=icon,
        template_name=expert_id,
    )
