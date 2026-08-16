"""MBTI personality type API — profiles, test, and per-agent persona apply.

Octop is multi-agent: the MBTI code lives on ``agents.persona_mbti`` /
``config_json["persona"]`` and is rendered into workspace ``SOUL.md`` on
agent reload.  The active agent is selected via ``X-Octop-Agent-Id``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from octop.api.common.agent import assert_agent_owner
from octop.api.deps import current_user, get_server
from octop.infra.agents.mbti_profiles import (
    MBTIProfile,
    get_all_profiles,
    get_profile,
)
from octop.infra.errors import ErrorCode, OctopError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mbti", tags=["mbti"])


# ---------------------------------------------------------------------------
# Helpers — agent resolution + config_json round-trip
# ---------------------------------------------------------------------------


def _resolve_agent_row(server: Any, user: Any, agent_id: str) -> Any:
    """Look up the agent row by id via AgentManager."""
    assert server.app_runtime is not None
    row = server.app_runtime.agent_registry.get_row(agent_id)
    if row is None:
        raise OctopError(ErrorCode.AGENT_NOT_FOUND, f"agent {agent_id} not found")
    assert_agent_owner(row, user)
    return row


def _parse_config(row: Any) -> dict[str, Any]:
    raw = row.config_json
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("agent %s has invalid config_json; treating as empty", row.agent_id)
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _persist_persona(server: Any, agent_id: str, row: Any, code: str) -> None:
    """Persist MBTI on the agent row and reload so ``SOUL.md`` is regenerated."""
    assert server.app_runtime is not None
    await server.app_runtime.agent_registry.apply_persona_mbti(agent_id, code)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DimensionsResponse(BaseModel):
    ei: list[Any] = Field(description="[pole, pct]")
    sn: list[Any] = Field(description="[pole, pct]")
    tf: list[Any] = Field(description="[pole, pct]")
    jp: list[Any] = Field(description="[pole, pct]")


class BehaviorResponse(BaseModel):
    answer_style: str
    casual_chat: str
    conflict: str
    creativity: str
    emotion: str
    planning: str
    answer_style_zh: str = ""
    casual_chat_zh: str = ""
    conflict_zh: str = ""
    creativity_zh: str = ""
    emotion_zh: str = ""
    planning_zh: str = ""


class MBTITypeResponse(BaseModel):
    code: str
    name_zh: str
    name_en: str
    nickname_zh: str
    summary_zh: str
    summary_en: str
    descriptors_zh: str
    descriptors_en: str
    dimensions: DimensionsResponse
    behavior: BehaviorResponse
    color: str
    symbol: str


def _profile_to_response(p: MBTIProfile) -> MBTITypeResponse:
    return MBTITypeResponse(
        code=p.code,
        name_zh=p.name_zh,
        name_en=p.name_en,
        nickname_zh=p.nickname_zh,
        summary_zh=p.summary_zh,
        summary_en=p.summary_en,
        descriptors_zh=p.descriptors_zh,
        descriptors_en=p.descriptors_en,
        dimensions=DimensionsResponse(
            ei=list(p.dimensions.ei),
            sn=list(p.dimensions.sn),
            tf=list(p.dimensions.tf),
            jp=list(p.dimensions.jp),
        ),
        behavior=BehaviorResponse(
            answer_style=p.behavior.answer_style,
            casual_chat=p.behavior.casual_chat,
            conflict=p.behavior.conflict,
            creativity=p.behavior.creativity,
            emotion=p.behavior.emotion,
            planning=p.behavior.planning,
            answer_style_zh=p.behavior.answer_style_zh,
            casual_chat_zh=p.behavior.casual_chat_zh,
            conflict_zh=p.behavior.conflict_zh,
            creativity_zh=p.behavior.creativity_zh,
            emotion_zh=p.behavior.emotion_zh,
            planning_zh=p.behavior.planning_zh,
        ),
        color=p.color,
        symbol=p.symbol,
    )


# ---------------------------------------------------------------------------
# GET /api/mbti/current — read persona from the active agent's config_json
# ---------------------------------------------------------------------------


class CurrentMBTIResponse(BaseModel):
    code: str = ""
    configured: bool = False


@router.get("/current", response_model=CurrentMBTIResponse)
async def get_current_mbti(
    x_octop_agent_id: str = Header(..., alias="X-Octop-Agent-Id"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> CurrentMBTIResponse:
    """Read the current MBTI type from the active agent's persisted config."""
    row = _resolve_agent_row(server, user, x_octop_agent_id)
    cfg = _parse_config(row)
    raw = row.persona_mbti or cfg.get("persona") or ""
    code = str(raw).upper() if isinstance(raw, str) else ""
    # Only expose codes that match a known profile to avoid leaking junk
    # left over from prior schemas.
    if code and get_profile(code) is None:
        code = ""
    return CurrentMBTIResponse(code=code, configured=bool(code))


