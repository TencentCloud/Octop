import { useDesktopChromeStyle } from "../hooks/useDesktopChrome";
import { useWindowFullscreen } from "../hooks/useWindowFullscreen";
import {
  chromeTopBandPx,
  DESKTOP_DRAG_REGION_CLASS,
  windowControlsInset,
} from "../utils/desktopChrome";

/**
 * macOS title-bar hit target, beside the traffic lights. Windows does not use
 * this strip: the caption menu row is the only place you can hold and drag
 * the window. `pointer-events: none` lets clicks reach controls underneath;
 * those controls opt out of dragging via the `no-drag` rules in `layout.css`.
 */
export default function DesktopWindowDragBand({
  position = "fixed",
}: {
  position?: "fixed" | "absolute";
}) {
  const desktopChrome = useDesktopChromeStyle();
  const windowFullscreen = useWindowFullscreen();
  if (desktopChrome !== "mac" || windowFullscreen) return null;

  return (
    <div
      aria-hidden
      className={`${DESKTOP_DRAG_REGION_CLASS} octop-shell-drag-band`}
      style={{
        position,
        top: 0,
        left: windowControlsInset(desktopChrome, "start"),
        right: windowControlsInset(desktopChrome, "end"),
        height: chromeTopBandPx(desktopChrome),
        pointerEvents: "none",
      }}
    />
  );
}
