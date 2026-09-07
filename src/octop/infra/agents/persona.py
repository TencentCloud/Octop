"""Render agent persona system prompt from MBTI profiles or the built-in default template."""

from __future__ import annotations

from octop.infra.agents.mbti_profiles import MBTIProfile, get_profile

_DEFAULT_PERSONA_TEMPLATE = """\
# Persona: Default

You are {agent_name}, an attentive AI assistant working with {user_display}.

Tone: warm, direct, and competent. Prefer concrete answers over hedging.
Match the user's level of detail. When uncertain, say so and propose how
to find out.

{custom}
"""


def render_persona_template(profile: MBTIProfile) -> str:
    """Return a persona template with ``{agent_name}``, ``{user_display}``, ``{custom}`` placeholders."""
    behavior = profile.behavior
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
        "{custom}\n"
    )


class PersonaLoader:
    """Build persona templates from ``mbti_profiles`` or the built-in default."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def load(self, code: str | None) -> str:
        if code:
            profile = get_profile(code)
            if profile is not None:
                if profile.code in self._cache:
                    return self._cache[profile.code]
                text = render_persona_template(profile)
                self._cache[profile.code] = text
                return text

        return _DEFAULT_PERSONA_TEMPLATE

    def render(
        self,
        *,
        mbti: str | None,
        agent_name: str,
        user_display: str,
        custom: str | None,
    ) -> str:
        template = self.load(mbti)
        # Replace the three known placeholders via ``str.replace`` instead of
        # ``str.format``: a persona that carries playbook variables rendered
        # later (e.g. {date} / {work_dir}, see ``_render_system_prompt`` in
        # AgentManager) must survive this pass unchanged — ``.format`` would
        # raise ``KeyError`` on any unknown placeholder.
        out = template.replace("{agent_name}", agent_name).replace("{user_display}", user_display)
        custom_text = (custom or "").strip()
        if custom_text:
            out = out.replace("{custom}", custom_text)
        else:
            # Custom block absent: drop the placeholder line entirely.
            out = out.replace("{custom}\n", "").replace("{custom}", "")
        return out


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
