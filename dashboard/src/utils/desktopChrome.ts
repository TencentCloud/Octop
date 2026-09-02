type DesktopWindow = Window & {
  _wails?: { invoke?: (message: string) => void };
};

export type DesktopChromeStyle = "mac" | "windows";
export type DesktopWindowAction = "minimise" | "toggle-maximise" | "close";

export const WINDOW_CONTROLS_INSET: Record<DesktopChromeStyle, number> = {
  // 3×12px lights + 2×8px gaps + 8px/12px padding, plus a little slack.
  mac: 80,
  // 3 × 46px caption buttons.
  windows: 138,
};

/** Right-edge overlay chrome (dock toolbar, etc.) to keep clear of caption buttons. */
export const CHROME_END_PAD_ATTR = "data-octop-chrome-end-pad";
export const WINDOW_CONTROLS_SPACER_ATTR = "data-octop-window-controls-spacer";

/**
 * Dock toolbar already has 12px end padding. Subtract that plus 6px so the
 * ⋮ / close group sits a few pixels closer to the caption buttons than the
 * personalization title row.
 */
export const DOCK_WINDOW_CONTROLS_PAD_PX = 18;

const INSET_VAR = "--window-controls-inset-end";

/** Inline padding so CSS-module `padding` shorthands cannot clobber the inset. */
export function chromeEndPadValue(minPx = 12): string {
  return `max(${minPx}px, var(${INSET_VAR}, 0px))`;
}

/** Pixel width of a flex spacer that clears overlay caption buttons. */
export function windowControlsEndSpacerPx(
  chrome: DesktopChromeStyle | null,
  panelTouchesWindowEnd: boolean,
  existingEndPadPx = 0,
): number {
  if (!chrome || !panelTouchesWindowEnd) return 0;
  return Math.max(0, WINDOW_CONTROLS_INSET[chrome] - existingEndPadPx);
}

/** Marks shell chrome that Wails should treat as a window-drag region. */
export const DESKTOP_DRAG_REGION_CLASS = "octop-desktop-drag";
export const DESKTOP_NO_DRAG_CLASS = "octop-desktop-no-drag";
export const DESKTOP_TITLEBAR_DRAG_HEIGHT = 32;

const NO_DRAG_SELECTOR =
  'button, a, input, textarea, select, [role="button"], [role="menuitem"], [data-octop-no-drag], .octop-desktop-no-drag';

export function isDesktopShell(
  win: Pick<DesktopWindow, "_wails"> = window as DesktopWindow,
): boolean {
  return typeof win._wails?.invoke === "function";
}

export function resolveDesktopChromeStyle(
  userAgent = navigator.userAgent,
): DesktopChromeStyle {
  if (/Mac|iPhone|iPad/.test(userAgent)) return "mac";
  return "windows";
}

export function titleRowEndPadding(outerPadPx: number): string {
  return `max(0px, calc(var(${INSET_VAR}, 0px) - ${outerPadPx}px))`;
}

export function applyDesktopChrome(
  style: DesktopChromeStyle | null,
  root: HTMLElement = document.documentElement,
): void {
  if (!style) {
    delete root.dataset.octopDesktopChrome;
    root.style.removeProperty(INSET_VAR);
    return;
  }
  root.dataset.octopDesktopChrome = style;
  root.style.setProperty(INSET_VAR, `${WINDOW_CONTROLS_INSET[style]}px`);
}

export function emitDesktopWindowAction(
  action: DesktopWindowAction,
  win: Pick<DesktopWindow, "_wails"> = window as DesktopWindow,
): boolean {
  const invoke = win._wails?.invoke;
  if (typeof invoke !== "function") return false;
  invoke(`wails:event:emit:desktop:${action}`);
  return true;
}

function dragEventElement(target: EventTarget | null): Element | null {
  if (target instanceof Element) return target;
  if (target instanceof Node) return target.parentElement;
  return null;
}

/** True when a primary click should start a frameless window-drag gesture. */
export function shouldArmDesktopDrag(
  event: Pick<MouseEvent, "button" | "clientY" | "target">,
): boolean {
  if (event.button !== 0) return false;
  const el = dragEventElement(event.target);
  if (!el) return false;
  if (el.closest(NO_DRAG_SELECTOR)) return false;
  const value = window
    .getComputedStyle(el)
    .getPropertyValue("--wails-draggable")
    .trim();
  if (value === "no-drag") return false;
  if (value === "drag") return true;
  return event.clientY <= DESKTOP_TITLEBAR_DRAG_HEIGHT;
}

/**
 * Wails only injects `_wails.invoke` into the remote dashboard origin.
 * The official `--wails-draggable` listeners live in `/wails/runtime.js`,
 * which this page never loads, so we start `wails:drag` ourselves.
 */
export function installDesktopWindowDrag(
  win: DesktopWindow = window as DesktopWindow,
): boolean {
  const invoke = win._wails?.invoke;
  if (typeof invoke !== "function") return false;
  const root = document.documentElement;
  if (root.dataset.octopDragReady === "1") return false;
  root.dataset.octopDragReady = "1";

  let armed = false;
  let startX = 0;
  let startY = 0;
  win.addEventListener(
    "mousedown",
    (event) => {
      if (!shouldArmDesktopDrag(event)) return;
      armed = true;
      startX = event.screenX;
      startY = event.screenY;
    },
    true,
  );
  win.addEventListener(
    "mousemove",
    (event) => {
      if (!armed) return;
      if (
        Math.abs(event.screenX - startX) < 3 &&
        Math.abs(event.screenY - startY) < 3
      ) {
        return;
      }
      armed = false;
      invoke("wails:drag");
    },
    true,
  );
  win.addEventListener(
    "mouseup",
    () => {
      armed = false;
    },
    true,
  );
  win.addEventListener(
    "dblclick",
    (event) => {
      if (!shouldArmDesktopDrag(event)) return;
      invoke("wails:drag:doubleclick");
    },
    true,
  );
  return true;
}
