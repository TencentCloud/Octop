"""Field mapping between LightClaw config schema and Octop DB models."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Maps LightClaw provider ID → Octop provider kind string.
# Octop kind matches the harness-agent provider registry names.
_PROVIDER_KIND_MAP: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "google": "google",
    "qwen": "qwen",
    "baidu": "baidu",
    "moonshot": "moonshot",
    "zhipuai": "zhipuai",
    "ollama": "ollama",
    "groq": "groq",
    "mistral": "mistral",
    "cohere": "cohere",
    "azure": "azure",
    "bedrock": "bedrock",
    "vertex": "vertex",
}

# LightClaw channel key → Octop channel kind string
_CHANNEL_KIND_MAP: dict[str, str] = {
    "feishu": "feishu",
    "dingtalk": "dingtalk",
    "wecom": "wecom",
    "qqbot": "qq",
    "qq": "qq",
    "weixin": "weixin",
    "yuanbao": "yuanbao",
    "discord": "discord",
    "dashboard": "dashboard",
}


def map_provider_kind(lightclaw_provider_id: str) -> str:
    """Map a LightClaw provider identifier to Octop kind."""
    pid = lightclaw_provider_id.lower()
    return _PROVIDER_KIND_MAP.get(pid, pid)


def map_channel_kind(lightclaw_channel_key: str) -> str | None:
    """Map a LightClaw channel key to Octop channel kind.

    Returns None if the channel type is not supported by Octop.
    """
    return _CHANNEL_KIND_MAP.get(lightclaw_channel_key.lower())


def extract_providers(lightclaw_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract provider entries from a lightclaw.json config.

    Returns a list of dicts with keys:
      ``provider_id``, ``kind``, ``base_url``, ``api_key``, ``models_json``.
    """
    out: list[dict[str, Any]] = []
    models_section = lightclaw_config.get("models")
    if not isinstance(models_section, dict):
        return out
    providers_map = models_section.get("providers")
    if not isinstance(providers_map, dict):
        return out

    for pid, entry in providers_map.items():
        if not isinstance(entry, dict):
            continue
        kind = map_provider_kind(pid)
        base_url = (entry.get("baseUrl") or entry.get("base_url") or "").strip()
        # Extract API key — may be empty string if finnie stripped it
        raw_key = entry.get("apiKey") or entry.get("api_key") or ""
        api_key = raw_key.strip() if isinstance(raw_key, str) else None
        # Collect model list if present
        models: list[dict[str, Any]] = []
        for source_key in ("models", "extraModels", "extra_models"):
            ml = entry.get(source_key)
            if isinstance(ml, list):
                models.extend(ml)
        models_json = json.dumps(models, ensure_ascii=False) if models else None
        out.append(
            {
                "provider_id": pid,
                "kind": kind,
                "base_url": base_url or None,
                "api_key": api_key or None,
                "models_json": models_json,
            }
        )
    return out



def extract_active_model(lightclaw_config: dict[str, Any]) -> tuple[str, str]:
    """Return (provider_id, model_id) of the active LLM from config."""
    models_section = lightclaw_config.get("models", {})
    if not isinstance(models_section, dict):
        return "", ""
    active_llm = str(models_section.get("activeLlm", ""))
    if "/" not in active_llm:
        return "", ""
    pid, _, model = active_llm.partition("/")
    return pid.strip(), model.strip()


def build_octop_cron_trigger(lc_schedule: dict[str, Any]) -> str:
    """Convert a LightClaw ScheduleSpec to an Octop trigger string (cron expression)."""
    if not isinstance(lc_schedule, dict):
        return "0 9 * * *"
    cron_expr = str(lc_schedule.get("cron", "0 9 * * *")).strip()
    # Octop stores cron as a 5-field cron expression.
    parts = cron_expr.split()
    if len(parts) == 5:
        return cron_expr
    # Fallback: daily at 9am
    return "0 9 * * *"


def _extract_text_from_input(inp: Any) -> str:
    """Recursively extract plain text from a LightClaw request.input value.

    Handles all known shapes:
    - str                                → returned as-is
    - dict {"content"|"text": "..."}     → plain dict shorthand
    - list of message objects            → [{role, content: [{type:text, text:...}]}]
    """
    if isinstance(inp, str):
        return inp.strip()
    if isinstance(inp, dict):
        return str(inp.get("content") or inp.get("text") or "").strip()
    if isinstance(inp, list):
        # Message array: [{role, content: [{type, text}]}]
        parts: list[str] = []
        for msg in inp:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if isinstance(content, str):
                parts.append(content.strip())
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = str(block.get("text") or "").strip()
                        if text:
                            parts.append(text)
        return "\n".join(parts).strip()
    return ""


def extract_disabled_skills(lightclaw_config: dict[str, Any]) -> list[str]:
    """Extract the list of *disabled* skill names from lightclaw.json.

    LightClaw stores skill toggle state under ``skills.entries``:
    ``{"skills": {"entries": {"pdf": {"enabled": true}, "xlsx": {"enabled": false}}}}``

    Returns skill names where ``enabled`` is explicitly ``False``.
    Skills not listed in ``entries`` are treated as enabled (default) and are
    NOT included in the returned list — they will be migrated as normal.

    The caller uses this list to skip writing the corresponding
    ``workspace/skills/<name>/`` directory during import.
    """
    skills_section = lightclaw_config.get("skills")
    if not isinstance(skills_section, dict):
        return []
    entries = skills_section.get("entries")
    if not isinstance(entries, dict):
        return []
    disabled: list[str] = []
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled") is False:
            disabled.append(str(name))
    return disabled


def extract_job_prompt(lc_job: dict[str, Any]) -> str:
    """Extract the user-facing prompt/input text from a LightClaw CronJobSpec.

    Resolution order:
    1. task_type=='text'  → ``text`` field
    2. task_type=='agent' → ``request.input`` (str / dict / message-array)
    3. Fallback           → ``name`` field (job display name used as prompt stub)
    """
    # task_type='text' → use text field
    if lc_job.get("task_type") == "text":
        result = str(lc_job.get("text") or "").strip()
        if result:
            return result
    # task_type='agent' → use request.input (any shape)
    request_block = lc_job.get("request")
    if isinstance(request_block, dict):
        result = _extract_text_from_input(request_block.get("input"))
        if result:
            return result
    # Fallback: use job name as prompt stub so the job is not silently dropped
    return str(lc_job.get("name") or "").strip()
