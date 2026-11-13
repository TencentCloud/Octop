import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHAT_SIDEBAR_KEY,
  CHAT_SIDEBAR_WIDE_BREAKPOINT,
  resolveChatSidebarOpenOnResize,
} from "./useChatSidebarState";

const WIDE = CHAT_SIDEBAR_WIDE_BREAKPOINT;
const NARROW = CHAT_SIDEBAR_WIDE_BREAKPOINT - 1;

describe("resolveChatSidebarOpenOnResize", () => {
  it("closes when crossing from wide to narrow", () => {
    expect(resolveChatSidebarOpenOnResize(WIDE, NARROW, true)).toBe(false);
  });

  it("opens when crossing from narrow to wide", () => {
    expect(resolveChatSidebarOpenOnResize(NARROW, WIDE, false)).toBe(true);
  });

  it("keeps the current state when the breakpoint is not crossed", () => {
    expect(resolveChatSidebarOpenOnResize(1600, WIDE, false)).toBe(false);
    expect(resolveChatSidebarOpenOnResize(800, NARROW, true)).toBe(true);
  });
});

describe("chat sidebar follows the breakpoint on window resize", () => {
  const setViewport = (width: number) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      writable: true,
      value: width,
    });
  };

  const resize = (width: number) => {
    act(() => {
      setViewport(width);
      window.dispatchEvent(new Event("resize"));
    });
  };

  beforeEach(() => {
    localStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    localStorage.clear();
  });

  async function mountAt(width: number) {
    setViewport(width);
    const mod = await import("./useChatSidebarState");
    return renderHook(() => mod.useChatSidebarOpen());
  }

  it("collapses on narrow and reopens on wide without persisting", async () => {
    const { result } = await mountAt(1440);
    expect(result.current[0]).toBe(true);

    resize(1000);
    expect(result.current[0]).toBe(false);

    resize(1300);
    expect(result.current[0]).toBe(true);

    expect(localStorage.getItem(CHAT_SIDEBAR_KEY)).toBeNull();
  });

  it("keeps a manual toggle while resizing within one side", async () => {
    const { result } = await mountAt(1000);
    expect(result.current[0]).toBe(false);

    act(() => result.current[1](true));
    resize(900);
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem(CHAT_SIDEBAR_KEY)).toBe("true");
  });
});
