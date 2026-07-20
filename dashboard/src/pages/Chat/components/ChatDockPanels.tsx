import { Globe } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import type { DisplayEnvironment } from "../../../api/types/browser";
import type { DockKind } from "../hooks/useChatDockPanel";
import styles from "../index.module.less";
import ChatDockPanel from "./ChatDockPanel";

interface ChatDockPanelsProps {
  hasBrowserTool: boolean;
  isMobile: boolean;
  dockOpen: boolean;
  dockKind: DockKind;
  dockMode: PanelMode;
  isResizing: boolean;
  panelSizes: { rightWidth: number; bottomHeight: number };
  agentId: string;
  filePaths: string[];
  initialPath?: string | null;
  browserSessionId: string | null;
  browserEnvironment: DisplayEnvironment;
  browserSessionState: string;
  browserControlOwner: "agent" | "user";
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.PointerEvent,
    direction: "horizontal" | "vertical",
  ) => void;
  onToggleBrowser: () => void;
  /** When true, render only the bottom-dock slot (inside chatMain). */
  slot: "bottom" | "side";
}

/**
 * Shared chat dock host: one shell for file / browser / preview.
 * ``slot="bottom"`` renders inside ``chatMain``; ``slot="side"`` covers
 * right + popup plus the floating browser status button.
 */
export default function ChatDockPanels({
  hasBrowserTool,
  isMobile,
  dockOpen,
  dockKind,
  dockMode,
  isResizing,
  panelSizes,
  agentId,
  filePaths,
  initialPath,
  browserSessionId,
  browserEnvironment,
  browserSessionState,
  browserControlOwner,
  onModeChange,
  onClose,
  onResizeStart,
  onToggleBrowser,
  slot,
}: ChatDockPanelsProps) {
  const { t } = useTranslation();
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

  const showStatusBtn =
    slot === "side" &&
    hasBrowserTool &&
    !isMobile &&
    !(dockOpen && dockKind === "browser");

  const showBottom = slot === "bottom" && dockOpen && dockMode === "bottom";
  const showSide =
    slot === "side" &&
    dockOpen &&
    !isMobile &&
    (dockMode === "right" || dockMode === "popup");
  const showMobilePopup =
    slot === "side" && isMobile && dockOpen && dockMode === "popup";

  return (
    <>
      {showStatusBtn && (
        <button
          type="button"
          className={`${styles.browserStatusBtn} ${
            styles.browserStatusActive
          } ${isAuth ? styles.browserStatusAuth : ""} ${
            browserControlOwner === "user" ? styles.browserStatusTakeover : ""
          }`}
          onClick={onToggleBrowser}
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

      {showBottom && (
        <>
          <div
            className={`${styles.panelResizer} ${styles.vertical} ${
              isResizing ? styles.resizerActive : ""
            }`}
            onPointerDown={(e) => onResizeStart(e, "vertical")}
          >
            <div className={styles.resizerHandle} />
          </div>
          <ChatDockPanel
            kind={dockKind}
            mode="bottom"
            onModeChange={onModeChange}
            onClose={onClose}
            style={{ height: panelSizes.bottomHeight }}
            agentId={agentId}
            filePaths={filePaths}
            initialPath={initialPath}
            browserEnvironment={browserEnvironment}
          />
        </>
      )}

      {(showSide || showMobilePopup) && (
        <>
          {dockMode === "right" && !isMobile && (
            <div
              className={`${styles.panelResizer} ${styles.horizontal} ${
                isResizing ? styles.resizerActive : ""
              }`}
              onPointerDown={(e) => onResizeStart(e, "horizontal")}
            >
              <div className={styles.resizerHandle} />
            </div>
          )}
          <ChatDockPanel
            kind={dockKind}
            mode={dockMode === "right" && isMobile ? "popup" : dockMode}
            onModeChange={onModeChange}
            onClose={onClose}
            style={
              dockMode === "right" && !isMobile
                ? { width: panelSizes.rightWidth }
                : undefined
            }
            agentId={agentId}
            filePaths={filePaths}
            initialPath={initialPath}
            browserEnvironment={browserEnvironment}
          />
        </>
      )}
    </>
  );
}
