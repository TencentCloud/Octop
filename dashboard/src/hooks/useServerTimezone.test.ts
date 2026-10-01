import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const { timezone } = vi.hoisted(() => ({ timezone: vi.fn() }));

vi.mock("../api/modules/settings", () => ({
  octopSettingsApi: { timezone },
}));

import {
  DEFAULT_SERVER_TIMEZONE,
  applyTimezoneFetchResult,
  useServerTimezone,
} from "./useServerTimezone";

describe("useServerTimezone", () => {
  it("retries on the next mount after a failed fetch instead of pinning UTC", async () => {
    timezone.mockRejectedValueOnce(new Error("settings endpoint offline"));
    const first = renderHook(() => useServerTimezone());
    await waitFor(() => expect(first.result.current).toBe("UTC"));
    first.unmount();

    timezone.mockResolvedValueOnce({ timezone: "Asia/Shanghai" });
    const second = renderHook(() => useServerTimezone());
    await waitFor(() => expect(second.result.current).toBe("Asia/Shanghai"));
  });
});

describe("applyTimezoneFetchResult", () => {
  it("does not cache a failed fetch so the next mount can retry", () => {
    const result = applyTimezoneFetchResult({ ok: false });
    expect(result.value).toBe(DEFAULT_SERVER_TIMEZONE);
    expect(result.cache).toBeNull();
  });

  it("caches the timezone reported by the server", () => {
    const result = applyTimezoneFetchResult({
      ok: true,
      timezone: "Asia/Shanghai",
    });
    expect(result.value).toBe("Asia/Shanghai");
    expect(result.cache).toBe("Asia/Shanghai");
  });

  it("falls back to UTC when the server reports an empty timezone", () => {
    const result = applyTimezoneFetchResult({ ok: true, timezone: "   " });
    expect(result.value).toBe(DEFAULT_SERVER_TIMEZONE);
  });

  it("ignores a non-string timezone", () => {
    const result = applyTimezoneFetchResult({ ok: true, timezone: 42 });
    expect(result.value).toBe(DEFAULT_SERVER_TIMEZONE);
  });
});