# ---------------------------------------------------------------------------
# GET /api/mbti/types
# ---------------------------------------------------------------------------


@router.get("/types", response_model=list[MBTITypeResponse])
async def list_types(
    user: Any = Depends(current_user),
) -> list[MBTITypeResponse]:
    """List all 16 MBTI types."""
    return [_profile_to_response(p) for p in get_all_profiles()]


# ---------------------------------------------------------------------------
# GET /api/mbti/types/{code}
# ---------------------------------------------------------------------------


@router.get("/types/{code}", response_model=MBTITypeResponse)
async def get_type(
    code: str,
    user: Any = Depends(current_user),
) -> MBTITypeResponse:
    """Get details for a single MBTI type."""
    profile = get_profile(code)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown MBTI type: {code}")
    return _profile_to_response(profile)


# ---------------------------------------------------------------------------
# GET /api/mbti/preview/{code} — rendered persona template (legacy /api/personas)
# ---------------------------------------------------------------------------


@router.get("/preview/{code}")
async def get_persona_preview(
    code: str,
    user: Any = Depends(current_user),
) -> dict[str, Any]:
    """Render a persona markdown preview with the current user substituted."""
    from octop.infra.agents.persona import PersonaLoader

    loader = PersonaLoader()
    text = loader.render(
        mbti=None if code == "_default" else code,
        agent_name="Your Agent",
        user_display=user.label,
        custom="",
    )
    return {"code": code, "preview": text}


# ---------------------------------------------------------------------------
# Test questions (28 items — 7 per dimension, A/B forced choice)
# ---------------------------------------------------------------------------


class TestQuestion(BaseModel):
    id: int
    dimension: str  # "EI" | "SN" | "TF" | "JP"
    a_pole: str  # e.g. "E"
    b_pole: str  # e.g. "I"
    question_zh: str
    option_a_zh: str
    option_b_zh: str
    question_en: str
    option_a_en: str
    option_b_en: str


