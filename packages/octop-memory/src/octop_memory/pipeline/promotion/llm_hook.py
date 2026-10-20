"""Default LLM escalation hook implementations for the promotion worker.

These wrap an :class:`LLMClient` (host-injected per D25) and provide the
three grey-zone disambiguations the rule path can't decide on its own:

- ``resolve_entity_match`` — alias / canonical_name miss → ask the LLM
  whether the candidate's subject refers to one of the existing
  entities of the same entity_type. Solves the M2.5a dogfood finding
  where ``"Project"`` and ``"Project database"`` got split into two
  entities because pure-rule alias normalization couldn't bridge them.
- ``same_assertion`` — semantic equality check used by lifecycle
  consolidation.
- ``is_contradiction`` — available for callers that need semantic
  contradiction classification.

Per design §8.3.2 each candidate is allotted **at most 1** LLM
escalation across the whole 5-check pipeline. The current
``PromotionWorker`` invokes only ``resolve_entity_match``; its duplicate
and conflict checks are rule-only. ``same_assertion`` is used separately
by the consolidation worker.

All methods catch :class:`LLMClientError` and return ``None`` so a
network blip never raises into user-blocking flow — the rule path's
tentative answer simply stands.
"""

from __future__ import annotations

import json
import logging

from octop_memory.ports.llm import LLMClient
from octop_memory.ports.llm._protocol import LLMClientError

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------


_RESOLVE_ENTITY_PROMPT = """\
You are a strict entity-matching assistant. Given a NEW subject string and
a list of EXISTING entity records, decide whether the NEW subject refers
to the **same real-world entity** as one of the existing records.

Rules:
- Return JSON ONLY: {{"entity_id": "<existing-id-or-null>"}}.
- entity_id MUST be one of the listed existing ids, or null.
- Choose null when uncertain. Do NOT guess. Loose semantic similarity
  is NOT enough — the two strings must clearly name the same entity.
- Different versions / variants of the same project (e.g. "Project X v2"
  vs "Project X") COUNT as the same entity.
- Different projects that happen to share a noun (e.g. "Apollo navigation"
  vs "Apollo cms") are NOT the same entity.

NEW subject: {subject!r}
NEW entity_type: {entity_type}

EXISTING records (id, canonical_name):
{candidates_block}

OUTPUT (JSON only):
"""

_SAME_ASSERTION_PROMPT = """\
You decide whether two short factual claims describe THE SAME FACT.

Rules:
- Return JSON ONLY: {{"same": true | false | null}}.
- Return null if you are uncertain. Do not guess.
- Two assertions describe the same fact iff a person told both versions
  would consider them redundant. Different wording about the same
  technical claim → same. Different topics → false.
- Negation MUST be respected: "X is true" and "X is not true" are NEVER
  the same assertion.

assertion A: {a!r}
assertion B: {b!r}

OUTPUT (JSON only):
"""

_CONTRADICTION_PROMPT = """\
You decide whether two short factual claims directly CONTRADICT each other.

Rules:
- Return JSON ONLY: {{"contradiction": true | false | null}}.
- Return null when uncertain. Do not guess.
- Two assertions contradict iff at most one can be true. Both about the
  same subject, with logically opposed states. Examples:
    "use PostgreSQL" vs "use MongoDB" (about the same project) → true
    "PostgreSQL is fast" vs "PostgreSQL is durable" → false
    "wake at 7am" vs "weather is nice" → false
- Different topics that happen to share words → false.

assertion A: {a!r}
assertion B: {b!r}

OUTPUT (JSON only):
"""


# ---------------------------------------------------------------------------
# Hook implementation
# ---------------------------------------------------------------------------


