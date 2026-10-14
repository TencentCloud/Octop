import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  SIDEBAR_AGENT_ORDER_STORAGE_KEY,
  readListOrder,
  sidebarAgentOrderStorageKey,
  useListOrder,
  writeListOrder,
} from "./useListOrder";

describe("useListOrder persistence", () => {
  afterEach(() => {
    localStorage.removeItem(SIDEBAR_AGENT_ORDER_STORAGE_KEY);
    localStorage.removeItem(sidebarAgentOrderStorageKey(7));
  });

  it("returns empty state when unset", () => {
    expect(readListOrder()).toEqual({ pinned: [], order: [] });
    expect(readListOrder(7)).toEqual({ pinned: [], order: [] });
  });

  it("round-trips per user and clears when empty", () => {
    writeListOrder({ pinned: ["b"], order: ["a", "b"] }, 7);
    expect(readListOrder(7)).toEqual({ pinned: ["b"], order: ["a", "b"] });
    expect(readListOrder()).toEqual({ pinned: [], order: [] });

    writeListOrder({ pinned: [], order: [] }, 7);
    expect(localStorage.getItem(sidebarAgentOrderStorageKey(7))).toBeNull();
  });

  it("ignores corrupt JSON", () => {
    localStorage.setItem(sidebarAgentOrderStorageKey(7), "{oops");
    expect(readListOrder(7)).toEqual({ pinned: [], order: [] });
  });

  it("survives localStorage throwing (private mode)", () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error("quota");
    };
    try {
      expect(() =>
        writeListOrder({ pinned: ["x"], order: ["x"] }, 7),
      ).not.toThrow();
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});

describe("useListOrder hook", () => {
  afterEach(() => {
    localStorage.removeItem(SIDEBAR_AGENT_ORDER_STORAGE_KEY);
  });

  it("move / relocate / togglePin update state and persist", () => {
    const { result } = renderHook(() => useListOrder());

    act(() => result.current.move(["a", "b", "c"], "a", 1));
    expect(result.current.state.order).toEqual(["b", "a", "c"]);

    act(() => result.current.relocate(["b", "a", "c"], "c", "b", "before"));
    expect(result.current.state.order).toEqual(["c", "b", "a"]);

    act(() => result.current.togglePin("b"));
    expect(result.current.state.pinned).toEqual(["b"]);

    expect(readListOrder()).toEqual({
      pinned: ["b"],
      order: ["c", "b", "a"],
    });
  });

  it("ignores out-of-bounds moves", () => {
    const { result } = renderHook(() => useListOrder());
    act(() => result.current.move(["a", "b"], "a", -1));
    expect(result.current.state).toEqual({ pinned: [], order: [] });
    act(() => result.current.move(["a", "b"], "zz", 1));
    expect(result.current.state).toEqual({ pinned: [], order: [] });
  });
});
