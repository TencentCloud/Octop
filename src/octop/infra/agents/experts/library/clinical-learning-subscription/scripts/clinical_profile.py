#!/usr/bin/env python3
"""Manage the minimal learning state for the clinical learning expert.

The state stays beside this expert package.  It is deliberately not a patient
record and does not accept arbitrary file paths.  V2 models a learning goal,
versioned learning track, immutable lesson units, and a delivery ledger.  The
ledger can reserve a lesson safely, but a real channel receipt is still needed
before a lesson is marked as delivered.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import secrets
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

try:  # The deployed runtime is Unix today; retain a safe fallback for tests.
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None  # type: ignore[assignment]


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
STATE_FILENAME = "clinical_learning_state.json"
USER_FILENAME = "USER.md"
LOCK_FILENAME = ".clinical_learning_state.lock"
LEARNING_SCHEMA_VERSION = 2

ID_CARD_RE = re.compile(r"\b\d{17}[\dXx]\b")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
SAFE_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.IGNORECASE)
PATIENT_MARKERS = (
    "患者",
    "病历号",
    "门诊号",
    "住院号",
    "身份证",
    "手机号",
    "影像号",
    "检查报告",
    "处方",
)
LEARNING_DIAGNOSIS_LEVELS = (
    "needs_foundation",
    "developing",
    "confident",
)
GOAL_KINDS = ("exam", "work_review", "update_tracking", "teaching", "custom")
GOAL_STATUSES = ("active", "paused", "completed", "archived")
TRACK_STATUSES = (
    "draft",
    "active",
    "paused",
    "completed",
    "archived",
    "superseded",
    "invalidated",
)
TRACK_PLAN_STATUSES = ("needs_planning", "ready", "needs_replan")
LESSON_DELIVERY_STATUSES = (
    "planned",
    "claimed",
    "prepared",
    "dispatching",
    "accepted",
    "failed_retryable",
    "unknown",
    "skipped",
    "superseded",
    "legacy_completed",
)
LESSON_LEARNING_STATUSES = ("not_started", "seen", "review", "mastered", "unknown")
DELIVERY_STATES = (
    "claimed",
    "prepared",
    "dispatching",
    "accepted",
    "failed_retryable",
    "unknown",
    "cancelled",
)
TERMINAL_LESSON_STATES = {"accepted", "legacy_completed", "skipped", "superseded"}


DEFAULT_STATE: dict[str, Any] = {
    "state_version": LEARNING_SCHEMA_VERSION,
    "revision": 0,
    "updated_at": "",
    "profile": {
        "consent_confirmed": False,
        "display_name": "",
        "region": "",
        "hospital": "",
        "department": "",
        "title": "",
    },
    "derived": {
        "department_system": "待识别",
        "specialty": "待识别",
        "learning_depth": "待识别",
        "insurance_scope": "待识别",
        "hospital_boundary": (
            "不推断本院 ICU、输血、内镜、ERCP、介入、手术、转运等能力；"
            "涉及执行条件时必须以本院正式制度、科室授权或医院医保办确认为准。"
        ),
    },
    # Retained as a read-only compatibility projection for v1 users.  New
    # workflows must use learning.tracks and lesson delivery states instead.
    "current_guideline": {
        "title": "待选择",
        "publisher": "待核验",
        "source_url": "待核验",
        "total_days": 0,
        "current_day": 0,
        "status": "not_selected",
    },
    "learning_diagnosis": {
        "goal": "待设定",
        "guideline_title": "待选择",
        "source_url": "待核验",
        "self_assessed_level": "not_assessed",
        "available_minutes_per_day": 0,
        "priority_topics": [],
        "recommended_start": "待诊断",
        "status": "not_started",
    },
    "learning": {
        "schema_version": LEARNING_SCHEMA_VERSION,
        "goals": [],
        "diagnostics": [],
        "tracks": [],
        "delivery_ledger": [],
        "migration": {
            "legacy_state_detected": False,
            "legacy_v1_current_guideline_imported": False,
            "legacy_v1_diagnosis_imported": False,
            "history": [],
        },
    },
    "subscriptions": {
        "daily_guideline_learning": "待绑定微信通道",
        "guideline_update_reminder": "待绑定微信通道",
        "insurance_policy_learning": "待绑定微信通道",
        "default_channel": "微信（内部 channel type: weixin）",
        "weixin_session_key": "待绑定",
    },
    "privacy": {
        "purpose": "仅用于用户明确启用的个性化指南学习、学习诊断摘要、专业指南更新提醒和地区医保政策变化学习。",
        "minimization": (
            "只保存称谓、地区、医院、科室、职称及用户明确要求保存的最小学习配置；"
            "可信投递账本和通道回执由平台服务保存，不放在专家工作区；"
            "不保存普通通用任务内容、课程正文、原始答题或患者信息。"
        ),
        "deletion_status": "未申请删除",
    },
}


def state_path(root: Path = PACKAGE_ROOT) -> Path:
    return root / STATE_FILENAME


def user_path(root: Path = PACKAGE_ROOT) -> Path:
    return root / USER_FILENAME


def lock_path(root: Path = PACKAGE_ROOT) -> Path:
    return root / LOCK_FILENAME


def _deep_default_state() -> dict[str, Any]:
    return copy.deepcopy(DEFAULT_STATE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shanghai_date() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None


def _merge_defaults(value: dict[str, Any]) -> dict[str, Any]:
    """Merge known top-level sections without dropping data from a newer state."""
    # v1 has a top-level current_guideline but no learning container.  A v2
    # compatibility projection also has current_guideline, so this detection
    # must happen before defaults are merged.
    legacy_v1_input = "learning" not in value and int(value.get("state_version") or 1) < LEARNING_SCHEMA_VERSION
    state = _deep_default_state()
    for section, section_value in value.items():
        if isinstance(section_value, dict) and isinstance(state.get(section), dict):
            state[section].update(section_value)
        else:
            state[section] = section_value
    _ensure_learning_shape(state)
    if legacy_v1_input:
        state["learning"]["migration"]["legacy_state_detected"] = True
    return state


def _ensure_learning_shape(state: dict[str, Any]) -> None:
    learning = state.get("learning")
    if not isinstance(learning, dict):
        learning = {}
        state["learning"] = learning
    defaults = copy.deepcopy(DEFAULT_STATE["learning"])
    for key, fallback in defaults.items():
        if key not in learning or not isinstance(learning[key], type(fallback)):
            learning[key] = fallback
    migration = learning["migration"]
    for key, fallback in defaults["migration"].items():
        migration.setdefault(key, copy.deepcopy(fallback))
    learning["schema_version"] = LEARNING_SCHEMA_VERSION
    state["state_version"] = LEARNING_SCHEMA_VERSION
    if not isinstance(state.get("revision"), int):
        state["revision"] = 0
    if not isinstance(state.get("updated_at"), str):
        state["updated_at"] = ""


def _read_state_unlocked(root: Path) -> dict[str, Any]:
    path = state_path(root)
    if not path.is_file():
        return _deep_default_state()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"档案状态文件损坏，无法读取：{exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError("档案状态文件格式错误：顶层必须是对象")
    return _merge_defaults(loaded)


@contextmanager
def _state_lock(root: Path) -> Iterator[None]:
    """Serialize writers. Atomic replacement protects readers from partial JSON."""
    root.mkdir(parents=True, exist_ok=True)
    handle = lock_path(root).open("a+", encoding="utf-8")
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _write_state_unlocked(state: dict[str, Any], root: Path) -> None:
    _atomic_write(
        state_path(root),
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
    )
    _atomic_write(user_path(root), render_user_text(state))


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _new_id(prefix: str, label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    if not slug:
        slug = "item"
    return f"{prefix}-{slug[:32]}-{_short_hash(f'{label}:{_now()}:{secrets.token_hex(4)}')}"


def _normalize_id(label: str, value: str, *, prefix: str, fallback_label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return _new_id(prefix, fallback_label)
    if not SAFE_ID_RE.fullmatch(normalized):
        raise ValueError(f"{label}必须为小写字母开头的 3-80 位 slug（字母、数字、连字符）")
    return normalized


def _reject_pii(label: str, value: str) -> None:
    if ID_CARD_RE.search(value) or PHONE_RE.search(value):
        raise ValueError(f"{label}疑似包含患者个人信息或联系方式，已拒绝写入")
    for marker in PATIENT_MARKERS:
        if marker in value:
            raise ValueError(f"{label}包含“{marker}”，已拒绝写入患者相关信息")


def _require_clean(label: str, value: str, *, max_length: int = 240) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise ValueError(f"{label}不能为空")
    if len(normalized) > max_length:
        raise ValueError(f"{label}过长，最多 {max_length} 个字符")
    _reject_pii(label, normalized)
    return normalized


def _optional_clean(label: str, value: str, *, fallback: str, max_length: int = 240) -> str:
    normalized = " ".join(str(value or "").strip().split())
    return _require_clean(label, normalized, max_length=max_length) if normalized else fallback


def _clean_url(label: str, value: str) -> str:
    normalized = _require_clean(label, value, max_length=2048)
    parsed = urlparse(normalized)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError(f"{label}必须是完整的 http 或 https 链接")
    return normalized


def _normalize_sha256(label: str, value: str) -> str:
    normalized = _require_clean(label, value, max_length=80).lower()
    if not SHA256_RE.fullmatch(normalized):
        raise ValueError(f"{label}必须是 sha256: 开头或 64 位十六进制哈希")
    return normalized if normalized.startswith("sha256:") else f"sha256:{normalized}"


def _optional_iso_date(label: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    try:
        datetime.fromisoformat(normalized).date()
    except ValueError as exc:
        raise ValueError(f"{label}必须是 YYYY-MM-DD 日期") from exc
    return normalized


def normalize_region(region: str) -> str:
    raw = _require_clean("地区", region)
    municipality = re.match(r"^(北京市|上海市|天津市|重庆市)(.*)$", raw)
    if municipality:
        city = municipality.group(1)
        rest = municipality.group(2).strip("-/／,， ")
        return f"{city}-{rest}" if rest else city
    parts = [part for part in re.split(r"[-/／,，\s]+", raw) if part]
    return "-".join(parts) if len(parts) > 1 else raw


def derive_department_system(department: str) -> str:
    if any(
        key in department
        for key in ("呼吸", "消化", "心内", "神内", "内分泌", "肾内", "血液", "风湿", "感染", "全科", "内科")
    ):
        return "临床内科系统"
    if any(key in department for key in ("普外", "骨科", "肝胆", "胃肠", "胸外", "泌尿外", "神外", "外科")):
        return "临床外科系统"
    if "儿科" in department:
        return "儿科系统"
    if "妇" in department or "产" in department:
        return "妇产科系统"
    if "急诊" in department or "重症" in department:
        return "急危重症学习主题"
    if any(key in department for key in ("影像", "检验", "药学", "医保", "病案", "质控")):
        return "医技/管理学习主题"
    return "综合临床学习主题"


def derive_specialty(department: str) -> str:
    if "呼吸" in department:
        return "呼吸内科（慢阻肺、哮喘、社区获得性肺炎、肺部感染、戒烟等基层高频方向）"
    if "消化" in department:
        return "消化内科（幽门螺杆菌、消化道早癌筛查、胃肠常见病等基层高频方向）"
    if "心" in department:
        return "心血管内科（高血压、冠心病、心衰、房颤等基层高频方向）"
    if "全科" in department:
        return "全科医学（慢病管理、常见病识别、转诊与公共卫生服务）"
    if "儿科" in department:
        return "儿科（儿童发热、腹泻脱水、热性惊厥、儿童用药安全等学习方向）"
    return department


def derive_learning_depth(title: str) -> str:
    if any(key in title for key in ("副高", "主任", "正高", "教授")):
        return "副高/正高（更新、争议、质量指标、科室管理和带教）"
    if any(key in title for key in ("主治", "中级")):
        return "主治/中级（分层、鉴别、流程质量、更新重点）"
    if any(key in title for key in ("住院", "初级", "执业", "助理")):
        return "初级/住院医师（基础规范、常见风险、学习提醒）"
    if any(key in title for key in ("质控", "医保", "病案", "编码", "管理")):
        return "辅助/管理岗位（报告、质控、医保、编码、流程）"
    return f"{title}（按岗位需要调整学习深度）"


def apply_derived_fields(state: dict[str, Any]) -> None:
    profile = state["profile"]
    department = profile.get("department") or ""
    title = profile.get("title") or ""
    region = profile.get("region") or ""
    state["derived"].update(
        {
            "department_system": derive_department_system(department) if department else "待识别",
            "specialty": derive_specialty(department) if department else "待识别",
            "learning_depth": derive_learning_depth(title) if title else "待识别",
            "insurance_scope": region or "待识别",
        },
    )


def _find_by_id(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == item_id), None)


def _find_track(state: dict[str, Any], track_id: str) -> dict[str, Any]:
    track = _find_by_id(state["learning"]["tracks"], track_id)
    if track is None:
        raise ValueError("未找到指定学习轨道")
    return track


def _find_lesson(track: dict[str, Any], lesson_id: str) -> dict[str, Any]:
    lesson = _find_by_id(track.get("lessons", []), lesson_id)
    if lesson is None:
        raise ValueError("该学习轨道中未找到指定学习单元")
    return lesson


def _find_delivery(state: dict[str, Any], delivery_id: str) -> dict[str, Any]:
    delivery = _find_by_id(state["learning"]["delivery_ledger"], delivery_id)
    if delivery is None:
        raise ValueError("未找到指定投递记录")
    return delivery


def _track_source(track: dict[str, Any]) -> dict[str, Any]:
    source = track.get("source")
    if not isinstance(source, dict):
        raise ValueError("学习轨道缺少来源快照")
    return source


def _lesson_is_terminal(lesson: dict[str, Any]) -> bool:
    return lesson.get("delivery_status") in TERMINAL_LESSON_STATES


def _first_open_lesson(track: dict[str, Any]) -> dict[str, Any] | None:
    lessons = sorted(track.get("lessons", []), key=lambda item: int(item.get("ordinal") or 0))
    for lesson in lessons:
        if not _lesson_is_terminal(lesson):
            return lesson
    return None


def _track_progress(track: dict[str, Any]) -> dict[str, int]:
    lessons = track.get("lessons", [])
    delivered = sum(1 for lesson in lessons if lesson.get("delivery_status") in {"accepted", "legacy_completed"})
    completed = sum(1 for lesson in lessons if lesson.get("learning_status") == "mastered")
    return {"total": len(lessons), "delivered": delivered, "mastered": completed}


def _refresh_legacy_guideline_projection(state: dict[str, Any]) -> None:
    tracks = state["learning"]["tracks"]
    active = next((track for track in tracks if track.get("status") == "active"), None)
    if active is None:
        return
    source = _track_source(active)
    progress = _track_progress(active)
    current = state["current_guideline"]
    current.update(
        {
            "title": source.get("title") or "待选择",
            "publisher": source.get("publisher") or "待核验",
            "source_url": source.get("url") or "待核验",
            "total_days": progress["total"],
            "current_day": progress["delivered"],
            "status": "completed"
            if progress["total"] and progress["delivered"] >= progress["total"]
            else "in_progress",
        }
    )


def _migrate_legacy_state(state: dict[str, Any]) -> list[str]:
    """Create an honest in-memory v2 projection of old day-number state.

    The migration deliberately does not fabricate a channel receipt.  Old
    completed days become legacy_completed lesson records and require a
    re-planned, re-verified course before any new formal delivery.
    """
    _ensure_learning_shape(state)
    learning = state["learning"]
    migration = learning["migration"]
    changes: list[str] = []
    legacy = state["current_guideline"]

    if (
        migration.get("legacy_state_detected")
        and
        not migration.get("legacy_v1_current_guideline_imported")
        and legacy.get("title")
        and legacy.get("title") != "待选择"
    ):
        title = str(legacy.get("title"))
        total_days = max(0, int(legacy.get("total_days") or 0))
        current_day = min(max(0, int(legacy.get("current_day") or 0)), total_days)
        track_id = _normalize_id("", "", prefix="legacy-track", fallback_label=title)
        lessons: list[dict[str, Any]] = []
        source_revision = "legacy-unreverified"
        for ordinal in range(1, total_days + 1):
            status = "legacy_completed" if ordinal <= current_day else "planned"
            lesson_id = f"{track_id}-unit-{ordinal:02d}"
            lessons.append(
                {
                    "id": lesson_id,
                    "ordinal": ordinal,
                    "title": f"旧版学习记录：第 {ordinal} 天",
                    "source_anchor": "旧版仅记录天数，待用权威原文回填章节",
                    "objectives": [],
                    "topic_tags": [],
                    "estimated_minutes": 0,
                    "unit_fingerprint": _hash(f"{track_id}:{ordinal}:legacy"),
                    "topic_fingerprint": _hash(f"{track_id}:{ordinal}:legacy-topic"),
                    "delivery_status": status,
                    "learning_status": "unknown",
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
        learning["tracks"].append(
            {
                "id": track_id,
                "kind": "guideline",
                "label": title,
                "goal_ids": [],
                "status": "active",
                "plan_status": "needs_replan",
                "source": {
                    "document_key": _hash(f"{title}:{legacy.get('source_url') or ''}:legacy"),
                    "title": title,
                    "publisher": legacy.get("publisher") or "待核验",
                    "version": "旧版未记录",
                    "source_revision": source_revision,
                    "url": legacy.get("source_url") or "待核验",
                    "verification_status": "legacy_unreverified",
                    "verified_at": "",
                },
                "lessons": lessons,
                "created_at": _now(),
                "updated_at": _now(),
                "migration_note": "由 v1 天数进度迁入；没有伪造微信回执，剩余章节需重新核验并规划。",
            }
        )
        migration["legacy_v1_current_guideline_imported"] = True
        migration["history"].append(
            {
                "at": _now(),
                "kind": "v1_current_guideline",
                "track_id": track_id,
                "note": "旧进度已转换为 legacy_completed；未生成投递回执。",
            }
        )
        changes.append("legacy_current_guideline_imported")

    diagnostic = state["learning_diagnosis"]
    if (
        migration.get("legacy_state_detected")
        and
        not migration.get("legacy_v1_diagnosis_imported")
        and diagnostic.get("status") == "saved"
        and diagnostic.get("goal")
        and diagnostic.get("goal") != "待设定"
    ):
        learning["diagnostics"].append(
            {
                "id": _new_id("diagnostic", str(diagnostic["goal"])),
                "goal_id": "",
                "goal": diagnostic.get("goal"),
                "guideline_title": diagnostic.get("guideline_title"),
                "source_url": diagnostic.get("source_url"),
                "self_assessed_level": diagnostic.get("self_assessed_level"),
                "available_minutes_per_day": diagnostic.get("available_minutes_per_day"),
                "priority_topics": diagnostic.get("priority_topics") or [],
                "recommended_start": diagnostic.get("recommended_start"),
                "saved_with_confirmation": True,
                "created_at": _now(),
                "migration_note": "由 v1 学习诊断摘要迁入；不含原始答题。",
            }
        )
        migration["legacy_v1_diagnosis_imported"] = True
        changes.append("legacy_learning_diagnosis_imported")
    return changes


def load_state(root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    state = _read_state_unlocked(root)
    _migrate_legacy_state(state)
    _refresh_legacy_guideline_projection(state)
    return state


def _touch_state(state: dict[str, Any]) -> None:
    _ensure_learning_shape(state)
    _refresh_legacy_guideline_projection(state)
    state["revision"] = int(state.get("revision") or 0) + 1
    state["updated_at"] = _now()


def save_state(state: dict[str, Any], root: Path = PACKAGE_ROOT) -> None:
    with _state_lock(root):
        _migrate_legacy_state(state)
        _touch_state(state)
        _write_state_unlocked(state, root)


def _mutate_state(
    root: Path,
    mutator: Callable[[dict[str, Any]], Any],
) -> tuple[dict[str, Any], Any]:
    with _state_lock(root):
        state = _read_state_unlocked(root)
        _migrate_legacy_state(state)
        result = mutator(state)
        _touch_state(state)
        _write_state_unlocked(state, root)
    return state, result


def register_profile(
    *,
    display_name: str,
    region: str,
    hospital: str,
    department: str,
    title: str,
    consent_confirmed: bool,
    root: Path = PACKAGE_ROOT,
) -> dict[str, Any]:
    if not consent_confirmed:
        raise ValueError("未确认用户同意处理 5 项医生信息，拒绝写入")

    def mutate(state: dict[str, Any]) -> None:
        state["profile"].update(
            {
                "consent_confirmed": True,
                "display_name": _require_clean("称谓", display_name),
                "region": normalize_region(region),
                "hospital": _require_clean("医院", hospital),
                "department": _require_clean("科室", department),
                "title": _require_clean("职称", title),
            },
        )
        state["privacy"]["deletion_status"] = "未申请删除"
        apply_derived_fields(state)

    state, _ = _mutate_state(root, mutate)
    return state


def _validate_goal_ids(state: dict[str, Any], goal_ids: list[str]) -> list[str]:
    unique: list[str] = []
    for raw_goal_id in goal_ids:
        goal_id = _normalize_id("学习目标 ID", raw_goal_id, prefix="goal", fallback_label=raw_goal_id)
        if goal_id not in unique:
            unique.append(goal_id)
    known = {goal["id"] for goal in state["learning"]["goals"]}
    missing = [goal_id for goal_id in unique if goal_id not in known]
    if missing:
        raise ValueError(f"未找到关联学习目标：{', '.join(missing)}")
    return unique


def save_learning_goal(
    *,
    label: str,
    kind: str,
    daily_minutes: int,
    target_date: str,
    priority: int,
    status: str,
    goal_id: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("保存学习目标必须显式确认")
    if kind not in GOAL_KINDS:
        raise ValueError(f"学习目标类型必须是以下之一：{', '.join(GOAL_KINDS)}")
    if status not in GOAL_STATUSES:
        raise ValueError(f"学习目标状态必须是以下之一：{', '.join(GOAL_STATUSES)}")
    if not 5 <= daily_minutes <= 240:
        raise ValueError("每日可投入时间必须在 5-240 分钟之间")
    if not 0 <= priority <= 100:
        raise ValueError("学习优先级必须在 0-100 之间")
    cleaned_label = _require_clean("学习目标", label)
    cleaned_target_date = _optional_iso_date("目标日期", target_date)
    normalized_id = _normalize_id("学习目标 ID", goal_id, prefix="goal", fallback_label=cleaned_label)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        goals = state["learning"]["goals"]
        existing = _find_by_id(goals, normalized_id)
        now = _now()
        goal = {
            "id": normalized_id,
            "label": cleaned_label,
            "kind": kind,
            "status": status,
            "target_date": cleaned_target_date,
            "daily_minutes": daily_minutes,
            "priority": priority,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        if existing is None:
            goals.append(goal)
        else:
            existing.clear()
            existing.update(goal)
        return goal

    return _mutate_state(root, mutate)


def save_learning_diagnosis(
    *,
    goal: str,
    guideline_title: str,
    source_url: str,
    self_assessed_level: str,
    available_minutes_per_day: int,
    priority_topics: list[str],
    recommended_start: str,
    confirm: bool,
    goal_id: str = "",
    root: Path = PACKAGE_ROOT,
) -> dict[str, Any]:
    """Persist only a user-confirmed, minimum diagnostic summary."""
    if not confirm:
        raise ValueError("保存学习诊断摘要必须显式确认")
    if self_assessed_level not in LEARNING_DIAGNOSIS_LEVELS:
        raise ValueError(f"学习自评等级必须是以下之一：{', '.join(LEARNING_DIAGNOSIS_LEVELS)}")
    if not 5 <= available_minutes_per_day <= 240:
        raise ValueError("每日可投入时间必须在 5-240 分钟之间")

    cleaned_goal = _require_clean("学习目标", goal)
    cleaned_title = _optional_clean("指南名称", guideline_title, fallback="待选择")
    cleaned_url = _optional_clean("权威来源", source_url, fallback="待核验", max_length=2048)
    if cleaned_url != "待核验":
        cleaned_url = _clean_url("权威来源", cleaned_url)
    normalized_topics: list[str] = []
    for topic in priority_topics:
        cleaned = _require_clean("优先学习主题", topic)
        if cleaned not in normalized_topics:
            normalized_topics.append(cleaned)
    if not normalized_topics:
        raise ValueError("至少保存一个优先学习主题")
    cleaned_start = _require_clean("建议起点", recommended_start)
    normalized_goal_id = (
        _normalize_id("学习目标 ID", goal_id, prefix="goal", fallback_label=cleaned_goal) if goal_id else ""
    )

    def mutate(state: dict[str, Any]) -> None:
        if normalized_goal_id and _find_by_id(state["learning"]["goals"], normalized_goal_id) is None:
            raise ValueError("未找到关联学习目标；请先保存目标或省略 goal_id")
        state["learning_diagnosis"].update(
            {
                "goal": cleaned_goal,
                "guideline_title": cleaned_title,
                "source_url": cleaned_url,
                "self_assessed_level": self_assessed_level,
                "available_minutes_per_day": available_minutes_per_day,
                "priority_topics": normalized_topics,
                "recommended_start": cleaned_start,
                "status": "saved",
            }
        )
        diagnostic = {
            "id": _new_id("diagnostic", cleaned_goal),
            "goal_id": normalized_goal_id,
            "goal": cleaned_goal,
            "guideline_title": cleaned_title,
            "source_url": cleaned_url,
            "self_assessed_level": self_assessed_level,
            "available_minutes_per_day": available_minutes_per_day,
            "priority_topics": normalized_topics,
            "recommended_start": cleaned_start,
            "saved_with_confirmation": True,
            "created_at": _now(),
        }
        state["learning"]["diagnostics"].append(diagnostic)

    state, _ = _mutate_state(root, mutate)
    return state


def clear_learning_diagnosis(*, confirm: bool, root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    if not confirm:
        raise ValueError("清除学习诊断摘要必须显式确认")

    def mutate(state: dict[str, Any]) -> None:
        state["learning_diagnosis"] = copy.deepcopy(DEFAULT_STATE["learning_diagnosis"])
        state["learning"]["diagnostics"] = []

    state, _ = _mutate_state(root, mutate)
    return state


def create_learning_track(
    *,
    label: str,
    publisher: str,
    version: str,
    source_url: str,
    source_revision: str,
    goal_ids: list[str],
    track_id: str,
    kind: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("创建学习轨道必须显式确认")
    if kind != "guideline":
        raise ValueError("当前专家包只允许 guideline 类型学习轨道")
    cleaned_label = _require_clean("指南名称", label)
    cleaned_publisher = _require_clean("发布机构", publisher)
    cleaned_version = _require_clean("指南版本", version)
    cleaned_source_url = _clean_url("权威来源", source_url)
    cleaned_revision = _require_clean("来源修订标识", source_revision)
    normalized_id = _normalize_id("学习轨道 ID", track_id, prefix="track", fallback_label=cleaned_label)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        if _find_by_id(state["learning"]["tracks"], normalized_id) is not None:
            raise ValueError("学习轨道 ID 已存在；请使用新的 ID 或先迁移/归档旧轨道")
        linked_goal_ids = _validate_goal_ids(state, goal_ids)
        now = _now()
        track = {
            "id": normalized_id,
            "kind": kind,
            "label": cleaned_label,
            "goal_ids": linked_goal_ids,
            "status": "draft",
            "plan_status": "needs_planning",
            "source": {
                "document_key": _hash(
                    f"{cleaned_label}|{cleaned_publisher}|{cleaned_version}|{cleaned_source_url}|{cleaned_revision}"
                ),
                "title": cleaned_label,
                "publisher": cleaned_publisher,
                "version": cleaned_version,
                "source_revision": cleaned_revision,
                "url": cleaned_source_url,
                "verification_status": "verified",
                "verified_at": now,
            },
            "lessons": [],
            "created_at": now,
            "updated_at": now,
        }
        state["learning"]["tracks"].append(track)
        return track

    return _mutate_state(root, mutate)


def _parse_lesson_json(raw: str, *, track: dict[str, Any]) -> dict[str, Any]:
    try:
        source = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"学习单元 JSON 格式错误：{exc.msg}") from exc
    if not isinstance(source, dict):
        raise ValueError("学习单元必须是 JSON 对象")
    try:
        ordinal = int(source.get("ordinal"))
    except (TypeError, ValueError) as exc:
        raise ValueError("学习单元 ordinal 必须为正整数") from exc
    if ordinal < 1:
        raise ValueError("学习单元 ordinal 必须为正整数")
    title = _require_clean("学习单元标题", str(source.get("title") or ""))
    source_anchor_value = source.get("source_anchor", "")
    if isinstance(source_anchor_value, dict):
        source_anchor = {
            "section": _require_clean("章节锚点 section", str(source_anchor_value.get("section") or "")),
            "locator": _optional_clean(
                "章节锚点 locator",
                str(source_anchor_value.get("locator") or ""),
                fallback="未提供",
            ),
        }
    else:
        source_anchor = _require_clean("章节锚点", str(source_anchor_value))
    raw_objectives = source.get("objectives", source.get("learning_objectives", []))
    if not isinstance(raw_objectives, list):
        raise ValueError("学习单元 objectives 必须是字符串数组")
    objectives: list[str] = []
    for item in raw_objectives:
        cleaned = _require_clean("学习目标", str(item))
        if cleaned not in objectives:
            objectives.append(cleaned)
    if not objectives:
        raise ValueError("每个学习单元至少需要一个学习目标")
    raw_tags = source.get("topic_tags", [])
    if not isinstance(raw_tags, list):
        raise ValueError("学习单元 topic_tags 必须是字符串数组")
    topic_tags: list[str] = []
    for item in raw_tags:
        cleaned = _require_clean("主题标签", str(item))
        if cleaned not in topic_tags:
            topic_tags.append(cleaned)
    try:
        estimated_minutes = int(source.get("estimated_minutes", 10))
    except (TypeError, ValueError) as exc:
        raise ValueError("预计学习时长必须是整数") from exc
    if not 3 <= estimated_minutes <= 90:
        raise ValueError("预计学习时长必须在 3-90 分钟之间")
    source_revision = _track_source(track)["source_revision"]
    anchor_key = json.dumps(source_anchor, ensure_ascii=False, sort_keys=True)
    unit_fingerprint = _normalize_sha256(
        "单元指纹",
        str(
            source.get("unit_fingerprint")
            or _hash(f"{track['id']}|{source_revision}|{ordinal}|{title}|{anchor_key}")
        ),
    )
    topic_fingerprint = _normalize_sha256(
        "主题指纹",
        str(source.get("topic_fingerprint") or _hash(f"{source_revision}|{'|'.join(topic_tags)}|{title}")),
    )
    lesson_id = _normalize_id(
        "学习单元 ID",
        str(source.get("id") or ""),
        prefix=f"{track['id']}-lesson",
        fallback_label=f"{track['id']}-{ordinal}-{title}",
    )
    now = _now()
    return {
        "id": lesson_id,
        "ordinal": ordinal,
        "title": title,
        "source_anchor": source_anchor,
        "objectives": objectives,
        "topic_tags": topic_tags,
        "estimated_minutes": estimated_minutes,
        "unit_fingerprint": unit_fingerprint,
        "topic_fingerprint": topic_fingerprint,
        "delivery_status": "planned",
        "learning_status": "not_started",
        "created_at": now,
        "updated_at": now,
    }


def replace_track_lessons(
    *,
    track_id: str,
    lesson_jsons: list[str],
    replace_pending: bool,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("保存学习单元计划必须显式确认")
    if not replace_pending:
        raise ValueError("替换待投递学习单元必须显式设置 replace_pending=true")
    if not lesson_jsons:
        raise ValueError("至少提供一个学习单元")

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        track = _find_track(state, track_id)
        existing = list(track.get("lessons", []))
        protected = [
            lesson
            for lesson in existing
            if lesson.get("delivery_status") != "planned"
        ]
        if any(lesson.get("delivery_status") in {"claimed", "prepared", "dispatching", "unknown"} for lesson in protected):
            raise ValueError("存在已领取、发送中或状态不明的学习单元；请先完成通道对账，不能改写计划")
        candidate = [_parse_lesson_json(raw, track=track) for raw in lesson_jsons]
        lesson_ids = [lesson["id"] for lesson in candidate]
        ordinals = [lesson["ordinal"] for lesson in candidate]
        fingerprints = [lesson["unit_fingerprint"] for lesson in candidate]
        if len(set(lesson_ids)) != len(lesson_ids):
            raise ValueError("学习单元 ID 不能重复")
        if len(set(ordinals)) != len(ordinals):
            raise ValueError("学习单元 ordinal 不能重复")
        if len(set(fingerprints)) != len(fingerprints):
            raise ValueError("同一轨道内不能保存重复学习单元")
        protected_ids = {lesson["id"] for lesson in protected}
        protected_ordinals = {lesson["ordinal"] for lesson in protected}
        protected_fingerprints = {lesson["unit_fingerprint"] for lesson in protected}
        if protected_ids.intersection(lesson_ids):
            raise ValueError("已投递的学习单元 ID 不能被改写")
        if protected_ordinals.intersection(ordinals):
            raise ValueError("已投递的学习单元序号不能被改写")
        if protected_fingerprints.intersection(fingerprints):
            raise ValueError("已投递的学习单元指纹不能复用")
        all_lessons = sorted(protected + candidate, key=lambda lesson: lesson["ordinal"])
        expected_ordinals = list(range(1, len(all_lessons) + 1))
        if [lesson["ordinal"] for lesson in all_lessons] != expected_ordinals:
            raise ValueError("学习单元 ordinal 必须从 1 开始连续编号")
        track["lessons"] = all_lessons
        track["plan_status"] = "ready"
        track["updated_at"] = _now()
        return {
            "track_id": track["id"],
            "lesson_count": len(all_lessons),
            "preserved_terminal_lessons": len(protected),
        }

    return _mutate_state(root, mutate)


def activate_learning_track(
    *,
    track_id: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("启用学习轨道必须显式确认")

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        track = _find_track(state, track_id)
        source = _track_source(track)
        if source.get("verification_status") != "verified":
            raise ValueError("来源未核验，不能启用正式学习轨道")
        if track.get("plan_status") != "ready" or not track.get("lessons"):
            raise ValueError("学习轨道尚无完整章节计划，不能启用")
        if track.get("status") == "superseded":
            raise ValueError("已迁移的旧轨道不能重新启用；请使用新轨道")
        track["status"] = "active"
        track["updated_at"] = _now()
        return _track_public_summary(track)

    return _mutate_state(root, mutate)


def set_learning_track_status(
    *,
    track_id: str,
    status: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pause or archive a track without deleting its immutable history."""
    if not confirm:
        raise ValueError("暂停或归档学习轨道必须显式确认")
    if status not in {"paused", "archived"}:
        raise ValueError("此操作只允许将学习轨道设为 paused 或 archived")

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        track = _find_track(state, track_id)
        if track.get("status") == "superseded":
            raise ValueError("已迁移的旧轨道不能再修改状态")
        track["status"] = status
        track["updated_at"] = _now()
        return _track_public_summary(track)

    return _mutate_state(root, mutate)


