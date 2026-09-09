import type { UpdateStatus } from "../api/modules/update";

export const UPDATE_STATUS_STORAGE_KEY = "octop:update-status";
export const UPDATE_STATUS_TTL_MS = 60 * 60 * 1000;
/** Failed probes expire quickly so a transient outage isn't pinned for an hour. */
export const UPDATE_STATUS_ERROR_TTL_MS = 5 * 60 * 1000;
/**
 * How often the UI re-evaluates the local cache. Cheap tick: the per-status
 * TTL (1h success / 5min failure) decides whether an actual probe happens,
 * so a failed check self-heals within ~5 minutes instead of waiting an hour.
 */
export const UPDATE_STATUS_POLL_MS = 60 * 1000;
export const UPDATE_STATUS_CHANGED_EVENT = "octop:update-status-changed";

interface StoredUpdateStatus {
  checkedAt: number;
  status: UpdateStatus;
}

/** True when the cached payload describes a failed probe (nothing to show). */
export function isFailedUpdateStatus(status: UpdateStatus): boolean {
  return !status.latest_version;
}

function ttlFor(status: UpdateStatus): number {
  return isFailedUpdateStatus(status)
    ? UPDATE_STATUS_ERROR_TTL_MS
    : UPDATE_STATUS_TTL_MS;
}

export function readStoredUpdateStatus(now = Date.now()): UpdateStatus | null {
  try {
    const raw = localStorage.getItem(UPDATE_STATUS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredUpdateStatus;
    if (
      !parsed ||
      typeof parsed.checkedAt !== "number" ||
      !parsed.status ||
      typeof parsed.status !== "object"
    ) {
      return null;
    }
    if (now - parsed.checkedAt >= ttlFor(parsed.status)) {
      return null;
    }
    return parsed.status;
  } catch {
    return null;
  }
}

export function storeUpdateStatus(
  status: UpdateStatus,
  checkedAt = Date.now(),
): void {
  try {
    const payload: StoredUpdateStatus = { checkedAt, status };
    localStorage.setItem(UPDATE_STATUS_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // quota / private mode
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(UPDATE_STATUS_CHANGED_EVENT, { detail: status }),
    );
  }
}

export function clearStoredUpdateStatus(): void {
  try {
    localStorage.removeItem(UPDATE_STATUS_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/** True when cache is missing or older than its status-specific TTL. */
export function isUpdateStatusCacheExpired(now = Date.now()): boolean {
  try {
    const raw = localStorage.getItem(UPDATE_STATUS_STORAGE_KEY);
    if (!raw) return true;
    const parsed = JSON.parse(raw) as StoredUpdateStatus;
    if (
      !parsed ||
      typeof parsed.checkedAt !== "number" ||
      !parsed.status ||
      typeof parsed.status !== "object"
    ) {
      return true;
    }
    return now - parsed.checkedAt >= ttlFor(parsed.status);
  } catch {
    return true;
  }
}
