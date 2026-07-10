"""SkillHub skillset marketplace integration for expert templates.

SkillHub currently exposes expert-like assets as *skillsets*. A skillset is a
workflow prompt plus a list of skill slugs. We normalize that package into the
same on-disk shape as bundled experts:

``manifest.json`` + ``SOUL.md`` + ``skills/<slug>/SKILL.md``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

MARKET_EXPERT_PREFIX = "skillhub-skillset-"
DEFAULT_SKILLHUB_HOST = "https://api.skillhub.cn"
_HTTP_TIMEOUT = 30
_SKILLSET_PAGE_SIZE = 100
_MAX_SKILLSET_PAGES = 20
_MAX_WORKFLOW_QUICK_PROMPTS = 9
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_STEP_HEADING_RE = re.compile(r"^##\s*步骤\s*(\d+)\s*[：:]\s*(.+?)\s*$", re.MULTILINE)
_QUICK_PROMPT_COLORS = (
    "#e8f4ff",
    "#fef3c7",
    "#dcfce7",
    "#f1f5f9",
    "#fff1f2",
    "#eef2ff",
    "#ecfeff",
    "#f0fdf4",
    "#faf5ff",
)


class SkillHubMarketError(RuntimeError):
    """Raised when SkillHub marketplace fetch/install fails."""


@dataclass(frozen=True)
class SkillHubSkillset:
    slug: str
    display_name: str
    display_name_en: str = ""
    summary: str = ""
    summary_en: str = ""
    scene: str = ""
    sub_scene: str = ""
    content: str = ""
    content_en: str = ""
    icon_url: str = ""
    skill_slugs: tuple[str, ...] = ()
    skill_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def expert_id(self) -> str:
        return market_expert_id(self.slug)

    def api_dict(self, *, include_content: bool = False) -> dict[str, Any]:
        name_zh = _expert_label_zh(self)
        name_en = _expert_label_en(self)
        out: dict[str, Any] = {
            "id": self.expert_id,
            "slug": self.slug,
            "label": {
                "zh": name_zh,
                "en": name_en,
            },
            "description": {
                "zh": self.summary,
                "en": _expert_summary_en(self, name_en),
            },
            "scene": self.scene,
            "sub_scene": self.sub_scene,
            "icon_url": self.icon_url or None,
            "icon_name": _scene_icon_name(self.scene),
            "color": _scene_color(self.scene),
            "skill_slugs": list(self.skill_slugs),
            "skill_count": self.skill_count or len(self.skill_slugs),
            "source": "skillhub",
        }
        if include_content:
            out["content"] = {"zh": self.content, "en": self.content_en}
            out["quick_prompts"] = quick_prompts_for_skillset(self)
        return out


def market_expert_id(slug: str) -> str:
    return f"{MARKET_EXPERT_PREFIX}{slug}"


def validate_skillset_slug(slug: str) -> str:
    trimmed = slug.strip()
    if not trimmed or not _SLUG_RE.fullmatch(trimmed):
        raise SkillHubMarketError("invalid skillset slug")
    return trimmed


def fetch_skillsets(query: str = "") -> list[SkillHubSkillset]:
    items = _fetch_all_skillsets()
    q = query.strip().lower()
    if not q:
        return items
    return [
        item
        for item in items
        if q in item.slug.lower()
        or q in item.display_name.lower()
        or q in item.display_name_en.lower()
        or q in item.summary.lower()
        or q in item.summary_en.lower()
        or q in item.scene.lower()
        or q in item.sub_scene.lower()
    ]


def _fetch_all_skillsets() -> list[SkillHubSkillset]:
    """Fetch the full SkillHub skillset list.

    The SkillHub endpoint defaults to 20 rows even though it returns ``total``.
    ``limit=`` is ignored by the current API; ``page`` + ``pageSize`` is the
    supported shape.
    """
    items: list[SkillHubSkillset] = []
    seen: set[str] = set()
    total: int | None = None
    page = 1

    while page <= _MAX_SKILLSET_PAGES:
        data = _http_json_get(
            _api_url(
                "/api/v1/skillsets",
                params={"page": page, "pageSize": _SKILLSET_PAGE_SIZE},
            )
        )
        raw_items = data.get("skillSets") if isinstance(data, dict) else None
        if not isinstance(raw_items, list):
            raise SkillHubMarketError("SkillHub skillsets response is invalid")
        if total is None:
            total = _coerce_positive_int(data.get("total")) if isinstance(data, dict) else None

        page_items = [_skillset_from_raw(x) for x in raw_items if isinstance(x, dict)]
        for item in page_items:
            if not item.slug or item.slug in seen:
                continue
            seen.add(item.slug)
            items.append(item)

        if not raw_items:
            break
        if total is not None and len(items) >= total:
            break
        if len(raw_items) < _SKILLSET_PAGE_SIZE:
            break
        page += 1

    return items


def fetch_skillset(slug: str) -> SkillHubSkillset:
    safe_slug = validate_skillset_slug(slug)
    for item in fetch_skillsets():
        if item.slug == safe_slug:
            return item
    raise SkillHubMarketError(f"SkillHub skillset {safe_slug!r} not found")


def install_skillset_template(*, slug: str, cache_root: Path) -> SkillHubSkillset:
    """Download a SkillHub skillset and cache it as an ExpertCatalog directory."""
    item = fetch_skillset(slug)
    package = _download_skillset_package(item.slug)
    manifest, prompt = _parse_skillset_package(
        package,
        skillset_slug=item.slug,
        fallback_content=item.content,
    )
    skill_slugs = _manifest_skill_slugs(manifest) or list(item.skill_slugs)
    if not skill_slugs:
        raise SkillHubMarketError(f"SkillHub skillset {item.slug!r} has no skills")

    cache_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skillhub-expert-") as tmp:
        tmp_expert_dir = Path(tmp) / item.expert_id
        _write_expert_template(
            expert_dir=tmp_expert_dir,
            item=item,
            skill_slugs=skill_slugs,
            skillset_prompt=prompt,
        )
        for skill_slug in skill_slugs:
            _download_skill_into_template(
                skill_slug=skill_slug,
                expert_dir=tmp_expert_dir,
            )

        target = cache_root / item.expert_id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(tmp_expert_dir, target)
    return item


def _skillset_from_raw(raw: dict[str, Any]) -> SkillHubSkillset:
    skill_slugs = raw.get("skillSlugs")
    if not isinstance(skill_slugs, list):
        skill_slugs = []
    return SkillHubSkillset(
        slug=str(raw.get("slug") or "").strip(),
        display_name=str(raw.get("displayName") or raw.get("name") or "").strip(),
        display_name_en=str(raw.get("displayNameEn") or "").strip(),
        summary=str(raw.get("summary") or raw.get("description") or "").strip(),
        summary_en=str(raw.get("summaryEn") or "").strip(),
        scene=str(raw.get("scene") or "").strip(),
        sub_scene=str(raw.get("subScene") or raw.get("sub_scene") or "").strip(),
        content=str(raw.get("content") or "").strip(),
        content_en=str(raw.get("contentEn") or "").strip(),
        icon_url=str(raw.get("iconUrl") or "").strip(),
        skill_slugs=tuple(str(s).strip() for s in skill_slugs if str(s).strip()),
        skill_count=int(raw.get("skillCount") or len(skill_slugs)),
        raw=raw,
    )


def _coerce_positive_int(value: Any) -> int | None:
    try:
        out = int(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def _api_host() -> str:
    return (os.environ.get("SKILLHUB_HOST", "").strip() or DEFAULT_SKILLHUB_HOST).rstrip("/")


def _api_url(path: str, params: dict[str, Any] | None = None) -> str:
    url = f"{_api_host()}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _http_get(url: str, *, accept: str) -> bytes:
    req = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "octop-expert-skillhub/1.0",
        },
    )
    try:
        with urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return bytes(resp.read())
    except HTTPError as exc:
        if exc.code == 404:
            raise SkillHubMarketError(f"SkillHub resource not found: {url}") from exc
        raise SkillHubMarketError(f"SkillHub request failed: HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SkillHubMarketError(f"SkillHub request failed: {exc}") from exc


def _http_json_get(url: str) -> Any:
    payload = _http_get(url, accept="application/json")
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillHubMarketError("SkillHub returned invalid JSON") from exc


def _download_skillset_package(slug: str) -> bytes:
    url = _api_url(f"/api/v1/skillsets/{quote(slug, safe='')}/download")
    return _http_get(url, accept="application/zip,*/*")


def _download_skill_package(slug: str) -> bytes:
    url = _api_url("/api/v1/download", params={"slug": slug})
    return _http_get(url, accept="application/zip,*/*")


def _parse_skillset_package(
    zip_bytes: bytes,
    *,
    skillset_slug: str,
    fallback_content: str,
) -> tuple[dict[str, Any], str]:
    try:
        import io

        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            _validate_zip(zf)
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            prompt = ""
            zip_names = zf.namelist()
            skillset_files = [
                n for n in zip_names if n.startswith("skillsets/") and n.endswith(".md")
            ]
            if skillset_files:
                preferred = f"skillsets/{skillset_slug}.md"
                selected = preferred if preferred in zip_names else skillset_files[0]
                prompt = zf.read(selected).decode("utf-8")
            elif "identify.md" in zip_names:
                prompt = zf.read("identify.md").decode("utf-8")
            elif fallback_content:
                prompt = fallback_content
    except KeyError as exc:
        raise SkillHubMarketError("SkillHub skillset package missing manifest.json") from exc
    except Exception as exc:
        raise SkillHubMarketError(f"Failed to parse SkillHub skillset package: {exc}") from exc
    if not isinstance(manifest, dict):
        raise SkillHubMarketError("SkillHub skillset manifest is invalid")
    if not prompt.strip():
        raise SkillHubMarketError("SkillHub skillset package missing workflow prompt")
    return manifest, _dedupe_frontmatter(prompt)


def _manifest_skill_slugs(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get("skillSlugs")
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    skillsets = manifest.get("skillSets")
    if not isinstance(skillsets, list):
        return []
    out: list[str] = []
    for item in skillsets:
        if not isinstance(item, dict):
            continue
        slugs = item.get("skillSlugs")
        if isinstance(slugs, list):
            out.extend(str(s).strip() for s in slugs if str(s).strip())
    seen: set[str] = set()
    deduped: list[str] = []
    for slug in out:
        if slug in seen:
            continue
        seen.add(slug)
        deduped.append(slug)
    return deduped


def _write_expert_template(
    *,
    expert_dir: Path,
    item: SkillHubSkillset,
    skill_slugs: list[str],
    skillset_prompt: str,
) -> None:
    expert_dir.mkdir(parents=True, exist_ok=True)
    (expert_dir / "manifest.json").write_text(
        json.dumps(
            _expert_manifest(item, skill_slugs, skillset_prompt=skillset_prompt),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (expert_dir / "SOUL.md").write_text(_expert_soul(item, skill_slugs), encoding="utf-8")
    skillset_dir = expert_dir / "skills" / item.slug
    skillset_dir.mkdir(parents=True, exist_ok=True)
    (skillset_dir / "SKILL.md").write_text(skillset_prompt, encoding="utf-8")


def _download_skill_into_template(*, skill_slug: str, expert_dir: Path) -> None:
    validate_skillset_slug(skill_slug)
    zip_bytes = _download_skill_package(skill_slug)
    target_dir = expert_dir / "skills" / skill_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    _extract_zip(zip_bytes, target_dir)


def _extract_zip(zip_bytes: bytes, target_dir: Path) -> None:
    import io

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        _validate_zip(zf)
        for member in zf.infolist():
            if member.is_dir():
                continue
            dest = target_dir / member.filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src:
                dest.write_bytes(src.read())


def _validate_zip(zf: zipfile.ZipFile) -> None:
    for member in zf.infolist():
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise SkillHubMarketError(f"unsafe zip path entry: {member.filename}")


def _dedupe_frontmatter(text: str) -> str:
    """Remove a repeated leading YAML frontmatter block if SkillHub duplicated it."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    if end == -1:
        return text
    block = text[: end + 4]
    rest = text[end + 4 :].lstrip("\n")
    if rest.startswith(block):
        return f"{block}\n\n{rest[len(block) :].lstrip()}"
    return text


