/** Queue a knowledge base to attach when Chat next mounts. */
let pendingAttachKnowledgeBaseId = "";

/** Remember a knowledge-base id to select in the composer after navigating to chat. */
export function setPendingAttachKnowledgeBaseId(id: string): void {
  pendingAttachKnowledgeBaseId = id.trim();
}

/** Read the queued knowledge-base id without clearing it. */
export function peekPendingAttachKnowledgeBaseId(): string {
  return pendingAttachKnowledgeBaseId;
}

/** Consume the queued knowledge-base id (clears after reading). */
export function consumePendingAttachKnowledgeBaseId(): string {
  const id = pendingAttachKnowledgeBaseId;
  pendingAttachKnowledgeBaseId = "";
  return id;
}
