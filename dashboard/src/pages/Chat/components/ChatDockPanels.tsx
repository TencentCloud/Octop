import type { PanelMode } from "../../../components/BrowserWorkspace";
import type { DisplayEnvironment } from "../../../api/types/browser";
import type { DockTab, DockTabId } from "../hooks/useChatDockPanel";
import styles from "../index.module.less";
import ChatDockPanel from "./ChatDockPanel";

interface ChatDockPanelsProps {
  isMobile: boolean;
  dockOpen: boolean;
  dockMode: PanelMode;
  isResizing: boolean;
  panelSizes: { rightWidth: number; bottomHeight: number };
  agentId: string;
  filePaths: string[];
  openTabs: DockTab[];
  activeTabId: DockTabId | null;
  onSelectTab: (id: DockTabId) => void;
  onCloseTab: (id: DockTabId) => void;
  onOpenFile: (path: string) => void;
  browserEnvironment: DisplayEnvironment;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.PointerEvent,
    direction: "horizontal" | "vertical",
  ) => void;
  /** When true, render only the bottom-dock slot (inside chatMain). */
  slot: "bottom" | "side";
}

/**
 * Shared chat dock host: one tabbed shell for file list / files / browser.
 * ``slot="bottom"`` renders inside ``chatMain``; ``slot="side"`` covers
 * right + popup. Floating browser / file buttons live in ChatPage.
 */
export default function ChatDockPanels({
  isMobile,
  dockOpen,
  dockMode,
  isResizing,
  panelSizes,
  agentId,
  filePaths,
  openTabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  onOpenFile,
  browserEnvironment,
  onModeChange,
  onClose,
  onResizeStart,
  slot,
}: ChatDockPanelsProps) {
  const showBottom = slot === "bottom" && dockOpen && dockMode === "bottom";
  const showSide =
    slot === "side" &&
    dockOpen &&
    !isMobile &&
    (dockMode === "right" || dockMode === "popup");
  const showMobilePopup =
    slot === "side" && isMobile && dockOpen && dockMode === "popup";

  const panel = (
    <ChatDockPanel
      mode={
        slot === "bottom"
          ? "bottom"
          : dockMode === "right" && isMobile
          ? "popup"
          : dockMode
      }
      onModeChange={onModeChange}
      onClose={onClose}
      style={
        slot === "bottom"
          ? { height: panelSizes.bottomHeight }
          : dockMode === "right" && !isMobile
          ? { width: panelSizes.rightWidth }
          : undefined
      }
      agentId={agentId}
      filePaths={filePaths}
      openTabs={openTabs}
      activeTabId={activeTabId}
      onSelectTab={onSelectTab}
      onCloseTab={onCloseTab}
      onOpenFile={onOpenFile}
      browserEnvironment={browserEnvironment}
    />
  );

  return (
    <>
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
          {panel}
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
          {panel}
        </>
      )}
    </>
  );
}
