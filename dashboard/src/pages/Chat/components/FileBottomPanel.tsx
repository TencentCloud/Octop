import type { PanelMode } from "../../../components/BrowserWorkspace";
import FilePanel from "./FilePanel";
import styles from "../index.module.less";

interface FileBottomPanelProps {
  agentId: string;
  filePaths: string[];
  initialPath?: string | null;
  isResizing: boolean;
  bottomHeight: number;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  onResizeStart: (
    e: React.PointerEvent,
    direction: "horizontal" | "vertical",
  ) => void;
}

/** Bottom-docked variant of {@link FilePanel} (inside ``chatMain``). */
export default function FileBottomPanel({
  agentId,
  filePaths,
  initialPath,
  isResizing,
  bottomHeight,
  onModeChange,
  onClose,
  onResizeStart,
}: FileBottomPanelProps) {
  return (
    <>
      <div
        className={`${styles.panelResizer} ${styles.vertical} ${
          isResizing ? styles.resizerActive : ""
        }`}
        onPointerDown={(e) => onResizeStart(e, "vertical")}
      >
        <div className={styles.resizerHandle} />
      </div>
      <FilePanel
        agentId={agentId}
        filePaths={filePaths}
        initialPath={initialPath}
        mode="bottom"
        onModeChange={onModeChange}
        onClose={onClose}
        style={{ height: bottomHeight }}
      />
    </>
  );
}
