import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { request } from "../../../api/request";
import { useMemoryMaintenance } from "./useMemoryMaintenance";

vi.mock("../../../api/request", () => ({ request: vi.fn() }));

afterEach(() => {
  vi.useRealTimers();
  vi.resetAllMocks();
});

describe("manual memory maintenance", () => {
  it.each(["done", "failed"])(
    "blocks during migration and restores sending after %s",
    async (end) => {
      vi.useFakeTimers();
      const phases = [
        "waiting",
        "backing_up",
        "deduplicating",
        "compacting",
        end,
      ];
      for (const phase of phases) {
        vi.mocked(request).mockResolvedValueOnce({
          memory_maintenance: { phase, kind: "memory_slim" },
        });
      }
      const { result, unmount } = renderHook(() =>
        useMemoryMaintenance("main", true),
      );
      await act(async () => {
        await Promise.resolve();
      });
      expect(result.current.visible).toBe(true);
      expect(result.current.blocking).toBe(false);
      for (let step = 0; step < 3; step++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(2000);
        });
        expect(result.current.blocking).toBe(true);
      }
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
      expect(result.current.blocking).toBe(false);
      expect(result.current.visible).toBe(true);
      unmount();
    },
  );
});

it("reports lost status without silently unblocking and recovers on the next successful poll", async () => {
  vi.useFakeTimers();
  vi.mocked(request)
    .mockResolvedValueOnce({
      memory_maintenance: { phase: "compacting", kind: "memory_slim" },
    })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({
      memory_maintenance: { phase: "done", kind: "memory_slim" },
    });
  const { result, unmount } = renderHook(() =>
    useMemoryMaintenance("main", true),
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(result.current.blocking).toBe(true);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(result.current.blocking).toBe(true);
  expect(result.current.connectionLost).toBe(true);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(result.current.blocking).toBe(false);
  expect(result.current.connectionLost).toBe(false);
  unmount();
});

it("does not turn legacy completion into a persistent manual-maintenance result", async () => {
  vi.mocked(request).mockResolvedValue({
    memory_maintenance: { phase: "done" },
  });
  const { result, unmount } = renderHook(() =>
    useMemoryMaintenance("main", true),
  );
  await act(async () => {
    await Promise.resolve();
  });
  expect(result.current.visible).toBe(false);
  expect(result.current.blocking).toBe(false);
  unmount();
});
