import { Maximize2, SlidersHorizontal } from "lucide-react";
import { Tooltip } from "antd";

import styles from "./StreamEdgeControls.module.less";

interface StreamEdgeControlsProps {
  visible?: boolean;
  isMobile: boolean;
  fullscreenLabel: string;
  controlsLabel: string;
  onFullscreen: () => void;
  onOpenControls: () => void;
}

export default function StreamEdgeControls({
  visible = true,
  isMobile,
  fullscreenLabel,
  controlsLabel,
  onFullscreen,
  onOpenControls,
}: StreamEdgeControlsProps) {
  if (!visible) return null;

  return (
    <>
      <div
        className={`${styles.edgeRail} ${styles.edgeRailLeft} ${
          isMobile ? styles.edgeRailHidden : ""
        }`}
      >
        <Tooltip title={fullscreenLabel}>
          <button
            type="button"
            className={`${styles.edgeFab} ${styles.edgeFabLeft}`}
            aria-label={fullscreenLabel}
            onClick={onFullscreen}
          >
            <Maximize2 size={18} />
          </button>
        </Tooltip>
      </div>
      <div
        className={`${styles.edgeRail} ${styles.edgeRailRight} ${
          isMobile ? styles.edgeRailMobileVisible : ""
        }`}
      >
        <Tooltip title={controlsLabel}>
          <button
            type="button"
            className={`${styles.edgeFab} ${styles.edgeFabRight}`}
            aria-label={controlsLabel}
            onClick={onOpenControls}
          >
            <SlidersHorizontal size={18} />
          </button>
        </Tooltip>
      </div>
    </>
  );
}
