"""tests/unit/i18n/test_errors.py"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from octop.i18n import error_message
from octop.infra.errors import ErrorCode, OctopError
from octop.infra.utils.locale import resolve_request_locale


def test_every_error_code_has_i18n_entry():
    for code in ErrorCode:
        assert error_message(code.value, "en")
        assert error_message(code.value, "zh")


def test_error_message_zh():
    assert "名称" in error_message("AGENT_NAME_TAKEN", "zh")


def test_octop_error_localized_factory():
    err = OctopError.localized(ErrorCode.FORBIDDEN, "zh")
    assert err.code is ErrorCode.FORBIDDEN
    assert err.message == "没有权限。"


def test_octop_error_to_envelope_with_locale():
    err = OctopError(ErrorCode.AGENT_NAME_TAKEN, "agent name 'x' already in use")
    envelope = err.to_envelope(locale="zh")
    assert envelope["error"]["code"] == "AGENT_NAME_TAKEN"
    assert envelope["error"]["message"] == "该名称已被使用，请换一个名称。"


def test_resolve_request_locale_from_accept_language():
    class _Headers:
        def get(self, key: str) -> str | None:
            if key.lower() == "accept-language":
                return "zh-CN,en;q=0.9"
            return None

    class _Req:
        headers = _Headers()

    assert resolve_request_locale(_Req()) == "zh"


def test_dashboard_api_errors_match_backend():
    repo = Path(__file__).resolve().parents[3]
    dash_en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    backend_en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    dash_codes = set(dash_en["apiErrors"].keys())
    backend_codes = set(backend_en["errors"].keys())
    assert dash_codes == backend_codes == {c.value for c in ErrorCode}


# i18next uses ``{{name}}``; a lone ``{name}`` is left uninterpolated in the UI.
_DASHBOARD_SINGLE_BRACE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


def test_dashboard_api_errors_use_i18next_placeholders():
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        data = json.loads(
            (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        )
        for code, msg in data["apiErrors"].items():
            found = _DASHBOARD_SINGLE_BRACE.findall(msg)
            assert not found, (
                f"{locale} apiErrors.{code} uses Python-style {{{', '.join(found)}}} — "
                "dashboard i18next needs {{name}} double braces"
            )


def test_login_locked_interpolates_minutes():
    assert "15" in error_message("LOGIN_LOCKED", "zh", minutes=15)
    assert "minutes" not in error_message("LOGIN_LOCKED", "zh", minutes=15).lower()
    assert "{minutes}" not in error_message("LOGIN_LOCKED", "en", minutes=15)


def test_knowledge_doc_too_large_interpolates_max_mb():
    assert "100" in error_message("KNOWLEDGE_DOC_TOO_LARGE", "zh", max_mb=100)
    assert "{max_mb}" not in error_message("KNOWLEDGE_DOC_TOO_LARGE", "en", max_mb=100)


def test_localized_message_falls_back_when_key_missing(monkeypatch: pytest.MonkeyPatch):
    err = OctopError(ErrorCode.AUTH_FAILED, "custom detail")
    monkeypatch.setattr(
        "octop.infra.errors.i18n_error_message",
        lambda *_a, **_k: (_ for _ in ()).throw(KeyError("errors.X")),
    )
    assert err.localized_message("zh") == "custom detail"


def test_config_file_corrupt_interpolates_path_and_detail():
    kwargs = {"path": "~/.octop/config.json", "detail": "line 3, column 1"}
    assert "~/.octop/config.json" in error_message("CONFIG_FILE_CORRUPT", "en", **kwargs)
    assert "line 3, column 1" in error_message("CONFIG_FILE_CORRUPT", "zh", **kwargs)
    for locale in ("en", "zh"):
        msg = error_message("CONFIG_FILE_CORRUPT", locale, **kwargs)
        assert "{path}" not in msg and "{detail}" not in msg


# ── PROJECT_TASK_THREAD_NOT_FOUND: zh is asserted explicitly ─────────────────
#
# ``loader.lookup`` falls back to English when a zh key is missing, so an en-only
# check would stay green while zh users read English. The zh value below is frozen
# by PLAN.md §7 / SPEC.md §边界与禁止项.


def test_project_task_thread_not_found_zh_is_frozen():
    assert error_message("PROJECT_TASK_THREAD_NOT_FOUND", "zh") == "关联会话不存在，无法创建任务"


def test_dashboard_api_error_zh_carries_the_same_frozen_text():
    repo = Path(__file__).resolve().parents[3]
    dash_zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert dash_zh["apiErrors"]["PROJECT_TASK_THREAD_NOT_FOUND"] == error_message(
        "PROJECT_TASK_THREAD_NOT_FOUND", "zh"
    )


def test_api_errors_namespaces_agree_in_both_locales():
    """The ``errors`` / ``apiErrors`` namespaces only — never the whole tree.

    Dashboard en/zh key trees differ outside these namespaces by design, so a
    whole-file equality assertion would be a false failure.
    """
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        dash = json.loads(
            (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        )
        backend = json.loads((repo / f"src/octop/i18n/{locale}.json").read_text(encoding="utf-8"))
        assert set(dash["apiErrors"]) == set(backend["errors"]) == {c.value for c in ErrorCode}


def test_backend_locales_have_identical_key_trees():
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "src/octop/i18n/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "src/octop/i18n/zh.json").read_text(encoding="utf-8"))

    def tree(value: object) -> object:
        return {k: tree(v) for k, v in value.items()} if isinstance(value, dict) else True

    assert tree(en) == tree(zh)


def test_dashboard_chat_labels_are_paired_and_localized():
    """The four S0/T2.6 labels — namespace-level parity, frozen zh wording."""
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert set(en["chat"]) == set(zh["chat"])
    assert len(zh["chat"]) == 211
    assert zh["chat"]["sectionPinned"] == "置顶"
    assert zh["chat"]["sectionActive"] == "会话"
    assert zh["chat"]["sectionUnused"] == "未使用"
    assert zh["chat"]["projectSessionBadge"] == "项目会话"
    assert en["chat"]["sectionPinned"] == "Pinned"
    assert en["chat"]["sectionActive"] == "Chats"
    assert en["chat"]["sectionUnused"] == "Unused"
    assert en["chat"]["projectSessionBadge"] == "Project chat"


# ── the seven metadata/dispatch rejection codes (PLAN.md §2.2 / §13.2) ───────
#
# zh values are frozen verbatim by PLAN.md §2.2. They are asserted on both sides
# (backend bundle + dashboard ``apiErrors``) because ``loader.py`` silently falls
# back to English for a missing zh key — an en-only gate would stay green while a
# zh user reads English.

_NEW_ERROR_ZH = {
    "PROJECT_TASK_TAG_INVALID": "标签不存在或不属于当前项目。",
    "PROJECT_TASK_DATE_INVALID": "任务日期不合法。",
    "PROJECT_TASK_DISPATCH_INVALID": "该任务的负责人不是可运行的智能体或团队。",
    "PROJECT_CUSTOM_FIELD_NOT_FOUND": "自定义字段不存在。",
    "PROJECT_CUSTOM_FIELD_INVALID": "自定义字段定义不合法。",
    "PROJECT_CUSTOM_FIELD_VALUE_INVALID": "自定义字段取值不符合字段定义。",
    "PROJECT_ATTACHMENT_INVALID": "附件不符合上传要求（类型或大小）。",
    # batch 2 (PLAN.md §11.2 / §12)
    "PROJECT_CONNECTOR_INVALID": "连接器类型不存在或不可用。",
    "PROJECT_SKILL_INVALID": "只能选择该专家已安装的技能。",
    "PROJECT_CRON_INVALID": "定时任务的执行专家或归属不合法。",
    "PROJECT_INSTRUCTION_INVALID": "指令内容不合法（超长或含非法字符）。",
}


def test_new_rejection_codes_have_the_frozen_zh_text():
    for code, expected in _NEW_ERROR_ZH.items():
        assert error_message(code, "zh") == expected, code


def test_new_rejection_codes_status_mapping():
    """One code has one default status; 413 is passed explicitly by the caller."""
    expected = {
        ErrorCode.PROJECT_TASK_TAG_INVALID: 409,
        ErrorCode.PROJECT_TASK_DATE_INVALID: 400,
        ErrorCode.PROJECT_TASK_DISPATCH_INVALID: 409,
        ErrorCode.PROJECT_CUSTOM_FIELD_NOT_FOUND: 404,
        ErrorCode.PROJECT_CUSTOM_FIELD_INVALID: 409,
        ErrorCode.PROJECT_CUSTOM_FIELD_VALUE_INVALID: 400,
        ErrorCode.PROJECT_ATTACHMENT_INVALID: 400,
    }
    for code, status in expected.items():
        assert OctopError(code, "detail").status == status, code
    assert OctopError(ErrorCode.PROJECT_ATTACHMENT_INVALID, "too large", status=413).status == 413
    # batch 2: one code has one default status; the duplicate-connector branch
    # passes ``status=409`` explicitly (PLAN.md §12).
    batch2 = {
        ErrorCode.PROJECT_CONNECTOR_INVALID: 400,
        ErrorCode.PROJECT_SKILL_INVALID: 409,
        ErrorCode.PROJECT_CRON_INVALID: 409,
        ErrorCode.PROJECT_INSTRUCTION_INVALID: 400,
    }
    for code, status in batch2.items():
        assert OctopError(code, "detail").status == status, code
    assert OctopError(ErrorCode.PROJECT_CONNECTOR_INVALID, "duplicate", status=409).status == 409


def test_dashboard_api_errors_carry_the_new_zh_text():
    repo = Path(__file__).resolve().parents[3]
    dash_zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    for code, expected in _NEW_ERROR_ZH.items():
        assert dash_zh["apiErrors"][code] == expected, code


def test_dashboard_projects_namespace_is_paired_and_localized():
    """The new ``projects.*`` keys — namespace-level parity, frozen zh wording.

    Only the named keys are asserted: dashboard en/zh whole-tree equality does not
    hold (and never did), so a tree-level assertion would be a false failure.
    """
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert set(en["projects"]) == set(zh["projects"])
    # 208 batch 2 + 4 batch 3 + 22 batch 4 + 4 D1/D2 + 1 batch 6 (PLAN §4.1) = 239.
    assert len(zh["projects"]) == 239
    # R6 copy change: values only, keys untouched.
    assert zh["projects"]["taskStatusReview"] == "审核中"
    assert zh["projects"]["taskStatusBlocked"] == "已阻塞"
    assert en["projects"]["taskStatusReview"] == "In review"
    assert en["projects"]["taskStatusBlocked"] == "Blocked"
    # New status labels.
    assert zh["projects"]["taskStatusPlanning"] == "待规划"
    assert zh["projects"]["statusCompleted"] == "已完成"
    assert zh["projects"]["statusCancelled"] == "已取消"
    assert en["projects"]["taskStatusPlanning"] == "Planned"
    assert en["projects"]["statusCompleted"] == "Completed"
    assert en["projects"]["statusCancelled"] == "Cancelled"
    # FIND-12: the board's explicit "dispatch" action label.
    assert zh["projects"]["boardDispatch"] == "派单"
    assert en["projects"]["boardDispatch"] == "Dispatch"


def test_dashboard_projects_new_keys_are_present_in_both_locales():
    """Every key PLAN.md §13.1 froze exists in both bundles (no invented names)."""
    repo = Path(__file__).resolve().parents[3]
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    frozen = (
        "taskStatusPlanning",
        "statusCompleted",
        "statusCancelled",
        # U2 create-task dialog
        "createTaskTitle",
        "createTaskDescription",
        "createTaskSubmit",
        "createTaskBreadcrumb",
        "createAndContinue",
        "switchToAgent",
        "attachFile",
        "attachmentsEmpty",
        "attachmentDeleteConfirm",
        "chipStatus",
        "chipPriority",
        "chipAssignee",
        "chipTags",
        "chipProject",
        "chipDueAt",
        "chipStartAt",
        "chipParentTask",
        "chipSubtasks",
        "chipCustomFields",
        "chipMore",
        "pickAssignee",
        "pickParentTask",
        "pickTag",
        "noMembers",
        "noTags",
        "noTasks",
        # U4 tags
        "tagsTitle",
        "tagName",
        "tagColor",
        "tagCreate",
        "tagDeleteConfirm",
        "tagsEmpty",
        "tagInvalid",
        # U6 custom fields
        "customFieldsTitle",
        "cfKey",
        "cfLabel",
        "cfType",
        "cfTypeText",
        "cfTypeNumber",
        "cfTypeDate",
        "cfTypeSelect",
        "cfRequired",
        "cfOptions",
        "cfAdd",
        "cfDeleteConfirm",
        "cfEmpty",
        "cfInvalid",
        # U7 attachments
        "attachmentsTitle",
        "attachmentUpload",
        "attachmentUploaded",
        "attachmentDownload",
        "attachmentTooLarge",
        "attachmentBadType",
    )
    assert len(frozen) == 56
    for key in frozen:
        assert zh["projects"].get(key), f"zh projects.{key} missing"
        assert en["projects"].get(key), f"en projects.{key} missing"


# ── the 56 batch-2 ``projects.*`` keys (PLAN.md §11.1 / S10) ─────────────────
#
# S10 is a *per-key value* assertion, not a key-set assertion. ``loader.py``
# falls back to English when a zh key is missing, so comparing key sets (or only
# counting them) stays green while a zh user reads English. Each of the 56 keys
# is therefore pinned to its verbatim zh string from PLAN.md §11.1.
_BATCH2_PROJECTS_ZH: dict[str, str] = {
    "tabDynamic": "动态",
    "tabPlan": "计划",
    "tabTasks": "任务",
    "tabAssets": "资产",
    "dynamicPlaceholder": "动态流即将上线",
    "dynamicComingSoon": "排入下一批",
    "configTitle": "项目配置",
    "instructionTitle": "指令",
    "instructionPlaceholder": "描述该项目的规范与约定",
    "instructionSaved": "指令已保存",
    "instructionTooLong": "指令不得超过 2000 字符",
    "instructionEmpty": "未填写",
    "connectorTitle": "连接器",
    "connectorAdd": "添加连接器",
    "connectorNone": "尚未声明连接器",
    "connectorAvailable": "可用",
    "connectorUnavailable": "对你不可用",
    "connectorUsing": "将使用 {{name}}",
    "expertTitle": "专家",
    "expertAdd": "添加专家",
    "expertNone": "暂无专家",
    "skillTitle": "技能",
    "skillAdd": "添加技能",
    "skillNone": "尚未声明技能",
    "skillStale": "已失效（该专家已不再安装）",
    "skillUnavailable": "只能选择该专家已安装的技能",
    "cronTitle": "定时任务",
    "cronCreate": "新建定时任务",
    "cronNone": "暂无定时任务",
    "cronEnable": "启用",
    "cronDisable": "停用",
    "cronDeleteConfirm": "删除该定时任务？",
    "cronPromptHidden": "正文已隐藏（其他成员创建）",
    "cronOwnedByOther": "由其他成员创建",
    "memberTitle": "成员",
    "memberRoleOwner": "所有者",
    "memberRoleAdmin": "管理员",
    "memberRoleMember": "成员",
    "memberRoleViewer": "只读",
    "assetTitle": "知识库",
    "assetEmpty": "尚未绑定知识库",
    "assetBind": "去绑定知识库",
    "assetOpen": "打开知识库",
    "assetDocCount": "{{count}} 篇文档",
    "taskListTitle": "任务列表",
    "taskListFilterStatus": "状态",
    "taskListFilterKeyword": "搜索任务",
    "taskListEmpty": "没有符合条件的任务",
    "taskListColumnStatus": "状态",
    "taskListColumnTitle": "标题",
    "taskListColumnAssignee": "负责人",
    "taskListColumnPriority": "优先级",
    "taskListColumnStartAt": "开始",
    "taskListColumnDueAt": "截止",
    "taskListColumnTags": "标签",
    "taskListColumnUpdatedAt": "更新时间",
}


def test_batch2_projects_keys_have_the_frozen_zh_text():
    """S10: every one of the 56 new keys carries its frozen zh wording."""
    repo = Path(__file__).resolve().parents[3]
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    assert len(_BATCH2_PROJECTS_ZH) == 56, "the frozen key table is 56 keys (PLAN.md §11.1)"
    for key, expected in _BATCH2_PROJECTS_ZH.items():
        assert zh["projects"][key] == expected, f"projects.{key}"


def test_batch2_projects_keys_exist_in_both_locales():
    """Key-set parity for the same 56 keys — the value check above is zh-only."""
    repo = Path(__file__).resolve().parents[3]
    zh = json.loads((repo / "dashboard/src/locales/zh.json").read_text(encoding="utf-8"))
    en = json.loads((repo / "dashboard/src/locales/en.json").read_text(encoding="utf-8"))
    for key in _BATCH2_PROJECTS_ZH:
        assert key in zh["projects"], f"zh projects.{key} missing"
        assert key in en["projects"], f"en projects.{key} missing"
        assert en["projects"][key] != "", f"en projects.{key} is empty"
    assert len(zh["projects"]) == 239
    assert len(en["projects"]) == 239


# ── batch 3 (T-I18N3): edit-dialog labels + two rejection codes ──────────────
#
# Per-key zh assertions (S10): a key-set comparison alone would stay green while a
# zh value silently fell back to English (``loader.py`` behaviour), and the L10
# transcription rule means the PLAN table's ``**`` markers are never part of a key
# or a value.

_T_I18N3_PROJECT_KEYS = {
    "editTaskTitle": ("Edit task", "编辑任务"),
    "editTaskSubmit": ("Save", "保存"),
    "editTaskSaved": ("Task updated", "任务已更新"),
    "kbUnbind": ("Unbind knowledge base", "解绑知识库"),
}

_T_I18N3_ERROR_ZH = {
    "PROJECT_KB_FORBIDDEN": "您没有该知识库的写入权限。",
    "PROJECT_TASK_PARENT_INVALID": "父任务不能是自身的后代（间接环）。",
}


def _dash(locale: str) -> dict:
    repo = Path(__file__).resolve().parents[3]
    return json.loads((repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8"))


def test_batch3_project_keys_are_localized_per_key():
    en, zh = _dash("en"), _dash("zh")
    for key, (en_value, zh_value) in _T_I18N3_PROJECT_KEYS.items():
        assert zh["projects"][key] == zh_value, key
        assert en["projects"][key] == en_value, key
        assert "**" not in zh["projects"][key] and "※" not in zh["projects"][key], key
    # Batch 4 appended 22 keys *after* these four, so they are no longer the tail.
    # The meaningful invariant is ordering: batch 3 sits before batch 4, and both
    # are inside ``projects``.
    order = list(zh["projects"])
    assert all(key in order for key in _T_I18N3_PROJECT_KEYS)
    assert all(key in order for key in _T_I18N4_PROJECT_KEYS)
    assert max(order.index(k) for k in _T_I18N3_PROJECT_KEYS) < min(
        order.index(k) for k in _T_I18N4_PROJECT_KEYS
    ), "batch 3 keys precede batch 4 keys"


def test_batch3_error_codes_are_localized_per_key():
    repo = Path(__file__).resolve().parents[3]
    backend_zh = json.loads((repo / "src/octop/i18n/zh.json").read_text(encoding="utf-8"))
    dash_zh = _dash("zh")
    for code, expected in _T_I18N3_ERROR_ZH.items():
        assert code in {c.value for c in ErrorCode}, code
        assert backend_zh["errors"][code] == expected, code
        assert dash_zh["apiErrors"][code] == expected, code
        assert error_message(code, "zh") == expected, code
        assert error_message(code, "en"), f"{code} has no en text"


def test_batch3_status_mapping():
    assert OctopError(ErrorCode.PROJECT_KB_FORBIDDEN, "x").status == 403
    assert OctopError(ErrorCode.PROJECT_TASK_PARENT_INVALID, "x").status == 400
    for code in (ErrorCode.PROJECT_KB_FORBIDDEN, ErrorCode.PROJECT_TASK_PARENT_INVALID):
        assert OctopError(code, "x").status != 500


def _duplicate_keys_in_one_object(path: Path) -> list[str]:
    """Duplicate keys **within a single JSON object** (cross-namespace repeats are legal)."""
    seen: list[str] = []

    def collect(pairs: list[tuple[str, object]]) -> dict:
        keys = [key for key, _ in pairs]
        seen.extend([key for key in set(keys) if keys.count(key) > 1])
        return dict(pairs)

    json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=collect)
    return seen


def test_no_duplicate_keys_inside_any_dashboard_object():
    """``L2``/``FIND-7``: ``JSON.parse`` silently keeps the last duplicate.

    The check therefore runs on the parsed pair list per object — not on a
    top-level line regex, which cannot tell the two cases apart.
    """
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        path = repo / f"dashboard/src/locales/{locale}.json"
        assert _duplicate_keys_in_one_object(path) == [], locale
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 81 and len(data["chat"]) == 211, locale


def test_the_projects_block_is_written_once():
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        text = (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        assert len(re.findall(r'^  "projects": \{', text, re.M)) == 1, locale


# ── batch 4 (T-I18N4): quick-input + task-detail labels ──────────────────────
#
# Per-key zh assertions again (S10): 22 new keys, so a key-set comparison would
# still be green if any single zh value silently fell back to English.

_T_I18N4_PROJECT_KEYS = {
    "quickInputPlaceholder": ("Type a message for the project agent…", "给项目智能体发消息…"),
    "quickInputSend": ("Send", "发送"),
    "quickInputSending": ("Sending…", "发送中…"),
    "quickInputSent": ("Sent", "已发送"),
    "quickInputFailed": (
        "Failed to send. Your text is kept — please retry.",
        "发送失败。内容已保留，请重试。",
    ),
    "quickInputNoAgent": (
        "Bind an expert to this project to send messages.",
        "请先在项目配置中绑定专家。",
    ),
    "quickInputTarget": ("To {{name}}", "发给 {{name}}"),
    "quickInputRefTask": ("Reference a task", "引用任务"),
    "quickInputRefRemoved": (
        "The referenced task no longer exists and was removed.",
        "引用的任务已不存在，已移除。",
    ),
    "taskDetailTitle": ("Task detail", "任务详情"),
    "taskDetailBack": ("Back to list", "返回列表"),
    "taskDetailDescription": ("Description", "描述"),
    "taskDetailParent": ("Parent task", "父任务"),
    "taskDetailDeps": ("Dependencies", "依赖"),
    "taskDetailAttachments": ("Attachments", "附件"),
    "taskDetailTimeline": ("Activity", "过程"),
    "taskDetailTimelineCreated": ("Created", "创建"),
    "taskDetailTimelineUpdated": ("Last updated", "最近更新"),
    "taskDetailTimelineDispatched": ("Dispatched", "已派单"),
    "taskDetailTimelineEmpty": ("No status changes yet", "暂无状态变更"),
    "taskDetailNotFound": ("Task not found in this project", "该项目中不存在该任务"),
    "taskDetailSave": ("Save", "保存"),
}


def test_batch4_project_keys_are_localized_per_key():
    """22 new keys, asserted one by one in both locales (PLAN.md §6.1)."""
    en, zh = _dash("en"), _dash("zh")
    assert len(_T_I18N4_PROJECT_KEYS) == 22
    for key, (en_value, zh_value) in _T_I18N4_PROJECT_KEYS.items():
        assert key in zh["projects"], f"zh projects.{key} missing"
        assert key in en["projects"], f"en projects.{key} missing"
        assert zh["projects"][key] == zh_value, key
        assert en["projects"][key] == en_value, key
        # L10: the PLAN table's bold / footnote markers are never part of a value.
        for value in (zh["projects"][key], en["projects"][key]):
            assert "**" not in value and "※" not in value, key
    assert len(zh["projects"]) == 239 and len(en["projects"]) == 239
    # The interpolation placeholder must survive transcription verbatim.
    assert zh["projects"]["quickInputTarget"] == "发给 {{name}}"
    assert en["projects"]["quickInputTarget"] == "To {{name}}"


# ── batch 5 (T-INT5): upstream role-management code, per key (S10) ───────────
#
# The upstream branch added ``USER_ROLE_IN_USE`` (409). Per-key assertions in both
# locales: a key-set comparison (§ the equality test above) would stay green even
# if one locale silently fell back to English.

_T_INT5_ERROR_TEXT = {
    "USER_ROLE_IN_USE": {
        "zh": "仍有用户使用此角色，请先改派后再删除。",
        "en": "This role is still assigned to users. Reassign them before deleting it.",
    },
}


def test_batch5_user_role_in_use_is_localized_per_key():
    repo = Path(__file__).resolve().parents[3]
    for locale in ("en", "zh"):
        backend = json.loads((repo / f"src/octop/i18n/{locale}.json").read_text(encoding="utf-8"))[
            "errors"
        ]
        dash = json.loads(
            (repo / f"dashboard/src/locales/{locale}.json").read_text(encoding="utf-8")
        )["apiErrors"]
        for code, expected in _T_INT5_ERROR_TEXT.items():
            assert code in {c.value for c in ErrorCode}, code
            assert backend[code] == expected[locale], f"backend {locale} {code}"
            assert dash[code] == expected[locale], f"dashboard {locale} {code}"
            assert error_message(code, locale) == expected[locale], f"tr {locale} {code}"


def test_batch5_user_role_in_use_is_409():
    error = OctopError(ErrorCode.USER_ROLE_IN_USE, "in use")
    assert error.status == 409
    assert error.status != 500


# ── D1/D2 recipient picker (T-QI-I18N): four new keys, per key (S10) ─────────

_T_QI_I18N_PROJECT_KEYS = {
    "quickInputRecipientTrigger": ("Choose recipient", "选择收件人"),
    "quickInputRecipientFilter": ("Type to filter…", "输入以过滤…"),
    "quickInputRecipientEmpty": ("No matching expert", "无匹配的专家"),
    "quickInputRecipientListLabel": ("Recipients", "收件人"),
}


def test_qi_recipient_keys_are_localized_per_key():
    """The recipient picker's four labels, asserted one by one in both locales."""
    en, zh = _dash("en"), _dash("zh")
    assert len(_T_QI_I18N_PROJECT_KEYS) == 4
    for key, (en_value, zh_value) in _T_QI_I18N_PROJECT_KEYS.items():
        assert key in zh["projects"], f"zh projects.{key} missing"
        assert key in en["projects"], f"en projects.{key} missing"
        assert zh["projects"][key] == zh_value, key
        assert en["projects"][key] == en_value, key
        for value in (zh["projects"][key], en["projects"][key]):
            assert "**" not in value and "※" not in value, key
    assert len(zh["projects"]) == 239 and len(en["projects"]) == 239
    # The reused strings must keep their existing wording (no silent redefinition).
    assert zh["projects"]["quickInputTarget"] == "发给 {{name}}"
    assert zh["projects"]["quickInputNoAgent"] == "请先在项目配置中绑定专家。"


