"""Render agent persona system prompt from MBTI profiles or the built-in default template."""

from __future__ import annotations

from octop.infra.agents.persona.mbti_profiles import MBTIProfile, get_profile
from octop.infra.utils.locale import DEFAULT_LOCALE, Locale

_DEFAULT_PERSONA_TEMPLATE = """\
# Persona: Default

You are {agent_name}, an attentive AI assistant working with {user_display}.

Tone: warm, direct, and competent. Prefer concrete answers over hedging.
Match the user's level of detail. When uncertain, say so and propose how
to find out.

Reply in the user's language.

{custom}
"""

_DEFAULT_PERSONA_TEMPLATE_ZH = """\
# 人格：默认

你是 {agent_name}，一位细心的 AI 助手，正在协助 {user_display}。

语气：温暖、直接、专业。优先给出具体答案，避免含糊其辞。
根据用户需要的详细程度作答。不确定时如实说明，并提出查明的办法。

默认使用简体中文回复，包括执行过程中的说明和最终答复；如果用户使用其他语言交流，则使用用户的语言回复。

{custom}
"""


def render_persona_template(profile: MBTIProfile, locale: Locale = DEFAULT_LOCALE) -> str:
    """Return a persona template with ``{agent_name}``, ``{user_display}``, ``{custom}`` placeholders."""
    behavior = profile.behavior
    # system_prompt is persisted per agent and shared by every user of it, so the
    # language line sets a default and follows the user instead of forcing zh.
    if locale == "zh":
        return (
            f"# 人格：{profile.code} — {profile.name_zh}\n\n"
            "你是 {agent_name}，一位 AI 助手，正在协助 {user_display}。\n\n"
            f"{profile.summary_zh}。特质：{profile.descriptors_zh}。\n\n"
            "## 行为准则\n\n"
            f"- **回答风格：** {behavior.answer_style_zh}\n"
            f"- **闲聊：** {behavior.casual_chat_zh}\n"
            f"- **冲突：** {behavior.conflict_zh}\n"
            f"- **创造力：** {behavior.creativity_zh}\n"
            f"- **情绪：** {behavior.emotion_zh}\n"
            f"- **规划：** {behavior.planning_zh}\n\n"
            "默认使用简体中文回复，包括执行过程中的说明和最终答复；"
            "如果用户使用其他语言交流，则使用用户的语言回复。\n\n"
            "{custom}\n"
        )
    return (
        f"# Persona: {profile.code} — {profile.name_en}\n\n"
        f"You are {{agent_name}}, an AI assistant working with {{user_display}}.\n\n"
        f"{profile.summary_en}. Traits: {profile.descriptors_en}.\n\n"
        "## Behavior\n\n"
        f"- **Answer style:** {behavior.answer_style}\n"
        f"- **Casual chat:** {behavior.casual_chat}\n"
        f"- **Conflict:** {behavior.conflict}\n"
        f"- **Creativity:** {behavior.creativity}\n"
        f"- **Emotion:** {behavior.emotion}\n"
        f"- **Planning:** {behavior.planning}\n\n"
        "Reply in the user's language.\n\n"
        "{custom}\n"
    )


class PersonaLoader:
    """Build persona templates from ``mbti_profiles`` or the built-in default."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, Locale], str] = {}

    def load(self, code: str | None, locale: Locale = DEFAULT_LOCALE) -> str:
        if code:
            profile = get_profile(code)
            if profile is not None:
                key = (profile.code, locale)
                if key in self._cache:
                    return self._cache[key]
                text = render_persona_template(profile, locale)
                self._cache[key] = text
                return text

        return _DEFAULT_PERSONA_TEMPLATE_ZH if locale == "zh" else _DEFAULT_PERSONA_TEMPLATE

    def render(
        self,
        *,
        mbti: str | None,
        agent_name: str,
        user_display: str,
        custom: str | None,
        locale: Locale = DEFAULT_LOCALE,
    ) -> str:
        template = self.load(mbti, locale)
        return template.format(
            agent_name=agent_name,
            user_display=user_display,
            custom=(custom or "").strip(),
        )


def resolve_persona_code(
    *,
    persona_mbti: str | None,
    config: dict[str, object] | None = None,
) -> str | None:
    if persona_mbti:
        return persona_mbti.upper()
    if config:
        raw = config.get("persona")
        if isinstance(raw, str) and raw.strip():
            return raw.strip().upper()
    return None
