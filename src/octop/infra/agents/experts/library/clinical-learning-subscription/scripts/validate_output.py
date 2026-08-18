#!/usr/bin/env python3
"""校验临床学习输出，在投递前检查格式、来源与边界声明。"""

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


_EXCLUDED_CONTENT_TYPE_PATTERNS: dict[str, str] = {
    "systematic_review": r"系统综述|系统评价|systematic\s+review",
    "meta_analysis": r"Meta\s*分析|荟萃分析|meta[-\s]?analysis",
    "systematic_review_and_meta_analysis": (
        r"系统综述与Meta\s*分析|系统评价与Meta\s*分析|systematic\s+review\s+and\s+meta"
    ),
    "narrative_review": r"叙述性综述|narrative\s+review",
    "scoping_review": r"范围综述|scoping\s+review",
    "umbrella_review": r"伞状综述|umbrella\s+review",
    "rapid_review": r"快速综述|rapid\s+review",
    "expert_review": r"专家综述|专家述评|expert\s+review",
    "literature_review": r"文献综述|literature\s+review",
    "randomized_controlled_trial": r"随机对照试验|randomi[sz]ed\s+controlled\s+trial|\bRCT\b",
    "observational_study": r"观察性研究|observational\s+stud(?:y|ies)",
    "case_report_or_case_series": r"病例报告|病例系列|case\s+(?:report|series)",
    "editorial_commentary_or_letter": r"述评|社论|读者来信|editorial|commentary|letter\s+to",
    "conference_abstract": r"会议摘要|conference\s+abstract",
    "preprint": r"预印本|preprint",
    "retracted_or_expression_of_concern": r"撤稿|关注声明|retract(?:ed|ion)|expression\s+of\s+concern",
    "science_popularization": r"科普",
    "repost_or_excerpt": r"转载|摘编",
    "interview_or_media_report": r"访谈|媒体报道",
    "public_health_check_education_or_interpretation": r"体检知识|体检解读",
    "conference_training_or_event_report": r"会议报道|培训报道|活动报道",
    "marketing_or_institutional_promotion": r"营销|机构宣传",
}