_QUESTIONS: list[TestQuestion] = [
    # ---- E/I (7 questions) ----
    TestQuestion(
        id=1,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="在社交活动后，你通常感到：",
        option_a_zh="充满活力，想继续交流",
        option_b_zh="需要独处来恢复精力",
        question_en="After a social event, you usually feel:",
        option_a_en="Energised and wanting to keep socialising",
        option_b_en="Drained and needing alone time to recharge",
    ),
    TestQuestion(
        id=2,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="面对新环境时，你更倾向于：",
        option_a_zh="主动与陌生人攀谈",
        option_b_zh="安静观察，等待合适时机",
        question_en="When entering a new environment, you tend to:",
        option_a_en="Initiate conversations with strangers",
        option_b_en="Observe quietly and wait for the right moment",
    ),
    TestQuestion(
        id=3,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="你更喜欢的工作方式是：",
        option_a_zh="团队讨论和头脑风暴",
        option_b_zh="独自深度思考",
        question_en="Your preferred working style is:",
        option_a_en="Team discussions and brainstorming",
        option_b_en="Deep thinking alone",
    ),
    TestQuestion(
        id=4,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="理想的周末是：",
        option_a_zh="和朋友聚会或参加活动",
        option_b_zh="在家读书、看剧或做自己的事",
        question_en="Your ideal weekend involves:",
        option_a_en="Going out with friends or attending events",
        option_b_en="Staying home reading, watching shows, or doing your own thing",
    ),
    TestQuestion(
        id=5,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="处理问题时，你倾向于：",
        option_a_zh="先和别人讨论，边说边想",
        option_b_zh="先自己想清楚，再和别人沟通",
        question_en="When solving problems, you tend to:",
        option_a_en="Talk it through with others, thinking out loud",
        option_b_en="Think it through yourself first, then communicate",
    ),
    TestQuestion(
        id=6,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="你的朋友圈通常是：",
        option_a_zh="广泛而多样，认识很多人",
        option_b_zh="小而深入，几个知心朋友",
        question_en="Your social circle is usually:",
        option_a_en="Wide and diverse, knowing many people",
        option_b_en="Small and deep, a few close friends",
    ),
    TestQuestion(
        id=7,
        dimension="EI",
        a_pole="E",
        b_pole="I",
        question_zh="在会议中，你更可能：",
        option_a_zh="积极发言，分享想法",
        option_b_zh="认真倾听，需要时再表达",
        question_en="In meetings, you are more likely to:",
        option_a_en="Speak up actively and share ideas",
        option_b_en="Listen carefully and speak when needed",
    ),
    # ---- S/N (7 questions) ----
    TestQuestion(
        id=8,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="学习新事物时，你更喜欢：",
        option_a_zh="从具体例子和实际操作开始",
        option_b_zh="先理解整体概念和理论框架",
        question_en="When learning something new, you prefer:",
        option_a_en="Starting with concrete examples and hands-on practice",
        option_b_en="Understanding the overall concept and theoretical framework first",
    ),
    TestQuestion(
        id=9,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="描述一件事时，你更倾向于：",
        option_a_zh="关注具体细节和实际发生的事",
        option_b_zh="描述整体印象和可能的含义",
        question_en="When describing something, you tend to:",
        option_a_en="Focus on specific details and what actually happened",
        option_b_en="Describe overall impressions and possible meanings",
    ),
    TestQuestion(
        id=10,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="你更信任：",
        option_a_zh="经过验证的经验和事实",
        option_b_zh="直觉和内心的感悟",
        question_en="You trust more:",
        option_a_en="Verified experience and facts",
        option_b_en="Intuition and inner insights",
    ),
    TestQuestion(
        id=11,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="在阅读时，你更被吸引的是：",
        option_a_zh="实用的操作指南和说明",
        option_b_zh="启发性的概念和隐喻",
        question_en="When reading, you are more drawn to:",
        option_a_en="Practical how-to guides and instructions",
        option_b_en="Inspirational concepts and metaphors",
    ),
    TestQuestion(
        id=12,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="你更欣赏的人是：",
        option_a_zh="脚踏实地、做事靠谱的人",
        option_b_zh="有远见、能提出新想法的人",
        question_en="You admire more someone who is:",
        option_a_en="Down-to-earth and dependable",
        option_b_en="Visionary and full of new ideas",
    ),
    TestQuestion(
        id=13,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="面对一个项目，你首先关注的是：",
        option_a_zh="当前需要做什么，具体步骤是什么",
        option_b_zh="这个项目最终要达到什么目标和愿景",
        question_en="When facing a project, you first focus on:",
        option_a_en="What needs to be done now and the specific steps",
        option_b_en="What the ultimate goal and vision should be",
    ),
    TestQuestion(
        id=14,
        dimension="SN",
        a_pole="S",
        b_pole="N",
        question_zh="你认为自己更像是：",
        option_a_zh="现实主义者",
        option_b_zh="想象力丰富的人",
        question_en="You consider yourself more of a:",
        option_a_en="Realist",
        option_b_en="Imaginative person",
    ),
    # ---- T/F (7 questions) ----
    TestQuestion(
        id=15,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="做重要决定时，你更依赖：",
        option_a_zh="逻辑分析和客观标准",
        option_b_zh="个人价值观和对他人的影响",
        question_en="When making important decisions, you rely more on:",
        option_a_en="Logical analysis and objective criteria",
        option_b_en="Personal values and impact on others",
    ),
    TestQuestion(
        id=16,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="当朋友向你倾诉烦恼时，你更倾向于：",
        option_a_zh="帮 ta 分析原因并提出解决方案",
        option_b_zh="先表达理解和共情，陪伴 ta",
        question_en="When a friend comes to you with a problem, you tend to:",
        option_a_en="Analyse the cause and suggest solutions",
        option_b_en="Express understanding and empathy first",
    ),
    TestQuestion(
        id=17,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="你更看重反馈中的：",
        option_a_zh="直接坦诚，即使有些尖锐",
        option_b_zh="措辞委婉，考虑对方感受",
        question_en="In feedback, you value more:",
        option_a_en="Direct honesty, even if a bit blunt",
        option_b_en="Tactful wording that considers feelings",
    ),
    TestQuestion(
        id=18,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="在团队中，你更关注：",
        option_a_zh="目标是否达成、效率是否最高",
        option_b_zh="团队氛围是否和谐、成员是否被尊重",
        question_en="In a team, you focus more on:",
        option_a_en="Whether goals are met and efficiency is maximised",
        option_b_en="Whether the atmosphere is harmonious and members feel respected",
    ),
    TestQuestion(
        id=19,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="评判一个方案时，你更看重：",
        option_a_zh="数据和逻辑推理",
        option_b_zh="人们的感受和接受程度",
        question_en="When evaluating a proposal, you weigh more:",
        option_a_en="Data and logical reasoning",
        option_b_en="How people feel about it and their acceptance",
    ),
    TestQuestion(
        id=20,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="别人评价你时，你更希望被认为是：",
        option_a_zh="聪明、能干、有逻辑",
        option_b_zh="善良、温暖、体贴",
        question_en="You would rather be seen as:",
        option_a_en="Smart, capable, and logical",
        option_b_en="Kind, warm, and considerate",
    ),
    TestQuestion(
        id=21,
        dimension="TF",
        a_pole="T",
        b_pole="F",
        question_zh="面对争议时，你倾向于：",
        option_a_zh="寻找客观事实来判断对错",
        option_b_zh="考虑每个人的立场和感受",
        question_en="When facing a controversy, you tend to:",
        option_a_en="Look for objective facts to judge right and wrong",
        option_b_en="Consider everyone's position and feelings",
    ),
    # ---- J/P (7 questions) ----
    TestQuestion(
        id=22,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="你更喜欢的生活方式是：",
        option_a_zh="有计划、有条理，按日程表行动",
        option_b_zh="灵活随性，保持开放和弹性",
        question_en="Your preferred lifestyle is:",
        option_a_en="Planned, organised, following a schedule",
        option_b_en="Flexible, spontaneous, keeping options open",
    ),
    TestQuestion(
        id=23,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="面对截止日期，你通常会：",
        option_a_zh="提前完成，留出缓冲时间",
        option_b_zh="在截止前才全力冲刺",
        question_en="When facing a deadline, you usually:",
        option_a_en="Finish early, leaving buffer time",
        option_b_en="Sprint at full speed near the deadline",
    ),
    TestQuestion(
        id=24,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="去旅行时，你更倾向于：",
        option_a_zh="详细规划行程和预订",
        option_b_zh="只定大方向，到了再说",
        question_en="When travelling, you prefer:",
        option_a_en="Detailed itinerary planning and bookings",
        option_b_en="Just setting a general direction and figuring it out on the go",
    ),
    TestQuestion(
        id=25,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="你的桌面或工作区域通常是：",
        option_a_zh="整洁有序，物品各归其位",
        option_b_zh="看似混乱但你能找到需要的东西",
        question_en="Your desk or workspace is usually:",
        option_a_en="Neat and organised, everything in its place",
        option_b_en="Seemingly messy but you can find what you need",
    ),
    TestQuestion(
        id=26,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="当计划突然改变时，你：",
        option_a_zh="感到不安，想尽快恢复秩序",
        option_b_zh="觉得无所谓，甚至有点兴奋",
        question_en="When plans suddenly change, you:",
        option_a_en="Feel uneasy and want to restore order quickly",
        option_b_en="Feel fine, maybe even a bit excited",
    ),
    TestQuestion(
        id=27,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="你做决定的速度通常是：",
        option_a_zh="快速做出决定并执行",
        option_b_zh="保持开放，收集更多信息再决定",
        question_en="Your decision-making speed is usually:",
        option_a_en="Quick to decide and execute",
        option_b_en="Staying open, gathering more information before deciding",
    ),
    TestQuestion(
        id=28,
        dimension="JP",
        a_pole="J",
        b_pole="P",
        question_zh="你更享受的过程是：",
        option_a_zh="完成任务打勾的满足感",
        option_b_zh="探索各种可能性的自由感",
        question_en="You enjoy more:",
        option_a_en="The satisfaction of checking off completed tasks",
        option_b_en="The freedom of exploring various possibilities",
    ),
]


