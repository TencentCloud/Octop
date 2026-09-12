"""Expert catalog — bundled "scene templates" inherited from finnie.

An *expert* is metadata in ``manifest.json`` plus files on disk under
``library/<id>/``. At seed time files (including a copy of ``manifest.json``)
are written into the agent workspace under ``.octop/manifest.json``.
``prompt_files`` in the manifest is metadata for the dashboard only — persona
text is read from the workspace. ``task_examples`` is an optional locale-keyed
string array shown as empty-state cards on the tasks page.

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
from octop.infra.agents.workspace_dir import DEFAULT_SYSTEM_FILES_PATH

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"
"""Expert template / published-snapshot welcome metadata filename (dir root)."""

WORKSPACE_MANIFEST_PATH = f"{DEFAULT_SYSTEM_FILES_PATH}/{MANIFEST_FILENAME}"
"""Agent-workspace path for welcome metadata (under ``.octop/``)."""

# Prefer system path; keep root ``manifest.json`` readable for pre-migration agents.
_WORKSPACE_MANIFEST_READ_PATHS = (WORKSPACE_MANIFEST_PATH, MANIFEST_FILENAME)


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
    task_examples: dict[str, list[str]] | None = None


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
    """Paths shown in the create-from-expert drawer: persona md, skills/, agents/."""
    return preview_paths_from_inventory(expert.prompt_files, expert.files)


def preview_paths_from_inventory(
    prompt_files: list[str],
    seed_paths: list[str],
) -> list[str]:
    """Build dashboard preview paths from manifest ``prompt_files`` + skills/agents."""
    paths: list[str] = []
    seen: set[str] = set()
    for rel in prompt_files:
        if rel in seen or rel == MANIFEST_FILENAME or not _is_prompt_md_path(rel):
            continue
        paths.append(rel)
        seen.add(rel)
    for rel in sorted(seed_paths):
        if rel.startswith("skills/") and rel not in seen:
            paths.append(rel)
            seen.add(rel)
    for rel in sorted(seed_paths):
        if _is_subagent_path(rel) and rel not in seen:
            paths.append(rel)
            seen.add(rel)
    return paths


def preview_paths_from_expert_dir(expert_dir: Path) -> list[str]:
    """Preview paths for a snapshot directory (published experts)."""
    manifest_path = expert_dir / MANIFEST_FILENAME
    prompt_files: list[str] = []
    if manifest_path.is_file():
        data = _read_manifest(manifest_path)
        if isinstance(data, dict):
            raw = data.get("prompt_files")
            if isinstance(raw, list):
                prompt_files = [str(item) for item in raw if str(item).strip()]
    return preview_paths_from_inventory(prompt_files, discover_seed_paths(expert_dir))


def _is_subagent_path(rel: str) -> bool:
    return rel.startswith("agents/") and rel.endswith(".md")


def _is_prompt_md_path(rel: str) -> bool:
    """Workspace-root persona markdown listed in ``prompt_files``."""
    return "/" not in rel and rel.endswith(".md")


async def seed_expert_directory(
    *,
    expert_dir: Path,
    workspace: BackendWorkspace,
    seed_paths: list[str] | None = None,
) -> int:
    """Upload expert template files into *workspace*, including welcome manifest.

    ``seed_paths`` / :func:`discover_seed_paths` omit the library manifest so
    catalog ``Expert.files`` stays seed-content only; this helper always
    copies library ``manifest.json`` to :data:`WORKSPACE_MANIFEST_PATH` when
    present (chat welcome source of truth).
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
        pairs.append((WORKSPACE_MANIFEST_PATH, manifest_path.read_bytes()))
    if not pairs:
        return 0
    await workspace.aupload_many(pairs)
    return len(pairs)


async def read_workspace_manifest_text(workspace: BackendWorkspace) -> str | None:
    """Read welcome manifest text from the agent workspace (``.octop`` then legacy root)."""
    for rel in _WORKSPACE_MANIFEST_READ_PATHS:
        text = await workspace.aread_text(rel)
        if text is not None and str(text).strip():
            return str(text)
    return None


async def read_workspace_manifest_bytes(workspace: BackendWorkspace) -> bytes | None:
    """Read welcome manifest bytes from the agent workspace (``.octop`` then legacy root)."""
    for rel in _WORKSPACE_MANIFEST_READ_PATHS:
        raw = await workspace.adownload_bytes(rel)
        if raw is not None and raw.strip():
            return raw
    return None


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


