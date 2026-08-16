import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import type { UpdateStatus } from "../api/modules/update";
import {
  UPDATE_STATUS_CHANGED_EVENT,
  UPDATE_STATUS_POLL_MS,
  clearStoredUpdateStatus,
  storeUpdateStatus,
} from "../utils/updateStatusCache";

const getUpdateStatus = vi.fn();

vi.mock("../api/modules/update", () => ({
  updateApi: {
    getUpdateStatus: (...args: unknown[]) => getUpdateStatus(...args),
  },
}));

import { useUpdateStatus } from "./useUpdateStatus";

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

describe("useUpdateStatus", () => {
  beforeEach(() => {
    localStorage.clear();
    getUpdateStatus.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-14T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    clearStoredUpdateStatus();
    localStorage.clear();
  });

  it("probes on mount when cache is empty", async () => {
    getUpdateStatus.mockResolvedValue(sample);
    const { result } = renderHook(() => useUpdateStatus());

    await act(async () => {
      await Promise.resolve();
    });

    expect(getUpdateStatus).toHaveBeenCalledTimes(1);
    expect(result.current.hasUpdate).toBe(true);
    expect(result.current.status?.latest_version).toBe("0.9.7");
  });

  it("re-probes after TTL via the poll interval", async () => {
    getUpdateStatus.mockResolvedValue(sample);
    renderHook(() => useUpdateStatus());

    await act(async () => {
      await Promise.resolve();
    });
    expect(getUpdateStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      // One poll tick lands at TTL; cache is expired so the probe runs again.
      vi.advanceTimersByTime(UPDATE_STATUS_POLL_MS);
      await Promise.resolve();
    });

    expect(getUpdateStatus.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("picks up status written by another screen", async () => {
    getUpdateStatus.mockResolvedValue({
      ...sample,
      has_update: false,
      latest_version: "0.9.6",
    });
    const { result } = renderHook(() => useUpdateStatus());

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.hasUpdate).toBe(false);

    await act(async () => {
      storeUpdateStatus(sample);
    });

    expect(result.current.hasUpdate).toBe(true);
    expect(result.current.status?.latest_version).toBe("0.9.7");
  });

  it("listens for the shared change event name", () => {
    expect(UPDATE_STATUS_CHANGED_EVENT).toBe("octop:update-status-changed");
  });
});
