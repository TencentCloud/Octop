"""Prompt v1 for the EntityPage regenerator.

Anchored to:
- D36-A — single JSON output containing summary + headline + topics
- D37-B — full prompt with all atoms (no incremental diff in M3)
- D34-A — explicit ``## My Notes`` heading is reserved for the user;
  the LLM is told never to invent or modify that section.

Edit ``PAGE_REGEN_VERSION`` whenever the prompt body changes; the
regenerator persists this string on the journal entry so future replay
can attribute outputs to the prompt version that produced them.
"""

from __future__ import annotations

PAGE_REGEN_VERSION = "page_v1.1"
"""Version tag stored on every page_regen journal entry.

Bump when:
- Body text below changes (rules, instructions)
- Output JSON schema changes
- Few-shot examples change in ways that affect output

Do NOT bump for whitespace / comment changes.
"""


_PROMPT_BODY = """\
You are an Entity Page Summarizer. Read a list of atomic facts (atoms)
about ONE entity and produce a single concise markdown summary.

OUTPUT FORMAT (STRICT — JSON only, no prose, no markdown fences):

{{
  "headline": "<= 30 characters, one line, no trailing period",
  "summary_markdown": "<full markdown body; see rules below>",
  "topics": ["<keyword>", "<keyword>", ...]
}}

Rules:

1. summary_markdown structure:
   - Open with one short paragraph describing the entity in 1-3 sentences.
   - Group remaining atoms under ``### `` subheadings if there are
     more than 4 atoms; otherwise a flat bullet list is fine.
   - Cite each atom inline using its short id in parentheses, e.g.
     ``(atom-1234)``. Use the id provided in the input.
   - Total length: aim for under 300 words. Verbosity is a bug.

2. NEVER write a ``## My Notes`` section. That heading is reserved
   exclusively for the human user; if it appears in the input it has
   already been stripped before you see this prompt. Your output MUST
   NOT contain the string ``## My Notes`` anywhere.

3. headline is a one-line plain-text gist used for hot recall — no
   markdown, no period, no quotes around it. Keep it under 30 chars.

4. topics is a flat list of 1-5 short keywords (no spaces) extracted
   from the atoms. Used by the M4 query router.

5. Preserve negations and qualifiers verbatim from atom assertions
   (do NOT paraphrase ``decided NOT to use X`` into ``decided to use X``).

6. If the atoms contradict each other, mention the contradiction
   explicitly in summary_markdown but do NOT pick a winner.

7. If the atom list is empty, output:
   {{"headline": "", "summary_markdown": "", "topics": []}}

8. LANGUAGE: write ``summary_markdown`` and ``headline`` in the same
   language the user uses in the atom assertions (e.g. Chinese atoms →
   Chinese summary). If the language is mixed or ambiguous, default to
   Simplified Chinese (简体中文). ``topics`` keywords should reuse the
   atoms' own wording. ``atom-id`` citations stay verbatim regardless.

ENTITY:
- canonical_name: {canonical_name}
- entity_type: {entity_type}

ATOMS (newest first; cite by id):
{atoms_json}

OUTPUT:
"""


def render_page_regen_prompt(
    *,
    canonical_name: str,
    entity_type: str,
    atoms_json: str,
) -> str:
    """Render the regen prompt for one entity.

    Args:
        canonical_name: Entity canonical name (D34/D36 — informs the LLM
            who/what the page is about).
        entity_type: One of ``EntityType`` literal values.
        atoms_json: JSON-serialised list of ``{id, importance, confidence,
            assertion, verbatim_quote, occurred_at}`` objects, newest
            first. Caller is responsible for trimming to budget.
    """
    return _PROMPT_BODY.format(
        canonical_name=canonical_name,
        entity_type=entity_type,
        atoms_json=atoms_json,
    )


__all__ = ["PAGE_REGEN_VERSION", "render_page_regen_prompt"]
