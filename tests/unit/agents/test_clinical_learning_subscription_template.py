"""Regression tests for the clinical learning + general assistant template."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from harness_agent.subagents.loader import parse_agent_markdown

from octop.infra.agents.experts.catalog import default_library_root

_ROOT = default_library_root() / "clinical-learning-subscription"


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_template_exposes_general_and_guideline_learning_entrypoints() -> None:
    manifest = json.loads((_ROOT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["id"] == "clinical-learning-subscription"
    assert {"SOUL.md", "AGENTS.md", "BOOTSTRAP.md"} <= set(manifest["prompt_files"])
    titles = {item["title"]["zh"] for item in manifest["quick_prompts"]}
    assert {"指南学习诊断", "指南学习地图", "处理其他任务"} <= titles
    assert {"预览下一学习单元", "创建学习轨道", "检查指南新版迁移"} <= titles

    soul = (_ROOT / "SOUL.md").read_text(encoding="utf-8")
    assert "其他普通任务" in soul
    assert "指南中的诊断标准学习" in soul
    assert "具体患者" in soul
    assert "平台拥有的投递服务" in soul
    assert (_ROOT / "references" / "learning-track-template.md").is_file()


def test_learning_diagnostic_summary_is_opt_in_and_can_be_cleared(tmp_path: Path) -> None:
    profile = _load_module(_ROOT / "scripts" / "clinical_profile.py", "clinical_profile_test")

    state = profile.save_learning_diagnosis(
        goal="副高考试复习",
        guideline_title="高血压防治指南",
        source_url="https://www.nhc.gov.cn/example",
        self_assessed_level="developing",
        available_minutes_per_day=20,
        priority_topics=["诊断标准", "分层概念", "诊断标准"],
        recommended_start="先学习适用范围与定义章节",
        confirm=True,
        root=tmp_path,
    )

    diagnostic = state["learning_diagnosis"]
    assert diagnostic["status"] == "saved"
    assert diagnostic["priority_topics"] == ["诊断标准", "分层概念"]
    assert "原始答题过程" in (tmp_path / "USER.md").read_text(encoding="utf-8")

    cleared = profile.clear_learning_diagnosis(confirm=True, root=tmp_path)
    assert cleared["learning_diagnosis"]["status"] == "not_started"
    assert cleared["profile"]["consent_confirmed"] is False


def test_learning_diagnostic_rejects_unconfirmed_or_patient_like_storage(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_rejection_test"
    )

    try:
        profile.save_learning_diagnosis(
            goal="继续学习",
            guideline_title="",
            source_url="",
            self_assessed_level="developing",
            available_minutes_per_day=20,
            priority_topics=["诊断标准"],
            recommended_start="第一章",
            confirm=False,
            root=tmp_path,
        )
    except ValueError as exc:
        assert "显式确认" in str(exc)
    else:
        raise AssertionError("expected explicit-confirmation rejection")

    try:
        profile.save_learning_diagnosis(
            goal="患者病例复习",
            guideline_title="",
            source_url="",
            self_assessed_level="developing",
            available_minutes_per_day=20,
            priority_topics=["诊断标准"],
            recommended_start="第一章",
            confirm=True,
            root=tmp_path,
        )
    except ValueError as exc:
        assert "患者" in str(exc)
    else:
        raise AssertionError("expected patient-like content rejection")


def test_learning_diagnostic_validator_requires_educational_structure_and_source() -> None:
    validator = _load_module(
        _ROOT / "scripts" / "validate_output.py", "clinical_output_validator_test"
    )
    text = """【指南学习诊断｜仅评估学习状态】
