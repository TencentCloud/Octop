#!/usr/bin/env python3
"""Validate phase-1 clinical learning outputs before delivery."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = PACKAGE_ROOT / "references" / "source-policy.yaml"


def _load_list_yaml(path: Path) -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_key = line[:-1].strip()
            data[current_key] = []
            continue
        if current_key and line.strip().startswith("- "):
            value = line.strip()[2:].strip().strip('"').strip("'")
            value = value.replace("\\\\", "\\")
            data[current_key].append(value)
    return data


def _domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lower().split("@")[-1].split(":")[0]


def _is_allowed_domain(domain: str, policy: dict[str, list[str]]) -> bool:
    if domain in set(policy.get("blocked_final_evidence_domains", [])):
        return False
    if domain in set(policy.get("allowed_final_evidence_exact_domains", [])):
        return True
    for suffix in policy.get("allowed_final_evidence_domain_suffixes", []):
        normalized = suffix.lower()
        if normalized.startswith(".") and domain.endswith(normalized):
            return True
        if domain == normalized:
            return True
    return False


def _extract_markdown_links(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", text)


def _extract_bare_urls(text: str) -> list[str]:
    masked = re.sub(r"\[[^\]]+\]\(https?://[^)\s]+\)", "", text)
    return sorted(set(re.findall(r"https?://[^\s)]+", masked)))


def _extract_markdown_urls(text: str) -> list[str]:
    markdown_urls = [url for _, url in _extract_markdown_links(text)]
    bare_urls = _extract_bare_urls(text)
    return sorted(set(markdown_urls + bare_urls))


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


# Modules that belong to the clinical safety domain.  Only these get the
# medical blocklist and the authoritative-source whitelist.  Anything else
# (general writing, translation, coding, other skills) is validated as a
# plain general-assistant output so the doctor's non-medical work and other
# skills are never degraded or truncated by medical rules.
_DEFAULT_CLINICAL_SAFETY_MODULES = (
    "guideline_learning",
    "daily_guideline_learning",
    "guideline_section_expansion",
    "guideline_learning_pathway",
    "guideline_learning_diagnosis",
    "guideline_update_reminder",
    "professional_update_summary",
    "insurance_policy_summary",
    "insurance_policy_learning",
    "insurance_policy_retrospective",
    "exam_material_recommendation",
    "high_risk_refusal",
)

_DEFAULT_SOURCE_RESTRICTED_MODULES = tuple(
    name for name in _DEFAULT_CLINICAL_SAFETY_MODULES if name != "high_risk_refusal"
)


def _policy_modules(policy: dict[str, list[str]], key: str, fallback: tuple[str, ...]) -> set[str]:
    configured = [item for item in policy.get(key, []) if item]
    return set(configured) if configured else set(fallback)


def _validate_daily_guideline_learning(text: str, errors: list[str], warnings: list[str]) -> None:
    numbered_points = re.findall(r"(?m)^\s*[1-3][.、]\s+", text)
    if len(numbered_points) != 3:
        errors.append("daily_template_requires_exactly_three_points")
    if "下一单元预告" not in text and "明日预告" not in text:
        errors.append("daily_template_missing:next_lesson_preview")
    if "学习单元" not in text:
        errors.append("daily_template_missing:learning_unit")
    if "依据：" not in text and "指南：" not in text:
        errors.append("daily_template_missing:versioned_guideline")
    if "自测题" in text:
        errors.append("daily_template_must_not_include_quiz")
    length = _visible_length(text)
    if length > 1000:
        errors.append(f"daily_template_too_long:{length}")
    elif length < 400:
        warnings.append(f"daily_template_short:{length}")


def _validate_guideline_learning_diagnosis(text: str, errors: list[str]) -> None:
    """Check that the learning-diagnostic response is recognizably educational."""
    if "【指南学习诊断" in text:
        required = ("学习目标", "学习信号", "优先补齐", "建议起点", "下一步", "边界")
    elif "【指南诊断标准学习" in text:
        required = ("学习框架", "易混淆点", "下一步", "边界")
    elif "【学习需求初评｜待选定指南】" in text:
        required = ("学习目标", "当前学习信号", "建议", "下一步", "边界")
    else:
        errors.append("learning_diagnosis_template_missing_header")
        return
    for label in required:
        if label not in text:
            errors.append(f"learning_diagnosis_template_missing:{label}")


def _validate_guideline_section_expansion(text: str, errors: list[str]) -> None:
    """Section expansion must stay a sourced reading aid, not a rewritten guideline."""
    if "【指南章节展开" not in text:
        errors.append("section_expansion_missing_header")
        return
    for label in ("依据", "章节", "原文要点", "学习提示", "边界"):
        if label not in text:
            errors.append(f"section_expansion_missing:{label}")
    if "原文定位" not in text and "定位" not in text:
        errors.append("section_expansion_missing:原文定位")
    if "不替代原文" not in text:
        errors.append("section_expansion_missing:不替代原文声明")


def _validate_guideline_learning_pathway(text: str, errors: list[str]) -> None:
    """Pathway output is a study order map; it must not read as clinical triage."""
    if "【指南学习路径图" not in text:
        errors.append("learning_pathway_missing_header")
        return
    for label in ("依据", "学习顺序", "前置知识", "边界"):
        if label not in text:
            errors.append(f"learning_pathway_missing:{label}")
    if not re.search(r"(?m)^\s*\d+[.、]\s+", text):
        errors.append("learning_pathway_missing_ordered_steps")
    for banned in ("处置流程", "诊疗流程", "抢救流程", "处理流程"):
        if banned in text:
            errors.append(f"learning_pathway_must_not_be_clinical_flow:{banned}")


def _validate_exam_material_recommendation(text: str, errors: list[str]) -> None:
    """Exam-oriented material lists must be explicit about scope and verification."""
    if "【备考学习材料推荐" not in text:
        errors.append("exam_material_missing_header")
        return
    for label in ("考试目标", "推荐材料", "学习顺序", "待确认", "边界"):
        if label not in text:
            errors.append(f"exam_material_missing:{label}")
    if "以官方考试大纲为准" not in text:
        errors.append("exam_material_missing:官方大纲优先声明")


def _validate_insurance_retrospective(text: str, errors: list[str]) -> None:
    """Long-window insurance review must state its window and stay non-authoritative."""
    if "【医保政策回顾学习" not in text:
        errors.append("insurance_retrospective_missing_header")
        return
    for label in ("回顾区间", "重点政策", "学习提示", "待确认"):
        if label not in text:
            errors.append(f"insurance_retrospective_missing:{label}")


def validate(text: str, module: str, policy_path: Path, allow_no_source: bool) -> dict[str, object]:
    policy = _load_list_yaml(policy_path)
    errors: list[str] = []
    warnings: list[str] = []

    clinical_modules = _policy_modules(
        policy, "clinical_safety_modules", _DEFAULT_CLINICAL_SAFETY_MODULES
    )
    source_restricted = _policy_modules(
        policy, "source_restricted_modules", _DEFAULT_SOURCE_RESTRICTED_MODULES
    )
    in_clinical_domain = module in clinical_modules

    # General-assistant outputs are not subject to the medical blocklist.
    if in_clinical_domain:
        for pattern in policy.get("blocked_output_patterns", []):
            if re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(f"blocked_output_pattern:{pattern}")

    markdown_links = _extract_markdown_links(text)
    bare_urls = _extract_bare_urls(text)
    urls = _extract_markdown_urls(text)
    source_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith(("来源：", "来源:"))
    ]
    source_required = module in source_restricted

    if source_required:
        if not urls and not allow_no_source:
            errors.append("missing_source_url")
        if urls and not markdown_links:
            errors.append("source_url_must_be_markdown_link")
        if urls and not any("[链接](" in line for line in source_lines):
            errors.append("source_line_missing_clickable_链接")
        for label, _url in markdown_links:
            if label != "链接":
                errors.append(f"source_link_label_must_be_链接:{label}")
        for url in bare_urls:
            errors.append(f"bare_source_url_not_allowed:{url}")

        # The authoritative-source whitelist only constrains medical and
        # policy claims.  General tasks may cite any legitimate link.
        for url in urls:
            domain = _domain(url)
            if not domain:
                errors.append(f"invalid_url:{url}")
                continue
            if not _is_allowed_domain(domain, policy):
                errors.append(f"disallowed_source_domain:{domain}")
    else:
        for url in urls:
            if not _domain(url):
                errors.append(f"invalid_url:{url}")

    if "本摘要不作为报销依据" not in text and module in {
        "insurance_policy_summary",
        "insurance_policy_learning",
        "insurance_policy_retrospective",
    }:
        errors.append("missing_insurance_non_reimbursement_notice")

    if "不提供个体诊疗" not in text and module == "high_risk_refusal":
        errors.append("missing_high_risk_refusal_boundary")

    if module == "daily_guideline_learning":
        _validate_daily_guideline_learning(text, errors, warnings)
    if module == "guideline_learning_diagnosis":
        _validate_guideline_learning_diagnosis(text, errors)
    if module == "guideline_section_expansion":
        _validate_guideline_section_expansion(text, errors)
    if module == "guideline_learning_pathway":
        _validate_guideline_learning_pathway(text, errors)
    if module == "exam_material_recommendation":
        _validate_exam_material_recommendation(text, errors)
    if module == "insurance_policy_retrospective":
        _validate_insurance_retrospective(text, errors)

    return {
        "ok": not errors,
        "module": module,
        "clinical_safety_domain": in_clinical_domain,
        "errors": errors,
        "warnings": warnings,
        "source_urls": urls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate phase-1 clinical learning output.")
    parser.add_argument("--module", required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--text-file", type=Path)
    parser.add_argument("--allow-no-source", action="store_true")
    args = parser.parse_args()

    text = args.text_file.read_text(encoding="utf-8") if args.text_file else sys.stdin.read()

    result = validate(text, args.module, args.policy, args.allow_no_source)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
