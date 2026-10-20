"""Prompt v2 for Candidate Extractor.

Anchored to design doc Appendix A. Edit ``EXTRACTOR_VERSION`` whenever the
prompt body changes — that string is persisted on every Candidate row so
the extractor output can be replayed against new prompt versions later.

The prompt is a single user-side string (we do not split system / user
because some LLM hosts only expose ``prompt`` and ignore ``system``).
"""

from __future__ import annotations

EXTRACTOR_VERSION = "v2.4"
"""Version tag persisted on every Candidate (`extractor_version` field).

Bump when:
- The body text below changes (rules, instructions, anti-dilution wording)
- The few-shot examples change in ways that affect output
- The output JSON schema changes

Do NOT bump for whitespace-only or comment changes.

v2.4 adds durable eligibility rules before confidence/importance scoring,
excluding transient runtime diagnostics while protecting troubleshooting
knowledge and user-explicit incident retention.

v2.3 changes (vs v2.2):
- Added confidence three-tier scoring rubric with explicit trigger signals
  and "extract with low rather than skip" philosophy
- Added importance three-tier scoring rubric with Anti-dilution linkage reminder
- Added candidate_type priority order: ConflictCandidate > Decision > Task >
  Preference > Fact, with per-type trigger conditions
- Added promotion_reason fill-in requirements (confidence rationale +
  importance rationale + key extraction signal; never empty)
- Added Example 4 (confidence=low, importance=medium: assistant suggestion,
  tentative user acceptance) and Example 5 (confidence=high, importance=medium:
  clearly stated non-critical preference)
"""

# ---------------------------------------------------------------------------
# Anti-dilution rules — kept as a separate constant so prompts.py & parser.py
# can both reference the canonical wording. The parser uses these to
# validate LLM output post-hoc; the prompt embeds them as instructions.
# ---------------------------------------------------------------------------

NEGATION_TOKENS = (
    # Chinese
    "不",
    "没",
    "别",
    "勿",
    "暂不",
    "先",
    "再",
    "暂",
    # English
    "not",
    "won't",
    "avoid",
    "first",
    "then",
    "for now",
    "instead",
    # Japanese
    "ない",
    "まだ",
)
"""Tokens whose presence signals negation/qualifier — must survive paraphrasing.

Used by the parser to **warn** when an assertion appears to have lost a
negation that was present in the verbatim quote (post-hoc anti-dilution check).
"""

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

