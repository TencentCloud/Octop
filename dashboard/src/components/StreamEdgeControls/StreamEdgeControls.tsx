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

/**
 * Corner FABs for fullscreen / controls.
 *
 * Intentionally NOT full-height edge rails — those stole pointer events along
 * the left/right of the remote desktop and blocked OS chrome (start menu, etc.).
 */
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
        className={`${styles.cornerFab} ${styles.cornerFabLeft} ${
          isMobile ? styles.cornerFabHidden : ""
        }`}
      >
        <Tooltip title={fullscreenLabel} placement="right">
          <button
            type="button"
            className={styles.fab}
            aria-label={fullscreenLabel}
            onClick={onFullscreen}
          >
            <Maximize2 size={16} />
          </button>
        </Tooltip>
      </div>
      <div
        className={`${styles.cornerFab} ${styles.cornerFabRight} ${
          isMobile ? styles.cornerFabMobileVisible : ""
        }`}
      >
        <Tooltip title={controlsLabel} placement="left">
          <button
            type="button"
            className={styles.fab}
            aria-label={controlsLabel}
            onClick={onOpenControls}
          >
            <SlidersHorizontal size={16} />
          </button>
        </Tooltip>
      </div>
    </>
  );
}
