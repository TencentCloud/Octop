"""tests/unit/test_persona.py"""

from __future__ import annotations

import pytest

from octop.infra.agents.mbti_profiles import get_profile
from octop.infra.agents.persona import PersonaLoader, render_persona_template


@pytest.fixture
def loader() -> PersonaLoader:
    return PersonaLoader()


def test_load_default(loader: PersonaLoader):
    text = loader.load(None)
    assert "{agent_name}" in text


def test_load_known_mbti(loader: PersonaLoader):
    text = loader.load("INTJ")
    assert "INTJ" in text
    assert "{agent_name}" in text


def test_unknown_mbti_falls_back_to_default(loader: PersonaLoader):
    assert loader.load("XYZA") == loader.load(None)


def test_render_substitutes_placeholders(loader: PersonaLoader):
    out = loader.render(mbti="INTJ", agent_name="Daria", user_display="Alice", custom="Be terse.")
    assert "Daria" in out
    assert "Alice" in out
    assert "Be terse." in out
    assert "{agent_name}" not in out
    assert "{user_display}" not in out


def test_render_handles_empty_custom(loader: PersonaLoader):
    out = loader.render(mbti=None, agent_name="A", user_display="B", custom=None)
    assert "{custom}" not in out


def test_render_preserves_unknown_placeholders_for_compile_time(loader: PersonaLoader):
    """Playbook variables rendered later ({date}/{work_dir}/…) must survive
    the persona pass untouched — ``str.format`` would raise KeyError."""
    out = loader.render(
        mbti=None,
        agent_name="A",
        user_display="B",
        custom="Today is {date}. Workdir {work_dir}. Model {model}.",
    )
    assert "{date}" in out
    assert "{work_dir}" in out
    assert "{model}" in out
    assert "{agent_name}" not in out


def test_render_persona_template_uses_profile_fields():
    profile = get_profile("INTJ")
    assert profile is not None
    text = render_persona_template(profile)
    assert "INTJ" in text
    assert "Architect" in text
    assert "Answer style:" in text
    assert "{agent_name}" in text