_FEW_SHOT_EXAMPLES = """\
Few-shot examples (study the format, then process the actual input):

Example 0 — subject.name must be a stable entity name, NOT an event description

  BAD (do NOT do this):
    subject: {"name": "Eileen Lunch 2026", "entity_type": "Person"}
    → WRONG: "Eileen Lunch 2026" mixes a person name with a time/event.
      The entity would be created fresh every time and never reused.

  GOOD (do this instead):
    subject: {"name": "Eileen", "entity_type": "Person"}
    assertion: "Eileen 在 2026 年某天吃了午餐"
    → CORRECT: subject.name is just the stable person name;
      the time/event detail lives in assertion.

  BAD (do NOT do this):
    subject: {"name": "User Lunch Today", "entity_type": "User"}
    → WRONG: User's name is always "User"; "Lunch Today" is an event.

  GOOD (do this instead):
    subject: {"name": "User", "entity_type": "User"}
    assertion: "用户今天午餐吃了抹茶奶冻"
    → CORRECT: subject.name stays "User"; the meal detail is in assertion.

Example 1 — high-importance decision with negation preserved
INPUT (raw events):
[
  {"event_id": "raw-A1", "event_type": "user_message",
   "content": "Octop Memory 这个项目，我决定先做 Augment 模式，不做 Replace。记住这个决定。",
   "timestamp": "2026-06-03T15:00:00Z", "session_id": "s1"},
  {"event_id": "raw-A2", "event_type": "assistant_message",
   "content": "好的，已经记住", "timestamp": "2026-06-03T15:00:01Z", "session_id": "s1"}
]
OUTPUT:
{
  "candidates": [
    {
      "candidate_id": "",
      "candidate_type": "Decision",
      "status": "pending",
      "title": "Octop Memory mode decision",
      "assertion": "Octop Memory 这个项目，我决定先做 Augment 模式，不做 Replace",
      "verbatim_quote": "Octop Memory 这个项目，我决定先做 Augment 模式，不做 Replace",
      "quote_event_id": "raw-A1",
      "subject": {"name": "Octop Memory", "entity_type": "Project", "entity_id_hint": ""},
      "target_entities": [],
      "source_refs": ["raw-A1", "raw-A2"],
      "confidence": "high",
      "importance": "high",
      "recommended_action": "promote",
      "promotion_reason": "explicit decision keyword '记住' + negation '不做 Replace' preserved"
    }
  ]
}

Example 2 — low-importance fact still extracted (demotion-only philosophy)
INPUT:
[
  {"event_id": "raw-B1", "event_type": "user_message",
   "content": "顺便说一下，alias table 默认大小是 10000",
   "timestamp": "2026-06-03T16:00:00Z", "session_id": "s1"}
]
OUTPUT:
{
  "candidates": [
    {
      "candidate_id": "",
      "candidate_type": "Fact",
      "status": "pending",
      "title": "alias table default size",
      "assertion": "alias table 默认大小是 10000",
      "verbatim_quote": "alias table 默认大小是 10000",
      "quote_event_id": "raw-B1",
      "subject": {"name": "alias table", "entity_type": "Fact", "entity_id_hint": ""},
      "target_entities": [],
      "source_refs": ["raw-B1"],
      "confidence": "medium",
      "importance": "low",
      "recommended_action": "promote",
      "promotion_reason": "stable configuration fact, low importance but useful for future reference"
    }
  ]
}

Example 3 — chit-chat NOT extracted
INPUT:
[
  {"event_id": "raw-C1", "event_type": "user_message",
   "content": "今天天气真好",
   "timestamp": "2026-06-03T17:00:00Z", "session_id": "s1"}
]
OUTPUT:
{"candidates": []}

Example 4 — confidence=low, importance=medium (assistant suggestion, user did not explicitly accept)
INPUT:
[
  {"event_id": "raw-D1", "event_type": "assistant_message",
   "content": "建议你把 retry 上限设为 3，这样既能容错又不会拖慢响应。",
   "timestamp": "2026-06-04T10:00:00Z", "session_id": "s2"},
  {"event_id": "raw-D2", "event_type": "user_message",
   "content": "嗯，先这样吧，之后再看看。",
   "timestamp": "2026-06-04T10:00:05Z", "session_id": "s2"}
]
OUTPUT:
{
  "candidates": [
    {
      "candidate_id": "",
      "candidate_type": "Fact",
      "status": "pending",
      "title": "retry limit suggestion",
      "assertion": "建议将 retry 上限设为 3 以平衡容错与响应速度",
      "verbatim_quote": "建议你把 retry 上限设为 3，这样既能容错又不会拖慢响应。",
      "quote_event_id": "raw-D1",
      "subject": {"name": "User", "entity_type": "User", "entity_id_hint": ""},
      "target_entities": [],
      "source_refs": ["raw-D1", "raw-D2"],
      "confidence": "low",
      "importance": "medium",
      "recommended_action": "promote",
      "promotion_reason": "confidence=low: this came from an assistant suggestion; user said '先这样吧' which is tentative acceptance, not explicit confirmation. importance=medium: retry configuration is a meaningful technical parameter that may affect future decisions — raised from low to avoid the low+low drop rule."
    }
  ]
}

Example 5 — confidence=high, importance=medium (user clearly stated a non-critical preference)
INPUT:
[
  {"event_id": "raw-E1", "event_type": "user_message",
   "content": "对了，我平时写 Python 喜欢用单引号，不用双引号。",
   "timestamp": "2026-06-04T11:00:00Z", "session_id": "s3"}
]
OUTPUT:
{
  "candidates": [
    {
      "candidate_id": "",
      "candidate_type": "Preference",
      "status": "pending",
      "title": "Python quote style preference",
      "assertion": "用户写 Python 时偏好使用单引号，不用双引号",
      "verbatim_quote": "我平时写 Python 喜欢用单引号，不用双引号",
      "quote_event_id": "raw-E1",
      "subject": {"name": "User", "entity_type": "User", "entity_id_hint": ""},
      "target_entities": [],
      "source_refs": ["raw-E1"],
      "confidence": "high",
      "importance": "medium",
      "recommended_action": "promote",
      "promotion_reason": "confidence=high: user stated this directly and unambiguously as a first-hand fact with no hedging. importance=medium: this is a stable coding style preference worth remembering for future code generation, but it does not affect project direction or major decisions — does not qualify for high."
    }
  ]
}
"""


