"""Parser for Candidate Extractor LLM output.

Responsibilities:

1. **Extract JSON from a noisy LLM string** — handle markdown code fences,
   leading/trailing whitespace, occasional prose around the JSON object.
2. **Validate against the expected schema shape** — types, required fields,
   enums (candidate_type / confidence / importance / etc.).
3. **Apply post-hoc anti-dilution checks** — flag suspicious paraphrasing
   (importance=high but assertion != verbatim_quote, lost negation tokens).
   We **warn** rather than reject because the LLM occasionally adds harmless
   trailing punctuation.
4. **Map JSON dicts to ``Candidate`` dataclass** — assigning worker-side ids
   and filling in fields that the LLM is forbidden to populate.

The parser does NOT call the LLM, retry, or persist anything. That orchestration
lives in ``CandidateExtractor`` (``__init__.py``).
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from octop_memory.pipeline.extractor.prompts import EXTRACTOR_VERSION, NEGATION_TOKENS
from octop_memory.types import (
    Candidate,
    CandidateType,
    ConfidenceLevel,
    EntityType,
    ImportanceLevel,
    RecommendedAction,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed enum values (mirror the Literals from types.py)
# ---------------------------------------------------------------------------

_VALID_CANDIDATE_TYPES = {"Fact", "Decision", "Task", "Preference", "ConflictCandidate"}
_VALID_ENTITY_TYPES = {"User", "Person", "Project", "Decision", "Task", "Fact"}
_VALID_CONFIDENCE = {"low", "medium", "high"}
_VALID_IMPORTANCE = {"low", "medium", "high"}
_VALID_ACTIONS = {"promote", "merge", "update", "reject", "conflict", "needs_review"}

CAP_WARNING_TITLE = "__cap_warning__"


class ExtractorParseError(ValueError):
    """Raised when LLM output cannot be parsed into Candidate JSON."""


@dataclass
class ParseResult:
    """Outcome of parsing one LLM response.

    - ``candidates``: successfully validated Candidate objects (already with
      worker-assigned ids).
    - ``warnings``: per-candidate anti-dilution / shape concerns. Caller
      decides whether to accept, log, or surface to the user.
    - ``cap_warning``: the LLM emitted the special "__cap_warning__" entry
      indicating it truncated. Caller may want to re-batch.
    - ``raw_count``: how many candidate dicts the LLM returned (before
      filtering invalid ones).
    """

    candidates: list[Candidate]
    warnings: list[str] = field(default_factory=list)
    cap_warning: str | None = None
    raw_count: int = 0


# ---------------------------------------------------------------------------
# JSON extraction — handle code fences and surrounding noise
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_YEAR_IN_NAME_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")
"""Regex to detect year numbers in subject.name (signals event-type entity name)."""


def extract_json_blob(raw: str) -> str:
    """Extract the JSON payload from a possibly noisy LLM response.

    Heuristics:
    1. If wrapped in ```json ... ``` (or just ``` ... ```), strip fences.
    2. Trim leading / trailing whitespace.
    3. If the result starts with prose, find the first '{' and pair it with
       the matching '}'.

    Returns the extracted string. Does NOT validate JSON syntax — that's
    the caller's job (so the caller can attach context to errors).
    """
    text = raw.strip()
    if not text:
        raise ExtractorParseError("LLM returned empty string")

    # Step 1: strip ``` fences if present.
    fence_match = _CODE_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Step 2: if there's prose before the first '{', try to crop.
    if not text.startswith("{"):
        first_brace = text.find("{")
        if first_brace == -1:
            raise ExtractorParseError(f"no JSON object found in LLM output (first 200 chars): {raw[:200]!r}")
        text = text[first_brace:]

    # Step 3: balance braces — defensive against trailing prose.
    depth = 0
    end_idx = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx == -1:
        raise ExtractorParseError(f"unbalanced braces in LLM output: {text[:200]!r}")
    return text[: end_idx + 1]


# ---------------------------------------------------------------------------
# Single-candidate validation + mapping
# ---------------------------------------------------------------------------


def _validate_enum(value: Any, allowed: set[str], field_name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ExtractorParseError(f"{field_name}: expected one of {sorted(allowed)}, got {value!r}")
    return value


def _validate_str(
    value: Any,
    field_name: str,
    *,
    max_len: int | None = None,
    truncate: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ExtractorParseError(f"{field_name}: expected string, got {type(value).__name__}")
    if max_len is not None and len(value) > max_len:
        if truncate:
            return value[:max_len]
        raise ExtractorParseError(f"{field_name}: length {len(value)} exceeds max {max_len}")
    return value


def _validate_str_list(value: Any, field_name: str, *, min_len: int = 0) -> list[str]:
    if not isinstance(value, list):
        raise ExtractorParseError(f"{field_name}: expected list, got {type(value).__name__}")
    if len(value) < min_len:
        raise ExtractorParseError(f"{field_name}: requires at least {min_len} item(s), got {len(value)}")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise ExtractorParseError(f"{field_name}[{i}]: expected string, got {type(item).__name__}")
        out.append(item)
    return out


def _check_anti_dilution(
    *,
    importance: ImportanceLevel,
    assertion: str,
    verbatim_quote: str,
) -> list[str]:
    """Post-hoc anti-dilution checks. Returns a list of warning strings."""
    warnings: list[str] = []

    # Rule: high importance => assertion must match verbatim_quote.
    if importance == "high" and assertion.strip() != verbatim_quote.strip():
        warnings.append(
            f"importance=high but assertion was paraphrased "
            f"(quote={verbatim_quote[:60]!r}, assertion={assertion[:60]!r})"
        )

    # Rule: negation tokens in quote should survive in assertion.
    quote_lower = verbatim_quote.lower()
    assertion_lower = assertion.lower()
    lost_tokens = [t for t in NEGATION_TOKENS if t.lower() in quote_lower and t.lower() not in assertion_lower]
    if lost_tokens:
        warnings.append(
            f"negation/qualifier tokens lost during paraphrase: {lost_tokens} "
            f"(quote={verbatim_quote[:60]!r}, assertion={assertion[:60]!r})"
        )

    return warnings


def _map_candidate_dict(
    item: dict[str, Any],
    *,
    session_id: str | None,
    raw_event_ids_universe: set[str],
    extractor_version: str,
) -> tuple[Candidate, list[str]]:
    """Validate one ``candidates[]`` dict and convert to a ``Candidate``.

    Returns ``(candidate, warnings)``. Raises ``ExtractorParseError`` on
    structural problems that prevent constructing the dataclass at all.
    """
    if not isinstance(item, dict):
        raise ExtractorParseError(f"each candidate must be a dict, got {type(item).__name__}")

    candidate_type = _validate_enum(item.get("candidate_type"), _VALID_CANDIDATE_TYPES, "candidate_type")

    # --- core text fields ------------------------------------------------
    title = _validate_str(item.get("title", ""), "title")
    assertion = _validate_str(item.get("assertion", ""), "assertion")
    raw_quote = item.get("verbatim_quote", "")
    quote_truncated = isinstance(raw_quote, str) and len(raw_quote) > 200
    verbatim_quote = _validate_str(raw_quote, "verbatim_quote", max_len=200, truncate=True)
    if not verbatim_quote.strip():
        raise ExtractorParseError("verbatim_quote is required (cannot be empty)")
    quote_event_id = _validate_str(item.get("quote_event_id", ""), "quote_event_id")
    if not quote_event_id:
        raise ExtractorParseError("quote_event_id is required")

    # --- subject ---------------------------------------------------------
    subject = item.get("subject")
    if not isinstance(subject, dict):
        raise ExtractorParseError(f"subject must be an object, got {type(subject).__name__}")
    subject_name = _validate_str(subject.get("name", ""), "subject.name")
    subject_entity_type_str = _validate_enum(subject.get("entity_type"), _VALID_ENTITY_TYPES, "subject.entity_type")

    # --- subject.name format check (warn only, do not reject) -----------
    if _YEAR_IN_NAME_RE.search(subject_name):
        logger.warning(
            "subject.name %r contains a year number — this looks like an event-type "
            "entity name rather than a stable entity name. "
            "Time/event details should be placed in the assertion field, not subject.name.",
            subject_name,
        )

    # --- source refs (must reference real events when possible) ----------
    source_refs = _validate_str_list(item.get("source_refs", []), "source_refs", min_len=1)
    if raw_event_ids_universe:
        unknown = [r for r in source_refs if r not in raw_event_ids_universe]
        if unknown:
            raise ExtractorParseError(f"source_refs contain ids not in input batch: {unknown[:5]}")
        if quote_event_id not in raw_event_ids_universe:
            raise ExtractorParseError(f"quote_event_id {quote_event_id!r} not in input batch")

    # --- enums -----------------------------------------------------------
    confidence = _validate_enum(item.get("confidence"), _VALID_CONFIDENCE, "confidence")
    importance = _validate_enum(item.get("importance"), _VALID_IMPORTANCE, "importance")
    recommended_action = _validate_enum(item.get("recommended_action"), _VALID_ACTIONS, "recommended_action")
    promotion_reason = _validate_str(item.get("promotion_reason", ""), "promotion_reason")

    # --- anti-dilution checks (warnings only, do not abort) -------------
    warnings = _check_anti_dilution(
        importance=importance,  # type: ignore[arg-type]
        assertion=assertion,
        verbatim_quote=verbatim_quote,
    )
    if quote_truncated:
        warnings.append("verbatim_quote: truncated to 200 chars (model output exceeded max)")

    candidate = Candidate(
        id=str(uuid.uuid4()),  # worker-assigned, NOT from LLM
        raw_event_ids=source_refs,
        candidate_type=candidate_type,  # type: ignore[arg-type]
        status="pending",
        title=title,
        assertion=assertion,
        verbatim_quote=verbatim_quote,
        quote_event_id=quote_event_id,
        subject_name=subject_name,
        subject_entity_type=subject_entity_type_str,  # type: ignore[arg-type]
        target_entity_id=None,  # worker resolves later in promotion
        confidence=confidence,  # type: ignore[arg-type]
        importance=importance,  # type: ignore[arg-type]
        recommended_action=recommended_action,  # type: ignore[arg-type]
        promotion_reason=promotion_reason,
        extractor_version=extractor_version,
        created_at=datetime.now(UTC),
        session_id=session_id,
    )
    return candidate, warnings


# ---------------------------------------------------------------------------
# Public parser entrypoint
# ---------------------------------------------------------------------------


def parse_extractor_output(
    raw_output: str,
    *,
    session_id: str | None,
    raw_event_ids: set[str] | None = None,
    extractor_version: str = EXTRACTOR_VERSION,
) -> ParseResult:
    """Parse one LLM response into a ``ParseResult``.

    Args:
        raw_output: The raw string returned by ``LLMClient.call_llm``.
        session_id: Session id to attach to every emitted Candidate.
        raw_event_ids: If non-empty, ``source_refs`` and ``quote_event_id``
            are checked against this set (rejects fabricated ids). Pass
            ``None`` to skip referential validation (e.g. in unit tests
            that want to use synthetic event ids).
        extractor_version: Persisted on every Candidate for replay.

    Raises:
        ExtractorParseError: when the JSON cannot be extracted or the
            top-level shape is wrong. Individual candidates that fail
            structural validation are skipped (warning) so one bad model
            item cannot discard the rest of the batch. Anti-dilution
            issues are reported as warnings, not errors.
    """
    blob = extract_json_blob(raw_output)
    try:
        decoded: Any = json.loads(blob)
    except json.JSONDecodeError as e:
        raise ExtractorParseError(f"invalid JSON: {e}; got blob={blob[:300]!r}") from e

    if not isinstance(decoded, dict):
        raise ExtractorParseError(f"top-level JSON must be an object, got {type(decoded).__name__}")
    items = decoded.get("candidates")
    if not isinstance(items, list):
        raise ExtractorParseError(f"candidates must be a list, got {type(items).__name__}")

    universe = raw_event_ids or set()
    candidates: list[Candidate] = []
    all_warnings: list[str] = []
    cap_warning: str | None = None

    for idx, item in enumerate(items):
        if isinstance(item, dict) and item.get("title") == CAP_WARNING_TITLE:
            cap_warning = str(item.get("assertion") or f"batch truncated at item {idx}")
            continue
        try:
            cand, warns = _map_candidate_dict(
                item,
                session_id=session_id,
                raw_event_ids_universe=universe,
                extractor_version=extractor_version,
            )
        except ExtractorParseError as e:
            # One malformed candidate must not discard the rest of a
            # usable batch — the model is assumed unreliable.
            all_warnings.append(f"candidates[{idx}] skipped: {e}")
            continue
        candidates.append(cand)
        all_warnings.extend(f"candidates[{idx}]: {w}" for w in warns)

    return ParseResult(
        candidates=candidates,
        warnings=all_warnings,
        cap_warning=cap_warning,
        raw_count=len(items),
    )


# Re-exports used by other modules so they don't need to import from internals.
__all__ = [
    "CAP_WARNING_TITLE",
    "Candidate",
    "CandidateType",
    "ConfidenceLevel",
    "EntityType",
    "ExtractorParseError",
    "ImportanceLevel",
    "ParseResult",
    "RecommendedAction",
    "extract_json_blob",
    "parse_extractor_output",
]