# ---------------------------------------------------------------------------
# GET /api/mbti/test/questions
# ---------------------------------------------------------------------------


@router.get("/test/questions", response_model=list[TestQuestion])
async def get_test_questions(
    user: Any = Depends(current_user),
) -> list[TestQuestion]:
    """Return all 28 test questions."""
    return _QUESTIONS


# ---------------------------------------------------------------------------
# POST /api/mbti/test/submit
# ---------------------------------------------------------------------------


class TestSubmitRequest(BaseModel):
    answers: dict[str, str] = Field(
        description='Map of question_id (str) -> "A" or "B"',
    )
    auto_apply: bool = Field(default=False)
    language: str = Field(default="zh")


class TestResultResponse(BaseModel):
    code: str
    profile: MBTITypeResponse
    dimensions: DimensionsResponse
    applied: bool = False


def _score_answers(answers: dict[str, str]) -> tuple[str, dict[str, Any]]:
    """Score test answers and return (mbti_code, dimension_details)."""
    # Count votes per axis
    axis_counts: dict[str, dict[str, int]] = {
        "EI": {"E": 0, "I": 0},
        "SN": {"S": 0, "N": 0},
        "TF": {"T": 0, "F": 0},
        "JP": {"J": 0, "P": 0},
    }

    q_map = {str(q.id): q for q in _QUESTIONS}
    answered = 0

    for qid, choice in answers.items():
        q = q_map.get(qid)
        if q is None:
            continue
        choice_upper = choice.upper()
        if choice_upper == "A":
            axis_counts[q.dimension][q.a_pole] += 1
            answered += 1
        elif choice_upper == "B":
            axis_counts[q.dimension][q.b_pole] += 1
            answered += 1

    if answered < 20:
        raise HTTPException(
            status_code=400,
            detail=f"Too few answers ({answered}/28). At least 20 required.",
        )

    # Calculate result
    code = ""
    dim_result = {}
    for axis_key, poles in [
        ("EI", ("E", "I")),
        ("SN", ("S", "N")),
        ("TF", ("T", "F")),
        ("JP", ("J", "P")),
    ]:
        a_count = axis_counts[axis_key][poles[0]]
        b_count = axis_counts[axis_key][poles[1]]
        total = a_count + b_count
        if total == 0:
            # No answers for this dimension — default to first pole
            dominant = poles[0]
            pct = 50
        else:
            dominant = poles[0] if a_count >= b_count else poles[1]
            dominant_count = max(a_count, b_count)
            pct = round(50 + dominant_count / total * 35)
            pct = max(50, min(85, pct))

        code += dominant
        dim_result[axis_key] = (dominant, pct)

    return code, dim_result


