"""Render agent persona system prompt from MBTI profiles or the built-in default template."""

from octop.infra.agents.persona.loader import (
    PersonaLoader,
    render_persona_template,
    resolve_persona_code,
)
from octop.infra.agents.persona.mbti_profiles import (
    MBTIProfile,
    get_all_profiles,
    get_profile,
)

__all__ = [
    "MBTIProfile",
    "PersonaLoader",
    "get_all_profiles",
    "get_profile",
    "render_persona_template",
    "resolve_persona_code",
]
