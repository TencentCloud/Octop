import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { hitl } = vi.hoisted(() => ({ hitl: vi.fn() }));

vi.mock("../api/modules/settings", () => ({
  octopSettingsApi: { hitl },
}));

import { useHitlEnabled } from "./useHitlEnabled";

describe("useHitlEnabled", () => {
  beforeEach(() => {
    hitl.mockReset();
  });

  it("reports enabled after the server says so", async () => {
    hitl.mockResolvedValue({
      enabled: true,
      tool_guard_require_approval: false,
      show_approval_ui: true,
    });
    const hook = renderHook(() => useHitlEnabled());
    expect(hook.result.current).toBe(false);
    await waitFor(() => expect(hook.result.current).toBe(true));
  });

  it("stays off when the server reports HITL disabled", async () => {
    hitl.mockResolvedValue({
      enabled: false,
      tool_guard_require_approval: false,
      show_approval_ui: false,
    });
    const hook = renderHook(() => useHitlEnabled());
    await waitFor(() => expect(hitl).toHaveBeenCalled());
    expect(hook.result.current).toBe(false);
  });

  it("shows approval UI when only command guard requires approval", async () => {
    hitl.mockResolvedValue({
      enabled: false,
      tool_guard_require_approval: true,
      show_approval_ui: true,
    });
    const hook = renderHook(() => useHitlEnabled());
    await waitFor(() => expect(hook.result.current).toBe(true));
  });

  it("hides the picker when the settings fetch fails", async () => {
    hitl.mockRejectedValueOnce(new Error("settings endpoint offline"));
    const hook = renderHook(() => useHitlEnabled());
    await waitFor(() => expect(hitl).toHaveBeenCalled());
    expect(hook.result.current).toBe(false);
  });
});
