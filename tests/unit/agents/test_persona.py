"""tests/unit/test_persona.py"""

from __future__ import annotations

import pytest

from octop.infra.agents.persona import PersonaLoader, render_persona_template
from octop.infra.agents.persona.mbti_profiles import get_profile


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


def test_render_persona_template_uses_profile_fields():
    profile = get_profile("INTJ")
    assert profile is not None
    text = render_persona_template(profile, "en")
    assert "INTJ" in text
    assert "Architect" in text
    assert "Answer style:" in text
    assert "Reply in the user's language." in text
    assert "{agent_name}" in text


def test_render_persona_template_zh_uses_chinese_fields():
    profile = get_profile("INTJ")
    assert profile is not None
    text = render_persona_template(profile, "zh")
    assert "建筑师" in text
    assert profile.behavior.answer_style_zh in text
    assert "默认使用简体中文回复" in text
    assert "使用用户的语言回复" in text
    assert "始终使用简体中文" not in text
    assert "Answer style:" not in text
    assert "{agent_name}" in text


def test_render_defaults_to_chinese(loader: PersonaLoader):
    for mbti in ("INTJ", None):
        out = loader.render(mbti=mbti, agent_name="A", user_display="B", custom=None)
        assert "默认使用简体中文回复" in out
        assert "使用用户的语言回复" in out
        assert "始终使用简体中文" not in out


def test_render_en_keeps_english(loader: PersonaLoader):
    for mbti in ("INTJ", None):
        out = loader.render(mbti=mbti, agent_name="A", user_display="B", custom=None, locale="en")
        assert "Reply in the user's language." in out
        assert "简体中文" not in out
