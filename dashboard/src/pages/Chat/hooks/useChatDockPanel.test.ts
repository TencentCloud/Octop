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

  it("toggleTrajectoryPanel opens trajectory tab then closes dock when active", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.toggleTrajectoryPanel();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.activeTabId).toBe("trajectory");
    expect(result.current.openTabs).toEqual([
      { id: "trajectory", kind: "trajectory" },
    ]);
    act(() => {
      result.current.toggleTrajectoryPanel();
    });
    expect(result.current.dockOpen).toBe(false);
    // Closing the float button only hides the dock — tab stays for keep-alive.
    expect(result.current.openTabs).toEqual([
      { id: "trajectory", kind: "trajectory" },
    ]);
  });

  it("reopening trajectory does not add another dock tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.toggleTrajectoryPanel();
    });
    act(() => {
      result.current.toggleTrajectoryPanel();
    });
    act(() => {
      result.current.toggleTrajectoryPanel();
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["trajectory"]);
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

  it("openToolUiTab dedupes by callId and focuses the tool tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openToolUiTab({
        callId: "call-1",
        title: "Demo card",
        toolName: "demo_card",
      });
    });
    act(() => {
      result.current.openToolUiTab({
        callId: "call-1",
        title: "Demo card",
      });
    });
    expect(result.current.dockOpen).toBe(true);
    expect(
      result.current.openTabs.filter((t) => t.kind === "toolUi"),
    ).toHaveLength(1);
    expect(result.current.activeTabId).toBe("toolUi:call-1");
    expect(result.current.openTabs[0]).toMatchObject({
      kind: "toolUi",
      callId: "call-1",
      title: "Demo card",
    });
  });

  it("focusToolUiTab reopens dock on an existing tool tab", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openToolUiTab({ callId: "call-2", title: "Card" });
      result.current.handleClose();
    });
    expect(result.current.dockOpen).toBe(false);
    // Closing the dock drops toolUi tabs so the message stream restores.
    expect(
      result.current.openTabs.filter((t) => t.kind === "toolUi"),
    ).toHaveLength(0);
    act(() => {
      result.current.openToolUiTab({ callId: "call-2", title: "Card" });
    });
    expect(result.current.dockOpen).toBe(true);
    expect(result.current.activeTabId).toBe("toolUi:call-2");
  });

  it("handleClose removes toolUi tabs but keeps other tabs", () => {
    const { result } = renderHook(() => useChatDockPanel(false));
    act(() => {
      result.current.openBrowserTab();
      result.current.openToolUiTab({ callId: "call-3", title: "Card" });
    });
    act(() => {
      result.current.handleClose();
    });
    expect(result.current.dockOpen).toBe(false);
    expect(result.current.openTabs.map((t) => t.id)).toEqual(["browser"]);
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