# ---------------------------------------------------------------------------
# Prompt body (anchored to design doc Appendix A)
# ---------------------------------------------------------------------------

_PROMPT_BODY_TEMPLATE = """\
You are a Candidate Memory Extractor. Read a batch of raw events and extract
candidate memories worth long-term retention. Output Candidate JSON only.

You MUST NOT:
- Write to long-term memory directly
- Modify Entity pages
- Fabricate information the user did not state
- Generate candidate_id or target_entities entity_id (leave empty; worker assigns)
- Paraphrase away negations or qualifiers (see "Anti-dilution rules")

Schema enums (use these EXACT spellings; case matters):

candidate_type — what KIND of memory this candidate is. Pick exactly one:
  - "Fact"              — a stable atomic claim about the world or project
  - "Decision"          — a confirmed / accepted choice the user has made
  - "Task"              — an open todo / follow-up the user wants to remember
  - "Preference"        — a stable user preference (likes/dislikes, style)
  - "ConflictCandidate" — new info contradicts an earlier memory

  Type selection priority (highest wins when multiple types could apply):
    ConflictCandidate > Decision > Task > Preference > Fact
  Quick triggers:
    • New info contradicts prior memory                → ConflictCandidate
    • Confirmation language + a choice being made      → Decision
    • Open todo / follow-up / action item              → Task
    • Stable like / dislike / style preference         → Preference
    • Everything else (stable facts, config, context)  → Fact

subject.entity_type — what KIND of entity this candidate is ABOUT. Pick exactly one:
  - "User"     — the speaking user themselves (their info / preferences / role)
  - "Person"   — a third-party person mentioned by the user
  - "Project"  — a long-running project or research direction
  - "Decision" — a named decision treated as a first-class entity
  - "Task"     — a named task / follow-up treated as a first-class entity
  - "Fact"     — a generic atomic fact entity (default when nothing else fits)

confidence — how certain you are that this information is accurate and user-intended.
  Apply scoring ONLY after the durable eligibility rules below. Never increase
  importance just to preserve transient runtime diagnostics.
  Philosophy: ALWAYS extract if the info has any future value; use confidence to
  reflect SOURCE QUALITY, not whether to extract. "low" means "keep but uncertain",
  NOT "discard". For eligible durable knowledge, confidence=low AND importance=low
  is the scoring combination dropped downstream — when in doubt, extract and give low
  confidence rather than skipping.

  - "high"   — Direct quote, no ambiguity. Use when:
                • User uses confirmation language in ANY language:
                  "记住" / "就这样" / "确定" / "remember this" / "go with this" /
                  "let's lock that in" / "確定" / "覚えて" / "запомни"
                • User states a first-hand fact with direct verbatim support,
                  no inference needed
                • User actively corrects prior information (correction itself
                  is a high-confidence signal)

  - "medium" — User-stated but with some ambiguity. Use when:
                • User uses hedging language: "好像是" / "大概" / "应该" /
                  "I think" / "probably" / "maybe"
                • Minor inference needed to form a complete assertion
                  (e.g. filling in an implicit subject from context)
                • User mentions in passing — not actively confirmed, but
                  still a first-hand user statement

  - "low"    — Inferred or from an external source, but still worth keeping.
                Use when:
                • Comes from an assistant suggestion the user has NOT
                  explicitly accepted (but also not rejected)
                • Comes from a tool result (external evidence, not user
                  preference or intent)
                • Context is incomplete; only inferable from surrounding text
                • User uses hypothetical language: "如果" / "可能" / "打算" /
                  "might" / "would" / "I'm thinking about"
                • User is relaying what someone else said: "他说" / "据说" /
                  "I heard" / "apparently"

  ⚠ DISCARD WARNING: confidence=low AND importance=low is the scoring combination
  that causes a candidate to be dropped (Promotion Check 1). If eligible info has
  any future value, raise importance to "medium" rather than skipping extraction.

importance — how much this memory will affect future answers, decisions, or
  project progress. This field carries weight 0.20 in recall reranking.

  - "high"   — Directly shapes future decisions, project direction, or core
                user preferences. Use when:
                • User uses confirmation language (same signals as confidence=high)
                • candidate_type is "Decision" and user explicitly confirmed it
                • Preference is long-term and stable (not a one-off remark)
                • Losing this memory would meaningfully degrade future answers
                ⚠ ANTI-DILUTION: When importance="high", you MUST set
                  assertion = verbatim_quote VERBATIM. Do NOT summarize,
                  rephrase, or shorten. The user's exact words are the assertion.

  - "medium" — Useful reference but not critical. Use when:
                • Configuration parameters, secondary preferences, project details
                • candidate_type is "Preference" with a stable but non-core habit
                • Useful context that improves answer quality but is not decisive
                • Default level when unsure between medium and low

  - "low"    — Marginal information, for reference only. Use when:
                • Peripheral facts that rarely affect future answers
                • One-off mentions with no clear long-term relevance
                ⚠ Combine with confidence=low ONLY if the info is truly
                  noise-level — this is the scoring combination that gets dropped.

subject.name — the STABLE, REUSABLE name of the entity. CRITICAL constraints:
  - MUST be a stable entity name: a person's name, project name, product name,
    or generic label ("User", "妹妹"). NEVER include time words, verbs, or
    event descriptions in subject.name.
  - When entity_type is "User" or "Person": use only the person's name or a
    generic label ("User", "妹妹", "Eileen"). Do NOT append year, month,
    action, or scene (e.g. "User Lunch Today" or "Eileen Lunch 2026" are WRONG).
  - When entity_type is "Project": use only the project name itself. Version
    suffixes ("v2") are acceptable; event descriptions are NOT.
  - If the raw text contains year/month/verb/scene info, move that info into
    the assertion field — NEVER into subject.name.

Note: candidate_type and entity_type share some names (Decision, Task, Fact)
but live in DIFFERENT fields and are NOT interchangeable. "User" / "Person" /
"Project" / "Preference" are exclusive to ONE of the two enums — re-read
the lists above before filling them in.

Extraction rules:
- Check durable value BEFORE confidence or importance. A transient system state
  is not long-term knowledge even when its occurrence is certain or disruptive.
- Do NOT extract runtime-generated failures, expired authentication, rate limits,
  connection errors, retries, or timeouts as stable facts, preferences or tasks.
  Such diagnostics belong in execution logs, not in long-term memory.
- Preserve normal troubleshooting knowledge: verified causes, successful fixes,
  stable configuration and reusable lessons, with their scope and conditions.
  Preserve user-explicit requests to remember an incident as a dated historical
  event; never generalize that the failure is still ongoing.
- Error terms such as "401", "timeout" or "token" alone are NOT a reason to
  discard user statements, confirmed troubleshooting experience or manual saves.
- subject.name MUST be a stable, reusable entity name (person name, project
  name, product name, or generic label such as "User"). It MUST NOT contain
  time words (years, months, dates), verbs, or event/scene descriptions.
- Time, event, and scene details belong in the assertion field, NOT in
  subject.name. Example: user says "我今天午餐吃了抹茶奶冻" → subject.name="User",
  assertion="用户今天午餐吃了抹茶奶冻" (NOT subject.name="User Lunch Today").
- Only extract info that may affect future answers, decisions, recall, or
  project progress.
- User-stated info > assistant inference.
- Assistant suggestions are eligible only if the user explicitly accepts them.
- Tool results are external evidence, not user preference.
- Do NOT extract one-off questions, transient emotion, casual chat, unconfirmed
  guesses, or vague discussion.
- HIGH-priority candidate when the user uses confirmation language in any
  language: "记住" / "就这样" / "确定" / "remember this" / "go with this"
  / "let's lock that in" / "確定" / "覚えて" / "запомни".
- If new info conflicts with prior memory, emit ConflictCandidate
  (recommended_action="conflict"). Never decide deprecation here.
- Each candidate MUST cite raw event_id(s) in source_refs (at least one).
- Each candidate MUST include verbatim_quote: a <=200-char direct quote from
  the user's raw text (the sentence that justifies this candidate).
  quote_event_id is the raw event id where this quote came from.
- promotion_reason MUST be a non-empty string. It MUST briefly explain:
  (1) WHY this confidence level was chosen (e.g. "user used '记住'" / "assistant
      suggestion, user did not explicitly accept" / "hedging language '大概'");
  (2) WHY this importance level was chosen (e.g. "core project decision" /
      "peripheral config detail" / "stable long-term preference");
  (3) the key signal that triggered extraction (e.g. confirmation keyword,
      negation token, conflict with prior memory).
  When recommended_action="conflict", also name the type of prior memory this
  contradicts (e.g. "conflicts with prior Decision about X").
  NEVER leave promotion_reason as an empty string.
- Output MUST be valid JSON only. No prose, no markdown fences, no leading
  or trailing commentary.
- HARD LIMIT: at most {max_candidates} candidates per batch. If more,
  prioritize highest importance + confidence and add a final entry with
  title="__cap_warning__" and assertion="batch truncated, N original candidates".

Anti-dilution rules (CRITICAL — violating these makes the output unusable):
- When importance="high", set assertion = verbatim_quote VERBATIM. Do NOT
  summarize, rephrase, or shorten. The user's exact words are the assertion.
- When the user statement contains negation ("不", "not", "won't", "avoid",
  "暂不", "先...再...", "first...then..."), preserve the negation/qualifier
  verbatim in assertion. Do NOT paraphrase negations away.
  Example BAD : "decided to use enhancement mode"
  Example GOOD: "decided to use enhancement mode first, NOT replace mode"
- When the user statement contains scope qualifiers ("only for X", "in case
  of Y", "for the prototype"), preserve them in assertion.

{few_shot}

Now process the actual input. Output JSON only.

INPUT (raw events to extract from):
{events_json}

OUTPUT:
"""


