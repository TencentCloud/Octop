/**
 * Gates for weak stream resume. Keep scroll / history-UX independent: only
 * keep isStreaming when a real turn is expected, limit reconnect thrash.
 */

/** Max auto re-subscribe attempts after an unexpected WS drop. */
export const MAX_STREAM_RESUME_ATTEMPTS = 8;

/**
 * Seal a sticky local stream when the socket is gone long enough that resume
 * is unlikely. Open sockets are exempt (long tool/thinking runs emit no tokens).
 */
export const STREAM_STALE_WITHOUT_SOCKET_MS = 20_000;

/**
 * Whether an unexpected WS close should keep the local stream open and
 * re-subscribe, instead of sealing the turn as finished.
 */
export function shouldResumeStreamAfterClose(opts: {
  intentionalClose: boolean;
  isStreaming: boolean;
  threadId: string | null | undefined;
  /** 0-based attempt counter for this resume streak */
  attempt?: number;
  maxAttempts?: number;
  /**
   * When set, only reconnect for the chat tab the user is looking at.
   * Background threads keep isStreaming but skip thrash reconnect.
   */
  sessionFocused?: boolean;
}): boolean {
  const tid = (opts.threadId || "").trim();
  const max = opts.maxAttempts ?? MAX_STREAM_RESUME_ATTEMPTS;
  const attempt = opts.attempt ?? 0;
  if (attempt >= max) return false;
  if (opts.sessionFocused === false) return false;
  return (
    !opts.intentionalClose &&
    opts.isStreaming &&
    tid.length > 0 &&
    tid !== "__empty__"
  );
}

/** History page hints that a turn may still be running server-side. */
export function historySuggestsActiveTurn(
  messages: Array<{ role: string; status?: string }>,
): boolean {
  if (messages.length === 0) return false;
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.status === "streaming") return true;
    if (m.role === "user") return true;
    if (m.role === "assistant" || m.role === "tool" || m.role === "system") {
      // Finished assistant/tool streak — no need to open a probe socket.
      if (m.role === "assistant") return false;
      continue;
    }
  }
  return false;
}

/**
 * When to open a subscribe probe after history is available.
 *
 * - already streaming: rebind after SPA remount / drop
 * - first hydrate: only when messages suggest mid-turn (avoids idle WS thrash)
 */
export function shouldProbeActiveTurn(opts: {
  isStreaming: boolean;
  justHydrated: boolean;
  /** From historySuggestsActiveTurn; only used on first hydrate. */
  historySuggestsActive?: boolean;
}): boolean {
  if (opts.isStreaming) return true;
  if (!opts.justHydrated) return false;
  return Boolean(opts.historySuggestsActive);
}

/**
 * Overscroll refresh / force-reload must not be frozen by sticky isStreaming
 * after a dropped socket. Only block while a live socket is bound.
 */
export function shouldBlockHistoryRefresh(opts: {
  isStreaming: boolean;
  hasLiveSocket: boolean;
}): boolean {
  return opts.isStreaming && opts.hasLiveSocket;
}

/**
 * Force-seal when local stream looks alive but no socket remains past the
 * reconnect grace window.
 */
export function shouldForceSealStream(opts: {
  isStreaming: boolean;
  hasLiveSocket: boolean;
  lastActivityAt: number | null;
  now: number;
  staleWithoutSocketMs?: number;
  /** Unfocused background threads pause auto-seal (reattach on focus). */
  sessionFocused?: boolean;
}): boolean {
  if (!opts.isStreaming) return false;
  if (opts.hasLiveSocket) return false;
  if (opts.sessionFocused === false) return false;
  const grace = opts.staleWithoutSocketMs ?? STREAM_STALE_WITHOUT_SOCKET_MS;
  if (opts.lastActivityAt == null) return true;
  return opts.now - opts.lastActivityAt >= grace;
}

/** Toast once after a non-zero resume attach rebinds a live turn. */
export function shouldEmitStreamResumeNotice(opts: {
  resumeAttempt: number;
  turnActive: boolean;
}): boolean {
  return opts.resumeAttempt > 0 && opts.turnActive;
}
