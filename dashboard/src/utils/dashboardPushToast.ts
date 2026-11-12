export type DashboardPushEvent = {
  type: "dashboard_push";
  agent_id: string;
  thread_id: string;
  text: string;
  agent_name?: string;
};

export function parseDashboardPushFrame(
  raw: unknown,
): DashboardPushEvent | null {
  if (raw === null || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  if (obj.type !== "dashboard_push") return null;
  const agentId = typeof obj.agent_id === "string" ? obj.agent_id.trim() : "";
  const threadId =
    typeof obj.thread_id === "string" ? obj.thread_id.trim() : "";
  const text = typeof obj.text === "string" ? obj.text : "";
  if (!agentId || !threadId || !text.trim()) return null;
  const name = typeof obj.agent_name === "string" ? obj.agent_name.trim() : "";
  return {
    type: "dashboard_push",
    agent_id: agentId,
    thread_id: threadId,
    text,
    ...(name ? { agent_name: name } : {}),
  };
}

export function truncatePushText(text: string, max = 240): string {
  if (text.length <= max) return text;
  return `${text.slice(0, max)}…`;
}

/** How long one tab's claim suppresses a duplicate system notification. */
export const PUSH_HANDLED_TTL_MS = 2_000;

const HANDLED_PREFIX = "octop-push-handled:";
const LOCK_PREFIX = "octop-push-lock:";

export type SystemNotifyPermission =
  | "granted"
  | "denied"
  | "default"
  | "unsupported";

export type PushDelivery = {
  /** Also raise an OS notification. The in-page toast is always shown. */
  system: boolean;
  offerEnable: boolean;
};

export function resolvePushDelivery(input: {
  permission: SystemNotifyPermission;
  visible: boolean;
}): PushDelivery {
  return {
    system: input.permission === "granted" && !input.visible,
    offerEnable: input.permission === "default",
  };
}

export function readSystemNotifyPermission(
  isSecureContext: boolean,
  notification: { permission: string } | undefined,
): SystemNotifyPermission {
  if (!isSecureContext || !notification) return "unsupported";
  const { permission } = notification;
  if (
    permission === "granted" ||
    permission === "denied" ||
    permission === "default"
  ) {
    return permission;
  }
  return "unsupported";
}

export function pushDedupeKey(event: {
  thread_id: string;
  text: string;
}): string {
  return `${event.thread_id}\n${event.text}`;
}

export function systemNotificationTag(threadId: string): string {
  return `dash-push:${threadId}`;
}

function hashPushKey(key: string): string {
  let hash = 5381;
  for (let i = 0; i < key.length; i++) {
    hash = Math.imul(hash, 33) ^ key.charCodeAt(i);
  }
  return (hash >>> 0).toString(36);
}

function storageKey(prefix: string, key: string): string {
  return `${prefix}${hashPushKey(key)}`;
}

function stampFresh(raw: string | null, now: number, ttlMs: number): boolean {
  if (!raw) return false;
  const ts = Number(raw.split("@")[0]);
  return Number.isFinite(ts) && now - ts < ttlMs;
}

function sweepPushKeys(storage: Storage, now: number): void {
  const stale: string[] = [];
  for (let i = 0; i < storage.length; i++) {
    const fullKey = storage.key(i);
    if (
      !fullKey ||
      (!fullKey.startsWith(HANDLED_PREFIX) && !fullKey.startsWith(LOCK_PREFIX))
    ) {
      continue;
    }
    if (!stampFresh(storage.getItem(fullKey), now, PUSH_HANDLED_TTL_MS)) {
      stale.push(fullKey);
    }
  }
  for (const fullKey of stale) storage.removeItem(fullKey);
}

export function markPushHandled(
  storage: Storage,
  key: string,
  now = Date.now(),
): void {
  sweepPushKeys(storage, now);
  storage.setItem(storageKey(HANDLED_PREFIX, key), String(now));
}

export function wasPushHandled(
  storage: Storage,
  key: string,
  now = Date.now(),
  ttlMs = PUSH_HANDLED_TTL_MS,
): boolean {
  return stampFresh(
    storage.getItem(storageKey(HANDLED_PREFIX, key)),
    now,
    ttlMs,
  );
}

/** Exclusive claim among tabs that race to show one system notification. */
export function claimPushLock(
  storage: Storage,
  key: string,
  tabId: string,
  now = Date.now(),
  ttlMs = PUSH_HANDLED_TTL_MS,
): boolean {
  const fullKey = storageKey(LOCK_PREFIX, key);
  const raw = storage.getItem(fullKey);
  if (raw) {
    const [stamp, owner] = raw.split("@");
    const ts = Number(stamp);
    if (owner && Number.isFinite(ts) && now - ts < ttlMs) return false;
  }
  const token = `${now}@${tabId}`;
  storage.setItem(fullKey, token);
  return storage.getItem(fullKey) === token;
}

/**
 * Claim the right to show a system notification.
 * Must stay synchronous: a background tab's timers and promises are deferred
 * until the tab is focused, which is too late to raise the notification.
 */
export function claimSystemPush(
  storage: Storage | null,
  key: string,
  tabId: string,
  now = Date.now(),
): boolean {
  if (storage && wasPushHandled(storage, key, now)) return false;
  if (storage && !claimPushLock(storage, key, tabId, now)) return false;
  if (storage) markPushHandled(storage, key, now);
  return true;
}
