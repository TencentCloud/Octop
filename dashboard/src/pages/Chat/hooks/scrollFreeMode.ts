/**
 * Decide whether a scrollTop decrease should leave follow mode.
 *
 * Tiny dips (Safari reflow / sub-pixel) while still in the bottom sticky zone
 * must NOT leave follow mode. Clear upward movement — even inside that zone —
 * must enter free mode, otherwise ResizeObserver follow-pins yank the user
 * back to the bottom and "scroll up to load earlier" never works.
 */
export function shouldEnterFreeModeOnScrollUp(opts: {
  upDelta: number;
  atBottom: boolean;
  /** Ignore sub-pixel / reflow noise. */
  intentionalUpPx?: number;
}): boolean {
  const intentionalUpPx = opts.intentionalUpPx ?? 8;
  if (opts.upDelta <= 1) return false;
  if (!opts.atBottom) return true;
  return opts.upDelta >= intentionalUpPx;
}
