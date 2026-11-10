import { useEffect, useState } from "react";
import CloseIcon from "../../../../dashboard/src/assets/window-controls/close.svg?react";
import MaximizeIcon from "../../../../dashboard/src/assets/window-controls/maximize.svg?react";
import MinimizeIcon from "../../../../dashboard/src/assets/window-controls/minimize.svg?react";
import RestoreIcon from "../../../../dashboard/src/assets/window-controls/restore.svg?react";
import styles from "./linux-window-controls.module.less";

const GLYPH = {
  minimize: MinimizeIcon,
  maximize: MaximizeIcon,
  restore: RestoreIcon,
  close: CloseIcon,
} as const;

function linuxDesktop(): boolean {
  return (
    typeof window.octopDesktop?.windowControls !== "undefined" &&
    /Linux/.test(navigator.userAgent) &&
    !/Android/.test(navigator.userAgent)
  );
}

/**
 * Square caption buttons while the dashboard menu row is not mounted yet.
 * Same 46×32 rectangles as the dashboard: no radius, close turns red.
 */
export function LinuxWindowControls() {
  const [maximized, setMaximized] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const shown = linuxDesktop();

  useEffect(() => {
    if (!shown) return;
    const controls = window.octopDesktop?.windowControls;
    if (!controls) return;
    let cancelled = false;
    void controls.isMaximized().then((value: boolean) => {
      if (!cancelled) setMaximized(value);
    });
    const unsubscribe = controls.onMaximizedChange(setMaximized);
    const unsubscribeFullscreen = window.octopDesktop?.onWindowFullscreenChange?.(
      setFullscreen,
    );
    return () => {
      cancelled = true;
      unsubscribe();
      unsubscribeFullscreen?.();
    };
  }, [shown]);

  if (!shown || fullscreen) return null;
  const controls = window.octopDesktop?.windowControls;

  return (
    <div className={styles.controls} role="group" aria-label="窗口控制">
      <button type="button" title="最小化" aria-label="最小化" onClick={() => controls?.minimize()}>
        <CaptionGlyph kind="minimize" />
      </button>
      <button
        type="button"
        title={maximized ? "还原" : "最大化"}
        aria-label={maximized ? "还原" : "最大化"}
        onClick={() => controls?.toggleMaximize()}
      >
        <CaptionGlyph kind={maximized ? "restore" : "maximize"} />
      </button>
      <button
        type="button"
        className={styles.close}
        title="关闭"
        aria-label="关闭"
        onClick={() => controls?.close()}
      >
        <CaptionGlyph kind="close" />
      </button>
    </div>
  );
}

function CaptionGlyph({ kind }: { kind: keyof typeof GLYPH }) {
  const Icon = GLYPH[kind];
  return <Icon aria-hidden="true" />;
}
