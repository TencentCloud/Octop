export interface AnchorGroup {
  messages: Array<{ id: string }>;
}

/**
 * Where an older-page prepend landed relative to the group that was first
 * when the load started.
 *
 * A send that arrives while that load is in flight grows the list at the
 * bottom. Counting every new group as a prepend shifts Virtuoso's
 * `firstItemIndex` and leaves a blank gap where the new message should be.
 */
export function prependAnchorShift(
  groups: AnchorGroup[],
  anchorId: string | null,
): { prependedGroups: number; mergedIntoFirst: boolean } {
  if (!anchorId) return { prependedGroups: 0, mergedIntoFirst: false };
  const idx = groups.findIndex((group) =>
    group.messages.some((message) => message.id === anchorId),
  );
  if (idx > 0) return { prependedGroups: idx, mergedIntoFirst: false };
  if (idx === 0 && groups[0]?.messages[0]?.id !== anchorId) {
    return { prependedGroups: 0, mergedIntoFirst: true };
  }
  return { prependedGroups: 0, mergedIntoFirst: false };
}