def _track_public_summary(track: dict[str, Any]) -> dict[str, Any]:
    source = _track_source(track)
    progress = _track_progress(track)
    next_lesson = _first_open_lesson(track)
    return {
        "id": track["id"],
        "label": track.get("label"),
        "status": track.get("status"),
        "plan_status": track.get("plan_status"),
        "source": {
            "title": source.get("title"),
            "publisher": source.get("publisher"),
            "version": source.get("version"),
            "source_revision": source.get("source_revision"),
            "url": source.get("url"),
            "verification_status": source.get("verification_status"),
        },
        "progress": {
            "planned_units": progress["total"],
            "user_marked_mastered": progress["mastered"],
        },
        "next_lesson": _lesson_public_summary(next_lesson) if next_lesson else None,
    }


def _lesson_public_summary(lesson: dict[str, Any] | None) -> dict[str, Any] | None:
    if lesson is None:
        return None
    return {
        "id": lesson.get("id"),
        "ordinal": lesson.get("ordinal"),
        "title": lesson.get("title"),
        "source_anchor": lesson.get("source_anchor"),
        "objectives": lesson.get("objectives"),
        "topic_tags": lesson.get("topic_tags"),
        "estimated_minutes": lesson.get("estimated_minutes"),
        "delivery_status": lesson.get("delivery_status"),
        "learning_status": lesson.get("learning_status"),
    }