def _expert_label_zh(item: SkillHubSkillset) -> str:
    name = (item.display_name or item.slug).strip()
    if not name:
        return "专家"
    return name if name.endswith("专家") else f"{name}专家"


def _expert_label_en(item: SkillHubSkillset) -> str:
    name = (item.display_name_en or _title_from_slug(item.slug) or item.slug).strip()
    if not name:
        return "Expert"
    return name if name.lower().endswith("expert") else f"{name} Expert"


def _expert_summary_en(item: SkillHubSkillset, name_en: str) -> str:
    return item.summary_en.strip() if item.summary_en.strip() else f"Expert workflow for {name_en}."


def _title_from_slug(slug: str) -> str:
    words = [word for word in re.split(r"[-_.\s]+", slug.strip()) if word]
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _expert_manifest(
    item: SkillHubSkillset,
    skill_slugs: list[str],
    *,
    skillset_prompt: str = "",
) -> dict[str, Any]:
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    summary_zh = item.summary
    summary_en = _expert_summary_en(item, name_en)
    return {
        "id": item.expert_id,
        "label": {"zh": name_zh, "en": name_en},
        "description": {"zh": summary_zh, "en": summary_en},
        "welcome_message": {
            "zh": f"我是「{name_zh}」。描述你的目标、材料或上下文，我会按专家工作流推进。",
            "en": f"I am the {name_en}. Describe your goal or context and I will follow the expert workflow.",
        },
        "icon_name": _scene_icon_name(item.scene),
        "color": _scene_color(item.scene),
        "prompt_files": ["SOUL.md"],
        "quick_prompts": quick_prompts_for_skillset(item, skillset_prompt),
        "source": {
            "type": "skillhub",
            "kind": "skillset",
            "slug": item.slug,
            "scene": item.scene,
            "sub_scene": item.sub_scene,
        },
        "skillhub": {
            "slug": item.slug,
            "scene": item.scene,
            "sub_scene": item.sub_scene,
            "skill_slugs": skill_slugs,
        },
    }


