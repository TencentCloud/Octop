import { describe, expect, it } from "vitest";
import {
  CHAT_SIDEBAR_WIDE_BREAKPOINT,
  resolveChatSidebarDefaultOpen,
} from "./useChatSidebarState";

describe("resolveChatSidebarDefaultOpen", () => {
  it("prefers stored true over viewport", () => {
    expect(resolveChatSidebarDefaultOpen("true", 800)).toBe(true);
    expect(
      resolveChatSidebarDefaultOpen("true", CHAT_SIDEBAR_WIDE_BREAKPOINT - 1),
    ).toBe(true);
  });

  it("prefers stored false over viewport", () => {
    expect(resolveChatSidebarDefaultOpen("false", 2000)).toBe(false);
    expect(
      resolveChatSidebarDefaultOpen("false", CHAT_SIDEBAR_WIDE_BREAKPOINT),
    ).toBe(false);
  });

  it("defaults open on wide viewport when no preference", () => {
    expect(
      resolveChatSidebarDefaultOpen(null, CHAT_SIDEBAR_WIDE_BREAKPOINT),
    ).toBe(true);
    expect(resolveChatSidebarDefaultOpen(null, 1600)).toBe(true);
  });

  it("defaults closed on narrow viewport when no preference", () => {
    expect(
      resolveChatSidebarDefaultOpen(null, CHAT_SIDEBAR_WIDE_BREAKPOINT - 1),
    ).toBe(false);
    expect(resolveChatSidebarDefaultOpen(null, 768)).toBe(false);
  });

  it("treats empty string like missing preference", () => {
    expect(resolveChatSidebarDefaultOpen("", 1400)).toBe(true);
    expect(resolveChatSidebarDefaultOpen("", 900)).toBe(false);
  });
});
