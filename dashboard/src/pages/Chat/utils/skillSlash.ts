/**
 * Skill tokens in the composer.
 *
 * UI shows ``{emoji} {label}`` (e.g. ``📦 Docker 管理``); the wire format stays
 * ``/slug`` so the agent can match the invoke. ``materializeSkillSlashes``
 * rewrites those tokens → ``/slug`` on send.
 */

/** A skill-style ``/slug`` at start or after whitespace (not a path). */
const SKILL_SLASH_TOKEN = /(?:^|[\s])(\/[a-zA-Z][\w-]*)(?=\s|$)/g;

const SKILL_SLASH_BEFORE_CURSOR = /(?:^|[\s])(\/[a-zA-Z][\w-]*)\s*$/;

/** Fallback when a skill has a friendly label but no emoji. */
const DEFAULT_SKILL_EMOJI = "✦";

export type SkillTokenRef = {
  slug: string;
  /** Friendly label shown in the composer; falls back to ``/slug``. */
  label?: string;
  /** Optional emoji shown before the label in the composer. */
  emoji?: string;
};

function normSlug(slug: string): string {
  return slug.trim().toLowerCase();
}

/** Visible token for a skill: ``emoji label`` when possible, else ``/slug``. */
export function skillComposerToken(skill: SkillTokenRef): string {
  const slug = normSlug(skill.slug);
  if (!slug) return "";
  const label = (skill.label ?? "").trim();
  if (label && label.toLowerCase() !== slug) {
    const emoji = (skill.emoji ?? "").trim() || DEFAULT_SKILL_EMOJI;
    return `${emoji} ${label}`;
  }
  return `/${slug}`;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Composer tokens that are not bare ``/slug`` (longer first for matching).
 * Includes both ``emoji label`` and bare ``label`` so older drafts still match.
 */
function labelEntries(skills: readonly SkillTokenRef[]): Array<{
  token: string;
  slug: string;
}> {
  const byToken = new Map<string, { token: string; slug: string }>();
  for (const skill of skills) {
    const slug = normSlug(skill.slug);
    if (!slug) continue;
    const full = skillComposerToken(skill);
    if (!full.startsWith("/")) {
      const key = full.toLowerCase();
      if (key && !byToken.has(key)) byToken.set(key, { token: full, slug });
    }
    const label = (skill.label ?? "").trim();
    if (label && label.toLowerCase() !== slug) {
      const key = label.toLowerCase();
      if (!byToken.has(key)) byToken.set(key, { token: label, slug });
    }
  }
  return [...byToken.values()].sort((a, b) => b.token.length - a.token.length);
}

function textHasSlashSlug(text: string, slug: string): boolean {
  const token = `/${normSlug(slug)}`;
  const re = new RegExp(`(?:^|[\\s])${escapeRegExp(token)}(?=\\s|$)`, "i");
  return re.test(text);
}

function textHasToken(text: string, token: string): boolean {
  const re = new RegExp(`(?:^|[\\s])${escapeRegExp(token)}(?=\\s|$)`, "i");
  return re.test(text);
}

/** Every skill referenced in the composer (``/slug`` or friendly token). */
export function parseSkillSlugsInText(
  text: string,
  skills: readonly SkillTokenRef[] = [],
): string[] {
  const out: string[] = [];
  const seen = new Set<string>();

  for (const match of text.matchAll(SKILL_SLASH_TOKEN)) {
    const slug = match[1].slice(1).toLowerCase();
    if (!seen.has(slug)) {
      seen.add(slug);
      out.push(slug);
    }
  }

  for (const { token, slug } of labelEntries(skills)) {
    if (seen.has(slug)) continue;
    if (textHasToken(text, token)) {
      seen.add(slug);
      out.push(slug);
    }
  }

  return out;
}

export function parseLeadingSkillSlug(
  text: string,
  skills: readonly SkillTokenRef[] = [],
): string | null {
  return parseSkillSlugsInText(text, skills)[0] ?? null;
}

/**
 * Append a skill token (``emoji label`` when available, else ``/slug``).
 * No-ops when that skill is already present.
 */
export function insertSkillSlash(
  text: string,
  skill: string | SkillTokenRef,
): string {
  const ref: SkillTokenRef =
    typeof skill === "string" ? { slug: skill } : skill;
  const slug = normSlug(ref.slug);
  if (!slug) return text;

  const token = skillComposerToken(ref);
  if (textHasSlashSlug(text, slug)) return text;
  if (parseSkillSlugsInText(text, [ref]).includes(slug)) return text;

  const pad = text.length > 0 && !/\s$/.test(text) ? " " : "";
  return `${text}${pad}${token} `;
}

/**
 * Rewrite friendly tokens to ``/slug`` for the agent. Existing ``/slug``
 * tokens are left unchanged.
 */
export function materializeSkillSlashes(
  text: string,
  skills: readonly SkillTokenRef[],
): string {
  let next = text;
  for (const { token, slug } of labelEntries(skills)) {
    const re = new RegExp(`(^|[\\s])(${escapeRegExp(token)})(?=\\s|$)`, "gi");
    next = next.replace(re, (_full, lead: string) => `${lead}/${slug}`);
  }
  return next;
}

/**
 * If Backspace would delete into a skill token (``/slug`` or friendly token),
 * remove the whole token. Returns null for normal Backspace.
 */
export function deleteSkillTokenAtCursor(
  text: string,
  cursor: number,
  skills: readonly SkillTokenRef[] = [],
): { text: string; cursor: number } | null {
  if (cursor <= 0 || cursor > text.length) return null;
  const before = text.slice(0, cursor);

  const slashMatch = before.match(SKILL_SLASH_BEFORE_CURSOR);
  if (slashMatch) {
    const token = slashMatch[1];
    const tokenStart = before.lastIndexOf(token);
    if (tokenStart >= 0) {
      return spliceToken(text, tokenStart, cursor);
    }
  }

  for (const { token } of labelEntries(skills)) {
    const trimmed = before.replace(/\s+$/, "");
    if (!trimmed.toLowerCase().endsWith(token.toLowerCase())) continue;
    const tokenStart = trimmed.length - token.length;
    if (tokenStart > 0 && !/\s/.test(trimmed[tokenStart - 1] ?? "")) {
      continue;
    }
    return spliceToken(text, tokenStart, cursor);
  }

  return null;
}

function spliceToken(
  text: string,
  tokenStart: number,
  cursor: number,
): { text: string; cursor: number } {
  let end = cursor;
  if (text[end] === " ") end += 1;
  const next = `${text.slice(0, tokenStart)}${text.slice(end)}`;
  const cleaned = next.replace(/  +/g, " ");
  return { text: cleaned, cursor: Math.min(tokenStart, cleaned.length) };
}
