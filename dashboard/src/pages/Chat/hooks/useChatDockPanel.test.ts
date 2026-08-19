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

  it("openFileListAt opens the files tab together with the focused file tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false, "main"));
    act(() => {
      result.current.openFileListAt("/outbound/a.txt");
    });
    const fileId = dockFileTabId("/outbound/a.txt", "main");
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["files", fileId]);
    expect(result.current.activeTabId).toBe(fileId);
  });

  it("openFileListAt without a path falls back to the files tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false, "main"));
    act(() => {
      result.current.openFileListAt(null);
    });
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["files"]);
    expect(result.current.activeTabId).toBe("files");
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

  it("toggleTerminalPanel opens terminal tab then closes dock when active", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.toggleTerminalPanel();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.activeTabId).toBe("terminal");
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["terminal"]);
    act(() => {
      result.current.toggleTerminalPanel();
    });
    expect(result.current.dockOpen).toBe(false);
    // Closing the float button only hides the dock — tab stays for keep-alive.
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["terminal"]);
  });

  it("reopening terminal does not add another dock tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.toggleTerminalPanel();
    });
    act(() => {
      result.current.toggleTerminalPanel();
    });
    act(() => {
      result.current.toggleTerminalPanel();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["terminal"]);
  });

  it("openTerminalTab adds and focuses the terminal tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openBrowserTab();
      result.current.openTerminalTab();
    });
    expect(result.current.activeTabId).toBe("terminal");
    expect(result.current.openTabs.map((t) => t.id)).toEqual([
      "browser",
      "terminal",
    ]);
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

  it("closes the dock and clears tabs when agentId changes", () => {
    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string | null }) =>
        useChatDockPanel(false, agentId),
      { initialProps: { agentId: "agent-a" as string | null } },
    );
    act(() => {
      result.current.openFileList();
      result.current.openBrowserTab();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.openTabs.length).toBeGreaterThan(0);

    rerender({ agentId: "agent-b" });

    expect(result.current.dockOpen).toBe(false);
    expect(result.current.openTabs).toEqual([]);
    expect(result.current.activeTabId).toBeNull();
  });

  it("does not clear dock on null ↔ id first paint races", () => {
    const { result, rerender } = renderHook(
      ({ agentId }: { agentId: string | null }) =>
        useChatDockPanel(false, agentId),
      { initialProps: { agentId: null as string | null } },
    );
    rerender({ agentId: "agent-a" });
    act(() => {
      result.current.openFileList();
    });
    expect(result.current.dockOpen).toBe(true);
    // Same agent again after transient identity — keep open.
    rerender({ agentId: "agent-a" });
    expect(result.current.dockOpen).toBe(true);
  });
});
