/**
 * Decide whether a scrollTop decrease should leave follow mode.
 *
 * Tiny dips (Safari reflow / sub-pixel) while still in the bottom sticky zone
 * must NOT leave follow mode. Clear upward movement — even inside that zone —
 * must enter free mode, otherwise ResizeObserver follow-pins yank the user
 * back to the bottom and "scroll up to load earlier" never works.
 *
 * Exception: a scroll-up whose *resulting* position is still within the bottom
 * band (`gapToBottom <= atBottomBandPx`) is a layout clamp — the browser
 * rewrote scrollTop because the viewport grew or content shrank (e.g. closing
 * the file dock returns the chat to full height). That is not user intent and
 * must not surface the ↓ control while the user is still pinned to the bottom.
 */
export function shouldEnterFreeModeOnScrollUp(opts: {
  upDelta: number;
  atBottom: boolean;
  /** Distance from the bottom at the scroll's resulting position. */
  gapToBottom: number;
  /** Ignore sub-pixel / reflow noise. */
  intentionalUpPx?: number;
  /** Scroll-ups landing within this band count as "still at the bottom". */
  atBottomBandPx?: number;
}): boolean {
  const intentionalUpPx = opts.intentionalUpPx ?? 8;
  const atBottomBandPx = opts.atBottomBandPx ?? 12;
  if (opts.upDelta <= 1) return false;
  if (opts.gapToBottom <= atBottomBandPx) return false;
  if (!opts.atBottom) return true;
  return opts.upDelta >= intentionalUpPx;
}
