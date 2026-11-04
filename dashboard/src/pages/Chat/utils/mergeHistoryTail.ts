import type { HistoryReceipts } from "../../../api/modules/octopThreads";
import type { ChatMessage } from "../hooks/sseHelpers";

function lastUserIndex(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") return i;
  }
  return -1;
}

/** Keep every unconfirmed send, including a turn followed by another send. */
export function inFlightTail(messages: ChatMessage[]): ChatMessage[] {
  const pending = messages.findIndex((m) => m.role === "user" && m.delivery);
  const index = pending >= 0 ? pending : lastUserIndex(messages);
  return index < 0 ? messages : messages.slice(index);
}

export function compareServerOrder(a: ChatMessage, b: ChatMessage): number {
  if (!a.serverOrder || !b.serverOrder) return 0;
  return (
    a.serverOrder[0] - b.serverOrder[0] || a.serverOrder[1] - b.serverOrder[1]
  );
}

/** Incoming persisted rows replace duplicates, including a misplaced cached copy. */
export function mergeOrderedMessages(
  existing: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const rows = new Map(existing.map((m) => [m.id, m]));
  for (const message of incoming) rows.set(message.id, message);
  return [...rows.values()].sort(compareServerOrder);
}

/** A cached transcript cannot establish that a turn is newer than a server page. */
export function preferLocalTranscript(
  memory: ChatMessage[],
  cached: ChatMessage[] | null | undefined,
): ChatMessage[] {
  if (!cached?.length || !memory.length) return memory;
  const userIndex = lastUserIndex(memory);
  const cachedUser = lastUserIndex(cached);
  if (
    userIndex < 0 ||
    cachedUser < 0 ||
    memory[userIndex].id !== cached[cachedUser].id
  )
    return memory;
  if (memory.length === userIndex + 1)
    return [...memory, ...cached.slice(cachedUser + 1)];
  return memory;
}

/** Only explicit durable confirmation can retire a cached turn. */
export function serverCaughtUp(
  loaded: ChatMessage[],
  cached: ChatMessage[],
  receipts: HistoryReceipts = {},
): boolean {
  if (!cached.length) return true;
  const users = cached.filter((m) => m.role === "user");
  return (
    users.length > 0 &&
    users.every(
      (user) =>
        receipts[user.id]?.persisted ||
        loaded.some((m) => m.id === user.id && m.turnStatus === "complete"),
    )
  );
}

/** Preserve only a contiguous, already persisted prefix and its paging cursor. */
export function retainedHistoryPrefix(
  loaded: ChatMessage[],
  current: ChatMessage[],
): ChatMessage[] {
  const ids = new Set(loaded.map((m) => m.id));
  const overlap = current.findIndex((m) => ids.has(m.id));
  if (overlap <= 0) return [];
  const prefix = current.slice(0, overlap);
  const positioned = loaded.some((m) => m.serverOrder);
  if (positioned && !current[overlap].serverOrder) return [];
  return prefix.every(
    (m) =>
      !m.delivery && m.status !== "streaming" && (!positioned || m.serverOrder),
  )
    ? prefix
    : [];
}

export interface HistoryMergeOptions {
  isStreaming?: boolean;
  /** Explicit sends created in this running store, never inferred from a cache. */
  pendingUserIds?: ReadonlySet<string>;
  receipts?: HistoryReceipts;
}

/** Server pages own chronology. Only identified local sends can extend the tail. */
export function mergeHistoryWithLocalTail(
  loaded: ChatMessage[],
  current: ChatMessage[],
  options: HistoryMergeOptions | boolean = {},
): ChatMessage[] {
  const opts =
    typeof options === "boolean" ? { isStreaming: options } : options;
  const receipts = opts.receipts ?? {};
  const prefix = retainedHistoryPrefix(loaded, current);
  let result = mergeOrderedMessages(prefix, loaded);
  const pendingIds =
    opts.pendingUserIds ??
    new Set(current.filter((m) => m.delivery).map((m) => m.id));

  for (let i = 0; i < current.length; i++) {
    const user = current[i];
    if (user.role !== "user") continue;
    let end = i + 1;
    while (end < current.length && current[end].role !== "user") end++;
    const tail = current.slice(i, end);
    const index = result.findIndex((m) => m.id === user.id);
    const receipt = receipts[user.id];
    if (receipt?.persisted) continue;
    if (index < 0) {
      const order = receipt?.server_order ?? user.serverOrder;
      const lastStored = loaded.filter((m) => m.serverOrder).at(-1);
      if (
        order &&
        lastStored &&
        compareServerOrder({ ...user, serverOrder: order }, lastStored) <= 0
      )
        continue;
      if (pendingIds.has(user.id) && receipt?.state !== "stored") {
        result = [
          ...result,
          ...tail.filter((m) => !result.some((r) => r.id === m.id)),
        ];
      }
      continue;
    }
    let serverEnd = index + 1;
    while (serverEnd < result.length && result[serverEnd].role !== "user")
      serverEnd++;
    if (serverEnd < result.length) continue;
    const status = result[index].turnStatus;
    if (status === "complete") continue;
    if (user.delivery)
      result[index] = {
        ...result[index],
        delivery: user.delivery,
        turnId: user.turnId,
      };
    const localLive =
      opts.isStreaming || tail.some((m) => m.status === "streaming");
    if (tail.length > 1 && (localLive || serverEnd === index + 1)) {
      result = [...result.slice(0, index + 1), ...tail.slice(1)];
    }
  }
  return result;
}
