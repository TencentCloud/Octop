/** Matches backend ``clip_thread_title`` max length. */
export const THREAD_TITLE_MAX = 40;

function normalizeTitleBlank(title: string | null | undefined): string {
  return (title ?? "")
    .replace(/[\r\n]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Clip a title for storage / optimistic UI (same rules as backend).
 * Longer than max → keep max-1 chars + ``…``.
 *
 * Exact-length titles without ellipsis are kept as-is (no hard-cut heuristic).
 * Legacy hard-cuts are fixed once in DB migration 003.
 */
export function clipThreadTitle(
  title: string | null | undefined,
  maxLen = THREAD_TITLE_MAX,
): string {
  const text = normalizeTitleBlank(title);
  if (!text) return "";
  if (maxLen <= 1) return "…";
  if (text.length <= maxLen) return text;
  return `${text.slice(0, maxLen - 1).replace(/\s+$/, "")}…`;
}

/**
 * Normalize a thread title for display (same clipping as storage).
 */
export function formatThreadTitle(title: string | null | undefined): string {
  return clipThreadTitle(title);
}
