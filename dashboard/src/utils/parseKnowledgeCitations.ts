/**
 * Parse knowledge-citation markers embedded in search_knowledge tool output.
 */

export type KnowledgeCitation = {
  kbId: string;
  kbName: string;
  docId: string;
  filename: string;
};

const CITATIONS_MARKER_RE =
  /\n*\s*<!--octop-kb-citations:(\[[\s\S]*?\])-->\s*$/;

function asCitation(raw: unknown): KnowledgeCitation | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const row = raw as Record<string, unknown>;
  const docId = String(row.doc_id ?? row.docId ?? "").trim();
  if (!docId) return null;
  return {
    kbId: String(row.kb_id ?? row.kbId ?? "").trim(),
    kbName: String(row.kb_name ?? row.kbName ?? "").trim(),
    docId,
    filename: String(row.filename ?? "").trim() || docId,
  };
}

/** Split tool output into display text + structured citations (if present). */
export function parseKnowledgeCitations(rawOutput: string | undefined): {
  text: string;
  citations: KnowledgeCitation[];
} {
  const raw = rawOutput ?? "";
  if (!raw) return { text: "", citations: [] };
  const match = raw.match(CITATIONS_MARKER_RE);
  if (!match) return { text: raw, citations: [] };
  const text = raw.slice(0, match.index).replace(/\s+$/, "");
  let parsed: unknown;
  try {
    parsed = JSON.parse(match[1] ?? "[]");
  } catch {
    return { text: raw, citations: [] };
  }
  if (!Array.isArray(parsed)) return { text, citations: [] };
  const citations: KnowledgeCitation[] = [];
  const seen = new Set<string>();
  for (const item of parsed) {
    const citation = asCitation(item);
    if (!citation || seen.has(citation.docId)) continue;
    seen.add(citation.docId);
    citations.push(citation);
  }
  return { text, citations };
}