def _extract_learning_position(text: str) -> tuple[int, int] | None:
    match = re.search(r"学习单元\s*[:：]\s*(\d+)\s*[/／]\s*(\d+)", text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _extract_section(text: str, heading: str) -> str:
    match = re.search(
        rf"{re.escape(heading)}\s*[:：]?\s*(.*?)(?=\n\s*(?:来源|说明)\s*[:：]|\Z)",
        text,
        flags=re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def _final_evidence_lines(text: str) -> list[str]:
    evidence_prefix = re.compile(
        r"^\s*(?:(?:依据|指南|来源|更新文件|政策文件|权威来源)\s*[:：]|[A-C][.、]\s*)"
    )
    return [line.strip() for line in text.splitlines() if evidence_prefix.search(line)]


def _validate_final_evidence_content_types(
    text: str, policy: dict[str, list[str]], errors: list[str]
) -> None:
    evidence_lines = _final_evidence_lines(text)
    for line in evidence_lines:
        for content_type in policy.get("excluded_final_evidence_content_types", []):
            pattern = _EXCLUDED_CONTENT_TYPE_PATTERNS.get(content_type)
            if pattern is None:
                continue
            if re.search(pattern, line, flags=re.IGNORECASE):
                errors.append(f"最终依据不得使用非规范性文档类型：{content_type}")
                break


# 临床安全域模块清单。只有这些模块会套用医学禁用词和权威来源白名单。
# 其他模块（通用写作/翻译/编程/其他 skill）按通用助手输出校验，
# 医生的非医学工作和其他 skill 的输出不会被医学规则降级或截断。
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
        errors.append("每日指南模板需要恰好3个编号要点")
    if "学习单元" not in text:
        errors.append("每日指南模板缺少：学习单元")
    if "依据：" not in text and "指南：" not in text:
        errors.append("每日指南模板缺少：版本化指南（依据/指南）")
    if "自测题" in text:
        errors.append("每日指南模板不得包含自测题")

    position = _extract_learning_position(text)
    if position is None:
        errors.append("每日指南模板缺少可解析的学习单元序号（N / 总数）")
    else:
        ordinal, total = position
        if ordinal < 1 or total < 1 or ordinal > total:
            errors.append("每日指南模板的学习单元序号无效")
        elif ordinal < total:
            preview = _extract_section(text, "下一单元预告") or _extract_section(text, "明日预告")
            if not preview:
                errors.append("非最后单元缺少实质性的下一单元预告")
            elif "—" not in preview and "学习目标" not in preview:
                errors.append("非最后单元预告需要同时写明下一单元主题与学习目标")
            if re.search(r"等待.*(?:复盘|确认新轨道)|本轨道单元已全部送达", preview):
                errors.append("非最后单元不得用等待状态代替下一单元主题与学习目标")
        else:
            if "下一单元预告" in text or "明日预告" in text:
                errors.append("最后单元不得继续使用下一单元预告")
            candidate_section = _extract_section(text, "下一阶段可选指南（待确认）")
            planning_section = _extract_section(text, "下一阶段规划（待你选择）")
            if candidate_section:
                candidates = re.findall(r"(?m)^\s*([A-C])[.、]\s*(.+)$", candidate_section)
                if not 2 <= len(candidates) <= 3:
                    errors.append("最后单元需要提供2-3个下一阶段正式指南候选")
                for _label, candidate in candidates:
                    if not re.search(r"指南|共识|规范|临床路径|质控|标准|办法|通知", candidate):
                        errors.append("下一阶段候选必须是正式指南/共识/规范性文件")
                    if not re.search(r"（[^）]*(?:19|20)\d{2}[^）]*[，,][^）]+）", candidate):
                        errors.append("下一阶段候选缺少年份/版本或发布机构")
                    if not re.search(r"\[链接\]\(https?://[^)\s]+\)", candidate):
                        errors.append("下一阶段候选缺少权威原文链接")
                if candidate_section.count("推荐衔接：") < len(candidates):
                    errors.append("每个下一阶段候选都需要说明推荐衔接")
                if "确认前不会创建或启用新轨道" not in candidate_section:
                    errors.append("最后单元缺少确认前不创建或启用新轨道的声明")
            elif planning_section:
                if "未取得足够的可核验正式指南" not in planning_section:
                    errors.append("无足够候选时必须如实说明未取得足够的可核验正式指南")
                if "学习方向" not in planning_section:
                    errors.append("无足够候选时必须询问用户下一阶段学习方向")
                if "确认前不会创建或启用新轨道" not in planning_section:
                    errors.append("最后单元缺少确认前不创建或启用新轨道的声明")
            else:
                errors.append("最后单元缺少待确认的下一阶段指南候选或学习方向询问")

    length = _visible_length(text)
    if length > 1000:
        errors.append(f"每日指南模板过长：{length}字")
    elif length < 400:
        warnings.append(f"每日指南模板偏短：{length}字")


def _validate_guideline_learning_diagnosis(text: str, errors: list[str]) -> None:
    """检查学习诊断回复是否为教育性内容。"""
    if "【指南学习诊断" in text:
        required = ("学习目标", "学习信号", "优先补齐", "建议起点", "下一步", "边界")
    elif "【指南诊断标准学习" in text:
        required = ("学习框架", "易混淆点", "下一步", "边界")
    elif "【学习需求初评｜待选定指南】" in text:
        required = ("学习目标", "当前学习信号", "建议", "下一步", "边界")
    else:
        errors.append("学习诊断模板缺少标题")
        return
    for label in required:
        if label not in text:
            errors.append(f"学习诊断模板缺少：{label}")


def _validate_guideline_section_expansion(text: str, errors: list[str]) -> None:
    """章节展开必须是带来源的阅读辅助，不能是改写后的指南。"""
    if "【指南章节展开" not in text:
        errors.append("章节展开模板缺少标题")
        return
    for label in ("依据", "章节", "原文要点", "学习提示", "边界"):
        if label not in text:
            errors.append(f"章节展开模板缺少：{label}")
    if "原文定位" not in text and "定位" not in text:
        errors.append("章节展开模板缺少：原文定位")
    if "不替代原文" not in text:
        errors.append("章节展开模板缺少：不替代原文声明")


def _validate_guideline_learning_pathway(text: str, errors: list[str]) -> None:
    """路径图是学习顺序图，不能读起来像临床分诊。"""
    if "【指南学习路径图" not in text:
        errors.append("学习路径图模板缺少标题")
        return
    for label in ("依据", "学习顺序", "前置知识", "边界"):
        if label not in text:
            errors.append(f"学习路径图模板缺少：{label}")
    if not re.search(r"(?m)^\s*\d+[.、]\s+", text):
        errors.append("学习路径图缺少编号步骤")
    for banned in ("处置流程", "诊疗流程", "抢救流程", "处理流程"):
        if banned in text:
            errors.append(f"学习路径图不得写成临床流程：{banned}")


def _validate_exam_material_recommendation(text: str, errors: list[str]) -> None:
    """备考材料清单必须明确范围与核验要求。"""
    if "【备考学习材料推荐" not in text:
        errors.append("备考材料模板缺少标题")
        return
    for label in ("考试目标", "推荐材料", "学习顺序", "待确认", "边界"):
        if label not in text:
            errors.append(f"备考材料模板缺少：{label}")
    if "以官方考试大纲为准" not in text:
        errors.append("备考材料模板缺少：以官方考试大纲为准声明")


def _validate_insurance_retrospective(text: str, errors: list[str]) -> None:
    """长周期医保回顾必须标注区间且不作为权威依据。"""
    if "【医保政策回顾学习" not in text:
        errors.append("医保回顾模板缺少标题")
        return
    for label in ("回顾区间", "重点政策", "学习提示", "待确认"):
        if label not in text:
            errors.append(f"医保回顾模板缺少：{label}")


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

    # 通用助手输出不受医学禁用词约束。
    if in_clinical_domain:
        for pattern in policy.get("blocked_output_patterns", []):
            if re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(f"命中禁止输出模式：{pattern}")

    markdown_links = _extract_markdown_links(text)
    bare_urls = _extract_bare_urls(text)
    urls = _extract_markdown_urls(text)
    source_lines = [
        line.strip() for line in text.splitlines() if line.strip().startswith(("来源：", "来源:"))
    ]
    source_required = module in source_restricted

    if source_required:
        if not urls and not allow_no_source:
            errors.append("缺少来源URL")
        if urls and not markdown_links:
            errors.append("来源URL必须是Markdown链接格式")
        if urls and not any("[链接](" in line for line in source_lines):
            errors.append("来源行缺少可点击的[链接](URL)")
        for label, _url in markdown_links:
            if label != "链接":
                errors.append(f"来源链接文字必须是'链接'：{label}")
        for url in bare_urls:
            errors.append(f"不允许裸URL：{url}")

        # 权威来源白名单只约束医学和政策声明；通用任务可引用任何合法链接。
        for url in urls:
            domain = _domain(url)
            if not domain:
                errors.append(f"无效URL：{url}")
                continue
            if not _is_allowed_domain(domain, policy):
                errors.append(f"来源域名不在白名单：{domain}")
        _validate_final_evidence_content_types(text, policy, errors)
    else:
        for url in urls:
            if not _domain(url):
                errors.append(f"无效URL：{url}")

    if "本摘要不作为报销依据" not in text and module in {
        "insurance_policy_summary",
        "insurance_policy_learning",
        "insurance_policy_retrospective",
    }:
        errors.append("医保内容缺少'本摘要不作为报销依据'声明")

    if "不提供个体诊疗" not in text and module == "high_risk_refusal":
        errors.append("高风险拒绝内容缺少'不提供个体诊疗'边界声明")

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
    parser = argparse.ArgumentParser(
        description="校验临床学习输出（投递前检查格式、来源与边界声明）。"
    )
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