def get_track_status(*, track_id: str, root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    state = load_state(root)
    if track_id:
        return {"track": _track_public_summary(_find_track(state, track_id))}
    return {
        "tracks": [_track_public_summary(track) for track in state["learning"]["tracks"]],
        "goals": [
            {
                key: goal.get(key)
                for key in ("id", "label", "kind", "status", "target_date", "daily_minutes", "priority")
            }
            for goal in state["learning"]["goals"]
        ],
    }


def get_next_lesson(*, track_id: str, root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    state = load_state(root)
    if track_id:
        track = _find_track(state, track_id)
    else:
        active_tracks = [track for track in state["learning"]["tracks"] if track.get("status") == "active"]
        if not active_tracks:
            raise ValueError("没有已启用的学习轨道")
        if len(active_tracks) > 1:
            raise ValueError("存在多个已启用的学习轨道；请明确选择 track_id")
        track = active_tracks[0]
    if track.get("status") != "active":
        raise ValueError("学习轨道未启用；预览可以查看计划，正式学习前请先启用")
    if track.get("plan_status") != "ready":
        raise ValueError("学习轨道需要重新规划；不得按旧天数随机继续")
    lesson = _first_open_lesson(track)
    return {
        "track": _track_public_summary(track),
        "lesson": _lesson_public_summary(lesson),
        "preview_only": True,
        "note": "读取下一单元不会创建投递账本，也不会推进学习进度。",
    }


def mark_lesson_learning(
    *,
    track_id: str,
    lesson_id: str,
    learning_status: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("更新学习完成状态必须显式确认")
    if learning_status not in LESSON_LEARNING_STATUSES:
        raise ValueError(f"学习状态必须是以下之一：{', '.join(LESSON_LEARNING_STATUSES)}")

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        track = _find_track(state, track_id)
        lesson = _find_lesson(track, lesson_id)
        lesson["learning_status"] = learning_status
        lesson["updated_at"] = _now()
        if all(item.get("learning_status") == "mastered" for item in track.get("lessons", [])):
            track["status"] = "completed"
        track["updated_at"] = _now()
        return _lesson_public_summary(lesson) or {}

    return _mutate_state(root, mutate)


def _delivery_is_expired(delivery: dict[str, Any]) -> bool:
    expiration = _parse_timestamp(str(delivery.get("lease_expires_at") or ""))
    return expiration is not None and expiration <= datetime.now(timezone.utc)


def _lease_expiration(seconds: int) -> str:
    if not 60 <= seconds <= 3600:
        raise ValueError("投递领取租约必须在 60-3600 秒之间")
    timestamp = datetime.now(timezone.utc).timestamp() + seconds
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _delivery_details(
    delivery: dict[str, Any],
    track: dict[str, Any],
    lesson: dict[str, Any],
    *,
    disposition: str,
    should_send: bool,
    claim_token: str = "",
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "disposition": disposition,
        "should_send": should_send,
        "delivery": {
            key: delivery.get(key)
            for key in (
                "id",
                "state",
                "attempt",
                "lease_expires_at",
            )
        },
        "track": _track_public_summary(track),
        "lesson": _lesson_public_summary(lesson),
    }
    if claim_token:
        details["security_note"] = "投递令牌只允许由平台受鉴权的 outbox 服务持有，不向模板或用户输出。"
    return details


def _delivery_for_lesson(
    state: dict[str, Any],
    track_id: str,
    lesson_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            record
            for record in state["learning"]["delivery_ledger"]
            if record.get("track_id") == track_id
            and record.get("lesson_id") == lesson_id
            and record.get("state") == "accepted"
        ),
        None,
    )


def _delivery_has_idempotency_key(delivery: dict[str, Any], key_hash: str) -> bool:
    key_hashes = delivery.get("idempotency_key_hashes", [])
    return key_hash == delivery.get("idempotency_key_hash") or key_hash in key_hashes


def _remember_idempotency_key(delivery: dict[str, Any], key_hash: str) -> None:
    remembered = list(delivery.get("idempotency_key_hashes") or [])
    primary = delivery.get("idempotency_key_hash")
    if primary and primary not in remembered:
        remembered.append(primary)
    if key_hash not in remembered:
        remembered.append(key_hash)
    delivery["idempotency_key_hash"] = key_hash
    delivery["idempotency_key_hashes"] = remembered


def _reclaim_delivery(
    delivery: dict[str, Any],
    lesson: dict[str, Any],
    *,
    key_hash: str,
    route_key: str,
    slot_key: str,
    lease_seconds: int,
) -> str:
    token = secrets.token_urlsafe(24)
    _remember_idempotency_key(delivery, key_hash)
    delivery.update(
        {
            "state": "claimed",
            "route_key_hash": route_key,
            "slot_key_hash": slot_key,
            "scheduled_local_date": _shanghai_date(),
            "attempt": int(delivery.get("attempt") or 0) + 1,
            "claim_token_hash": _hash(token),
            "lease_expires_at": _lease_expiration(lease_seconds),
            "updated_at": _now(),
        }
    )
    lesson["delivery_status"] = "claimed"
    lesson["updated_at"] = _now()
    return token


def _platform_delivery_lifecycle_unavailable() -> None:
    raise RuntimeError(
        "正式投递账本和通道回执必须由平台受鉴权的 outbox 服务持有；"
        "专家工作区中的脚本不提供领取、发送、失败或送达确认能力。"
    )


def _claim_delivery_for_platform(
    *,
    track_id: str,
    lesson_id: str,
    route_key: str,
    slot_key: str,
    idempotency_key: str,
    lease_seconds: int,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reserved for a future platform-owned outbox, never callable in this template."""
    _platform_delivery_lifecycle_unavailable()
    cleaned_route = _require_clean("投递路由", route_key)
    cleaned_slot = _require_clean("投递时段", slot_key)
    cleaned_key = _require_clean("幂等键", idempotency_key, max_length=512)
    route_hash = _hash(cleaned_route)
    slot_hash = _hash(cleaned_slot)
    key_hash = _hash(cleaned_key)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        track = _find_track(state, track_id)
        if track.get("status") != "active" or track.get("plan_status") != "ready":
            raise ValueError("只能为已启用且计划完整的学习轨道领取正式投递单元")
        if lesson_id:
            lesson = _find_lesson(track, lesson_id)
            expected = _first_open_lesson(track)
            if expected is not None and expected["id"] != lesson["id"]:
                raise ValueError("正式投递必须按轨道顺序领取下一学习单元")
        else:
            lesson = _first_open_lesson(track)
            if lesson is None:
                raise ValueError("该学习轨道没有可正式投递的学习单元")

        existing_same_key = next(
            (
                record
                for record in state["learning"]["delivery_ledger"]
                if _delivery_has_idempotency_key(record, key_hash)
            ),
            None,
        )
        if existing_same_key is not None:
            if (
                existing_same_key.get("track_id") != track["id"]
                or existing_same_key.get("lesson_id") != lesson["id"]
                or existing_same_key.get("route_key_hash") != route_hash
            ):
                raise ValueError("幂等键已绑定到另一条学习轨道、单元或投递路由，不能复用")
            existing_track = _find_track(state, str(existing_same_key["track_id"]))
            existing_lesson = _find_lesson(existing_track, str(existing_same_key["lesson_id"]))
            if existing_same_key.get("state") == "accepted":
                return _delivery_details(
                    existing_same_key,
                    existing_track,
                    existing_lesson,
                    disposition="already_accepted",
                    should_send=False,
                )
            if existing_same_key.get("state") in {"prepared", "dispatching", "unknown"}:
                if existing_same_key.get("state") == "prepared" and _delivery_is_expired(existing_same_key):
                    existing_same_key["state"] = "unknown"
                    existing_lesson["delivery_status"] = "unknown"
                    existing_same_key["updated_at"] = _now()
                    existing_lesson["updated_at"] = _now()
                return _delivery_details(
                    existing_same_key,
                    existing_track,
                    existing_lesson,
                    disposition="needs_transport_reconcile",
                    should_send=False,
                )
            if existing_same_key.get("state") == "claimed" and not _delivery_is_expired(existing_same_key):
                return _delivery_details(
                    existing_same_key,
                    existing_track,
                    existing_lesson,
                    disposition="already_claimed",
                    should_send=False,
                )
            # An expired unprepared claim or a retryable failure can safely reuse
            # the same delivery ID but receives a fresh, transient claim token.
            token = _reclaim_delivery(
                existing_same_key,
                existing_lesson,
                key_hash=key_hash,
                route_key=route_hash,
                slot_key=slot_hash,
                lease_seconds=lease_seconds,
            )
            return _delivery_details(
                existing_same_key,
                existing_track,
                existing_lesson,
                disposition="reclaimed",
                should_send=True,
                claim_token=token,
            )

        # A scheduler retry normally has a new run key and slot. Preserve the
        # original delivery ID for the same lesson and route, rather than
        # creating a second ledger record that could duplicate the content.
        existing_retry = next(
            (
                record
                for record in reversed(state["learning"]["delivery_ledger"])
                if record.get("track_id") == track["id"]
                and record.get("lesson_id") == lesson["id"]
                and record.get("route_key_hash") == route_hash
                and record.get("state") == "failed_retryable"
            ),
            None,
        )
        if existing_retry is not None:
            token = _reclaim_delivery(
                existing_retry,
                lesson,
                key_hash=key_hash,
                route_key=route_hash,
                slot_key=slot_hash,
                lease_seconds=lease_seconds,
            )
            return _delivery_details(
                existing_retry,
                track,
                lesson,
                disposition="reclaimed",
                should_send=True,
                claim_token=token,
            )

        existing_slot = next(
            (
                record
                for record in state["learning"]["delivery_ledger"]
                if record.get("route_key_hash") == route_hash
                and record.get("slot_key_hash") == slot_hash
                and record.get("state") not in {"failed_retryable", "cancelled"}
            ),
            None,
        )
        if existing_slot is not None:
            slot_track = _find_track(state, str(existing_slot["track_id"]))
            slot_lesson = _find_lesson(slot_track, str(existing_slot["lesson_id"]))
            return _delivery_details(
                existing_slot,
                slot_track,
                slot_lesson,
                disposition="slot_taken",
                should_send=False,
            )

        accepted = _delivery_for_lesson(state, track["id"], lesson["id"])
        if accepted is not None:
            return _delivery_details(
                accepted,
                track,
                lesson,
                disposition="lesson_already_accepted",
                should_send=False,
            )
        if lesson.get("delivery_status") in {"prepared", "dispatching", "unknown"}:
            return {
                "disposition": "lesson_needs_transport_reconcile",
                "should_send": False,
                "track": _track_public_summary(track),
                "lesson": _lesson_public_summary(lesson),
            }
        if lesson.get("delivery_status") == "claimed":
            return {
                "disposition": "lesson_already_claimed",
                "should_send": False,
                "track": _track_public_summary(track),
                "lesson": _lesson_public_summary(lesson),
            }
        if _lesson_is_terminal(lesson):
            raise ValueError("该学习单元已结束，不能作为新的正式投递重新领取")

        token = secrets.token_urlsafe(24)
        now = _now()
        delivery = {
            "id": _new_id("delivery", f"{track['id']}-{lesson['id']}-{cleaned_slot}"),
            "idempotency_key_hash": key_hash,
            "idempotency_key_hashes": [key_hash],
            "route_key_hash": route_hash,
            "slot_key_hash": slot_hash,
            "scheduled_local_date": _shanghai_date(),
            "track_id": track["id"],
            "lesson_id": lesson["id"],
            "source_revision": _track_source(track)["source_revision"],
            "state": "claimed",
            "attempt": 1,
            "claim_token_hash": _hash(token),
            "lease_expires_at": _lease_expiration(lease_seconds),
            "content_sha256": "",
            "provider_message_id_hash": "",
            "created_at": now,
            "updated_at": now,
        }
        state["learning"]["delivery_ledger"].append(delivery)
        lesson["delivery_status"] = "claimed"
        lesson["updated_at"] = now
        return _delivery_details(
            delivery,
            track,
            lesson,
            disposition="claimed",
            should_send=True,
            claim_token=token,
        )

    return _mutate_state(root, mutate)


def _verify_delivery_token(delivery: dict[str, Any], claim_token: str) -> None:
    if not secrets.compare_digest(str(delivery.get("claim_token_hash") or ""), _hash(claim_token)):
        raise ValueError("投递领取令牌无效或已过期")


# These state transitions intentionally have no CLI command. A template agent
# cannot attest that WeChat accepted a message. A future platform-owned outbox
# may call private helpers after it verifies a channel receipt.
def _record_delivery_prepared_from_verified_sender(
    *,
    delivery_id: str,
    claim_token: str,
    content_sha256: str,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Record that a validated draft exists, without claiming channel success."""
    _platform_delivery_lifecycle_unavailable()
    normalized_content_hash = _normalize_sha256("内容哈希", content_sha256)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        delivery = _find_delivery(state, delivery_id)
        track = _find_track(state, str(delivery["track_id"]))
        lesson = _find_lesson(track, str(delivery["lesson_id"]))
        if delivery.get("state") == "accepted":
            return _delivery_details(delivery, track, lesson, disposition="already_accepted", should_send=False)
        if delivery.get("state") != "claimed":
            raise ValueError("只有已领取的投递记录可以写入已准备状态")
        if _delivery_is_expired(delivery):
            raise ValueError("投递领取租约已过期，请重新领取，不能继续发送")
        _verify_delivery_token(delivery, claim_token)
        delivery.update(
            {
                "state": "prepared",
                "content_sha256": normalized_content_hash,
                "updated_at": _now(),
            }
        )
        lesson["delivery_status"] = "prepared"
        lesson["updated_at"] = _now()
        return _delivery_details(delivery, track, lesson, disposition="prepared", should_send=True)

    return _mutate_state(root, mutate)


def _begin_delivery_send_from_verified_sender(
    *,
    delivery_id: str,
    claim_token: str,
    content_sha256: str,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Move to dispatching immediately before a real channel send."""
    _platform_delivery_lifecycle_unavailable()
    normalized_content_hash = _normalize_sha256("内容哈希", content_sha256)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        delivery = _find_delivery(state, delivery_id)
        track = _find_track(state, str(delivery["track_id"]))
        lesson = _find_lesson(track, str(delivery["lesson_id"]))
        if delivery.get("state") == "accepted":
            return _delivery_details(delivery, track, lesson, disposition="already_accepted", should_send=False)
        if delivery.get("state") not in {"claimed", "prepared"}:
            raise ValueError("投递记录当前不能开始发送")
        if _delivery_is_expired(delivery):
            raise ValueError("投递领取租约已过期，请重新领取，不能开始发送")
        _verify_delivery_token(delivery, claim_token)
        delivery.update(
            {
                "state": "dispatching",
                "content_sha256": normalized_content_hash,
                "updated_at": _now(),
            }
        )
        lesson["delivery_status"] = "dispatching"
        lesson["updated_at"] = _now()
        return _delivery_details(delivery, track, lesson, disposition="dispatching", should_send=True)

    return _mutate_state(root, mutate)


def _acknowledge_delivery_from_verified_sender(
    *,
    delivery_id: str,
    claim_token: str,
    provider_message_id: str,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Accept a real, positive channel receipt and unlock the next lesson."""
    _platform_delivery_lifecycle_unavailable()
    cleaned_provider_id = _require_clean("通道回执 ID", provider_message_id, max_length=512)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        delivery = _find_delivery(state, delivery_id)
        track = _find_track(state, str(delivery["track_id"]))
        lesson = _find_lesson(track, str(delivery["lesson_id"]))
        if delivery.get("state") == "accepted":
            return _delivery_details(delivery, track, lesson, disposition="already_accepted", should_send=False)
        if delivery.get("state") != "dispatching":
            raise ValueError("只有通道发送中的投递记录可以确认回执")
        _verify_delivery_token(delivery, claim_token)
        now = _now()
        delivery.update(
            {
                "state": "accepted",
                "provider_message_id_hash": _hash(cleaned_provider_id),
                "updated_at": now,
            }
        )
        lesson.update(
            {
                "delivery_status": "accepted",
                "updated_at": now,
            }
        )
        track["updated_at"] = now
        return _delivery_details(delivery, track, lesson, disposition="accepted", should_send=False)

    return _mutate_state(root, mutate)


def _fail_delivery_from_verified_sender(
    *,
    delivery_id: str,
    claim_token: str,
    kind: str,
    error_code: str,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _platform_delivery_lifecycle_unavailable()
    if kind not in {"retryable", "unknown"}:
        raise ValueError("投递失败类型必须为 retryable 或 unknown")
    cleaned_error = _optional_clean("失败码", error_code, fallback="unspecified", max_length=120)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        delivery = _find_delivery(state, delivery_id)
        track = _find_track(state, str(delivery["track_id"]))
        lesson = _find_lesson(track, str(delivery["lesson_id"]))
        if delivery.get("state") == "accepted":
            raise ValueError("已确认送达的投递记录不能改为失败")
        _verify_delivery_token(delivery, claim_token)
        next_state = "failed_retryable" if kind == "retryable" else "unknown"
        now = _now()
        delivery.update({"state": next_state, "error_code": cleaned_error, "updated_at": now})
        lesson["delivery_status"] = next_state
        lesson["updated_at"] = now
        return _delivery_details(
            delivery,
            track,
            lesson,
            disposition=next_state,
            should_send=False,
        )

    return _mutate_state(root, mutate)


def _recover_stale_deliveries_for_platform(
    *,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Recover only unprepared claims; a send-in-progress state remains unknown."""
    _platform_delivery_lifecycle_unavailable()

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        recovered: list[str] = []
        reconciled: list[str] = []
        for delivery in state["learning"]["delivery_ledger"]:
            if not _delivery_is_expired(delivery):
                continue
            if delivery.get("state") not in {"claimed", "prepared", "dispatching"}:
                continue
            track = _find_track(state, str(delivery["track_id"]))
            lesson = _find_lesson(track, str(delivery["lesson_id"]))
            now = _now()
            if delivery.get("state") == "claimed":
                delivery.update({"state": "failed_retryable", "updated_at": now, "error_code": "lease_expired_before_send"})
                lesson["delivery_status"] = "failed_retryable"
                recovered.append(str(delivery["id"]))
            else:
                delivery.update({"state": "unknown", "updated_at": now, "error_code": "transport_receipt_unknown"})
                lesson["delivery_status"] = "unknown"
                reconciled.append(str(delivery["id"]))
            lesson["updated_at"] = now
        return {
            "recovered_retryable_delivery_ids": recovered,
            "needs_transport_reconcile_delivery_ids": reconciled,
        }

    return _mutate_state(root, mutate)


def preview_track_migration(
    *,
    track_id: str,
    publisher: str,
    version: str,
    source_url: str,
    source_revision: str,
    root: Path = PACKAGE_ROOT,
) -> dict[str, Any]:
    state = load_state(root)
    track = _find_track(state, track_id)
    new_source = {
        "publisher": _require_clean("发布机构", publisher),
        "version": _require_clean("指南新版本", version),
        "url": _clean_url("权威来源", source_url),
        "source_revision": _require_clean("来源修订标识", source_revision),
    }
    progress = _track_progress(track)
    unresolved = [
        lesson["ordinal"]
        for lesson in track.get("lessons", [])
        if lesson.get("delivery_status") not in TERMINAL_LESSON_STATES
    ]
    return {
        "preview_only": True,
        "old_track": _track_public_summary(track),
        "candidate_source": new_source,
        "impact": {
            "delivered_or_legacy_units_kept_on_old_track": progress["delivered"],
            "unresolved_unit_ordinals": unresolved,
            "requires_new_lessons": True,
            "rule": "不会静默覆盖旧版本、旧学习单元或既有投递账本。",
        },
        "next_action": "用户确认后，创建保留旧轨道历史的新版本草稿轨道，再重新核验并规划章节。",
    }


def migrate_track(
    *,
    track_id: str,
    publisher: str,
    version: str,
    source_url: str,
    source_revision: str,
    new_track_id: str,
    confirm: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not confirm:
        raise ValueError("迁移到新的指南版本必须显式确认")
    cleaned_publisher = _require_clean("发布机构", publisher)
    cleaned_version = _require_clean("指南新版本", version)
    cleaned_url = _clean_url("权威来源", source_url)
    cleaned_revision = _require_clean("来源修订标识", source_revision)

    def mutate(state: dict[str, Any]) -> dict[str, Any]:
        old_track = _find_track(state, track_id)
        if old_track.get("status") == "superseded":
            raise ValueError("该轨道已经迁移；请查看其后继轨道")
        new_id = _normalize_id(
            "新学习轨道 ID",
            new_track_id,
            prefix="track",
            fallback_label=f"{old_track['label']}-{cleaned_version}",
        )
        if _find_by_id(state["learning"]["tracks"], new_id) is not None:
            raise ValueError("新学习轨道 ID 已存在")
        now = _now()
        new_track = {
            "id": new_id,
            "kind": old_track.get("kind", "guideline"),
            "label": old_track.get("label"),
            "goal_ids": list(old_track.get("goal_ids") or []),
            "status": "draft",
            "plan_status": "needs_planning",
            "source": {
                "document_key": _hash(
                    f"{old_track.get('label')}|{cleaned_publisher}|{cleaned_version}|{cleaned_url}|{cleaned_revision}"
                ),
                "title": old_track.get("label"),
                "publisher": cleaned_publisher,
                "version": cleaned_version,
                "source_revision": cleaned_revision,
                "url": cleaned_url,
                "verification_status": "verified",
                "verified_at": now,
            },
            "lessons": [],
            "created_at": now,
            "updated_at": now,
            "supersedes_track_id": old_track["id"],
            "migration_note": "经用户确认创建；旧轨道、章节和投递账本保留不覆写。",
        }
        old_track["status"] = "superseded"
        old_track["superseded_by_track_id"] = new_id
        old_track["updated_at"] = now
        state["learning"]["tracks"].append(new_track)
        state["learning"]["migration"]["history"].append(
            {
                "at": now,
                "kind": "source_version_migration",
                "from_track_id": old_track["id"],
                "to_track_id": new_id,
                "old_source_revision": _track_source(old_track).get("source_revision"),
                "new_source_revision": cleaned_revision,
            }
        )
        return {
            "old_track_id": old_track["id"],
            "new_track": _track_public_summary(new_track),
            "next_action": "为新轨道保存章节单元计划后，用户确认启用。",
        }

    return _mutate_state(root, mutate)


def set_guideline(
    *,
    title: str,
    publisher: str,
    source_url: str,
    total_days: int,
    current_day: int,
    status: str,
    root: Path = PACKAGE_ROOT,
) -> dict[str, Any]:
    """Compatibility bridge for v1 callers; it never creates a send receipt."""
    if total_days < 1 or total_days > 14:
        raise ValueError("计划总天数必须在 1-14 天之间")
    if current_day < 0 or current_day > total_days:
        raise ValueError("当前进度必须在 0 到计划总天数之间")
    cleaned_title = _require_clean("指南名称", title)
    cleaned_publisher = _require_clean("发布机构", publisher)
    cleaned_url = _clean_url("权威来源", source_url)

    def mutate(state: dict[str, Any]) -> None:
        state["current_guideline"].update(
            {
                "title": cleaned_title,
                "publisher": cleaned_publisher,
                "source_url": cleaned_url,
                "total_days": total_days,
                "current_day": current_day,
                "status": status,
            }
        )
        # Mark as not imported so the v1 projection is migrated under the same
        # locked write, with a re-plan requirement instead of unsafe new lessons.
        state["learning"]["migration"]["legacy_state_detected"] = True
        state["learning"]["migration"]["legacy_v1_current_guideline_imported"] = False
        _migrate_legacy_state(state)

    state, _ = _mutate_state(root, mutate)
    return state


def advance_guideline(*, current_day: int | None, increment: int, root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    del current_day, increment, root
    raise ValueError(
        "guideline-advance 已停用：生成内容不代表微信已送达。只有平台拥有的投递服务"
        "在验证真实通道回执后，才能确认送达并推进学习单元。"
    )


def clear_profile(*, confirm: bool, root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    if not confirm:
        raise ValueError("清除档案必须显式确认")
    with _state_lock(root):
        state = _deep_default_state()
        state["privacy"]["deletion_status"] = "已清除"
        _touch_state(state)
        _write_state_unlocked(state, root)
    return state


def state_migrate(
    *,
    confirm: bool,
    dry_run: bool,
    root: Path = PACKAGE_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with _state_lock(root):
        state = _read_state_unlocked(root)
        changes = _migrate_legacy_state(state)
        details = {"dry_run": dry_run, "changes": changes, "will_write": bool(changes and not dry_run)}
        if dry_run:
            _refresh_legacy_guideline_projection(state)
            return state, details
        if changes and not confirm:
            raise ValueError("状态迁移会写入新的学习轨道；请使用 --confirm true")
        if changes:
            _touch_state(state)
            _write_state_unlocked(state, root)
        return state, details


def render_user_text(state: dict[str, Any]) -> str:
    profile = state["profile"]
    derived = state["derived"]
    learning_diagnosis = state["learning_diagnosis"]
    subscriptions = state["subscriptions"]
    privacy = state["privacy"]
    learning = state["learning"]
    consent = "已确认（仅用于学习订阅配置）" if profile.get("consent_confirmed") else "待确认"
    active_tracks = [track for track in learning["tracks"] if track.get("status") == "active"]
    active_goals = [goal for goal in learning["goals"] if goal.get("status") == "active"]

    if active_goals:
        goal_lines = "\n".join(
            f"- {goal.get('label')}（{goal.get('kind')}；每日 {goal.get('daily_minutes')} 分钟；"
            f"目标日期：{goal.get('target_date') or '未设定'}）"
            for goal in active_goals
        )
    else:
        goal_lines = "- 暂无已保存的学习目标"

    if active_tracks:
        track_lines: list[str] = []
        for track in active_tracks:
            source = _track_source(track)
            progress = _track_progress(track)
            next_lesson = _first_open_lesson(track)
            next_label = (
                f"学习单元 {next_lesson.get('ordinal')}/{progress['total']}：{next_lesson.get('title')}"
                if next_lesson
                else "无待投递学习单元"
            )
            track_lines.append(
                f"- {source.get('title')}（{source.get('version')}；{source.get('publisher')}）\n"
                f"  - 计划单元：{progress['total']}；"
                f"用户标记掌握：{progress['mastered']}/{progress['total']}\n"
                f"  - 下一单元：{next_label}\n"
                f"  - 来源：{source.get('url') or '待核验'}"
            )
        track_text = "\n".join(track_lines)
    else:
        track_text = "- 暂无已启用的学习轨道；预览、诊断和普通通用任务均不需要创建轨道。"

    return f"""---
summary: "基层医生学习与通用助手学习档案（v2）"
read_when:
  - 医生登记
  - 学习目标与学习轨道
  - 指南学习诊断
  - 专业指南更新提醒
  - 地区医保政策变化学习
---

# 基层医生学习与通用助手学习档案

本文件由 scripts/clinical_profile.py 根据结构化档案自动生成。不得手动编辑；登记、学习目标、轨道、学习单元和学习诊断摘要变更必须调用脚本。正式投递状态与通道回执由平台服务保存，不写入本文件。

本文件只保存用户明确同意或明确要求保存的个性化医学学习最小信息。普通通用任务不应读取或写入本文件。不得写入患者姓名、手机号、身份证号、病历号、影像号、处方、检查报告或其他患者个人信息。

## 个性化医学学习登记

- 登记同意：{consent}
- 称谓：{profile.get("display_name") or "待确认"}
- 地区：{profile.get("region") or "待确认"}
- 医院：{profile.get("hospital") or "待确认"}
- 科室：{profile.get("department") or "待确认"}
- 职称：{profile.get("title") or "待确认"}

## 学习订阅识别

- 科室系统：{derived.get("department_system") or "待识别"}
- 亚专业：{derived.get("specialty") or "待识别"}
- 职称学习深度：{derived.get("learning_depth") or "待识别"}
- 地区医保关注范围：{derived.get("insurance_scope") or "待识别"}
- 医院能力边界：{derived.get("hospital_boundary") or DEFAULT_STATE["derived"]["hospital_boundary"]}

## 已保存学习目标

{goal_lines}

## 已启用学习轨道

{track_text}

轨道只记录已核验的指南版本和固定学习单元。预览、学习地图、学习诊断和小测不创建正式投递账本、不推进进度。正式送达事实只由平台通道回执确认，且不等于已掌握或临床胜任；学习掌握状态只能由用户明确更新。

## 最近一次指南学习诊断

- 状态：{learning_diagnosis.get("status") or "not_started"}
- 学习目标：{learning_diagnosis.get("goal") or "待设定"}
- 关联指南：{learning_diagnosis.get("guideline_title") or "待选择"}
- 权威来源：{learning_diagnosis.get("source_url") or "待核验"}
- 学习自评：{learning_diagnosis.get("self_assessed_level") or "not_assessed"}
- 每日可投入时间：{learning_diagnosis.get("available_minutes_per_day") or "待设定"} 分钟
- 优先学习主题：{'；'.join(learning_diagnosis.get("priority_topics") or []) or "待诊断"}
- 建议起点：{learning_diagnosis.get("recommended_start") or "待诊断"}
- 隐私规则：只保存用户明确要求保存的摘要；不保存原始答题过程、课程正文、真实病例或患者信息。

## 订阅任务状态

- 每日指南连续学习：{subscriptions.get("daily_guideline_learning") or "待绑定微信通道"}
- 专业指南更新提醒：{subscriptions.get("guideline_update_reminder") or "待绑定微信通道"}
- 地区医保政策变化学习：{subscriptions.get("insurance_policy_learning") or "待绑定微信通道"}
- 默认推送通道：{subscriptions.get("default_channel") or "微信（内部 channel type: weixin）"}
- 微信绑定状态：{"已保存（绑定标识未显示）" if subscriptions.get("weixin_session_key") not in {"", "待绑定"} else "待绑定"}

## 隐私与停用

- 信息用途：{privacy.get("purpose") or DEFAULT_STATE["privacy"]["purpose"]}
- 最小化原则：{privacy.get("minimization") or DEFAULT_STATE["privacy"]["minimization"]}
- 删除状态：{privacy.get("deletion_status") or "未申请删除"}
"""


def render_user_md(state: dict[str, Any], root: Path = PACKAGE_ROOT) -> None:
    _atomic_write(user_path(root), render_user_text(state))


def _parse_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "已确认", "同意"}:
        return True
    if normalized in {"false", "0", "no", "n", "未确认", "不同意"}:
        return False
    raise argparse.ArgumentTypeError("必须是 true/false")


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Remove channel and delivery internals from agent-visible script output."""
    public = copy.deepcopy(state)
    subscriptions = public.get("subscriptions")
    if isinstance(subscriptions, dict) and subscriptions.get("weixin_session_key") not in {"", "待绑定"}:
        subscriptions["weixin_session_key"] = "[已隐藏]"
    learning = public.get("learning")
    if isinstance(learning, dict):
        learning.pop("delivery_ledger", None)
    return public


def _ok(state: dict[str, Any], action: str, details: dict[str, Any] | None = None) -> int:
    payload: dict[str, Any] = {
        "ok": True,
        "action": action,
        "profile_complete": bool(
            state["profile"].get("consent_confirmed")
            and state["profile"].get("display_name")
            and state["profile"].get("region")
            and state["profile"].get("hospital")
            and state["profile"].get("department")
            and state["profile"].get("title")
        ),
        "state_revision": state.get("revision"),
        "state": _public_state(state),
    }
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _add_goal_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--label", required=True)
    parser.add_argument("--kind", choices=GOAL_KINDS, default="custom")
    parser.add_argument("--daily-minutes", required=True, type=int)
    parser.add_argument("--target-date", default="")
    parser.add_argument("--priority", type=int, default=50)
    parser.add_argument("--status", choices=GOAL_STATUSES, default="active")
    parser.add_argument("--goal-id", default="")
    parser.add_argument("--confirm", required=True, type=_parse_bool)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage clinical learning profile state.")
    sub = parser.add_subparsers(dest="command", required=True)

    get = sub.add_parser("get", help="Print the current structured profile.")
    get.add_argument("--format", choices=("json", "markdown"), default="json")

    migrate = sub.add_parser("state-migrate", help="Preview or persist v1 to v2 state migration.")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--confirm", type=_parse_bool, default=False)

    register = sub.add_parser("register", help="Register or update the 5 doctor fields.")
    register.add_argument("--display-name", required=True)
    register.add_argument("--region", required=True)
    register.add_argument("--hospital", required=True)
    register.add_argument("--department", required=True)
    register.add_argument("--title", required=True)
    register.add_argument("--consent-confirmed", required=True, type=_parse_bool)

    guideline_set = sub.add_parser("guideline-set", help="Legacy compatibility bridge; creates a v2 re-plan requirement.")
    guideline_set.add_argument("--title", required=True)
    guideline_set.add_argument("--publisher", required=True)
    guideline_set.add_argument("--source-url", required=True)
    guideline_set.add_argument("--total-days", required=True, type=int)
    guideline_set.add_argument("--current-day", type=int, default=0)
    guideline_set.add_argument("--status", choices=("not_selected", "in_progress", "completed"), default="in_progress")

    guideline_advance = sub.add_parser("guideline-advance", help="Deprecated; use delivery acknowledgements.")
    guideline_advance.add_argument("--current-day", type=int)
    guideline_advance.add_argument("--increment", type=int, default=1)

    learning_diagnosis_save = sub.add_parser(
        "learning-diagnosis-save",
        help="Save a user-confirmed, minimal summary of a guideline learning diagnostic.",
    )
    learning_diagnosis_save.add_argument("--goal", required=True)
    learning_diagnosis_save.add_argument("--goal-id", default="")
    learning_diagnosis_save.add_argument("--guideline-title", default="")
    learning_diagnosis_save.add_argument("--source-url", default="")
    learning_diagnosis_save.add_argument(
        "--self-assessed-level",
        required=True,
        choices=LEARNING_DIAGNOSIS_LEVELS,
    )
    learning_diagnosis_save.add_argument("--available-minutes-per-day", required=True, type=int)
    learning_diagnosis_save.add_argument("--priority-topic", action="append", default=[])
    learning_diagnosis_save.add_argument("--recommended-start", required=True)
    learning_diagnosis_save.add_argument("--confirm", required=True, type=_parse_bool)

    learning_diagnosis_clear = sub.add_parser(
        "learning-diagnosis-clear",
        help="Clear the saved learning-diagnostic summary without deleting the profile.",
    )
    learning_diagnosis_clear.add_argument("--confirm", required=True, type=_parse_bool)

    goal_save = sub.add_parser(
        "learning-goal-save",
        aliases=["goal-create"],
        help="Create or update one user-confirmed learning goal.",
    )
    _add_goal_arguments(goal_save)

    track_create = sub.add_parser(
        "learning-track-create",
        aliases=["track-create"],
        help="Create a verified guideline track as a draft.",
    )
    track_create.add_argument("--label", required=True)
    track_create.add_argument("--publisher", required=True)
    track_create.add_argument("--version", required=True)
    track_create.add_argument("--source-url", required=True)
    track_create.add_argument("--source-revision", required=True)
    track_create.add_argument("--goal-id", action="append", default=[])
    track_create.add_argument("--track-id", default="")
    track_create.add_argument("--kind", default="guideline")
    track_create.add_argument("--confirm", required=True, type=_parse_bool)

    lessons_replace = sub.add_parser(
        "learning-track-lessons-replace",
        aliases=["track-lessons-replace"],
        help="Save a complete, immutable lesson plan and replace only pending units.",
    )
    lessons_replace.add_argument("--track-id", required=True)
    lessons_replace.add_argument("--lesson-json", action="append", default=[])
    lessons_replace.add_argument("--replace-pending", required=True, type=_parse_bool)
    lessons_replace.add_argument("--confirm", required=True, type=_parse_bool)

    track_activate = sub.add_parser(
        "learning-track-activate",
        aliases=["track-activate"],
        help="Activate a verified track with a complete lesson plan.",
    )
    track_activate.add_argument("--track-id", required=True)
    track_activate.add_argument("--confirm", required=True, type=_parse_bool)

    track_status_set = sub.add_parser(
        "learning-track-set-status",
        aliases=["track-set-status"],
        help="Pause or archive a track while retaining its history.",
    )
    track_status_set.add_argument("--track-id", required=True)
    track_status_set.add_argument("--status", required=True, choices=("paused", "archived"))
    track_status_set.add_argument("--confirm", required=True, type=_parse_bool)

    track_status = sub.add_parser(
        "learning-track-status",
        aliases=["track-status"],
        help="Show public goal and track progress without ledger secrets.",
    )
    track_status.add_argument("--track-id", default="")

    next_lesson = sub.add_parser(
        "learning-next-lesson",
        aliases=["next-lesson"],
        help="Preview the next lesson without writing a delivery ledger.",
    )
    next_lesson.add_argument("--track-id", default="")

    lesson_mark = sub.add_parser(
        "learning-lesson-mark",
        aliases=["lesson-mark"],
        help="Set a user-confirmed learning status; delivered does not mean mastered.",
    )
    lesson_mark.add_argument("--track-id", required=True)
    lesson_mark.add_argument("--lesson-id", required=True)
    lesson_mark.add_argument("--learning-status", required=True, choices=LESSON_LEARNING_STATUSES)
    lesson_mark.add_argument("--confirm", required=True, type=_parse_bool)

    migration_preview = sub.add_parser(
        "learning-track-migration-preview",
        aliases=["track-migration-preview"],
        help="Preview a source version migration without writing state.",
    )
    migration_preview.add_argument("--track-id", required=True)
    migration_preview.add_argument("--publisher", required=True)
    migration_preview.add_argument("--version", required=True)
    migration_preview.add_argument("--source-url", required=True)
    migration_preview.add_argument("--source-revision", required=True)

    track_migrate = sub.add_parser(
        "learning-track-migrate",
        aliases=["track-migrate"],
        help="Create a confirmed new-version draft and preserve the old track.",
    )
    track_migrate.add_argument("--track-id", required=True)
    track_migrate.add_argument("--publisher", required=True)
    track_migrate.add_argument("--version", required=True)
    track_migrate.add_argument("--source-url", required=True)
    track_migrate.add_argument("--source-revision", required=True)
    track_migrate.add_argument("--new-track-id", default="")
    track_migrate.add_argument("--confirm", required=True, type=_parse_bool)

    clear = sub.add_parser("clear", help="Clear profile and all learning state.")
    clear.add_argument("--confirm", required=True, type=_parse_bool)

    sub.add_parser("render-user", help="Regenerate USER.md from structured state.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "get":
            state = load_state()
            if args.format == "markdown":
                print(render_user_text(state))
                return 0
            return _ok(state, "get")
        if args.command == "state-migrate":
            state, details = state_migrate(confirm=args.confirm, dry_run=args.dry_run)
            return _ok(state, "state-migrate", details)
        if args.command == "register":
            return _ok(
                register_profile(
                    display_name=args.display_name,
                    region=args.region,
                    hospital=args.hospital,
                    department=args.department,
                    title=args.title,
                    consent_confirmed=args.consent_confirmed,
                ),
                "register",
            )
        if args.command == "guideline-set":
            return _ok(
                set_guideline(
                    title=args.title,
                    publisher=args.publisher,
                    source_url=args.source_url,
                    total_days=args.total_days,
                    current_day=args.current_day,
                    status=args.status,
                ),
                "guideline-set",
            )
        if args.command == "guideline-advance":
            return _ok(advance_guideline(current_day=args.current_day, increment=args.increment), "guideline-advance")
        if args.command == "learning-diagnosis-save":
            return _ok(
                save_learning_diagnosis(
                    goal=args.goal,
                    goal_id=args.goal_id,
                    guideline_title=args.guideline_title,
                    source_url=args.source_url,
                    self_assessed_level=args.self_assessed_level,
                    available_minutes_per_day=args.available_minutes_per_day,
                    priority_topics=args.priority_topic,
                    recommended_start=args.recommended_start,
                    confirm=args.confirm,
                ),
                "learning-diagnosis-save",
            )
        if args.command == "learning-diagnosis-clear":
            return _ok(clear_learning_diagnosis(confirm=args.confirm), "learning-diagnosis-clear")
        if args.command in {"learning-goal-save", "goal-create"}:
            state, details = save_learning_goal(
                label=args.label,
                kind=args.kind,
                daily_minutes=args.daily_minutes,
                target_date=args.target_date,
                priority=args.priority,
                status=args.status,
                goal_id=args.goal_id,
                confirm=args.confirm,
            )
            return _ok(state, "learning-goal-save", details)
        if args.command in {"learning-track-create", "track-create"}:
            state, details = create_learning_track(
                label=args.label,
                publisher=args.publisher,
                version=args.version,
                source_url=args.source_url,
                source_revision=args.source_revision,
                goal_ids=args.goal_id,
                track_id=args.track_id,
                kind=args.kind,
                confirm=args.confirm,
            )
            return _ok(state, "learning-track-create", details)
        if args.command in {"learning-track-lessons-replace", "track-lessons-replace"}:
            state, details = replace_track_lessons(
                track_id=args.track_id,
                lesson_jsons=args.lesson_json,
                replace_pending=args.replace_pending,
                confirm=args.confirm,
            )
            return _ok(state, "learning-track-lessons-replace", details)
        if args.command in {"learning-track-activate", "track-activate"}:
            state, details = activate_learning_track(
                track_id=args.track_id,
                confirm=args.confirm,
            )
            return _ok(state, "learning-track-activate", details)
        if args.command in {"learning-track-set-status", "track-set-status"}:
            state, details = set_learning_track_status(
                track_id=args.track_id,
                status=args.status,
                confirm=args.confirm,
            )
            return _ok(state, "learning-track-set-status", details)
        if args.command in {"learning-track-status", "track-status"}:
            state = load_state()
            return _ok(state, "learning-track-status", get_track_status(track_id=args.track_id))
        if args.command in {"learning-next-lesson", "next-lesson"}:
            state = load_state()
            return _ok(state, "learning-next-lesson", get_next_lesson(track_id=args.track_id))
        if args.command in {"learning-lesson-mark", "lesson-mark"}:
            state, details = mark_lesson_learning(
                track_id=args.track_id,
                lesson_id=args.lesson_id,
                learning_status=args.learning_status,
                confirm=args.confirm,
            )
            return _ok(state, "learning-lesson-mark", details)
        if args.command in {"learning-track-migration-preview", "track-migration-preview"}:
            state = load_state()
            details = preview_track_migration(
                track_id=args.track_id,
                publisher=args.publisher,
                version=args.version,
                source_url=args.source_url,
                source_revision=args.source_revision,
            )
            return _ok(state, "learning-track-migration-preview", details)
        if args.command in {"learning-track-migrate", "track-migrate"}:
            state, details = migrate_track(
                track_id=args.track_id,
                publisher=args.publisher,
                version=args.version,
                source_url=args.source_url,
                source_revision=args.source_revision,
                new_track_id=args.new_track_id,
                confirm=args.confirm,
            )
            return _ok(state, "learning-track-migrate", details)
        if args.command == "clear":
            return _ok(clear_profile(confirm=args.confirm), "clear")
        if args.command == "render-user":
            state = load_state()
            render_user_md(state)
            return _ok(state, "render-user")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
