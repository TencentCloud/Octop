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