async def read_workspace_manifest_data(
    workspace: BackendWorkspace,
) -> dict[str, Any] | None:
    """Parse workspace ``.octop/manifest.json`` (legacy root fallback) as a dict."""
    text = await read_workspace_manifest_text(workspace)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("workspace %s is not valid JSON", WORKSPACE_MANIFEST_PATH)
        return None
    return data if isinstance(data, dict) else None


async def read_workspace_manifest_welcome(
    workspace: BackendWorkspace,
) -> dict[str, Any] | None:
    """Parse workspace welcome manifest (``.octop/manifest.json``), if present and valid."""
    data = await read_workspace_manifest_data(workspace)
    if data is None:
        return None
    payload = welcome_payload_from_manifest_data(data)
    return payload if welcome_payload_has_content(payload) else None


async def read_workspace_manifest_task_examples(
    workspace: BackendWorkspace,
) -> dict[str, list[str]] | None:
    """Return ``task_examples`` from the workspace manifest, or ``None`` if absent."""
    data = await read_workspace_manifest_data(workspace)
    if data is None:
        return None
    return parse_task_examples(data)


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


def _coerce_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            text = item.strip()
            if text:
                out.append(text)
    return out


def parse_task_examples(data: dict[str, Any]) -> dict[str, list[str]] | None:
    """Parse ``task_examples`` from a manifest dict.

    Canonical form is locale-keyed string arrays::

        {"zh": ["…"], "en": ["…"]}

    A plain ``["…"]`` list is treated as the same strings for both locales.
    Missing or invalid values return ``None`` so callers can keep default cards.
    """
    if "task_examples" not in data:
        return None
    raw = data["task_examples"]
    if isinstance(raw, list):
        items = _coerce_string_list(raw)
        return {"zh": list(items), "en": list(items)}
    if isinstance(raw, dict):
        zh_raw = raw.get("zh")
        en_raw = raw.get("en")
        if isinstance(zh_raw, list) or isinstance(en_raw, list):
            return {
                "zh": _coerce_string_list(zh_raw),
                "en": _coerce_string_list(en_raw),
            }
    return None


_TASK_EXAMPLE_COUNT_THREE = 3
_TASK_EXAMPLE_COUNT_SIX = 6


def default_task_examples(label_zh: str, label_en: str) -> dict[str, list[str]]:
    """Shared bilingual fallbacks for generated / padded ``task_examples``."""
    return {
        "zh": [
            f"每天「09:00」按「{label_zh}」工作流巡检一次，有结果再发给我，任务创建后立即启用",
            f"每周一「10:00」汇总上周与「{label_zh}」相关的进展和下周计划",
            "每个工作日「18:00」复盘当天工作，列出待跟进项",
            f"每周五「17:00」汇总本周与「{label_zh}」相关的交付物和下周安排",
            f"每天「08:00」按「{label_zh}」工作流推送一条可执行简报",
            f"每月 1 日「09:30」复盘上月「{label_zh}」进展，列出本月优先项",
        ],
        "en": [
            (
                f"Every day at 09:00, run the {label_en} workflow once and notify me "
                "when there is a result — enable immediately"
            ),
            f"Every Monday at 10:00, summarize last week's {label_en} progress and next week's plan",
            "Every weekday at 18:00, recap the day's work and list follow-ups",
            f"Every Friday at 17:00, recap this week's {label_en} deliverables and next week's plan",
            f"Every day at 08:00, push one actionable {label_en} briefing",
            (
                f"On the 1st of each month at 09:30, recap last month's {label_en} "
                "progress and list this month's priorities"
            ),
        ],
    }


def normalize_task_examples_for_display(
    parsed: dict[str, list[str]] | None,
) -> dict[str, list[str]] | None:
    """Keep display lists at 3 or 6 entries; 4–5 truncate to 3, extras cap at 6."""
    if parsed is None:
        return None
    zh = list(parsed.get("zh") or [])
    en = list(parsed.get("en") or [])
    if not zh and not en:
        return {"zh": [], "en": []}
    cap = (
        _TASK_EXAMPLE_COUNT_SIX
        if max(len(zh), len(en)) >= _TASK_EXAMPLE_COUNT_SIX
        else _TASK_EXAMPLE_COUNT_THREE
    )
    return {"zh": zh[:cap], "en": en[:cap]}


