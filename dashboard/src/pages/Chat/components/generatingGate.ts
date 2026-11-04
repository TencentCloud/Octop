/**
 * Whether the chat footer should show the unified "generating" indicator.
 * One bottom status for the whole turn (no separate thinking / continuing).
 *
 * Team rooms clear ``isStreaming`` when the host unlocks the composer, but
 * members may still be generating — ``hasLiveSpeakers`` keeps the footer up.
 *
 * Stop/cancel lives only on the composer send button — this footer is status
 * text only, so it can stay visible for the entire live turn.
 */
export function shouldShowGenerating(opts: {
  isStreaming: boolean;
  loading?: boolean;
  /** Speakers still producing tokens/tools after the host turn settled. */
  hasLiveSpeakers?: boolean;
}): boolean {
  const live = Boolean(opts.isStreaming) || Boolean(opts.hasLiveSpeakers);
  return Boolean(live && !opts.loading);
}

/** Assistant row that has no text, tool, or thinking yet (decision stamp only). */
export function isInvisibleAssistantPlaceholder(message: {
  role: string;
  content?: string;
  toolData?: unknown;
  hitlData?: unknown;
  status?: string;
  attachments?: unknown[] | null;
  contentBlocks?: Array<{ content?: string }> | null;
}): boolean {
  if (message.role !== "assistant") return false;
  if (message.toolData || message.hitlData) return false;
  if (message.status === "error") return false;
  if ((message.content || "").trim()) return false;
  if ((message.attachments?.length ?? 0) > 0) return false;
  if (message.contentBlocks?.some((block) => (block.content || "").trim())) {
    return false;
  }
  return true;
}

/**
 * True until this turn has something to draw besides the footer status.
 * A decision-only placeholder must not count, or the elapsed label flips
 * and the avatar stays hidden until the first tool or token.
 */
export function awaitingVisibleAssistantReply(
  messages: Array<{
    role: string;
    content?: string;
    toolData?: unknown;
    hitlData?: unknown;
    status?: string;
    attachments?: unknown[] | null;
    contentBlocks?: Array<{ content?: string }> | null;
  }>,
): boolean {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "user") return true;
    if (message.role === "tool") return false;
    if (
      message.role === "assistant" &&
      !isInvisibleAssistantPlaceholder(message)
    ) {
      return false;
    }
  }
  return true;
}

/**
 * Footer + elapsed timer phase for the unified generating indicator.
 * Elapsed only while we are still waiting for the first visible assistant row.
 */
export function chatGeneratingPhase(opts: {
  isStreaming: boolean;
  loading?: boolean;
  lastMessageRole?: string | null;
  hasLiveSpeakers?: boolean;
  /** Overrides the role check when a decision-only placeholder is already stored. */
  awaitingVisibleReply?: boolean;
}): {
  showFooter: boolean;
  showElapsed: boolean;
  membersOnly: boolean;
} {
  const showFooter = shouldShowGenerating(opts);
  const membersOnly = Boolean(
    showFooter && !opts.isStreaming && opts.hasLiveSpeakers,
  );
  const stillWaiting =
    opts.awaitingVisibleReply ??
    (!opts.lastMessageRole || opts.lastMessageRole === "user");
  const showElapsed = Boolean(showFooter && !membersOnly && stillWaiting);
  return { showFooter, showElapsed, membersOnly };
}