def _expert_soul(item: SkillHubSkillset, skill_slugs: list[str]) -> str:
    name = _expert_label_zh(item)
    skill_list = "\n".join(f"- `{slug}`" for slug in skill_slugs)
    summary = item.summary or "围绕该 SkillHub skillset 提供专家级工作流支持。"
    return f"""# {name}

你是「{name}」，来源于 SkillHub skillset `{item.slug}`。

## 专家定位

{summary}

## 工作方式

- 优先遵循 `skills/{item.slug}/SKILL.md` 中的工作流编排。
- 根据用户目标主动拆解步骤、识别输入缺口，并给出可执行产物。
- 需要具体能力时，调用已安装的配套技能；不要把技能清单当作用户可见负担。
- 输出时保持结构清晰，先给结论和下一步，再补充必要依据。

## 配套技能

{skill_list}
"""


def _default_quick_prompts(item: SkillHubSkillset) -> list[dict[str, Any]]:
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    return [
        {
            "title": {"zh": "开始处理任务", "en": "Start a task"},
            "description": {
                "zh": "描述目标和上下文，按专家工作流推进",
                "en": "Describe the goal and context; follow the expert workflow",
            },
            "prompt": {
                "zh": f"请作为「{name_zh}」，帮我完成以下任务：\n\n",
                "en": f"As the {name_en}, help me complete this task:\n\n",
            },
            "color": "#e8f4ff",
            "icon_name": "zap",
        },
        {
            "title": {"zh": "先制定计划", "en": "Make a plan first"},
            "description": {
                "zh": "先拆解步骤、输入材料和交付物",
                "en": "Break down steps, required inputs, and deliverables first",
            },
            "prompt": {
                "zh": f"请根据「{name_zh}」工作流，先为下面的问题制定执行计划：\n\n",
                "en": f"Using the {name_en} workflow, first create an execution plan for:\n\n",
            },
            "color": "#dcfce7",
            "icon_name": "list-todo",
        },
    ]


