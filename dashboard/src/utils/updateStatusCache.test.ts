import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UpdateStatus } from "../api/modules/update";
import {
  UPDATE_STATUS_STORAGE_KEY,
  UPDATE_STATUS_TTL_MS,
  clearStoredUpdateStatus,
  isUpdateStatusCacheExpired,
  readStoredUpdateStatus,
  storeUpdateStatus,
} from "./updateStatusCache";

const sample: UpdateStatus = {
  current_version: "0.9.6",
  latest_version: "0.9.7",
  has_update: true,
  is_editable: false,
  service_mode: null,
  error: null,
  last_check_time: "2026-07-14T00:00:00Z",
  release_notes: null,
};

describe("updateStatusCache", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-14T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
  });

  it("round-trips status within TTL", () => {
    storeUpdateStatus(sample);
    expect(readStoredUpdateStatus()).toEqual(sample);
    expect(isUpdateStatusCacheExpired()).toBe(false);
  });

  it("expires after 1 hour", () => {
    storeUpdateStatus(sample);
    vi.setSystemTime(Date.now() + UPDATE_STATUS_TTL_MS + 1);
    expect(readStoredUpdateStatus()).toBeNull();
    expect(isUpdateStatusCacheExpired()).toBe(true);
  });

  it("treats corrupt payload as miss", () => {
    localStorage.setItem(UPDATE_STATUS_STORAGE_KEY, "{not-json");
    expect(readStoredUpdateStatus()).toBeNull();
    expect(isUpdateStatusCacheExpired()).toBe(true);
  });

  it("clear removes the entry", () => {
    storeUpdateStatus(sample);
    clearStoredUpdateStatus();
    expect(localStorage.getItem(UPDATE_STATUS_STORAGE_KEY)).toBeNull();
  });
});
