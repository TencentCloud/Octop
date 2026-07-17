import ChatBrowserPanel from "../../../components/BrowserWorkspace/ChatBrowserPanel";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import type { DisplayEnvironment } from "../../../api/types/browser";
import { resolveBrowserProfile } from "../../../utils/browserProfile";
import styles from "../index.module.less";

interface ChatBrowserBottomPanelProps {
  environment: DisplayEnvironment;
  isResizing: boolean;
  bottomHeight: number;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.MouseEvent,
    direction: "horizontal" | "vertical",
  ) => void;
}

export default function ChatBrowserBottomPanel({
  environment,
  isResizing,
  bottomHeight,
  onModeChange,
  onClose,
  onResizeStart,
}: ChatBrowserBottomPanelProps) {
  return (
    <>
      <div
        className={`${styles.panelResizer} ${styles.vertical} ${
          isResizing ? styles.resizerActive : ""
        }`}
        onMouseDown={(e) => onResizeStart(e, "vertical")}
      >
        <div className={styles.resizerHandle} />
      </div>
      <ChatBrowserPanel
        sessionId={resolveBrowserProfile()}
        environment={environment}
        mode="bottom"
        onModeChange={onModeChange}
        onClose={onClose}
        style={{ height: bottomHeight }}
      />
    </>
  );
}