def quick_prompts_for_skillset(
    item: SkillHubSkillset,
    workflow_prompt: str | None = None,
) -> list[dict[str, Any]]:
    prompts = _workflow_quick_prompts(item, workflow_prompt or item.content)
    return prompts if prompts else _default_quick_prompts(item)


def _workflow_quick_prompts(
    item: SkillHubSkillset,
    workflow_prompt: str,
) -> list[dict[str, Any]]:
    steps = _workflow_steps(workflow_prompt)
    if not steps:
        return []
    name_zh = _expert_label_zh(item)
    name_en = _expert_label_en(item)
    prompts: list[dict[str, Any]] = []
    for idx, step in enumerate(steps[:_MAX_WORKFLOW_QUICK_PROMPTS]):
        title = _clip_text(step["title"], 22)
        description = _clip_text(_step_description(step["section"]), 42)
        if not description:
            description = f"按工作流完成{title}"
        prompts.append(
            {
                "title": {"zh": title, "en": f"Workflow step {idx + 1}"},
                "description": {
                    "zh": description,
                    "en": "Run this step and produce the requested deliverable",
                },
                "prompt": {
                    "zh": _workflow_prompt_zh(name_zh, step),
                    "en": _workflow_prompt_en(name_en, idx, step),
                },
                "color": _QUICK_PROMPT_COLORS[idx % len(_QUICK_PROMPT_COLORS)],
                "icon_name": _quick_prompt_icon(step["title"], step["section"], idx),
            }
        )
    return prompts


