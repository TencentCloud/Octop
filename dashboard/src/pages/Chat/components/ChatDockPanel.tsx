import React, { useCallback, useEffect, useRef, useState } from "react";
import { Tooltip } from "antd";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import BrowserWorkspace, {
  type PanelMode,
} from "../../../components/BrowserWorkspace";
import ChatDockPanelShell from "../../../components/BrowserWorkspace/ChatDockPanelShell";
import type { DisplayEnvironment } from "../../../api/types/browser";
import { resolveBrowserProfile } from "../../../utils/browserProfile";
import type { DockKind } from "../hooks/useChatDockPanel";
import styles from "../index.module.less";
import FilePanelContent, { type FilePanelChrome } from "./FilePanelContent";

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
  const { t } = useTranslation();
  const [fileMounted, setFileMounted] = useState(kind === "file");
  const [browserMounted, setBrowserMounted] = useState(kind === "browser");
  const [fileChrome, setFileChrome] = useState<FilePanelChrome | null>(null);
  const browserRefreshRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (kind === "file") setFileMounted(true);
    if (kind === "browser") setBrowserMounted(true);
  }, [kind]);

  const handleFileChromeChange = useCallback(
    (chrome: FilePanelChrome | null) => {
      setFileChrome(chrome);
    },
    [],
  );

  const handleBrowserRefreshReady = useCallback((refresh: () => void) => {
    browserRefreshRef.current = refresh;
  }, []);

  const sessionId = resolveBrowserProfile();

  const title =
    kind === "browser"
      ? t("chat.remoteBrowserTitle", "远程浏览器")
      : (fileChrome?.title ?? null);

  const toolbarActions =
    kind === "browser" ? (
      <Tooltip title={t("browserWorkspace.reconnect")}>
        <button
          type="button"
          className={styles.fileModalIconBtn}
          onClick={() => browserRefreshRef.current?.()}
          aria-label={t("browserWorkspace.reconnect")}
        >
          <RefreshCw size={16} strokeWidth={2} />
        </button>
      </Tooltip>
    ) : (
      (fileChrome?.actions ?? null)
    );

  return (
    <ChatDockPanelShell
      mode={mode}
      onModeChange={onModeChange}
      onClose={onClose}
      style={style}
      title={title}
      toolbarActions={toolbarActions}
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
            onChromeChange={handleFileChromeChange}
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
            hideHeaderRefresh
            onRefreshReady={handleBrowserRefreshReady}
          />
        </div>
      )}
    </ChatDockPanelShell>
  );
};

export default ChatDockPanel;
