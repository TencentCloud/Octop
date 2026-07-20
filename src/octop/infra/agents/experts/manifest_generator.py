"""Generate SkillHub expert welcome metadata with an internal generator skill."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from octop.infra.utils.llm_text import ainvoke_text

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).with_name("manifest_generator_skill.md")
_MANIFEST_FILENAME = "manifest.json"
_MAX_WORKFLOW_CHARS = 6000
_MAX_SKILL_EXCERPT_CHARS = 500
_MAX_LABEL_CHARS = 64
_MAX_EXPERT_DESCRIPTION_CHARS = 220
_MAX_PROMPT_CHARS = 180
_MAX_TITLE_CHARS = 18
_MAX_DESCRIPTION_CHARS = 36
_MAX_WELCOME_CHARS_ZH = 40
_MAX_WELCOME_CHARS_EN = 90
_MAX_QUICK_PROMPTS = 6
_MIN_QUICK_PROMPTS = 6

_ALLOWED_ICONS = {
    "zap",
    "list-todo",
    "file-text",
    "activity",
    "trending-up",
    "presentation",
    "cpu",
    "server",
    "wrench",
    "message-square",
    "book-open",
    "globe",
    "mail",
    "terminal",
    "hard-drive",
    "heart",
    "user",
    "sparkles",
}
_ICON_FALLBACKS = ["zap", "list-todo", "file-text", "presentation"]
_COLOR_FALLBACKS = (
    "#e8f4ff",
    "#dcfce7",
    "#fef3c7",
    "#fce7f3",
    "#f1f5f9",
    "#eef2ff",
    "#ecfeff",
    "#fff1f2",
)


class ExpertManifestGenerationError(RuntimeError):
    """Raised when model output cannot be normalized into manifest metadata."""


async def generate_and_apply_skillhub_manifest_assets(
    *,
    llm: Any,
    item: Any,
    expert_dir: Path,
    model_ref: str,
    timeout: float = 45.0,
) -> bool:
    """Generate welcome metadata for a cached SkillHub expert and write manifest.json.

    Returns ``True`` when model-generated assets were written. Callers should catch
    :class:`Exception` and keep the deterministic fallback manifest when generation
    fails; expert creation should never depend on this enrichment.
    """
    manifest_path = expert_dir / _MANIFEST_FILENAME
    manifest = await asyncio.to_thread(_read_manifest, manifest_path)
    if not manifest:
        raise ExpertManifestGenerationError("cached expert manifest is missing")

    skill_slugs = _manifest_skill_slugs(manifest)
    skillset_prompt = await asyncio.to_thread(
        _read_text,
        expert_dir / "skills" / item.slug / "SKILL.md",
    )
    if not skillset_prompt.strip():
        raise ExpertManifestGenerationError("cached skillset workflow prompt is missing")
    skill_context = await asyncio.to_thread(
        collect_skill_context,
        expert_dir,
        skill_slugs=skill_slugs,
        main_skill_slug=item.slug,
    )

    assets = await generate_skillhub_manifest_assets(
        llm=llm,
        item=item,
        skill_slugs=skill_slugs,
        skillset_prompt=skillset_prompt,
        skill_context=skill_context,
        timeout=timeout,
    )
    await asyncio.to_thread(
        apply_manifest_assets,
        manifest_path,
        assets,
        model_ref=model_ref,
    )
    return True


async def generate_skillhub_manifest_assets(
    *,
    llm: Any,
    item: Any,
    skill_slugs: list[str],
    skillset_prompt: str,
    skill_context: list[dict[str, str]],
    timeout: float = 45.0,
) -> dict[str, Any]:
    """Call the internal generator skill and return normalized manifest fields."""
    system_prompt = await asyncio.to_thread(_SKILL_PATH.read_text, encoding="utf-8")
    fallback_label_zh = _fallback_label_zh(item)
    fallback_label_en = _fallback_label_en(item)
    context = {
        "expert": {
            "slug": item.slug,
            "name_zh": fallback_label_zh,
            "name_en": fallback_label_en,
            "source_name_zh": item.display_name or item.slug,
            "source_name_en": item.display_name_en or "",
            "summary_zh": item.summary,
            "summary_en": item.summary_en or "",
            "scene": item.scene,
            "sub_scene": item.sub_scene,
            "skill_slugs": skill_slugs,
        },
        "workflow_prompt": _clip(skillset_prompt, _MAX_WORKFLOW_CHARS),
        "skills": skill_context,
        "target": {
            "locale_fields": ["zh", "en"],
            "welcome_max_chars_zh": _MAX_WELCOME_CHARS_ZH,
            "welcome_max_chars_en": _MAX_WELCOME_CHARS_EN,
            "quick_prompt_min": _MIN_QUICK_PROMPTS,
            "quick_prompt_max": _MAX_QUICK_PROMPTS,
            "output": "label + description + one-line welcome_message + quick_prompts for Octop expert manifest",
        },
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(context, ensure_ascii=False, indent=2)),
    ]
    generator_llm = _bind_json_response(llm)
    text = await ainvoke_text(generator_llm, messages, timeout=timeout)
    raw = parse_model_json(text)
    return normalize_manifest_assets(
        raw,
        fallback_name_zh=fallback_label_zh,
        fallback_name_en=fallback_label_en,
        fallback_summary_zh=item.summary,
        fallback_summary_en=item.summary_en or f"Expert workflow for {fallback_label_en}.",
    )


def _bind_json_response(llm: Any) -> Any:
    """Use provider JSON mode when the LangChain model supports binding kwargs."""
    bind = getattr(llm, "bind", None)
    if not callable(bind):
        return llm
    try:
        return bind(response_format={"type": "json_object"})
    except TypeError:
        return llm


def merge_manifest_assets(
    manifest: dict[str, Any],
    assets: dict[str, Any],
    *,
    model_ref: str,
) -> dict[str, Any]:
    """Return a copy of *manifest* with generated welcome metadata merged in."""
    out = dict(manifest)
    out["label"] = assets["label"]
    out["description"] = assets["description"]
    out["welcome_message"] = assets["welcome_message"]
    out["quick_prompts"] = assets["quick_prompts"]
    raw_skillhub = out.get("skillhub")
    skillhub = dict(raw_skillhub) if isinstance(raw_skillhub, dict) else {}
    generated = {
        "by": "expert-manifest-generator",
        "model": model_ref,
    }
    skillhub["manifest_generated"] = generated
    skillhub["welcome_generated"] = generated
    out["skillhub"] = skillhub
    return out


def apply_manifest_assets(
    manifest_path: Path,
    assets: dict[str, Any],
    *,
    model_ref: str,
) -> None:
    """Merge generated welcome metadata into a cached expert manifest."""
    manifest = _read_manifest(manifest_path)
    if manifest is None:
        raise ExpertManifestGenerationError("manifest is not valid JSON")
    merged = merge_manifest_assets(manifest, assets, model_ref=model_ref)
    manifest_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def build_skillhub_agent_manifest_bytes(
    *,
    llm: Any,
    item: Any,
    expert_dir: Path,
    model_ref: str,
    timeout: float = 45.0,
) -> bytes:
    """Generate welcome metadata from the cached template; return manifest bytes.

    Reads the shared SkillHub cache for workflow context only — does not mutate it.
    Callers should upload the returned bytes to the agent workspace.
    """
    manifest_path = expert_dir / _MANIFEST_FILENAME
    manifest = await asyncio.to_thread(_read_manifest, manifest_path)
    if not manifest:
        raise ExpertManifestGenerationError("cached expert manifest is missing")

    skill_slugs = _manifest_skill_slugs(manifest)
    skillset_prompt = await asyncio.to_thread(
        _read_text,
        expert_dir / "skills" / item.slug / "SKILL.md",
    )
    if not skillset_prompt.strip():
        raise ExpertManifestGenerationError("cached skillset workflow prompt is missing")
    skill_context = await asyncio.to_thread(
        collect_skill_context,
        expert_dir,
        skill_slugs=skill_slugs,
        main_skill_slug=item.slug,
    )

    assets = await generate_skillhub_manifest_assets(
        llm=llm,
        item=item,
        skill_slugs=skill_slugs,
        skillset_prompt=skillset_prompt,
        skill_context=skill_context,
        timeout=timeout,
    )
    merged = merge_manifest_assets(manifest, assets, model_ref=model_ref)
    return (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def collect_skill_context(
    expert_dir: Path,
    *,
    skill_slugs: list[str],
    main_skill_slug: str,
) -> list[dict[str, str]]:
    """Summarize cached skill files for the generator prompt."""
    ordered = _unique([main_skill_slug, *skill_slugs])
    out: list[dict[str, str]] = []
    for slug in ordered:
        text = _read_text(expert_dir / "skills" / slug / "SKILL.md")
        if not text.strip():
            continue
        meta = _frontmatter(text)
        body = _strip_frontmatter(text)
        out.append(
            {
                "slug": slug,
                "name": meta.get("name") or slug,
                "description": meta.get("description") or "",
                "excerpt": _clip(body.strip(), _MAX_SKILL_EXCERPT_CHARS),
            },
        )
    return out


def parse_model_json(text: str) -> dict[str, Any]:
    """Extract one JSON object from a model response."""
    cleaned = text.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ExpertManifestGenerationError("model did not return JSON") from None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExpertManifestGenerationError("model returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ExpertManifestGenerationError("model JSON root must be an object")
    return payload


def normalize_manifest_assets(
    payload: dict[str, Any],
    *,
    fallback_name_zh: str,
    fallback_name_en: str,
    fallback_summary_zh: str = "",
    fallback_summary_en: str = "",
) -> dict[str, Any]:
    """Validate and trim generated manifest fields."""
    if isinstance(payload.get("manifest"), dict):
        payload = payload["manifest"]
    label_zh, label_en = _localized_pair(
        payload.get("label"),
        fallback_zh=fallback_name_zh,
        fallback_en=fallback_name_en,
        max_chars=_MAX_LABEL_CHARS,
    )
    label_zh = _ensure_zh_expert_label(label_zh)
    label_en = _ensure_en_expert_label(label_en)

    expert_description_zh, expert_description_en = _localized_pair(
        payload.get("description"),
        fallback_zh=fallback_summary_zh or f"围绕「{label_zh}」提供专家级工作流支持。",
        fallback_en=fallback_summary_en or f"Expert workflow for {label_en}.",
        max_chars=_MAX_EXPERT_DESCRIPTION_CHARS,
    )
    welcome = payload.get("welcome_message")
    if isinstance(welcome, dict):
        welcome_zh_raw = str(welcome.get("zh") or welcome.get("cn") or "")
        welcome_en_raw = str(welcome.get("en") or "")
    elif isinstance(welcome, str):
        welcome_zh_raw, welcome_en_raw = welcome, ""
    else:
        welcome_zh_raw, welcome_en_raw = "", ""
    welcome_zh_fallback = _capability_welcome_fallback_zh(expert_description_zh)
    welcome_en_fallback = _capability_welcome_fallback_en(expert_description_en)
    welcome_zh = _clip_welcome(
        welcome_zh_raw.strip(),
        _MAX_WELCOME_CHARS_ZH,
        fallback=welcome_zh_fallback,
        require_chinese=True,
    )
    welcome_en = _clip_welcome(
        welcome_en_raw.strip(),
        _MAX_WELCOME_CHARS_EN,
        fallback=welcome_en_fallback,
        require_chinese=False,
    )

    raw_prompts = payload.get("quick_prompts")
    if not isinstance(raw_prompts, list):
        raise ExpertManifestGenerationError("quick_prompts must be a list")

    prompts: list[dict[str, Any]] = []
    for idx, raw in enumerate(raw_prompts):
        if not isinstance(raw, dict):
            continue
        title_zh, title_en = _localized_pair(
            raw.get("title"),
            fallback_zh="开始处理",
            fallback_en="Start work",
            max_chars=_MAX_TITLE_CHARS,
        )
        description_zh, description_en = _localized_pair(
            raw.get("description"),
            fallback_zh="描述目标、材料和期望结果",
            fallback_en="Describe the goal, materials, and expected result",
            max_chars=_MAX_DESCRIPTION_CHARS,
        )
        prompt_zh, prompt_en = _localized_pair(
            raw.get("prompt"),
            fallback_zh=f"请作为「{label_zh}」，帮我处理以下任务：\n\n",
            fallback_en=f"As the {label_en}, help me with this task:\n\n",
            max_chars=_MAX_PROMPT_CHARS,
        )
        if not (title_zh and title_en and prompt_zh and prompt_en):
            continue
        prompts.append(
            {
                "title": {"zh": title_zh, "en": title_en},
                "description": {"zh": description_zh, "en": description_en},
                "prompt": {"zh": prompt_zh, "en": prompt_en},
                "color": _normalize_color(raw.get("color"), idx),
                "icon_name": _normalize_icon(raw.get("icon_name"), idx),
            },
        )
        if len(prompts) >= _MAX_QUICK_PROMPTS:
            break

    if len(prompts) < 2:
        raise ExpertManifestGenerationError("model returned too few usable quick prompts")
    while len(prompts) < _MIN_QUICK_PROMPTS:
        idx = len(prompts)
        prompts.append(
            {
                "title": {
                    "zh": _clip(f"继续推进 {idx + 1}", _MAX_TITLE_CHARS),
                    "en": _clip(f"Continue {idx + 1}", _MAX_TITLE_CHARS),
                },
                "description": {
                    "zh": "补充目标与材料，继续专家工作流",
                    "en": "Add context and continue the workflow",
                },
                "prompt": {
                    "zh": f"请作为「{label_zh}」，帮我继续推进下一步。\n我的情况/目标/材料是：\n",
                    "en": (
                        f"As the {label_en}, help me continue with the next step.\n"
                        "My context, goals, or materials are:\n"
                    ),
                },
                "color": _normalize_color(None, idx),
                "icon_name": _normalize_icon(None, idx),
            },
        )
    return {
        "label": {"zh": label_zh, "en": label_en},
        "description": {"zh": expert_description_zh, "en": expert_description_en},
        "welcome_message": {"zh": welcome_zh, "en": welcome_en},
        "quick_prompts": prompts[:_MAX_QUICK_PROMPTS],
    }


def _manifest_skill_slugs(manifest: dict[str, Any]) -> list[str]:
    skillhub = manifest.get("skillhub")
    raw = skillhub.get("skill_slugs") if isinstance(skillhub, dict) else None
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    return []


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[4:end].splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip().strip("\"'")
    return out


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    return text[end + 4 :].lstrip("\n") if end != -1 else text


def _fallback_label_zh(item: Any) -> str:
    name = str(getattr(item, "display_name", "") or getattr(item, "slug", "") or "").strip()
    if not name:
        return "专家"
    return _ensure_zh_expert_label(name)


def _fallback_label_en(item: Any) -> str:
    raw = str(getattr(item, "display_name_en", "") or "").strip()
    if not raw:
        raw = _title_from_slug(str(getattr(item, "slug", "") or ""))
    if not raw:
        raw = "Expert"
    return _ensure_en_expert_label(raw)


def _title_from_slug(slug: str) -> str:
    words = [word for word in re.split(r"[-_.\s]+", slug.strip()) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _ensure_zh_expert_label(name: str) -> str:
    text = name.strip()
    if not text:
        return "专家"
    return text if text.endswith("专家") else f"{text}专家"


def _ensure_en_expert_label(name: str) -> str:
    text = name.strip()
    if not text:
        return "Expert"
    return text if text.lower().endswith("expert") else f"{text} Expert"


def _localized_pair(
    node: Any,
    *,
    fallback_zh: str,
    fallback_en: str,
    max_chars: int,
) -> tuple[str, str]:
    if isinstance(node, dict):
        zh = str(node.get("zh") or node.get("cn") or fallback_zh)
        en = str(node.get("en") or fallback_en)
    elif isinstance(node, str):
        zh, en = node, fallback_en
    else:
        zh, en = fallback_zh, fallback_en
    return _clip(zh.strip(), max_chars), _clip(en.strip(), max_chars)


def _normalize_color(value: Any, idx: int) -> str:
    """Assign quick-card chip colors from the built-in pastel palette.

    Model-provided colors are ignored: LLMs often emit saturated brand colors that
    do not match bundled expert chips even after lightening.
    """
    return _COLOR_FALLBACKS[idx % len(_COLOR_FALLBACKS)]


def _normalize_icon(value: Any, idx: int) -> str:
    icon = str(value or "").strip()
    if icon in _ALLOWED_ICONS:
        return icon
    return _ICON_FALLBACKS[idx % len(_ICON_FALLBACKS)]


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _clip_welcome(
    text: str,
    max_chars: int,
    *,
    fallback: str,
    require_chinese: bool | None = None,
) -> str:
    """Return one complete welcome line; never mid-sentence ellipsis."""
    cleaned = " ".join((text or "").split())
    if require_chinese is True and cleaned and not _looks_chinese(cleaned):
        cleaned = ""
    if require_chinese is False and cleaned and _looks_chinese(cleaned):
        cleaned = ""
    if cleaned:
        for sep in ("。", "！", "？", ".", "!", "?"):
            idx = cleaned.find(sep)
            if idx >= 6:
                cleaned = cleaned[:idx].strip()
                break
        if 6 <= len(cleaned) <= max_chars:
            return cleaned
    fb = " ".join((fallback or "").split())
    if not fb:
        return ""
    if len(fb) <= max_chars:
        return fb
    # Fallbacks are authored short; keep a complete prefix without ellipsis marks.
    for sep in ("，", ",", "、", " "):
        idx = fb.rfind(sep, 0, max_chars + 1)
        if idx >= 6:
            return fb[:idx].strip()
    return fb[:max_chars].rstrip()


_CJK_RE = re.compile(r"[\u3400-\u9fff]")


def _looks_chinese(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def _capability_welcome_fallback_zh(description_zh: str) -> str:
    line = _clip_welcome(
        description_zh,
        _MAX_WELCOME_CHARS_ZH,
        fallback="提供专业、可落地的专家工作流支持",
        require_chinese=True,
    )
    return line or "提供专业、可落地的专家工作流支持"


def _capability_welcome_fallback_en(description_en: str) -> str:
    line = _clip_welcome(
        description_en,
        _MAX_WELCOME_CHARS_EN,
        fallback="Practical expert workflow support for your goals",
        require_chinese=False,
    )
    return line or "Practical expert workflow support for your goals"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