def snap_task_examples(
    zh: list[str],
    en: list[str],
    *,
    fillers_zh: list[str],
    fillers_en: list[str],
    count: int | None = None,
) -> dict[str, list[str]]:
    """Keep exactly 3 or 6 bilingual examples (4–5 pad to 6; fewer pad to 3)."""
    out_zh = [item for item in zh if item][:_TASK_EXAMPLE_COUNT_SIX]
    out_en = [item for item in en if item][:_TASK_EXAMPLE_COUNT_SIX]
    if count in (_TASK_EXAMPLE_COUNT_THREE, _TASK_EXAMPLE_COUNT_SIX):
        target = count
    else:
        target = (
            _TASK_EXAMPLE_COUNT_SIX
            if max(len(out_zh), len(out_en)) > _TASK_EXAMPLE_COUNT_THREE
            else _TASK_EXAMPLE_COUNT_THREE
        )

    def _pad(side: list[str], extras: list[str]) -> None:
        for item in extras:
            if len(side) >= target:
                return
            if item and item not in side:
                side.append(item)
        idx = 0
        while len(side) < target and extras:
            side.append(extras[idx % len(extras)])
            idx += 1

    _pad(out_zh, fillers_zh)
    _pad(out_en, fillers_en)
    return {"zh": out_zh[:target], "en": out_en[:target]}


class ExpertCatalog:
    """Loads expert templates from a directory tree.

    Construction is cheap (it only validates the root); :meth:`refresh`
    walks the directory and populates the in-memory cache. Tests can
    point ``library_root`` at a fixture directory.
    """

    def __init__(self, library_root: Path, extra_roots: list[Path] | None = None) -> None:
        self._root = library_root
        self._extra_roots = list(extra_roots or [])
        self._experts: dict[str, Expert] = {}
        self._expert_dirs: dict[str, Path] = {}

    @property
    def root(self) -> Path:
        return self._root

    @property
    def roots(self) -> tuple[Path, ...]:
        return (self._root, *self._extra_roots)

    def expert_dir(self, expert_id: str) -> Path:
        return self._expert_dirs.get(expert_id) or (self._root / expert_id)

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
        dirs: dict[str, Path] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for entry in sorted(root.iterdir()):
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
                    task_examples=normalize_task_examples_for_display(parse_task_examples(data)),
                )
                out[ex_id] = Expert(
                    summary=summary,
                    files=seed_paths,
                    prompt_files=prompt_files,
                    quick_prompts=summary.quick_prompts,
                )
                dirs[ex_id] = entry
        self._experts = out
        self._expert_dirs = dirs
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


def expert_agent_config(_expert_id: str, _expert: Expert, **extra: Any) -> dict[str, Any]:
    """Harness-facing extras for an agent created from an expert template.

    Display fields (icon, color, welcome) belong on ``AgentCreateSpec`` / DB
    columns, not in ``config_json``. ``expert_id`` is ``template_name``.
    """
    return dict(extra)


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
    runtime_config: dict[str, Any] | None = None,
    agent_id: str | None = None,
    icon: str | None = None,
    icon_name: str | None = None,
    icon_url: str | None = None,
    color: str | None = None,
    welcome_message: str | None = None,
    published_expert_id: str | None = None,
    skill_package_ids: list[str] | None = None,
    knowledge_base_ids: list[str] | None = None,
    mcp_servers: list[str] | None = None,
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
    extra = dict(config_extra or {})
    extra_color = extra.pop("color", None)
    extra_icon_url = extra.pop("icon_url", None)
    extra_icon_name = extra.pop("icon_name", None)
    extra.pop("expert_id", None)
    extra.pop("published_expert_id", None)
    extra.pop("welcome_message", None)
    extra.pop("skill_package_ids", None)
    extra.pop("knowledge_base_ids", None)
    extra.pop("mcp_servers", None)
    return AgentCreateSpec(
        agent_id=agent_id,
        name=resolved_name,
        user_id=user_id,
        description=resolved_description,
        default_model=default_model,
        config=expert_agent_config(expert_id, expert, **extra),
        runtime_config=dict(runtime_config or {}),
        icon=icon,
        template_name=expert_id,
        icon_name=icon_name or extra_icon_name or expert.summary.icon_name,
        icon_url=icon_url or extra_icon_url,
        color=color or extra_color or expert.summary.color,
        skill_package_ids=skill_package_ids,
        knowledge_base_ids=knowledge_base_ids,
        mcp_servers=mcp_servers,
        published_expert_id=published_expert_id,
        welcome_message=welcome_message,
    )
