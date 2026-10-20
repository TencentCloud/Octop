"""Built-in tool: ``ask_user_question``.

The tool whose *real implementation is the human*. When a HITL channel is
attached (``interrupt_on`` contains ``ask_user_question``), LangChain's
:class:`~langchain.agents.middleware.human_in_the_loop.HumanInTheLoopMiddleware`
intercepts the call **before execution** and raises a LangGraph ``interrupt``.
The host application renders the questions, collects the answer, and resumes
with a ``{"type": "respond", "message": ...}`` decision — the middleware then
synthesises a successful ``ToolMessage`` from that message.

The function body below is therefore a *fail-safe fallback*, reached only in
headless runs (cron jobs, unattended channels, or when the tool is mounted
without a HITL channel). It must never block: it tells the model to state its
assumption and keep going.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

MAX_QUESTIONS = 4
MAX_OPTIONS = 4

ASK_USER_TOOL_NAME = "ask_user_question"

# Returned when no interactive channel is attached. Phrased as an instruction so
# the model recovers by continuing rather than by retrying the tool.
HEADLESS_FALLBACK = (
    "No interactive user is available in this run. Do not call ask_user_question "
    "again. Pick the most reasonable default, state the assumption explicitly in "
    "your reply, and continue."
)


class AskOption(BaseModel):
    """One selectable answer."""

    label: str = Field(
        ...,
        min_length=1,
        max_length=40,
        description="User-facing choice, 1-5 words. Shown as a button.",
    )
    description: str = Field(
        "",
        max_length=200,
        description="One short sentence explaining the tradeoff if picked.",
    )


class AskQuestion(BaseModel):
    """One question with optional preset choices."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="The question, phrased so it can be answered in one step.",
    )
    header: str | None = Field(
        None,
        max_length=24,
        description="Optional 1-3 word topic label, e.g. 'Database'.",
    )
    options: list[AskOption] = Field(
        default_factory=list,
        max_length=MAX_OPTIONS,
        description=(
            "2-4 mutually exclusive choices, recommended option first. "
            "Leave empty only for genuinely open-ended questions."
        ),
    )
    multi_select: bool = Field(
        False,
        description="Allow selecting more than one option.",
    )

    @field_validator("question", "header")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class AskUserQuestionArgs(BaseModel):
    """Arguments for :func:`ask_user_question`."""

    questions: list[AskQuestion] = Field(
        ...,
        min_length=1,
        max_length=MAX_QUESTIONS,
        description="Ask everything you need in ONE call; do not chain calls.",
    )


@tool(ASK_USER_TOOL_NAME, args_schema=AskUserQuestionArgs)
def ask_user_question(questions: list[Any]) -> str:
    """Ask the user to decide, then wait for their answer before continuing.

    Use this ONLY at a real decision fork: the answer cannot be derived from the
    workspace or any other tool, and guessing wrong would waste significant work
    or produce something the user did not want. Typical good uses: choosing
    between two viable architectures, confirming a destructive migration,
    resolving genuinely ambiguous requirements.

    Do NOT use it to:
    - ask for information you can obtain with another tool (read the file, run
      the command, search the web);
    - ask for permission to proceed with an obvious next step;
    - check in on progress or ask "shall I continue?".

    Prefer stating an assumption and continuing. Ask at most a handful of times
    per task, and bundle every open question into a single call.

    Args:
        questions: 1-4 questions. Each has ``question`` text, an optional short
            ``header``, up to 4 ``options`` (``label`` + ``description``, best
            option first), and ``multi_select`` when several may apply.

    Returns:
        The user's answer as text. In headless runs where nobody can answer,
        returns an instruction to assume a default and continue.
    """
    del questions  # The human answers on behalf of this tool when HITL is on.
    return HEADLESS_FALLBACK


__all__ = [
    "ASK_USER_TOOL_NAME",
    "HEADLESS_FALLBACK",
    "MAX_OPTIONS",
    "MAX_QUESTIONS",
    "AskOption",
    "AskQuestion",
    "AskUserQuestionArgs",
    "ask_user_question",
]
