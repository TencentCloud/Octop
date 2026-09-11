/** Stable dock tab id for a knowledge-base citation document. */
export function dockKnowledgeTabId(kbId: string, docId: string): string {
  return `knowledge:${kbId}:${docId}`;
}
