import { describe, expect, it, beforeEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useHiddenSharedExperts } from "./useHiddenSharedExperts";
import {
  HIDDEN_SHARED_EXPERTS_STORAGE_KEY,
  hiddenExpertsStorageKey,
} from "../utils/hiddenExpertsPrefs";

vi.mock("../../../hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ id: 1, username: "tester" }),
}));

const owned = { agent_id: "own-1", is_shared: false, is_owner: true };
const shared = { agent_id: "shared-1", is_shared: true, is_owner: false };

describe("useHiddenSharedExperts（放开隐藏 / AC-S0-7）", () => {
  beforeEach(() => {
    localStorage.removeItem(HIDDEN_SHARED_EXPERTS_STORAGE_KEY);
    localStorage.removeItem(hiddenExpertsStorageKey(1));
  });

  it("canHide 恒 true，且 storage key 字面量不变", () => {
    const { result } = renderHook(() => useHiddenSharedExperts());

    expect(HIDDEN_SHARED_EXPERTS_STORAGE_KEY).toBe(
      "octop:hidden-shared-experts",
    );
    expect(hiddenExpertsStorageKey(1)).toBe("octop:hidden-shared-experts:1");
    expect(result.current.canHide(owned)).toBe(true);
    expect(result.current.canHide(shared)).toBe(true);
    expect(result.current.canHide({ agent_id: "team-1" })).toBe(true);
  });

  it("自建专家可隐藏 / 可恢复，不再按 isSharedExpertViewer 过滤", () => {
    const { result } = renderHook(() => useHiddenSharedExperts());
    const agents = [owned, shared];

    act(() => result.current.hide(owned.agent_id));
    expect([...result.current.hiddenIds]).toEqual(["own-1"]);
    expect(result.current.filterVisible(agents)).toEqual([shared]);
    expect(result.current.pickHidden(agents)).toEqual([owned]);
    expect(localStorage.getItem(hiddenExpertsStorageKey(1))).toBe('["own-1"]');

    act(() => result.current.unhide(owned.agent_id));
    expect(result.current.filterVisible(agents)).toEqual([owned, shared]);
    expect(result.current.pickHidden(agents)).toEqual([]);
    expect(localStorage.getItem(hiddenExpertsStorageKey(1))).toBeNull();
  });
});
