/**
 * Gate for "scroll up → load earlier messages" (MessageList canLoadOlderRef).
 *
 * Session switches must disarm first; history-ready re-arms when messages exist
 * and initial loading is done. Keep these as separate effect ticks in that order.
 */
export function nextCanLoadOlder(opts: {
  kind: "session-reset" | "history-ready";
  loading: boolean;
  messageCount: number;
}): boolean {
  if (opts.kind === "session-reset") return false;
  return !opts.loading && opts.messageCount > 0;
}

/** Whether the MessageList load-more latch should clear after onLoadMoreHistory. */
export function shouldReleaseLoadMoreLatch(started: boolean | void): boolean {
  return started === false;
}

/**
 * Non-overflow auto-fill of older pages. Must NOT take isStreaming — users need
 * to grow the thread while a reply is in flight (scroll-up / short lists).
 */
export function shouldAutoFillOlderHistory(opts: {
  historyHasMore: boolean;
  historyLoadingMore: boolean;
  loading: boolean;
  canLoadOlder: boolean;
}): boolean {
  return (
    opts.historyHasMore &&
    !opts.historyLoadingMore &&
    !opts.loading &&
    opts.canLoadOlder
  );
}
