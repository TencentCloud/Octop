"""Tests for ``octop_harness.middleware.skill_filter.SkillFilterMiddleware``."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware import ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.config import var_child_runnable_config
from langgraph.prebuilt.tool_node import ToolCallRequest

from octop_harness.config import HarnessAgentConfig
from octop_harness.middleware.skill_filter import (
    SkillFilterMiddleware,
    disabled_skill_block_reason,
    render_slash_skill_prompt,
    slash_skill_slug,
)


@pytest.fixture
def sample_skills_metadata() -> list[dict[str, object]]:
    return [
        {
            "name": "web-search",
            "description": "Search the web",
            "path": "/_builtin_skills/web-search/SKILL.md",
            "license": None,
            "compatibility": None,
            "metadata": {},
            "allowed_tools": [],
        },
        {
            "name": "joke-mode",
            "description": "Tell jokes",
            "path": "/skills/joke-mode/SKILL.md",
            "license": None,
            "compatibility": None,
            "metadata": {},
            "allowed_tools": [],
        },
    ]


class TestSkillFilterMiddleware:
    @contextmanager
    def _runnable_config(self, configurable: dict[str, object]) -> Iterator[None]:
        token = var_child_runnable_config.set({"configurable": configurable})
        try:
            yield
        finally:
            var_child_runnable_config.reset(token)

    def _middleware(self, *, disabled: frozenset[str] = frozenset()) -> SkillFilterMiddleware:
        return SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=disabled))

    def _request(
        self,
        skills_metadata: list[dict[str, object]],
        *,
        user: str | None = None,
    ) -> ModelRequest:
        messages = [HumanMessage(content=user)] if user is not None else []
        return ModelRequest(
            model=MagicMock(),
            messages=messages,
            system_message=SystemMessage(content="Base prompt"),
            tool_choice=None,
            tools=[],
            response_format=None,
            state={"skills_metadata": skills_metadata, "messages": messages},
            runtime=MagicMock(),
            model_settings={},
        )

    def test_no_filter_passes_through(self, sample_skills_metadata: list[dict[str, object]]) -> None:
        """When no skills filter is set, state and system message are unchanged."""
        mw = self._middleware()
        with self._runnable_config({}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                captured["system_message"] = r.system_message
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["metadata"] == sample_skills_metadata
        assert captured["system_message"] is req.system_message

    def test_config_disabled_skills_filtered_without_request_filter(
        self,
        sample_skills_metadata: list[dict[str, object]],
    ) -> None:
        mw = self._middleware(disabled=frozenset({"joke-mode"}))
        with self._runnable_config({}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        metadata = captured["metadata"]
        assert isinstance(metadata, list)
        assert [s["name"] for s in metadata] == ["web-search"]

    def test_filters_state_to_named_skills(self, sample_skills_metadata: list[dict[str, object]]) -> None:
        """When a filter is set, only listed skills remain in state metadata."""
        mw = self._middleware()
        with self._runnable_config({"skills": ["joke-mode"]}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                captured["system_message"] = r.system_message
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        metadata = captured["metadata"]
        assert isinstance(metadata, list)
        assert [s["name"] for s in metadata] == ["joke-mode"]
        assert captured["system_message"] is req.system_message

    def test_disabled_and_request_filter_intersect(
        self,
        sample_skills_metadata: list[dict[str, object]],
    ) -> None:
        mw = self._middleware(disabled=frozenset({"web-search"}))
        with self._runnable_config({"skills": ["web-search", "joke-mode"]}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        metadata = captured["metadata"]
        assert isinstance(metadata, list)
        assert [s["name"] for s in metadata] == ["joke-mode"]

    def test_per_turn_filter_accepts_slug(self) -> None:
        metadata = [
            {
                "name": "Joke Mode",
                "description": "Tell jokes",
                "path": "/skills/joke-mode/SKILL.md",
                "license": None,
                "compatibility": None,
                "metadata": {},
                "allowed_tools": [],
            },
        ]
        mw = self._middleware()
        with self._runnable_config({"skills": ["joke-mode"]}):
            req = self._request(metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        result = captured["metadata"]
        assert isinstance(result, list)
        assert [s["name"] for s in result] == ["Joke Mode"]

    def test_per_turn_filter_accepts_display_name(self) -> None:
        metadata = [
            {
                "name": "Joke Mode",
                "description": "Tell jokes",
                "path": "/skills/joke-mode/SKILL.md",
                "license": None,
                "compatibility": None,
                "metadata": {},
                "allowed_tools": [],
            },
        ]
        mw = self._middleware()
        with self._runnable_config({"skills": ["Joke Mode"]}):
            req = self._request(metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        result = captured["metadata"]
        assert isinstance(result, list)
        assert [s["name"] for s in result] == ["Joke Mode"]

    def test_empty_skills_list_clears_metadata(self, sample_skills_metadata: list[dict[str, object]]) -> None:
        """When an empty list is passed, skills_metadata is emptied in state."""
        mw = self._middleware()
        with self._runnable_config({"skills": []}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                captured["system_message"] = r.system_message
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["metadata"] == []
        assert captured["system_message"] is req.system_message

    def test_unknown_skills_warn_but_pass_through(self, sample_skills_metadata: list[dict[str, object]]) -> None:
        """Unknown skill names trigger a logger warning but do not raise."""
        mw = self._middleware()
        with self._runnable_config({"skills": ["nonexistent"]}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["metadata"] == []

    def test_invalid_skills_type_passes_through(self, sample_skills_metadata: list[dict[str, object]]) -> None:
        """A non-list skills value triggers a warning and leaves state unchanged."""
        mw = self._middleware()
        with self._runnable_config({"skills": "web-search"}):
            req = self._request(sample_skills_metadata)
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["metadata"] == sample_skills_metadata

    def test_no_skills_metadata_in_state(self) -> None:
        """When state has no skills_metadata, filtering against empty list works."""
        mw = self._middleware()
        with self._runnable_config({"skills": ["web-search"]}):
            req = ModelRequest(
                model=MagicMock(),
                messages=[],
                system_message=None,
                tool_choice=None,
                tools=[],
                response_format=None,
                state={},
                runtime=MagicMock(),
                model_settings={},
            )
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["metadata"] == []

    def test_slash_invoke_does_not_mutate_system_prompt(
        self,
        sample_skills_metadata: list[dict[str, object]],
    ) -> None:
        """``/slug`` guidance is compiled into the system prompt, not injected per turn."""
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(language="en"))
        with self._runnable_config({}):
            req = self._request(sample_skills_metadata, user="/web-search look up X")
            captured: dict[str, object] = {}

            def handler(r: ModelRequest) -> ModelResponse:
                captured["system_message"] = r.system_message
                captured["metadata"] = r.state.get("skills_metadata")
                return ModelResponse(result=[])

            mw.wrap_model_call(req, handler)

        assert captured["system_message"] is req.system_message
        assert captured["metadata"] == sample_skills_metadata


def test_slash_skill_slug() -> None:
    assert slash_skill_slug("/web-search") == "web-search"
    assert slash_skill_slug("/web-search look up X") == "web-search"
    assert slash_skill_slug("  /Joke-Mode") == "joke-mode"
    assert slash_skill_slug("/root/ddd") is None
    assert slash_skill_slug("see /web-search") is None
    assert slash_skill_slug("hello") is None


def test_render_slash_skill_prompt_is_stable() -> None:
    en = render_slash_skill_prompt(language="en")
    zh = render_slash_skill_prompt(language="zh")
    assert "SKILL.md" in en
    assert "/name" in en
    assert "name or slug" in en
    assert "web-search" not in en
    assert "SKILL.md" in zh
    assert "/name" in zh
    assert "name 或 slug" in zh
    assert en == render_slash_skill_prompt(language="en")


class TestDisabledSkillBlockReason:
    def test_ignores_slug_outside_skills_tree(self) -> None:
        reason = disabled_skill_block_reason(
            "/generated/joke-mode/out.txt",
            disabled=frozenset({"joke-mode"}),
        )
        assert reason is None

    def test_matches_relative_and_glob_patterns(self) -> None:
        disabled = frozenset({"joke-mode"})
        assert disabled_skill_block_reason("skills/joke-mode/SKILL.md", disabled=disabled)
        assert disabled_skill_block_reason("**/_builtin_skills/joke-mode/**", disabled=disabled)
        assert disabled_skill_block_reason("cat /skills/joke-mode/SKILL.md", disabled=disabled)
        assert disabled_skill_block_reason("echo joke-mode", disabled=disabled) is None

    def test_matches_system_files_path_prefix(self) -> None:
        disabled = frozenset({"joke-mode"})
        assert disabled_skill_block_reason(
            ".custom/skills/joke-mode/SKILL.md",
            disabled=disabled,
            system_files_path=".custom",
        )
        assert disabled_skill_block_reason(
            "cat /.custom/_builtin_skills/joke-mode/x.md",
            disabled=disabled,
            system_files_path=".custom",
        )
        # Jail bind path ``/skills/…`` still matches regardless of prefix.
        assert disabled_skill_block_reason(
            "/skills/joke-mode/SKILL.md",
            disabled=disabled,
            system_files_path=".custom",
        )


class TestDisabledSkillFilesystemBlock:
    def _request(
        self,
        *,
        tool_name: str,
        args: dict[str, object],
        tool_id: str = "tc1",
    ) -> ToolCallRequest:
        req = MagicMock(spec=ToolCallRequest)
        req.tool_call = {
            "name": tool_name,
            "args": args,
            "id": tool_id,
        }
        return req

    def _run(
        self,
        mw: SkillFilterMiddleware,
        request: ToolCallRequest,
        *,
        allowed: str = "ok",
    ) -> ToolMessage:
        async def handler(_req: ToolCallRequest) -> ToolMessage:
            return ToolMessage(content=allowed, tool_call_id=str(request.tool_call["id"]))

        import asyncio

        result = asyncio.run(mw.awrap_tool_call(request, handler))
        assert isinstance(result, ToolMessage)
        return result

    def test_blocks_read_file_for_disabled_skill(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(
                tool_name="read_file",
                args={"file_path": "/skills/joke-mode/SKILL.md"},
            ),
        )
        assert result.status == "error"
        assert "disabled" in str(result.content)

    def test_allows_read_file_for_enabled_skill(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(
                tool_name="read_file",
                args={"file_path": "/skills/web-search/SKILL.md"},
                tool_id="tc2",
            ),
            allowed="ok",
        )
        assert result.content == "ok"

    def test_blocks_glob_pattern_without_path(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(tool_name="glob", args={"pattern": "skills/joke-mode/**"}),
        )
        assert result.status == "error"

    def test_blocks_grep_path_arg(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(
                tool_name="grep",
                args={"pattern": "TODO", "path": "/_builtin_skills/joke-mode"},
            ),
        )
        assert result.status == "error"

    def test_blocks_execute_command_targeting_skill(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(tool_name="execute", args={"command": "cat /skills/joke-mode/SKILL.md"}),
        )
        assert result.status == "error"

    def test_allows_execute_without_skill_path(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(tool_name="execute", args={"command": "echo joke-mode"}),
        )
        assert result.content == "ok"

    def test_allows_path_that_only_shares_slug(self) -> None:
        mw = SkillFilterMiddleware(config=HarnessAgentConfig(skills_disabled=frozenset({"joke-mode"})))
        result = self._run(
            mw,
            self._request(
                tool_name="read_file",
                args={"file_path": "/generated/joke-mode/out.txt"},
            ),
        )
        assert result.content == "ok"
