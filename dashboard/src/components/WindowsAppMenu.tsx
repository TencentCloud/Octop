import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useDesktopChromeStyle } from "../hooks/useDesktopChrome";
import {
  DESKTOP_DRAG_REGION_CLASS,
  WINDOWS_CAPTION_HEIGHT,
} from "../utils/desktopChrome";
import {
  getDesktopBridge,
  type WindowsMenuModel,
} from "../utils/desktopBridge";
import { chromeSlot } from "../utils/overlayLayers";
import LinuxWindowControls from "./LinuxWindowControls";

/**
 * One full-width caption row on Windows and Linux. The transparent overlay
 * hides the native menu bar, so this row carries File / Edit / View / Help
 * beside the window buttons and draws each submenu in the page. Choosing an
 * item asks the shell to run that command.
 * Fullscreen keeps this row; the native caption buttons are hidden separately.
 * The row is the top flex item (`#octop-chrome`). Popups mount in
 * `#octop-stage` below it, so they cannot cover this row. The open submenu
 * still portals to `document.body` so it can hang over the page.
 */
export default function WindowsAppMenu() {
  const desktopChrome = useDesktopChromeStyle();
  const barRef = useRef<HTMLDivElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const titleRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [model, setModel] = useState<WindowsMenuModel | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [popupBox, setPopupBox] = useState<{
    top: number;
    left: number;
  } | null>(null);
  const showRow = desktopChrome === "windows";

  useEffect(() => {
    const root = document.documentElement;
    if (!showRow) {
      delete root.dataset.octopCaptionRow;
      root.style.removeProperty("--octop-caption-row");
      return;
    }
    root.dataset.octopCaptionRow = "";
    root.style.setProperty(
      "--octop-caption-row",
      `${WINDOWS_CAPTION_HEIGHT}px`,
    );
    return () => {
      delete root.dataset.octopCaptionRow;
      root.style.removeProperty("--octop-caption-row");
    };
  }, [showRow]);

  useEffect(() => {
    if (!showRow) return;
    const menu = getDesktopBridge()?.windowsMenu;
    if (!menu) return;
    let cancelled = false;
    void menu.model().then((value) => {
      if (!cancelled && value) setModel(value);
    });
    return () => {
      cancelled = true;
    };
  }, [showRow]);

  useLayoutEffect(() => {
    if (open === null) {
      setPopupBox(null);
      return;
    }
    const place = () => {
      const title = titleRefs.current[open];
      if (!title) return;
      const rect = title.getBoundingClientRect();
      setPopupBox({ top: rect.bottom + 4, left: rect.left });
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [open]);

  useEffect(() => {
    if (open === null) return;
    const closeOnOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (
        barRef.current?.contains(target) ||
        popupRef.current?.contains(target)
      )
        return;
      setOpen(null);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(null);
    };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  if (!showRow) return null;

  const titles = model?.titles ?? [];
  const entries = open === null ? [] : model?.menus[open] ?? [];
  const popup =
    open !== null && popupBox
      ? createPortal(
          <div
            ref={popupRef}
            className="octop-win-menu-popup"
            role="menu"
            style={{ top: popupBox.top, left: popupBox.left }}
          >
            {entries.map((entry, entryIndex) =>
              entry.kind === "separator" ? (
                <div
                  key={`sep-${entryIndex}`}
                  className="octop-win-menu-sep"
                  role="separator"
                />
              ) : (
                <button
                  key={entry.id}
                  type="button"
                  role="menuitem"
                  className="octop-win-menu-command"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => {
                    setOpen(null);
                    void getDesktopBridge()?.windowsMenu?.invoke(entry.id);
                  }}
                >
                  <span>{entry.label}</span>
                  {entry.accelerator ? (
                    <span className="octop-win-menu-accel">
                      {entry.accelerator}
                    </span>
                  ) : null}
                </button>
              ),
            )}
          </div>,
          document.body,
        )
      : null;

  return createPortal(
    <div
      ref={barRef}
      className={`${DESKTOP_DRAG_REGION_CLASS} octop-win-menu`}
      role="menubar"
    >
      {titles.map((label, index) => {
        const expanded = open === index;
        return (
          <div key={label} className="octop-win-menu-slot">
            <button
              ref={(node) => {
                titleRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              aria-haspopup="menu"
              aria-expanded={expanded}
              className={
                expanded ? "octop-win-menu-item is-open" : "octop-win-menu-item"
              }
              onMouseDown={(event) => event.preventDefault()}
              onMouseEnter={() => {
                if (open !== null) setOpen(index);
              }}
              onClick={() => setOpen(expanded ? null : index)}
            >
              {label}
            </button>
          </div>
        );
      })}
      {popup}
      <LinuxWindowControls />
    </div>,
    chromeSlot(),
  );
}
