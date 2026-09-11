/** Resolve composer connector selection on catalog load. */
export function resolveInitialConnectors(opts: {
  prev: string[];
  saved: string[];
  /** When true, respect saved even if empty (user cleared defaults). */
  hasSaved: boolean;
  defaults: string[];
  allowed: Set<string>;
  /** Ignore in-memory selection (new empty chat should re-apply defaults). */
  ignorePrev?: boolean;
  /** Ignore per-agent localStorage (new chats should not reuse last turn). */
  ignoreSaved?: boolean;
  /** Trust prev even when empty (user opted out in this session). */
  preferPrev?: boolean;
}): string[] {
  const {
    prev,
    saved,
    hasSaved,
    defaults,
    allowed,
    ignorePrev,
    ignoreSaved,
    preferPrev,
  } = opts;
  if (preferPrev || (!ignorePrev && prev.length > 0)) {
    return prev.filter((n) => allowed.has(n));
  }
  if (!ignoreSaved && hasSaved) {
    return saved.filter((n) => allowed.has(n));
  }
  return defaults.filter((n) => allowed.has(n));
}
