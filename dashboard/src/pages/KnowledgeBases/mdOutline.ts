/**
 * Markdown outline (table of contents) extraction for the KB preview.
 *
 * Walks ATX headings (``# … ######``) outside fenced code blocks and records,
 * per item, which occurrence of its title it is — the preview sidebar uses
 * that to scroll to the exact rendered heading even when titles repeat.
 */

export interface MdOutlineItem {
  /** 1-6, from the leading ``#`` run. */
  level: number;
  title: string;
  /** 0-based occurrence of this exact title among non-fence headings. */
  occurrence: number;
}

/** Normalize heading text for TOC display and scroll matching: unescape
 *  markdown escapes, drop bold/italic/code markers, collapse spaces. */
export function stripMdInlineMarks(text: string): string {
  return text
    .replace(/\\(.)/g, "$1")
    .replace(/[*_`~]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function extractMarkdownOutline(content: string): MdOutlineItem[] {
  const items: MdOutlineItem[] = [];
  const seen = new Map<string, number>();
  let inFence = false;
  for (const line of content.split("\n")) {
    if (/^\s{0,3}(```|~~~)/.test(line)) {
      inFence = !inFence;
      continue;
    }
    if (inFence) continue;
    const match = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
    if (!match) continue;
    const title = stripMdInlineMarks(match[2].replace(/\s*#+\s*$/, "").trim());
    if (!title) continue;
    const occurrence = seen.get(title) ?? 0;
    seen.set(title, occurrence + 1);
    items.push({ level: match[1].length, title, occurrence });
  }
  return items;
}
