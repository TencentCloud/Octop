import type { KnowledgeCitation } from "./parseKnowledgeCitations";
import { knowledgePathParent, normalizeKnowledgePath } from "./knowledgePath";

/** Deep-link into Knowledge Bases for a citation. */
export function knowledgeCitationHref(citation: KnowledgeCitation): string {
  const params = new URLSearchParams();
  if (citation.kbId) params.set("kb", citation.kbId);
  if (citation.docId) params.set("doc", citation.docId);
  const qs = params.toString();
  return qs ? `/knowledge-bases?${qs}` : "/knowledge-bases";
}

/** Parent directory of a citation path; empty at KB root. */
export function knowledgeCitationDirectory(
  path: string | null | undefined,
): string {
  if (!path) return "";
  try {
    return knowledgePathParent(path);
  } catch {
    return "";
  }
}

/**
 * Hover tooltip: ``KB · path`` when path is known, else ``KB · filename``.
 */
export function knowledgeCitationTooltip(citation: KnowledgeCitation): string {
  const fileLabel = (() => {
    if (citation.path) {
      try {
        return normalizeKnowledgePath(citation.path) || citation.filename;
      } catch {
        return citation.filename;
      }
    }
    return citation.filename;
  })();
  if (citation.kbName) {
    return `${citation.kbName} · ${fileLabel}`;
  }
  return fileLabel;
}

/**
 * True when tooltip adds info beyond the chip (nested path / directory).
 * Truncation is detected in the chip UI separately.
 */
export function knowledgeCitationHasNestedPath(
  citation: KnowledgeCitation,
): boolean {
  return Boolean(knowledgeCitationDirectory(citation.path));
}
