import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useWindowFullscreen } from "../hooks/useWindowFullscreen";
import { getDesktopBridge, isLinuxDesktopShell } from "../utils/desktopBridge";

/**
 * Square caption buttons for the Linux shell. Electron's title-bar overlay
 * paints Adwaita circles, so that overlay stays off and these sit in the
 * reserved corner of the menu row. Close turns red on hover.
 */
export default function LinuxWindowControls() {
  const { t } = useTranslation();
  const fullscreen = useWindowFullscreen();
  const [maximized, setMaximized] = useState(false);
  const linux = isLinuxDesktopShell();

  useEffect(() => {
    if (!linux) return;
    const controls = getDesktopBridge()?.windowControls;
    if (!controls) return;
    let cancelled = false;
    void controls.isMaximized().then((value) => {
      if (!cancelled) setMaximized(value);
    });
    const unsubscribe = controls.onMaximizedChange(setMaximized);
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [linux]);

  if (!linux || fullscreen || !getDesktopBridge()?.windowControls) return null;

  const controls = getDesktopBridge()?.windowControls;
  const restoreLabel = t("layout.windowRestore", "还原");
  const maximizeLabel = t("layout.windowMaximize", "最大化");

  return (
    <div
      className="octop-linux-controls"
      role="group"
      aria-label={t("layout.windowControls", "窗口控制")}
    >
      <button
        type="button"
        title={t("layout.windowMinimize", "最小化")}
        aria-label={t("layout.windowMinimize", "最小化")}
        onClick={() => controls?.minimize()}
      >
        <CaptionGlyph kind="minimize" />
      </button>
      <button
        type="button"
        title={maximized ? restoreLabel : maximizeLabel}
        aria-label={maximized ? restoreLabel : maximizeLabel}
        onClick={() => controls?.toggleMaximize()}
      >
        <CaptionGlyph kind={maximized ? "restore" : "maximize"} />
      </button>
      <button
        type="button"
        className="octop-linux-controls-close"
        title={t("layout.windowClose", "关闭")}
        aria-label={t("layout.windowClose", "关闭")}
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
        <rect
          x="1"
          y="1"
          width="8"
          height="8"
          fill="none"
          stroke="currentColor"
        />
      ) : null}
      {kind === "restore" ? (
        <path d="M3 1h6v6M1 3h6v6H1z" fill="none" stroke="currentColor" />
      ) : null}
      {kind === "close" ? (
        <path d="M2 2l6 6M8 2L2 8" stroke="currentColor" />
      ) : null}
    </svg>
  );
}
