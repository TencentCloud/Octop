"""Generate SkillHub expert welcome metadata with an internal generator skill."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

_SKILL_PATH = Path(__file__).with_name("manifest_generator_skill.md")
_MANIFEST_FILENAME = "manifest.json"
_MAX_WORKFLOW_CHARS = 6000
_MAX_SKILL_EXCERPT_CHARS = 500
_MAX_LABEL_CHARS = 64
_MAX_EXPERT_DESCRIPTION_CHARS = 220
_MAX_PROMPT_CHARS = 1200
_MAX_TITLE_CHARS = 48
_MAX_DESCRIPTION_CHARS = 120
_MAX_WELCOME_CHARS = 220
_MAX_QUICK_PROMPTS = 9

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
_COLOR_FALLBACKS = ["#e8f4ff", "#dcfce7", "#fef3c7", "#fce7f3"]
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


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
            "quick_prompt_min": 6,
            "quick_prompt_max": _MAX_QUICK_PROMPTS,
            "output": "label + description + welcome_message + quick_prompts for Octop expert manifest",
        },
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(context, ensure_ascii=False, indent=2)),
    ]
    generator_llm = _bind_json_response(llm)
    result = await asyncio.wait_for(
        generator_llm.ainvoke(messages),
        timeout=timeout,
    )
    raw = parse_model_json(_message_text(result))
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
    manifest["label"] = assets["label"]
    manifest["description"] = assets["description"]
    manifest["welcome_message"] = assets["welcome_message"]
    manifest["quick_prompts"] = assets["quick_prompts"]
    skillhub = manifest.get("skillhub")
    if not isinstance(skillhub, dict):
        skillhub = {}
    generated = {
        "by": "expert-manifest-generator",
        "model": model_ref,
    }
    skillhub["manifest_generated"] = generated
    skillhub["welcome_generated"] = generated
    manifest["skillhub"] = skillhub
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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
    welcome_zh, welcome_en = _localized_pair(
        welcome,
        fallback_zh=f"我是「{label_zh}」。告诉我你的目标和材料，我会按专家工作流推进。",
        fallback_en=(
            f"I am the {label_en}. Share your goal and materials, "
            "and I will follow the expert workflow."
        ),
        max_chars=_MAX_WELCOME_CHARS,
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
    return {
        "label": {"zh": label_zh, "en": label_en},
        "description": {"zh": expert_description_zh, "en": expert_description_en},
        "welcome_message": {"zh": welcome_zh, "en": welcome_en},
        "quick_prompts": prompts,
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
    if isinstance(value, str) and _HEX_COLOR_RE.fullmatch(value.strip()):
        return value.strip()
    return _COLOR_FALLBACKS[idx % len(_COLOR_FALLBACKS)]


def _normalize_icon(value: Any, idx: int) -> str:
    icon = str(value or "").strip()
    if icon in _ALLOWED_ICONS:
        return icon
    return _ICON_FALLBACKS[idx % len(_ICON_FALLBACKS)]


def _message_text(result: Any) -> str:
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content or "")


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
