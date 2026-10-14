/**
 * listOrder - manual ordering + pinning for sidebar lists (experts / teams).
 *
 * Pure helpers shared by the classic SessionList and the minimal nav so both
 * layouts use identical ordering semantics and can be unit-tested without
 * React.
 *
 * Persisted state shape:
 *   - ``pinned``: membership list (who is pinned).
 *   - ``order``:  full id sequence the user arranged (pinned group first).
 *     Pin membership is a set — the render order of pinned items follows
 *     their position inside ``order``.
 */

export interface ListOrderState {
  pinned: string[];
  order: string[];
}

export const EMPTY_LIST_ORDER: ListOrderState = { pinned: [], order: [] };

/** Tolerant parse of the persisted JSON blob; anything unusable → empty. */
export function parseListOrder(raw: string | null): ListOrderState {
  if (!raw) return { pinned: [], order: [] };
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return { pinned: [], order: [] };
    }
    const obj = parsed as Record<string, unknown>;
    return {
      pinned: normalizeIdList(obj.pinned),
      order: normalizeIdList(obj.order),
    };
  } catch {
    return { pinned: [], order: [] };
  }
}

function normalizeIdList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of value) {
    if (typeof item !== "string" || item.length === 0 || seen.has(item)) {
      continue;
    }
    seen.add(item);
    out.push(item);
  }
  return out;
}

/**
 * Merge a known manual sequence with the fresh id list (default order):
 *   - stale ids (deleted items) are dropped;
 *   - still-existing ids keep their manual sequence;
 *   - brand-new ids are appended (in incoming order) after the manual block.
 */
export function mergeOrder(
  known: readonly string[],
  incoming: readonly string[],
): string[] {
  const knownSet = new Set(known);
  const incomingSet = new Set(incoming);
  const kept = known.filter((id) => incomingSet.has(id));
  const keptSet = new Set(kept);
  const fresh = incoming.filter((id) => !knownSet.has(id) && !keptSet.has(id));
  return [...kept, ...fresh];
}

/**
 * Default order is the base; the user-arranged sequence overrides it.
 * Items never arranged keep their default relative order after the manual
 * block. Falls back to ``defaults`` when ``order`` is empty.
 */
export function applyManualOrder<T>(
  defaults: readonly T[],
  order: readonly string[],
  getId: (item: T) => string,
): T[] {
  const byId = new Map<string, T>();
  for (const item of defaults) byId.set(getId(item), item);
  const seq = mergeOrder(order, defaults.map(getId));
  const out: T[] = [];
  for (const id of seq) {
    const item = byId.get(id);
    if (item !== undefined) out.push(item);
  }
  return out;
}

/** Apply both pinning (pinned group renders first) and manual order. */
export function applyListOrder<T>(
  defaults: readonly T[],
  state: ListOrderState | null | undefined,
  getId: (item: T) => string,
): T[] {
  const ordered = applyManualOrder(
    defaults,
    state?.order ?? EMPTY_LIST_ORDER.order,
    getId,
  );
  const pinnedSet = new Set(state?.pinned ?? EMPTY_LIST_ORDER.pinned);
  const pinned: T[] = [];
  const rest: T[] = [];
  for (const item of ordered) {
    (pinnedSet.has(getId(item)) ? pinned : rest).push(item);
  }
  return [...pinned, ...rest];
}

/** Toggle ``id`` in the pinned membership list. */
export function togglePinned(
  pinned: readonly string[],
  id: string,
): string[] {
  if (!id) return [...pinned];
  return pinned.includes(id)
    ? pinned.filter((x) => x !== id)
    : [...pinned, id];
}

/** Split a rendered sequence into its pinned / unpinned groups. */
export interface GroupedSequence {
  pinnedSeq: string[];
  restSeq: string[];
}

export function groupSequence(
  seq: readonly string[],
  pinned: ReadonlySet<string>,
): GroupedSequence {
  const pinnedSeq: string[] = [];
  const restSeq: string[] = [];
  for (const id of seq) {
    (pinned.has(id) ? pinnedSeq : restSeq).push(id);
  }
  return { pinnedSeq, restSeq };
}

export function joinSequence(groups: GroupedSequence): string[] {
  return [...groups.pinnedSeq, ...groups.restSeq];
}

/** Move ``id`` one step within ``seq``; null when the move is out of bounds. */
export function moveIdBy(
  seq: readonly string[],
  id: string,
  delta: number,
): string[] | null {
  const from = seq.indexOf(id);
  if (from < 0) return null;
  const to = from + delta;
  if (to < 0 || to >= seq.length) return null;
  const next = [...seq];
  next.splice(from, 1);
  next.splice(to, 0, id);
  return next;
}

/** Move ``id`` before/after ``targetId`` within ``seq``; null when unresolvable. */
export function moveIdTo(
  seq: readonly string[],
  id: string,
  targetId: string,
  placement: "before" | "after",
): string[] | null {
  if (id === targetId) return null;
  const from = seq.indexOf(id);
  if (from < 0) return null;
  const next = seq.filter((_, i) => i !== from);
  let to = next.indexOf(targetId);
  if (to < 0) return null;
  if (placement === "after") to += 1;
  next.splice(to, 0, id);
  return next;
}
