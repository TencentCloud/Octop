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

/**
 * Footer + elapsed timer phase for the unified generating indicator.
 * Elapsed only while we are still waiting for the first assistant bubble.
 */
export function chatGeneratingPhase(opts: {
  isStreaming: boolean;
  loading?: boolean;
  lastMessageRole?: string | null;
  hasLiveSpeakers?: boolean;
}): {
  showFooter: boolean;
  showElapsed: boolean;
  membersOnly: boolean;
} {
  const showFooter = shouldShowGenerating(opts);
  const membersOnly = Boolean(
    showFooter && !opts.isStreaming && opts.hasLiveSpeakers,
  );
  const showElapsed = Boolean(
    showFooter &&
      !membersOnly &&
      (!opts.lastMessageRole || opts.lastMessageRole === "user"),
  );
  return { showFooter, showElapsed, membersOnly };
}
