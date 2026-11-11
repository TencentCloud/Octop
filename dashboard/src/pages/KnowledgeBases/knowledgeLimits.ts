/**
 * Per-base document cap used by the knowledge-bases page.
 * `0` is the unlimited sentinel (create/edit hint and the API). A missing
 * value falls back to the instance default.
 */
export function knowledgeDocumentCap(
  maxDocuments: number | null | undefined,
  fallback: number,
): number | null {
  const max = maxDocuments ?? fallback;
  return max > 0 ? max : null;
}

export function isKnowledgeDocumentLimitReached(
  fileCount: number,
  cap: number | null,
): boolean {
  return cap !== null && fileCount >= cap;
}