def render_prompt(events_json: str, *, max_candidates: int = 20) -> str:
    """Render the full Candidate Extractor prompt for a batch of raw events.

    Args:
        events_json: JSON-serialized list of raw events. Caller is
            responsible for trimming / batching to fit the model's context
            window.
        max_candidates: Hard cap on the number of candidates the LLM may
            emit per batch. Embedded into the prompt's HARD LIMIT clause.

    Returns:
        The complete prompt string ready to pass to ``LLMClient.call_llm``.
    """
    return _PROMPT_BODY_TEMPLATE.format(
        max_candidates=max_candidates,
        few_shot=_FEW_SHOT_EXAMPLES,
        events_json=events_json,
    )


def render_retry_prompt(original_prompt: str, malformed_output: str) -> str:
    """Render a retry prompt after the first attempt produced unparseable JSON.

    Strategy: keep the original prompt context but be very explicit about
    what went wrong. Avoid re-issuing few-shot examples to save tokens.
    """
    return (
        original_prompt
        + "\n\n"
        + (
            "----\n"
            "Your previous response was not valid JSON. Below is what you returned:\n"
            "----\n"
            f"{malformed_output[:1000]}\n"
            "----\n"
            "Reply ONLY with a valid JSON object matching the schema. "
            "No markdown fences. No commentary. JSON only.\n"
        )
    )
