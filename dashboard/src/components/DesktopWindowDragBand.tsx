import { useDesktopChromeStyle } from "../hooks/useDesktopChrome";
import { useWindowFullscreen } from "../hooks/useWindowFullscreen";
import {
  chromeTopBandPx,
  DESKTOP_DRAG_REGION_CLASS,
  windowControlsInset,
} from "../utils/desktopChrome";

/**
 * The hidden titlebar's hit target. Native buttons stay outside it: macOS
 * traffic lights on the leading edge, Windows caption buttons on the trailing
 * edge. `pointer-events: none` lets clicks reach controls underneath; those
 * controls opt out of dragging via the `no-drag` rules in `layout.css`.
 */
export default function DesktopWindowDragBand({
  position = "fixed",
}: {
  position?: "fixed" | "absolute";
}) {
  const desktopChrome = useDesktopChromeStyle();
  const windowFullscreen = useWindowFullscreen();
  if (!desktopChrome || windowFullscreen) return null;

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