@router.post("/test/submit", response_model=TestResultResponse)
async def submit_test(
    req: TestSubmitRequest,
    x_octop_agent_id: str | None = Header(None, alias="X-Octop-Agent-Id"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> TestResultResponse:
    """Score test answers and return the MBTI result.

    When ``auto_apply`` is true, the resulting code is also written to the
    active agent's ``config_json.persona``. The header is required only in
    that case; without ``auto_apply`` the endpoint is read-only and works
    without an agent context.
    """
    code, dim_result = _score_answers(req.answers)

    profile = get_profile(code)
    if profile is None:
        raise HTTPException(status_code=500, detail=f"Profile not found for {code}")

    applied = False
    if req.auto_apply:
        if not x_octop_agent_id:
            raise HTTPException(
                status_code=400,
                detail="X-Octop-Agent-Id header required when auto_apply is true",
            )
        row = _resolve_agent_row(server, user, x_octop_agent_id)
        try:
            await _persist_persona(server, x_octop_agent_id, row, code)
            applied = True
        except Exception:
            logger.exception("Failed to auto-apply MBTI %s to agent %s", code, x_octop_agent_id)
            applied = False

    dims = DimensionsResponse(
        ei=list(dim_result["EI"]),
        sn=list(dim_result["SN"]),
        tf=list(dim_result["TF"]),
        jp=list(dim_result["JP"]),
    )

    return TestResultResponse(
        code=code,
        profile=_profile_to_response(profile),
        dimensions=dims,
        applied=applied,
    )


# ---------------------------------------------------------------------------
# POST /api/mbti/apply
# ---------------------------------------------------------------------------


class ApplyRequest(BaseModel):
    code: str
    language: str = Field(default="zh")


class ApplyResponse(BaseModel):
    success: bool
    code: str
    message: str = ""


@router.post("/apply", response_model=ApplyResponse)
async def apply_type(
    req: ApplyRequest,
    x_octop_agent_id: str = Header(..., alias="X-Octop-Agent-Id"),
    user: Any = Depends(current_user),
    server: Any = Depends(get_server),
) -> ApplyResponse:
    """Apply a specific MBTI type to the active agent's persona."""
    code = req.code.upper()
    profile = get_profile(code)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Unknown MBTI type: {code}")

    row = _resolve_agent_row(server, user, x_octop_agent_id)
    try:
        await _persist_persona(server, x_octop_agent_id, row, code)
    except Exception as exc:
        logger.exception("Failed to apply MBTI %s to agent %s", code, x_octop_agent_id)
        raise HTTPException(status_code=500, detail="Failed to persist persona") from exc

    return ApplyResponse(
        success=True,
        code=code,
        message=f"Applied {code} ({profile.name_en}) to agent persona",
    )
