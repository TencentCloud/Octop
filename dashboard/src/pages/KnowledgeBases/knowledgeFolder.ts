/**
 * Knowledge-base folder UI helpers.
 * Path math lives in ``utils/knowledgePath``; this module re-exports it and
 * keeps DOM-aware folder-open gating for the KB page.
 */

export {
  isDirectKnowledgeChild,
  joinKnowledgePath,
  knowledgeBasename,
  knowledgeBreadcrumb,
  knowledgePathParent,
  normalizeKnowledgePath,
} from "../../utils/knowledgePath";

export function shouldOpenKnowledgeFolder(
  isDir: boolean,
  event?: { target?: EventTarget | null },
): boolean {
  if (!isDir) return false;
  const target = event?.target;
  if (target instanceof Element && target.closest("[data-kb-doc-actions]")) {
    return false;
  }
  return true;
}
