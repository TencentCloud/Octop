/** Resolve composer connector selection on catalog load. */
export function resolveInitialConnectors(opts: {
  prev: string[];
  saved: string[];
  /** When true, respect saved even if empty (user cleared defaults). */
  hasSaved: boolean;
  defaults: string[];
  allowed: Set<string>;
}): string[] {
  const { prev, saved, hasSaved, defaults, allowed } = opts;
  if (prev.length > 0) {
    return prev.filter((n) => allowed.has(n));
  }
  if (hasSaved) {
    return saved.filter((n) => allowed.has(n));
  }
  return defaults.filter((n) => allowed.has(n));
}
