/**
 * Drop live frames that belong to another dashboard thread (anti-串流).
 * Frames without ``thread_id`` still pass — ping/pong and some error paths.
 */

export function frameBelongsToThread(frame: object, threadId: string): boolean {
  const expected = threadId.trim();
  if (!expected) return true;
  const got =
    "thread_id" in frame
      ? (frame as { thread_id?: unknown }).thread_id
      : undefined;
  if (typeof got !== "string" || !got.trim()) return true;
  return got.trim() === expected;
}
