import type { UpdateStatus } from "../api/modules/update";

export const UPDATE_STATUS_STORAGE_KEY = "octop:update-status";
export const UPDATE_STATUS_TTL_MS = 60 * 60 * 1000;

interface StoredUpdateStatus {
  checkedAt: number;
  status: UpdateStatus;
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
    if (now - parsed.checkedAt >= UPDATE_STATUS_TTL_MS) {
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
}

export function clearStoredUpdateStatus(): void {
  try {
    localStorage.removeItem(UPDATE_STATUS_STORAGE_KEY);
  } catch {
    // ignore
  }
}

/** True when cache is missing or older than TTL. */
export function isUpdateStatusCacheExpired(now = Date.now()): boolean {
  try {
    const raw = localStorage.getItem(UPDATE_STATUS_STORAGE_KEY);
    if (!raw) return true;
    const parsed = JSON.parse(raw) as StoredUpdateStatus;
    if (!parsed || typeof parsed.checkedAt !== "number") return true;
    return now - parsed.checkedAt >= UPDATE_STATUS_TTL_MS;
  } catch {
    return true;
  }
}