def _workflow_steps(workflow_prompt: str) -> list[dict[str, str]]:
    matches = list(_STEP_HEADING_RE.finditer(workflow_prompt or ""))
    steps: list[dict[str, str]] = []
    for idx, match in enumerate(matches):
        section_start = match.end()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(workflow_prompt)
        raw_title = match.group(2).strip()
        title = _clean_step_title(raw_title)
        if not title:
            continue
        steps.append(
            {
                "number": match.group(1),
                "title": title,
                "section": workflow_prompt[section_start:section_end].strip(),
            }
        )
    return steps


def _clean_step_title(raw: str) -> str:
    text = re.sub(r"[（(][^）)]*层[）)]", "", raw).strip()
    return text.strip(" ：:-")


def _workflow_prompt_zh(name_zh: str, step: dict[str, str]) -> str:
    actions = _step_actions(step["section"])
    output = _step_output_target(step["section"])
    lines = [
        f"我想做一次「{step['title']}」。",
        "",
        f"请作为「{name_zh}」，按以下方式引导我：",
    ]
    if actions:
        lines.extend(f"{idx}. {action}" for idx, action in enumerate(actions, start=1))
    else:
        lines.extend(
            [
                "1. 先澄清目标、输入材料和限制条件",
                "2. 按专家工作流完成分析和处理",
                "3. 给出可直接执行的下一步建议",
            ]
        )
    if output:
        lines.extend(["", f"请输出：{output}。"])
    else:
        lines.extend(["", "请输出可直接使用的结果，并标明下一步建议。"])
    lines.extend(["", "我的情况/目标/材料是：", ""])
    return "\n".join(lines)


def _workflow_prompt_en(
    name_en: str,
    idx: int,
    step: dict[str, str],
) -> str:
    lines = [
        f"As the {name_en}, help me complete workflow step {idx + 1}.",
        "",
        "Please guide me through the required inputs, analysis, and deliverable.",
        "Ask for any missing context before producing the final result.",
        "Keep the output practical and ready to use.",
    ]
    lines.extend(["", "My context, goals, or materials are:", ""])
    return "\n".join(lines)


def _step_description(section: str) -> str:
    output = _step_output_target(section)
    if output:
        return _normalize_output_line(output)
    for line in section.splitlines():
        text = _clean_markdown_line(line)
        if not text:
            continue
        if text.startswith("- "):
            return text[2:].strip().rstrip("。")
    return ""


