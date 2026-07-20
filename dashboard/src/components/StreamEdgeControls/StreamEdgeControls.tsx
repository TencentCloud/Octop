import { Maximize2, SlidersHorizontal } from "lucide-react";
import { Tooltip } from "antd";

import styles from "./StreamEdgeControls.module.less";

interface StreamEdgeControlsProps {
  visible?: boolean;
  isMobile: boolean;
  fullscreenLabel: string;
  controlsLabel: string;
  streamingLabel?: string;
  onFullscreen: () => void;
  onOpenControls: () => void;
}

/**
 * Minimal top HUD: hidden until the pointer enters the top edge.
 * No pill chrome — just quiet icons and a status word.
 */
export default function StreamEdgeControls({
  visible = true,
  isMobile,
  fullscreenLabel,
  controlsLabel,
  streamingLabel,
  onFullscreen,
  onOpenControls,
}: StreamEdgeControlsProps) {
  if (!visible) return null;

  return (
    <div
      className={`${styles.topHoverZone} ${
        isMobile ? styles.topHoverZoneMobile : ""
      }`}
    >
      <div className={styles.hud}>
        <div className={styles.hudSide}>
          {!isMobile && (
            <Tooltip title={fullscreenLabel} placement="bottom">
              <button
                type="button"
                className={styles.iconBtn}
                aria-label={fullscreenLabel}
                onClick={onFullscreen}
              >
                <Maximize2 size={15} strokeWidth={1.75} />
              </button>
            </Tooltip>
          )}
        </div>

        <div className={styles.hudCenter}>
          {streamingLabel ? (
            <span className={styles.statusText}>
              <span className={styles.statusDot} />
              {streamingLabel}
            </span>
          ) : null}
        </div>

        <div className={`${styles.hudSide} ${styles.hudSideRight}`}>
          <Tooltip title={controlsLabel} placement="bottom">
            <button
              type="button"
              className={styles.iconBtn}
              aria-label={controlsLabel}
              onClick={onOpenControls}
            >
              <SlidersHorizontal size={15} strokeWidth={1.75} />
            </button>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}
