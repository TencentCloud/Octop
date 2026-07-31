/**
 * Whether the chat footer should show the unified "generating" indicator.
 * One bottom status for the whole turn (no separate thinking / continuing).
 */
export function shouldShowGenerating(opts: {
  isStreaming: boolean;
  loading?: boolean;
}): boolean {
  return Boolean(opts.isStreaming && !opts.loading);
}

/**
 * Footer + elapsed timer phase for the unified generating indicator.
 * Elapsed only while we are still waiting for the first assistant bubble.
 */
export function chatGeneratingPhase(opts: {
  isStreaming: boolean;
  loading?: boolean;
  lastMessageRole?: string | null;
}): { showFooter: boolean; showElapsed: boolean } {
  const showFooter = shouldShowGenerating(opts);
  const showElapsed = Boolean(
    showFooter &&
      (!opts.lastMessageRole || opts.lastMessageRole === "user"),
  );
  return { showFooter, showElapsed };
}
