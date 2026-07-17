import { Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import ChatBrowserPanel from "../../../components/BrowserWorkspace/ChatBrowserPanel";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import type { DisplayEnvironment } from "../../../api/types/browser";
import { resolveBrowserProfile } from "../../../utils/browserProfile";
import styles from "../index.module.less";

interface ChatBrowserPanelsProps {
  hasBrowserTool: boolean;
  isMobile: boolean;
  browserPanelOpen: boolean;
  browserPanelMode: PanelMode;
  isResizing: boolean;
  panelSizes: { rightWidth: number; bottomHeight: number };
  browserSessionId: string | null;
  browserEnvironment: DisplayEnvironment;
  browserSessionState: string;
  browserControlOwner: "agent" | "user";
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.MouseEvent,
    direction: "horizontal" | "vertical",
  ) => void;
  onTogglePanel: () => void;
}

export default function ChatBrowserPanels({
  hasBrowserTool,
  isMobile,
  browserPanelOpen,
  browserPanelMode,
  isResizing,
  panelSizes,
  browserSessionId,
  browserEnvironment,
  browserSessionState,
  browserControlOwner,
  onModeChange,
  onClose,
  onResizeStart,
  onTogglePanel,
}: ChatBrowserPanelsProps) {
  const { t } = useTranslation();
  // Attach to the shared default harness profile so headed chat browsers stay
  // consistent with headless/standalone usage (one profile for all
  // conversations) instead of spawning a per-conversation `thr_*` profile.
  // The profile identifier has a single source of truth in
  // browserProfile.resolveBrowserProfile so the panel and any future bubble
  // logic cannot drift apart.
  const sessionId = resolveBrowserProfile();
  const isAuth =
    browserSessionState === "awaiting_user_auth" ||
    browserSessionState === "authenticating";

  const statusTitle = browserSessionId
    ? t("browserWorkspace.browserStatusActive", {
        owner:
          browserControlOwner === "agent"
            ? t("browserWorkspace.agentControl")
            : t("browserWorkspace.userTakeover"),
      })
    : t("browserWorkspace.browserStatusIdle");

  if (!hasBrowserTool || isMobile) return null;

  return (
    <>
      {!browserPanelOpen && (
        <button
          type="button"
          className={`${styles.browserStatusBtn} ${
            styles.browserStatusActive
          } ${isAuth ? styles.browserStatusAuth : ""} ${
            browserControlOwner === "user" ? styles.browserStatusTakeover : ""
          }`}
          onClick={onTogglePanel}
          title={statusTitle}
        >
          <Globe size={14} />
          {browserSessionId && (
            <span
              className={`${styles.browserStatusDot} ${
                styles[`browserStatus_${browserControlOwner}`]
              }`}
            />
          )}
        </button>
      )}

      {browserPanelOpen && (
        <>
          {browserPanelMode === "right" && (
            <div
              className={`${styles.panelResizer} ${styles.horizontal} ${
                isResizing ? styles.resizerActive : ""
              }`}
              onMouseDown={(e) => onResizeStart(e, "horizontal")}
            >
              <div className={styles.resizerHandle} />
            </div>
          )}
          <ChatBrowserPanel
            sessionId={sessionId}
            environment={browserEnvironment}
            mode={browserPanelMode}
            onModeChange={onModeChange}
            onClose={onClose}
            style={
              browserPanelMode === "right"
                ? { width: panelSizes.rightWidth }
                : undefined
            }
          />
        </>
      )}
    </>
  );
}