class ModelEscalationHook:
    """Default :class:`LLMEscalationHook` wrapping a host LLM client.

    Construct with the LLMClient that the host adapter injects (D25 —
    OpenClawLLMClient / HermesLLMClient / etc.). Memory's plugin code
    never imports the bridge directly; tests pass a ``MockLLMClient``.

    Args:
        llm: any object satisfying :class:`LLMClient`.
        timeout_seconds: ignored here (the LLMClient implementation owns
            its own timeout); kept for future symmetry with the
            extractor's ``CandidateExtractor`` constructor.
    """

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    # ---- check 3 (entity) -------------------------------------------------

    def resolve_entity_match(
        self,
        *,
        candidate_subject: str,
        candidate_entity_type: str,
        candidates: list[tuple[str, str]],
    ) -> str | None:
        if not candidates:
            return None
        # Build a numbered list. We deliberately pass entity_id as-is so
        # the LLM cannot synthesize a fake id — we still validate against
        # the input list afterwards.
        block_lines = [f'  - id: "{eid}"  canonical_name: "{name}"' for eid, name in candidates]
        prompt = _RESOLVE_ENTITY_PROMPT.format(
            subject=candidate_subject,
            entity_type=candidate_entity_type,
            candidates_block="\n".join(block_lines),
        )

        raw = self._safe_complete(prompt, response_format="json")
        if raw is None:
            return None

        parsed = self._safe_json_object(raw)
        if parsed is None:
            return None
        picked = parsed.get("entity_id")
        if picked is None or picked == "null":
            return None
        if not isinstance(picked, str):
            return None
        # Worker re-validates against the allowed set; returning a value
        # not in the input list is treated as "uncertain" upstream. We
        # still bail out early if the LLM hallucinated an id.
        valid_ids = {eid for eid, _ in candidates}
        if picked not in valid_ids:
            _log.debug("LLM returned non-member entity id %r; treating as uncertain", picked)
            return None
        return picked

    # ---- check 4 (duplicate, grey zone) ----------------------------------

    def same_assertion(
        self,
        *,
        candidate_assertion: str,
        existing_assertion: str,
    ) -> bool | None:
        prompt = _SAME_ASSERTION_PROMPT.format(
            a=candidate_assertion,
            b=existing_assertion,
        )
        raw = self._safe_complete(prompt, response_format="json")
        if raw is None:
            return None
        parsed = self._safe_json_object(raw)
        if parsed is None:
            return None
        v = parsed.get("same")
        if v is True or v is False:
            return v
        return None

    # ---- check 5 (conflict, grey zone) -----------------------------------

    def is_contradiction(
        self,
        *,
        candidate_assertion: str,
        existing_assertion: str,
    ) -> bool | None:
        prompt = _CONTRADICTION_PROMPT.format(
            a=candidate_assertion,
            b=existing_assertion,
        )
        raw = self._safe_complete(prompt, response_format="json")
        if raw is None:
            return None
        parsed = self._safe_json_object(raw)
        if parsed is None:
            return None
        v = parsed.get("contradiction")
        if v is True or v is False:
            return v
        return None

    # ---- internals --------------------------------------------------------

    def _safe_complete(self, prompt: str, *, response_format: str) -> str | None:
        try:
            return self._llm.call_llm(
                prompt,
                tier="light",
                temperature=0.0,
                response_format=response_format,  # type: ignore[arg-type]
            )
        except LLMClientError as e:
            _log.warning("LLM escalation failed: %s", e)
            return None

    @staticmethod
    def _safe_json_object(raw: str) -> dict[str, object] | None:
        # Try strict JSON first, then a permissive fence-stripping pass
        # for hosts that wrap output in ```json fences.
        text = raw.strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            cleaned = _strip_fences(text)
            try:
                obj = json.loads(cleaned)
            except json.JSONDecodeError:
                _log.debug("LLM hook: response is not valid JSON: %r", text[:200])
                return None
        if not isinstance(obj, dict):
            _log.debug("LLM hook: response is not a JSON object: %r", text[:200])
            return None
        return obj


def _strip_fences(text: str) -> str:
    """Best-effort: strip a leading ``` fence and trailing ``` if present."""
    if text.startswith("```"):
        # drop first line ('```json' or '```'), drop trailing fence
        lines = text.splitlines()
        if len(lines) >= _MIN_FENCED_LINES:
            body = lines[1:]
            while body and body[-1].strip().startswith("```"):
                body.pop()
            return "\n".join(body).strip()
    return text


__all__ = ["ModelEscalationHook"]

_MIN_FENCED_LINES = 2
"""Minimum line count for a fenced code block (fence line + at least one content line)."""
