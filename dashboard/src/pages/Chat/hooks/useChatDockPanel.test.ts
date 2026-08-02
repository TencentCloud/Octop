import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { dockFileTabId } from "../utils/dockFilePath";
import { useChatDockPanel } from "./useChatDockPanel";

describe("useChatDockPanel tabs", () => {
  it("openFileList focuses the pinned files tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openFileList();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.activeTabId).toBe("files");
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["files"]);
  });

  it("openFileAt dedupes by normalized path and focuses the file tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false, "main"));
    act(() => {
      result.current.openFileAt(
        "/home/wally/.octop/agents/main/outbound/a.txt",
      );
    });
    act(() => {
      result.current.openFileAt("/.octop/agents/main/outbound/a.txt");
    });
    const fileId = dockFileTabId("outbound/a.txt", "main");
    expect(
      result.current.openTabs.filter((t) => t.kind === "file"),
    ).toHaveLength(1);
    expect(result.current.activeTabId).toBe(fileId);
    expect(result.current.openTabs.map((t) => t.id)).toEqual([fileId]);
  });

  it("toggleBrowserPanel opens browser tab then closes dock when active", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.toggleBrowserPanel();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.activeTabId).toBe("browser");
    act(() => {
      result.current.toggleBrowserPanel();
    });
    expect(result.current.dockOpen).toBe(false);
  });

  it("closeTab can close the files list tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openFileList();
      result.current.openBrowserTab();
    });
    act(() => {
      result.current.closeTab("files");
    });
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["browser"]);
    expect(result.current.activeTabId).toBe("browser");
    expect(result.current.dockOpen).toBe(true);
  });

  it("closeTab falls back to files and closes dock when empty", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openBrowserTab();
    });
    act(() => {
      result.current.closeTab("browser");
    });
    expect(result.current.openTabs).toEqual([]);
    expect(result.current.dockOpen).toBe(false);
  });

  it("does not expose deprecated dismiss / kind aliases", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    expect(result.current).not.toHaveProperty("userDismissedRef");
    expect(result.current).not.toHaveProperty("dockKind");
    expect(result.current).not.toHaveProperty("openFilePanel");
    expect(result.current).not.toHaveProperty("openBrowserPanel");
    expect(result.current).not.toHaveProperty("resetDismissOnSessionGone");
  });
});
