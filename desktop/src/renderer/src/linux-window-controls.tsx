import { useEffect, useState } from "react";
import "./linux-window-controls.css";

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
    <div className="octop-linux-controls" role="group" aria-label="窗口控制">
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
        className="octop-linux-controls-close"
        title="关闭"
        aria-label="关闭"
        onClick={() => controls?.close()}
      >
        <CaptionGlyph kind="close" />
      </button>
    </div>
  );
}

function CaptionGlyph({
  kind,
}: {
  kind: "minimize" | "maximize" | "restore" | "close";
}) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
      {kind === "minimize" ? <path d="M1 8h8" stroke="currentColor" /> : null}
      {kind === "maximize" ? (
        <rect x="1" y="1" width="8" height="8" fill="none" stroke="currentColor" />
      ) : null}
      {kind === "restore" ? (
        <path d="M3 1h6v6M1 3h6v6H1z" fill="none" stroke="currentColor" />
      ) : null}
      {kind === "close" ? <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" /> : null}
    </svg>
  );
}