学习目标：副高考试复习
学习信号：建议巩固（依据：本次作答）
优先补齐：诊断标准
建议起点：先学习定义章节
下一步：展开该章节
来源：示例页面：[链接](https://www.nhc.gov.cn/example)
边界：本结果只反映本次学习信号，不是患者诊断、临床胜任力认证或诊疗建议。
"""

    result = validator.validate(
        text,
        module="guideline_learning_diagnosis",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is True


def test_daily_learning_validator_requires_fixed_unit_structure() -> None:
    validator = _load_module(
        _ROOT / "scripts" / "validate_output.py", "clinical_daily_validator_test"
    )
    text = """【指南学习单元｜全科】
轨道：高血压学习轨道
依据：高血压防治指南（2024，国家卫生健康委）
学习单元：1 / 2
章节：第一章 1.1
主题：适用范围与核心定义
1. 学习适用范围与核心概念，避免将学习条目代入具体患者。
2. 关注概念之间的关系和质量意识，不把它写成处置命令。
3. 医院制度和本地执行口径需要以正式文件确认。
下一单元预告：
风险分层框架 — 学习识别风险分层的核心概念。
来源：示例页面：[链接](https://www.nhc.gov.cn/example)
说明：本内容用于医生继续学习，不提供个体诊疗、处方剂量或急诊处置建议。
"""
    result = validator.validate(
        text,
        module="daily_guideline_learning",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is True


def test_daily_learning_final_unit_requires_confirmed_next_stage_choices() -> None:
    validator = _load_module(
        _ROOT / "scripts" / "validate_output.py", "clinical_final_daily_validator_test"
    )
    text = """【指南学习单元｜全科】
轨道：儿童合理用药学习轨道
依据：关于进一步加强儿童临床用药管理工作的通知（2023，国家卫生健康委）
学习单元：6 / 6
章节：健康宣教与随访
主题：家长指导与用药随访
1. 学习家长沟通中的核心信息与安全边界。
2. 关注随访制度与用药连续性管理的衔接。
3. 本地执行口径仍需以医疗机构正式制度为准。

下一阶段可选指南（待确认）：
A. 《基层儿童健康管理指南》（2025，国家卫生健康委）：[链接](https://www.nhc.gov.cn/next-a)
   推荐衔接：继续学习儿童健康管理与随访框架。
B. 《儿童用药质量控制规范》（2024，中华医学会）：[链接](https://www.cma.org.cn/next-b)
   推荐衔接：从健康宣教延伸到机构用药质量控制。
回复 A/B，或告诉我其他学习方向。确认前不会创建或启用新轨道。

来源：儿童临床用药管理通知：[链接](https://www.nhc.gov.cn/example)
说明：本内容用于医生继续学习，不提供个体诊疗、处方剂量或急诊处置建议。
"""
    result = validator.validate(
        text,
        module="daily_guideline_learning",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is True


def test_daily_learning_final_unit_rejects_canned_waiting_preview() -> None:
    validator = _load_module(
        _ROOT / "scripts" / "validate_output.py", "clinical_canned_final_validator_test"
    )
    text = """【指南学习单元｜全科】
轨道：儿童合理用药学习轨道
依据：关于进一步加强儿童临床用药管理工作的通知（2023，国家卫生健康委）
学习单元：6 / 6
章节：健康宣教与随访
主题：家长指导与用药随访
1. 学习家长沟通中的核心信息。
2. 关注随访制度与用药连续性。
3. 本地执行口径以正式制度为准。
下一单元预告：
本轨道单元已全部送达，等待用户复盘或确认新轨道。
来源：儿童临床用药管理通知：[链接](https://www.nhc.gov.cn/example)
说明：本内容用于医生继续学习，不提供个体诊疗、处方剂量或急诊处置建议。
"""
    result = validator.validate(
        text,
        module="daily_guideline_learning",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is False
    assert "最后单元不得继续使用下一单元预告" in result["errors"]


def test_source_validator_rejects_review_as_final_evidence() -> None:
    validator = _load_module(_ROOT / "scripts" / "validate_output.py", "review_source_test")
    text = """【指南学习诊断｜仅评估学习状态】
学习目标：继续学习
学习信号：建议巩固
优先补齐：核心概念
建议起点：从规范性文件开始
下一步：确认学习方向
来源：儿童合理用药系统综述：[链接](https://www.medjournals.cn/review)
边界：本结果只反映本次学习信号，不是患者诊断、临床胜任力认证或诊疗建议。
"""
    result = validator.validate(
        text,
        module="guideline_learning_diagnosis",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is False
    assert "最终依据不得使用非规范性文档类型：systematic_review" in result["errors"]


def test_daily_learning_final_unit_can_ask_for_direction_without_review_fallback() -> None:
    validator = _load_module(
        _ROOT / "scripts" / "validate_output.py", "clinical_final_direction_validator_test"
    )
    text = """【指南学习单元｜全科】
轨道：儿童合理用药学习轨道
依据：关于进一步加强儿童临床用药管理工作的通知（2023，国家卫生健康委）
学习单元：6 / 6
章节：健康宣教与随访
主题：家长指导与用药随访
1. 学习家长沟通中的核心信息。
2. 关注随访制度与用药连续性。
3. 本地执行口径以正式制度为准。
下一阶段规划（待你选择）：
未取得足够的可核验正式指南，因此不使用综述或研究论文补位。请告诉我希望继续的学习方向。确认前不会创建或启用新轨道。
来源：儿童临床用药管理通知：[链接](https://www.nhc.gov.cn/example)
说明：本内容用于医生继续学习，不提供个体诊疗、处方剂量或急诊处置建议。
"""
    result = validator.validate(
        text,
        module="daily_guideline_learning",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert result["ok"] is True


def test_source_policy_filters_content_type_and_prefers_current_version() -> None:
    validator = _load_module(_ROOT / "scripts" / "validate_output.py", "source_policy_test")
    policy = validator._load_list_yaml(_ROOT / "references" / "source-policy.yaml")

    assert {
        "systematic_review",
        "meta_analysis",
        "narrative_review",
        "scoping_review",
        "umbrella_review",
        "science_popularization",
        "guideline_or_consensus_interpretation",
        "repost_or_excerpt",
        "interview_or_media_report",
        "public_health_check_education_or_interpretation",
    } <= set(policy["excluded_final_evidence_content_types"])
    assert "formal_journal_full_text" not in policy["allowed_final_evidence_content_types"]

    source_verify = (_ROOT / "skills" / "source-verify" / "SKILL.md").read_text(encoding="utf-8")
    assert "权威网站不等于" in source_verify
    assert "科普、转载/摘编、访谈/媒体报道" in source_verify
    assert "不得出现在最终“来源”、下一阶段指南候选或正式学习轨道来源中" in source_verify
    assert "最新且当前有效的正式版本" in source_verify
    assert "网页更新时间" in source_verify
    assert "整个用户回合累计" in source_verify

    section_skill = (_ROOT / "skills" / "guideline-section-expansion" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "默认只选 1 份" in section_skill
    assert "整个用户回合的总工具预算" in section_skill
    assert "累计预算已耗尽时不得继续搜索补链" in section_skill


def _bplus_section_output(*, include_primary: bool = True, label_pair: bool = True) -> str:
    primary_label = "原始元数据" if label_pair else "正式出处"
    secondary_label = "正文承载" if label_pair else "参考页面"
    primary = (
        f"\n来源：{primary_label}（国家卫生健康委）：[链接](https://www.nhc.gov.cn/example)"
        if include_primary
        else ""
    )
    return f"""【指南章节展开｜高血压随访】
依据：高血压正式指南
章节：随访管理
原文定位：随访管理相关章节
原文要点：定期评估诊室外血压与危险因素。
学习提示：结合原文章节理解随访框架。
边界：本内容用于指南学习，不替代原文，不提供个体诊疗。{primary}
来源：{secondary_label}（原始正文访问受限）：[链接](https://guide.medlive.cn/example)
"""


def test_bplus_source_requires_primary_metadata_and_explicit_labels() -> None:
    validator = _load_module(_ROOT / "scripts" / "validate_output.py", "bplus_source_test")
    policy_path = _ROOT / "references" / "source-policy.yaml"

    valid = validator.validate(
        _bplus_section_output(),
        module="guideline_section_expansion",
        policy_path=policy_path,
        allow_no_source=False,
    )
    assert valid["ok"] is True

    missing_primary = validator.validate(
        _bplus_section_output(include_primary=False),
        module="guideline_section_expansion",
        policy_path=policy_path,
        allow_no_source=False,
    )
    assert "B+正文承载链接必须同时提供S/A原始元数据链接" in missing_primary["errors"]

    missing_labels = validator.validate(
        _bplus_section_output(label_pair=False),
        module="guideline_section_expansion",
        policy_path=policy_path,
        allow_no_source=False,
    )
    assert "B+受控降级必须标明：原始元数据" in missing_labels["errors"]
    assert "B+受控降级必须标明：正文承载" in missing_labels["errors"]


def test_bplus_guideline_interpretation_is_not_final_evidence() -> None:
    validator = _load_module(_ROOT / "scripts" / "validate_output.py", "bplus_interpretation_test")
    text = _bplus_section_output().replace("正文承载（原始正文访问受限）", "正文承载（指南解读）")
    result = validator.validate(
        text,
        module="guideline_section_expansion",
        policy_path=_ROOT / "references" / "source-policy.yaml",
        allow_no_source=False,
    )
    assert (
        "最终依据不得使用非规范性文档类型：guideline_or_consensus_interpretation"
        in result["errors"]
    )


def test_internal_learning_team_members_have_no_tools() -> None:
    for name in ("guideline-learning-designer.md", "medical-learning-safety-reviewer.md"):
        text = (_ROOT / "agents" / name).read_text(encoding="utf-8")
        spec = parse_agent_markdown(text, path_fragment=f"agents/{name}", parent_tools=[])
        assert spec is not None
        assert spec["tools"] == []


def _create_active_track(profile: ModuleType, root: Path) -> tuple[str, list[str]]:
    _state, goal = profile.save_learning_goal(
        label="副高考试复习",
        kind="exam",
        daily_minutes=20,
        target_date="2026-10-31",
        priority=80,
        status="active",
        goal_id="exam-goal",
        confirm=True,
        root=root,
    )
    _state, track = profile.create_learning_track(
        label="高血压防治指南",
        publisher="国家卫生健康委",
        version="2024",
        source_url="https://www.nhc.gov.cn/example",
        source_revision="2024-01",
        goal_ids=[goal["id"]],
        track_id="hypertension-track",
        kind="guideline",
        confirm=True,
        root=root,
    )
    lesson_ids = ["hypertension-track-unit-1", "hypertension-track-unit-2"]
    lessons = [
        {
            "id": lesson_ids[0],
            "ordinal": 1,
            "title": "适用范围与核心定义",
            "source_anchor": {"section": "第一章", "locator": "1.1"},
            "objectives": ["理解适用人群"],
            "topic_tags": ["定义"],
            "estimated_minutes": 10,
        },
        {
            "id": lesson_ids[1],
            "ordinal": 2,
            "title": "风险分层框架",
            "source_anchor": {"section": "第二章", "locator": "2.1"},
            "objectives": ["识别学习中的分层概念"],
            "topic_tags": ["风险分层"],
            "estimated_minutes": 10,
        },
    ]
    profile.replace_track_lessons(
        track_id=track["id"],
        lesson_jsons=[json.dumps(item, ensure_ascii=False) for item in lessons],
        replace_pending=True,
        confirm=True,
        root=root,
    )
    profile.activate_learning_track(track_id=track["id"], confirm=True, root=root)
    return track["id"], lesson_ids


def test_learning_track_preview_is_read_only_and_delivery_lifecycle_is_not_exposed(
    tmp_path: Path,
) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_delivery_test"
    )
    track_id, lesson_ids = _create_active_track(profile, tmp_path)

    preview = profile.get_next_lesson(track_id=track_id, root=tmp_path)
    assert preview["lesson"]["id"] == lesson_ids[0]
    assert profile.load_state(tmp_path)["learning"]["delivery_ledger"] == []

    with pytest.raises(RuntimeError, match="平台受鉴权"):
        profile._claim_delivery_for_platform(
            track_id=track_id,
            lesson_id=lesson_ids[0],
            route_key="weixin:daily_guideline_learning",
            slot_key="weixin:daily_guideline_learning:2026-07-31",
            idempotency_key="cron:guideline:2026-07-31T07:30:00+08:00",
            lease_seconds=900,
            root=tmp_path,
        )
    assert profile.load_state(tmp_path)["learning"]["delivery_ledger"] == []

    parser = profile.build_parser()
    command_names = parser._subparsers._group_actions[0].choices
    # The platform-owned delivery lifecycle (claim/confirm with tokens) must stay
    # unexposed; only the weak cron dedup ledger commands are allowed.
    assert not any("claim" in name or "confirm-delivery" in name for name in command_names)
    assert "delivery-check" in command_names
    assert "delivery-record" in command_names


def test_weak_delivery_ledger_dedups_and_advances(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_weak_delivery_test"
    )
    track_id, lesson_ids = _create_active_track(profile, tmp_path)

    first_check = profile.check_daily_delivery(
        track_id=track_id, logical_date="2026-08-03", root=tmp_path
    )
    assert first_check["already_sent"] is False

    recorded = profile.record_daily_delivery(
        track_id=track_id, lesson_id="", logical_date="2026-08-03", confirm=True, root=tmp_path
    )
    state, details = recorded
    assert details["recorded"] is True
    assert details["lesson_id"] == lesson_ids[0]

    second_check = profile.check_daily_delivery(
        track_id=track_id, logical_date="2026-08-03", root=tmp_path
    )
    assert second_check["already_sent"] is True

    _state2, dup = profile.record_daily_delivery(
        track_id=track_id, lesson_id="", logical_date="2026-08-03", confirm=True, root=tmp_path
    )
    assert dup["recorded"] is False
    assert dup["already_sent"] is True

    next_preview = profile.get_next_lesson(track_id=track_id, root=tmp_path)
    assert next_preview["lesson"]["id"] == lesson_ids[1]


def test_public_state_hides_delivery_ledger_and_route_metadata(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_ledger_privacy_test"
    )
    track_id, lesson_ids = _create_active_track(profile, tmp_path)
    state = profile.load_state(tmp_path)
    state["learning"]["delivery_ledger"] = [
        {
            "id": "delivery-private",
            "track_id": track_id,
            "lesson_id": lesson_ids[0],
            "route_key_hash": "sha256:route",
            "slot_key_hash": "sha256:slot",
            "idempotency_key_hash": "sha256:key",
        }
    ]
    public = profile._public_state(state)
    assert "delivery_ledger" not in public["learning"]
    assert "route_key_hash" not in json.dumps(public, ensure_ascii=False)


def test_v1_day_progress_migrates_without_fabricating_delivery_receipt(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_migration_test"
    )
    legacy = {
        "current_guideline": {
            "title": "高血压防治指南",
            "publisher": "国家卫生健康委",
            "source_url": "https://www.nhc.gov.cn/example",
            "total_days": 3,
            "current_day": 1,
            "status": "in_progress",
        }
    }
    (tmp_path / "clinical_learning_state.json").write_text(
        json.dumps(legacy, ensure_ascii=False),
        encoding="utf-8",
    )

    projected = profile.load_state(tmp_path)
    track = projected["learning"]["tracks"][0]
    assert track["plan_status"] == "needs_replan"
    assert track["lessons"][0]["delivery_status"] == "legacy_completed"
    assert track["lessons"][1]["delivery_status"] == "planned"
    assert projected["learning"]["delivery_ledger"] == []

    persisted, details = profile.state_migrate(confirm=True, dry_run=False, root=tmp_path)
    assert details["changes"] == ["legacy_current_guideline_imported"]
    assert persisted["revision"] == 1
    reloaded = json.loads((tmp_path / "clinical_learning_state.json").read_text(encoding="utf-8"))
    assert reloaded["learning"]["delivery_ledger"] == []
    assert reloaded["learning"]["tracks"][0]["lessons"][0]["delivery_status"] == "legacy_completed"


def test_version_migration_requires_confirmation_and_keeps_old_track(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_version_migration_test"
    )
    track_id, _lesson_ids = _create_active_track(profile, tmp_path)
    preview = profile.preview_track_migration(
        track_id=track_id,
        publisher="国家卫生健康委",
        version="2026",
        source_url="https://www.nhc.gov.cn/new-example",
        source_revision="2026-01",
        root=tmp_path,
    )
    assert preview["preview_only"] is True
    assert preview["impact"]["requires_new_lessons"] is True

    with pytest.raises(ValueError, match="显式确认"):
        profile.migrate_track(
            track_id=track_id,
            publisher="国家卫生健康委",
            version="2026",
            source_url="https://www.nhc.gov.cn/new-example",
            source_revision="2026-01",
            new_track_id="hypertension-track-2026",
            confirm=False,
            root=tmp_path,
        )

    state, details = profile.migrate_track(
        track_id=track_id,
        publisher="国家卫生健康委",
        version="2026",
        source_url="https://www.nhc.gov.cn/new-example",
        source_revision="2026-01",
        new_track_id="hypertension-track-2026",
        confirm=True,
        root=tmp_path,
    )
    assert details["new_track"]["id"] == "hypertension-track-2026"
    assert state["learning"]["tracks"][0]["status"] == "superseded"
    assert state["learning"]["tracks"][1]["status"] == "draft"
    assert state["learning"]["tracks"][1]["lessons"] == []


def test_user_summary_and_cli_state_hide_weixin_session_identifier(tmp_path: Path) -> None:
    profile = _load_module(
        _ROOT / "scripts" / "clinical_profile.py", "clinical_profile_privacy_test"
    )
    state = profile._deep_default_state()
    state["subscriptions"]["weixin_session_key"] = "user:weixin:private-session-value"
    profile.save_state(state, root=tmp_path)

    summary = (tmp_path / "USER.md").read_text(encoding="utf-8")
    assert "private-session-value" not in summary
    assert "session_key" not in summary
    assert profile._public_state(state)["subscriptions"]["weixin_session_key"] == "[已隐藏]"
