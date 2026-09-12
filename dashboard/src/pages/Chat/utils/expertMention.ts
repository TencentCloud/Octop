/**
 * Composer helpers for expert / subagent @mentions.
 *
 * harness-agent no longer intercepts ``target_agent_ids``; the host must put
 * ``@Name`` in the user message so the model can call ``ask_agent`` (teammate)
 * or ``task`` (workspace subagent).
 */

export function expertMentionToken(name: string): string {
  const token = name.trim().replace(/\s+/g, "-");
  return token ? `@${token}` : "";
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** ``@Name`` as a whole token (start / whitespace bounded). */
export function expertMentionPattern(name: string): RegExp {
  const token = expertMentionToken(name);
  return new RegExp(`(^|\\s)${escapeRegExp(token)}(?=\\s|$)`);
}

export function textHasExpertMention(text: string, name: string): boolean {
  const token = expertMentionToken(name);
  if (!token) return false;
  return expertMentionPattern(name).test(text);
}

export function mentionedExpertIds(
  text: string,
  experts: Array<{ agent_id: string; name: string }>,
): string[] {
  return experts
    .filter((expert) => textHasExpertMention(text, expert.name))
    .map((expert) => expert.agent_id);
}

/** Subagent ``task`` names are slugs (e.g. ``@researcher``). */
export function mentionedSubagentSlugs(
  text: string,
  subagents: Array<{ slug: string }>,
): string[] {
  return subagents
    .filter((subagent) => textHasExpertMention(text, subagent.slug))
    .map((subagent) => subagent.slug);
}

/** Replace a trailing ``@query`` (from the mention picker) with ``@Name ``. */
export function replaceMentionQuery(
  text: string,
  atIndex: number,
  query: string,
  name: string,
): { text: string; cursor: number } {
  const token = expertMentionToken(name);
  const before = text.slice(0, atIndex);
  const after = text.slice(atIndex + 1 + query.length);
  if (!token) {
    const next = `${before}${after}`.replace(/^\s+/, "");
    return { text: next, cursor: before.length };
  }
  if (textHasExpertMention(`${before} ${after}`, name)) {
    const next = `${before}${after.replace(/^\s*/, "")}`;
    return { text: next, cursor: before.length };
  }
  const next = `${before}${token} ${after.replace(/^\s*/, "")}`;
  return { text: next, cursor: before.length + token.length + 1 };
}

/** Insert ``@Name ``, or remove it if already present. */
export function toggleExpertMention(
  text: string,
  name: string,
): { text: string; cursor: number } {
  const token = expertMentionToken(name);
  if (!token) return { text, cursor: text.length };

  const pattern = expertMentionPattern(name);
  const match = pattern.exec(text);
  if (match) {
    const prefix = match[1] ?? "";
    const start = match.index + prefix.length;
    const end = start + token.length;
    const after = text.slice(end);
    const eatenAfter = after.startsWith(" ") ? after.slice(1) : after;
    const next = `${text.slice(0, start)}${eatenAfter}`.replace(/ {2,}/g, " ");
    const trimmed = next.replace(/^\s+/, "");
    return { text: trimmed, cursor: Math.min(start, trimmed.length) };
  }

  const trimmed = text.trimEnd();
  const next = trimmed ? `${trimmed} ${token} ` : `${token} `;
  return { text: next, cursor: next.length };
}

/** Restore ``@Name`` tokens for queued messages that only stored agent ids. */
export function ensureExpertMentions(
  text: string,
  agentIds: string[],
  experts: Array<{ agent_id: string; name: string }>,
): string {
  let next = text;
  for (const id of agentIds) {
    const expert = experts.find((item) => item.agent_id === id);
    if (!expert) continue;
    if (!textHasExpertMention(next, expert.name)) {
      next = toggleExpertMention(next, expert.name).text;
    }
  }
  return next;
}
