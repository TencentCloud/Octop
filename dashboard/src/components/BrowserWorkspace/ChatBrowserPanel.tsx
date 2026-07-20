import React from "react";
import BrowserWorkspace, { type PanelMode } from "./index";
import type { DisplayEnvironment } from "../../api/types/browser";
import ChatDockPanelShell from "./ChatDockPanelShell";

interface ChatBrowserPanelProps {
  /** Profile/session id forwarded to the browser view. */
  sessionId?: string | null;
  environment?: DisplayEnvironment;
  /** Controlled layout mode (owned by the chat shell, persisted there). */
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  /** Bookmark state for the current URL (forwarded to the address bar). */
  bookmarked?: boolean;
  onToggleBookmark?: (url: string, title: string) => void;
}

/**
 * Chat-specific chrome around the shared BrowserWorkspace: panel-mode
 * switching (bottom / right / popup), popup drag-to-move, and close.
 *
 * All browser-view logic (connect, paint, session metadata, handoff) stays in
 * BrowserWorkspace so it can be reused by other surfaces without dragging
 * chat-specific UI along.
 */
const ChatBrowserPanel: React.FC<ChatBrowserPanelProps> = ({
  sessionId,
  environment,
  mode,
  onModeChange,
  onClose,
  style,
  bookmarked,
  onToggleBookmark,
}) => {
  return (
    <ChatDockPanelShell
      mode={mode}
      onModeChange={onModeChange}
      onClose={onClose}
      style={style}
    >
      <BrowserWorkspace
        sessionId={sessionId}
        environment={environment}
        style={{ flex: 1, minHeight: 0 }}
        bookmarked={bookmarked}
        onToggleBookmark={onToggleBookmark}
      />
    </ChatDockPanelShell>
  );
};

export default ChatBrowserPanel;
