/**
 * Window sizing shared by the Early Window and the Dashboard window.
 *
 * The floor keeps the desktop layout intact: the Dashboard falls back to its
 * mobile layout under 767px, and the sidebar already spends 220px of the width,
 * so anything narrower would not be a window the app knows how to fill.
 */
export const MIN_WINDOW_SIZE = { width: 960, height: 600 } as const;

/** Size of the Dashboard window on first launch (it is not persisted yet). */
export const DEFAULT_WINDOW_SIZE = { width: 1280, height: 800 } as const;