def _step_actions(section: str, limit: int = 4) -> list[str]:
    actions: list[str] = []
    seen: set[str] = set()
    for line in section.splitlines():
        text = _clean_markdown_line(line)
        if not text.startswith("- "):
            continue
        action = text[2:].strip().rstrip("。")
        if not action or action.startswith(("输出", "输出物")):
            continue
        if action in seen:
            continue
        seen.add(action)
        actions.append(action)
        if len(actions) >= limit:
            break
    return actions


def _step_output_target(section: str) -> str:
    for line in section.splitlines():
        text = _clean_markdown_line(line)
        if not text:
            continue
        if text.startswith("输出物"):
            return _normalize_output_target(text.removeprefix("输出物"))
        if text.startswith("输出"):
            return _normalize_output_target(text.removeprefix("输出"))
    return ""


def _clean_markdown_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^\s*[-*]\s+", "- ", text)
    text = text.replace("**", "").replace("`", "")
    return text.strip()


def _normalize_output_target(text: str) -> str:
    text = text.strip(" ：:。")
    if text.startswith("：") or text.startswith(":"):
        text = text[1:].strip()
    return text.rstrip("。")


def _normalize_output_line(text: str) -> str:
    target = _normalize_output_target(text)
    if not target:
        return ""
    if target.startswith(("生成", "输出", "给出", "形成", "交付")):
        return target.rstrip("。")
    return f"生成{target}".rstrip("。")


def _clip_text(text: str, max_chars: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean
    return clean[: max_chars - 1].rstrip() + "…"


def _quick_prompt_icon(title: str, section: str, idx: int) -> str:
    text = f"{title}\n{section}"
    keyword_icons = [
        (("巡检", "健康", "诊断", "异常", "日志", "监控", "分析"), "activity"),
        (("评分", "指标", "数据", "统计", "预算", "投研", "经营", "趋势"), "trending-up"),
        (("修复", "调试", "排查", "配置", "风险"), "wrench"),
        (("云", "实例", "OS", "服务器", "集群", "节点"), "server"),
        (("代码", "测试", "脚本", "命令", "自动化"), "terminal"),
        (("视频", "分镜", "镜头", "画面", "剪辑", "脚本"), "video"),
        (("合同", "文书", "报告", "纪要", "简历", "法条"), "file-text"),
        (("检索", "搜索", "法规", "跨境", "市场"), "globe"),
        (("计划", "方案", "策略", "SOP", "流程", "清单"), "list-todo"),
        (("输出", "生成", "导出", "PPT", "PDF", "交付"), "presentation"),
    ]
    for keywords, icon in keyword_icons:
        if any(k in text for k in keywords):
            return icon
    return [
        "zap",
        "list-todo",
        "activity",
        "file-text",
        "presentation",
        "sparkles",
        "message-square",
        "book-open",
        "globe",
    ][idx % 9]


def _scene_icon_name(scene: str) -> str:
    mapping = {
        "academic": "book-open",
        "content-creation": "pen-tool",
        "design": "palette",
        "ecommerce": "globe",
        "education": "book-open",
        "finance": "candlestick-chart",
        "healthcare": "heart",
        "lifestyle": "heart",
        "marketing": "trending-up",
        "mysticism": "sparkles",
        "tech": "cpu",
        "media": "video",
        "legal": "file-text",
        "hr": "user",
        "office": "presentation",
        "data": "trending-up",
    }
    return mapping.get(scene, "zap")


def _scene_color(scene: str) -> str:
    mapping = {
        "academic": "#4f46e5",
        "content-creation": "#c026d3",
        "design": "#db2777",
        "ecommerce": "#16a34a",
        "education": "#2563eb",
        "finance": "#059669",
        "healthcare": "#dc2626",
        "lifestyle": "#f97316",
        "marketing": "#ca8a04",
        "mysticism": "#7c3aed",
        "tech": "#2563eb",
        "media": "#db2777",
        "legal": "#0f766e",
        "hr": "#7c3aed",
        "office": "#ea580c",
        "data": "#0891b2",
    }
    return mapping.get(scene, "#6366f1")
