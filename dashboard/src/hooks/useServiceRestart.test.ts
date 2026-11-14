import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { ApiResponseError } from "../api/responseError";
import {
  hasProcessRestarted,
  shouldPollAfterRestartError,
  useServiceRestart,
} from "./useServiceRestart";

const probeHealth = vi.fn();
const restartService = vi.fn();
const bustServiceWorkerAndReload = vi.fn();

vi.mock("../api/probeHealth", () => ({
  probeHealth: (...args: unknown[]) => probeHealth(...args),
}));

vi.mock("../api/modules/update", () => ({
  updateApi: {
    restartService: (...args: unknown[]) => restartService(...args),
  },
}));

vi.mock("../utils/reloadOnStaleChunk", () => ({
  bustServiceWorkerAndReload: (...args: unknown[]) =>
    bustServiceWorkerAndReload(...args),
}));

describe("hasProcessRestarted", () => {
  it("returns true when started_at changes", () => {
    expect(hasProcessRestarted(100, 200)).toBe(true);
  });

  it("returns false when started_at is missing or unchanged", () => {
    expect(hasProcessRestarted(undefined, 200)).toBe(false);
    expect(hasProcessRestarted(100, undefined)).toBe(false);
    expect(hasProcessRestarted(100, 100)).toBe(false);
  });
});

describe("shouldPollAfterRestartError", () => {
  it.each([502, 503, 504])("polls after HTTP %i", (status) => {
    expect(
      shouldPollAfterRestartError(new ApiResponseError(status, null, null)),
    ).toBe(true);
  });

  it.each([400, 403, 409, 500])("does not poll after HTTP %i", (status) => {
    expect(
      shouldPollAfterRestartError(new ApiResponseError(status, null, null)),
    ).toBe(false);
  });

  it("keeps polling for network errors without an HTTP response", () => {
    expect(shouldPollAfterRestartError(new Error("Failed to fetch"))).toBe(
      true,
    );
  });
});

describe("useServiceRestart", () => {
  beforeEach(() => {
    probeHealth.mockReset();
    restartService.mockReset();
    bustServiceWorkerAndReload.mockReset();
    bustServiceWorkerAndReload.mockResolvedValue(undefined);
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-09T12:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("clears the service worker cache before reloading after restart", async () => {
    probeHealth
      .mockResolvedValueOnce({ ok: true, started_at: 1_000 })
      .mockResolvedValue({ ok: true, started_at: 2_000 });
    restartService.mockResolvedValue({
      status: "restarting",
      service_mode: "systemd",
    });

    const { result } = renderHook(() => useServiceRestart());

    await act(async () => {
      await result.current.executeRestart();
    });

    expect(result.current.restartPhase).toBe("restarting");
    expect(bustServiceWorkerAndReload).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_200);
    });

    expect(result.current.restartPhase).toBe("success");
    expect(bustServiceWorkerAndReload).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });

    expect(bustServiceWorkerAndReload).toHaveBeenCalledOnce();
  });
});
