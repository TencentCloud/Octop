import { createContext, useContext, useMemo, type ReactNode } from "react";
import { dockToolUiTabId } from "./utils/dockToolUiTabId";
import type { DockTab, DockTabId } from "./hooks/useChatDockPanel";

export interface OpenToolUiPanelOptions {
  callId: string;
  title?: string;
  toolName?: string;
}

interface ChatToolDockContextValue {
  openToolUiPanel: (opts: OpenToolUiPanelOptions) => void;
  closeToolUiPanel: (callId: string) => void;
  focusToolUiPanel: (callId: string) => void;
  isToolUiDocked: (callId: string | undefined) => boolean;
}

const ChatToolDockContext = createContext<ChatToolDockContextValue | null>(
  null,
);

export function ChatToolDockProvider({
  dockOpen,
  openTabs,
  activeTabId,
  openToolUiPanel,
  closeToolUiPanel,
  focusToolUiPanel,
  children,
}: {
  dockOpen: boolean;
  openTabs: DockTab[];
  activeTabId: DockTabId | null;
  openToolUiPanel: (opts: OpenToolUiPanelOptions) => void;
  closeToolUiPanel: (callId: string) => void;
  focusToolUiPanel: (callId: string) => void;
  children: ReactNode;
}) {
  const activeToolUiCallId = useMemo(() => {
    if (!dockOpen || activeTabId == null) return null;
    const active = openTabs.find((tab) => tab.id === activeTabId);
    return active?.kind === "toolUi" ? active.callId : null;
  }, [dockOpen, openTabs, activeTabId]);

  const value = useMemo<ChatToolDockContextValue>(
    () => ({
      openToolUiPanel,
      closeToolUiPanel,
      focusToolUiPanel,
      // Placeholder only while this tool's tab is the visible dock surface.
      // Closing the dock, the tab, or switching away restores the chat card.
      isToolUiDocked: (callId) => !!callId && activeToolUiCallId === callId,
    }),
    [activeToolUiCallId, openToolUiPanel, closeToolUiPanel, focusToolUiPanel],
  );

  return (
    <ChatToolDockContext.Provider value={value}>
      {children}
    </ChatToolDockContext.Provider>
  );
}

export function useChatToolDock(): ChatToolDockContextValue | null {
  return useContext(ChatToolDockContext);
}

export function dockTabIdForToolCall(callId: string): DockTabId {
  return dockToolUiTabId(callId);
}
