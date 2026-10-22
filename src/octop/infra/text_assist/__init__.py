"""One-shot LLM text assist (polish / generate) for dashboard forms and chat."""

from __future__ import annotations

from octop.infra.text_assist.service import ASSIST_KINDS, run_text_assist

__all__ = ["ASSIST_KINDS", "run_text_assist"]
