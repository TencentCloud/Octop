import React, { useEffect, useState } from "react";
import BrowserWorkspace, {
  type PanelMode,
} from "../../../components/BrowserWorkspace";
import ChatDockPanelShell from "../../../components/BrowserWorkspace/ChatDockPanelShell";
import type { DisplayEnvironment } from "../../../api/types/browser";
import { resolveBrowserProfile } from "../../../utils/browserProfile";
import type { DockKind } from "../hooks/useChatDockPanel";
import FilePanelContent from "./FilePanelContent";

interface ChatDockPanelProps {
  kind: DockKind;
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  /** File body */
  agentId: string;
  filePaths: string[];
  initialPath?: string | null;
  /** Browser body */
  browserEnvironment?: DisplayEnvironment;
}

/**
 * Single dock shell whose body switches between file viewer and browser.
 * Both bodies stay mounted (after first open) so switching is instant and the
 * browser stream does not tear down when peeking at a file.
 */
const ChatDockPanel: React.FC<ChatDockPanelProps> = ({
  kind,
  mode,
  onModeChange,
  onClose,
  style,
  agentId,
  filePaths,
  initialPath,
  browserEnvironment = "desktop",
}) => {
  const [fileMounted, setFileMounted] = useState(kind === "file");
  const [browserMounted, setBrowserMounted] = useState(kind === "browser");

  useEffect(() => {
    if (kind === "file") setFileMounted(true);
    if (kind === "browser") setBrowserMounted(true);
  }, [kind]);

  const sessionId = resolveBrowserProfile();

  return (
    <ChatDockPanelShell
      mode={mode}
      onModeChange={onModeChange}
      onClose={onClose}
      style={style}
    >
      {fileMounted && (
        <div
          hidden={kind !== "file"}
          style={{
            display: kind === "file" ? "flex" : "none",
            flex: 1,
            minHeight: 0,
            flexDirection: "column",
          }}
        >
          <FilePanelContent
            agentId={agentId}
            filePaths={filePaths}
            initialPath={initialPath}
          />
        </div>
      )}
      {browserMounted && (
        <div
          hidden={kind !== "browser"}
          style={{
            display: kind === "browser" ? "flex" : "none",
            flex: 1,
            minHeight: 0,
            flexDirection: "column",
          }}
        >
          <BrowserWorkspace
            sessionId={sessionId}
            environment={browserEnvironment}
            style={{ flex: 1, minHeight: 0 }}
          />
        </div>
      )}
    </ChatDockPanelShell>
  );
};

export default ChatDockPanel;