# ── batch 6 (T-P6-I18N): team-picker empty state ─────────────────────────────

_T_P6_I18N_PROJECT_KEYS = {
    "pickerEmptyTeams": ("No teams available", "暂无可选团队"),
}


def test_batch6_picker_empty_teams_is_localized_per_key():
    """The one new key of batch 6, per key, plus the reused ones it sits beside."""
    en, zh = _dash("en"), _dash("zh")
    for key, (en_value, zh_value) in _T_P6_I18N_PROJECT_KEYS.items():
        assert key in zh["projects"], f"zh projects.{key} missing"
        assert key in en["projects"], f"en projects.{key} missing"
        assert zh["projects"][key] == zh_value, key
        assert en["projects"][key] == en_value, key
        for value in (zh["projects"][key], en["projects"][key]):
            assert "**" not in value and "※" not in value, key
    assert len(zh["projects"]) == 239 and len(en["projects"]) == 239
    # The reused keys must keep their wording: this batch adds exactly one key.
    assert set(_T_P6_I18N_PROJECT_KEYS) <= set(zh["projects"])
    for reused, expected in (
        ("subjectUser", "用户"),
        ("subjectAgent", "专家"),
        ("subjectTeam", "团队"),
        ("expertNone", "暂无专家"),
        ("memberAdd", "添加成员"),
        ("expertAdd", "添加专家"),
    ):
        assert zh["projects"][reused] == expected, reused
