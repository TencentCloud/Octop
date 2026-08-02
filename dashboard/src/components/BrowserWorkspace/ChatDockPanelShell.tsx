import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dropdown, Tooltip } from "antd";
import type { MenuProps } from "antd";
import { useTranslation } from "react-i18next";
import {
  Check,
  Maximize2,
  Minimize2,
  MoreVertical,
  PanelBottom,
  PanelRight,
  PictureInPicture2,
  X,
} from "lucide-react";
import { beginPointerDragSession } from "../../hooks/usePointerDragSession";
import type { PanelMode } from "./index";
import styles from "./ChatBrowserPanel.module.less";

interface ChatDockPanelShellProps {
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  /** Left-side title (filename / “远程浏览器”). */
  title?: React.ReactNode;
  /** Content actions left of the layout/close group (mode, refresh, download…). */
  toolbarActions?: React.ReactNode;
  children: React.ReactNode;
}

const POPUP_MIN_W = 360;
const POPUP_MIN_H = 280;

/**
 * Stacking for floating dock. Keep CSS (ChatBrowserPanel.module.less) in sync:
 *   .popupMask  / .popup  use the same numbers.
 * Antd Dropdown defaults (~1050) sit *under* the panel without POPUP_Z.menu.
 */
const POPUP_Z = {
  mask: 1100,
  panel: 1101,
  menu: 2100,
} as const;

/**
 * Clear drag/placement offsets written outside React.
 * Never touch width/height here — right dock owns width via React ``style``.
 */
function clearPopupPlacementStyles(panel: HTMLElement | null) {
  if (!panel) return;
  for (const prop of [
    "left",
    "top",
    "right",
    "bottom",
    "transform",
  ] as const) {
    panel.style.removeProperty(prop);
  }
}

/**
 * Drop size written by corner-resize only when React is not driving that axis.
 * Clearing React-owned ``width`` (right dock) collapses the panel to empty.
 */
function clearPopupSizeIfUnowned(
  panel: HTMLElement | null,
  reactStyle?: React.CSSProperties,
) {
  if (!panel) return;
  if (reactStyle?.width === undefined) {
    panel.style.removeProperty("width");
  }
  if (reactStyle?.height === undefined) {
    panel.style.removeProperty("height");
  }
}

/** Leave popup → right/bottom: placement always; size only if unowned. */
function clearWhenLeavingPopup(
  panel: HTMLElement | null,
  reactStyle?: React.CSSProperties,
) {
  clearPopupPlacementStyles(panel);
  clearPopupSizeIfUnowned(panel, reactStyle);
}

/** Enter/exit fullscreen or reset centered popup: CSS owns geometry. */
function clearAllPopupCommandStyles(panel: HTMLElement | null) {
  clearPopupPlacementStyles(panel);
  if (!panel) return;
  panel.style.removeProperty("width");
  panel.style.removeProperty("height");
}

/**
 * Shared chat dock chrome for file / browser panels: layout mode switch
 * (bottom / right / popup), centered-draggable popup, corner resize, fullscreen
 * (popup only), and close.
 *
 * Popup move/resize mutate the panel DOM directly (rAF) so heavy children
 * (Monaco / markdown) are not React-re-rendered on every pointermove.
 * ``data-dock-resizing`` lets editors pause ``automaticLayout`` until pointerup.
 */
const ChatDockPanelShell: React.FC<ChatDockPanelShellProps> = ({
  mode,
  onModeChange,
  onClose,
  style,
  title,
  toolbarActions,
  children,
}) => {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const prevModeRef = useRef<PanelMode>(mode);
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [isPopupDragging, setIsPopupDragging] = useState(false);
  const [isPopupResizing, setIsPopupResizing] = useState(false);
  /** Popup-only: expand to full viewport (not a separate PanelMode). */
  const [popupFullscreen, setPopupFullscreen] = useState(false);
  const [layoutMenuOpen, setLayoutMenuOpen] = useState(false);
  const popupDragRef = useRef<{
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);
  const popupSizeRef = useRef<{
    startX: number;
    startY: number;
    origW: number;
    origH: number;
    origLeft: number;
    origTop: number;
  } | null>(null);
  const pendingPosRef = useRef<{ x: number; y: number } | null>(null);
  // After a drag, the mouseup can land on the mask (panel has pointer-events:
  // none while dragging) and would otherwise fire a spurious close.
  const suppressMaskCloseRef = useRef(false);

  const setResizingFlag = useCallback((on: boolean) => {
    const panel = panelRef.current;
    if (!panel) return;
    if (on) panel.setAttribute("data-dock-resizing", "1");
    else panel.removeAttribute("data-dock-resizing");
  }, []);

  // Only when leaving popup: drop drag state + rogue inline geometry.
  // Do not run clear on ordinary right/bottom mounts (wipes React width).
  useEffect(() => {
    const prev = prevModeRef.current;
    prevModeRef.current = mode;
    if (mode === "popup") return;

    setPopupPos(null);
    setIsPopupDragging(false);
    setIsPopupResizing(false);
    setPopupFullscreen(false);
    setLayoutMenuOpen(false);
    if (prev === "popup") {
      clearWhenLeavingPopup(panelRef.current, style);
    }
  }, [mode, style]);

  // Esc exits fullscreen only (keeps popup open).
  useEffect(() => {
    if (mode !== "popup" || !popupFullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopPropagation();
      setPopupFullscreen(false);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [mode, popupFullscreen]);

  // Enter/exit fullscreen: CSS owns size; drop command styles + nudge editors.
  useEffect(() => {
    if (mode !== "popup") return;
    clearAllPopupCommandStyles(panelRef.current);
    setPopupPos(null);
    setIsPopupDragging(false);
    setIsPopupResizing(false);
    setResizingFlag(true);
    const t = window.setTimeout(() => {
      setResizingFlag(false);
      window.dispatchEvent(new Event("resize"));
    }, 50);
    return () => {
      window.clearTimeout(t);
      setResizingFlag(false);
    };
  }, [popupFullscreen, mode, setResizingFlag]);

  const handlePopupDragStart = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== "popup" || popupFullscreen || e.button !== 0) return;
      const target = e.target as HTMLElement;
      if (
        target.closest("button") ||
        target.closest("input") ||
        target.closest("a") ||
        target.closest('[role="button"]') ||
        target.closest('[role="tab"]') ||
        target.closest(".octop-select, .ant-select") ||
        target.closest(".octop-segmented, .ant-segmented") ||
        target.closest(".octop-dropdown, .ant-dropdown") ||
        target.closest(`.${styles.popupResizeHandle}`)
      ) {
        return;
      }
      e.preventDefault();
      const panel = panelRef.current;
      if (!panel) return;
      const handle = e.currentTarget as HTMLElement;
      const rect = panel.getBoundingClientRect();
      // Lock centered (transform) position into left/top before the first move.
      const origin = popupPos ?? { x: rect.left, y: rect.top };
      if (!popupPos) {
        panel.style.left = `${origin.x}px`;
        panel.style.top = `${origin.y}px`;
        panel.style.right = "auto";
        panel.style.bottom = "auto";
        panel.style.transform = "none";
        setPopupPos(origin);
      }
      popupDragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origX: origin.x,
        origY: origin.y,
      };
      pendingPosRef.current = origin;
      setIsPopupDragging(true);

      beginPointerDragSession({
        pointerId: e.pointerId,
        target: handle,
        onMove: (clientX, clientY) => {
          const drag = popupDragRef.current;
          if (!drag) return;
          const dx = clientX - drag.startX;
          const dy = clientY - drag.startY;
          const el = panelRef.current;
          let newX = drag.origX + dx;
          let newY = drag.origY + dy;
          if (el) {
            const w = el.offsetWidth;
            const h = el.offsetHeight;
            newX = Math.max(0, Math.min(newX, window.innerWidth - w));
            newY = Math.max(0, Math.min(newY, window.innerHeight - h));
          }
          pendingPosRef.current = { x: newX, y: newY };
          if (panelRef.current) {
            panelRef.current.style.left = `${newX}px`;
            panelRef.current.style.top = `${newY}px`;
          }
        },
        onEnd: () => {
          const finalPos = pendingPosRef.current;
          pendingPosRef.current = null;
          popupDragRef.current = null;
          suppressMaskCloseRef.current = true;
          setIsPopupDragging(false);
          if (finalPos) setPopupPos(finalPos);
          window.setTimeout(() => {
            suppressMaskCloseRef.current = false;
          }, 0);
        },
      });
    },
    [mode, popupFullscreen, popupPos],
  );

  const handlePopupResizeStart = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== "popup" || popupFullscreen || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const panel = panelRef.current;
      if (!panel) return;
      const handle = e.currentTarget as HTMLElement;

      const rect = panel.getBoundingClientRect();
      // Ensure placed coordinates before resizing a centered popup.
      if (!popupPos) {
        panel.style.left = `${rect.left}px`;
        panel.style.top = `${rect.top}px`;
        panel.style.right = "auto";
        panel.style.bottom = "auto";
        panel.style.transform = "none";
        setPopupPos({ x: rect.left, y: rect.top });
      }

      popupSizeRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origW: rect.width,
        origH: rect.height,
        origLeft: rect.left,
        origTop: rect.top,
      };
      setIsPopupResizing(true);
      setResizingFlag(true);

      beginPointerDragSession({
        pointerId: e.pointerId,
        target: handle,
        cursor: "nwse-resize",
        onMove: (clientX, clientY) => {
          const start = popupSizeRef.current;
          if (!start || !panelRef.current) return;
          const maxW = window.innerWidth - start.origLeft - 8;
          const maxH = window.innerHeight - start.origTop - 8;
          const w = Math.min(
            maxW,
            Math.max(POPUP_MIN_W, start.origW + (clientX - start.startX)),
          );
          const h = Math.min(
            maxH,
            Math.max(POPUP_MIN_H, start.origH + (clientY - start.startY)),
          );
          panelRef.current.style.width = `${w}px`;
          panelRef.current.style.height = `${h}px`;
        },
        onEnd: () => {
          popupSizeRef.current = null;
          setIsPopupResizing(false);
          setResizingFlag(false);
        },
      });
    },
    [mode, popupFullscreen, popupPos, setResizingFlag],
  );

  const handleMaskClick = useCallback(() => {
    if (
      suppressMaskCloseRef.current ||
      isPopupDragging ||
      isPopupResizing ||
      layoutMenuOpen ||
      popupFullscreen
    ) {
      // Fullscreen covers the mask visually; don't close on stray clicks.
      return;
    }
    onClose();
  }, [
    isPopupDragging,
    isPopupResizing,
    layoutMenuOpen,
    onClose,
    popupFullscreen,
  ]);

  const applyLayoutMode = useCallback(
    (next: PanelMode) => {
      if (next === mode) return;
      if (mode === "popup") {
        setPopupFullscreen(false);
        // Clear before mode switch; right/bottom `style` still intact on next paint.
        clearWhenLeavingPopup(panelRef.current, style);
      }
      onModeChange(next);
    },
    [mode, onModeChange, style],
  );

  const togglePopupFullscreen = useCallback(() => {
    setPopupFullscreen((v) => !v);
  }, []);

  const popupStyle: React.CSSProperties | undefined =
    mode === "popup" && popupFullscreen
      ? { ...style }
      : mode === "popup" && popupPos
        ? {
            ...style,
            left: popupPos.x,
            top: popupPos.y,
            right: "auto",
            bottom: "auto",
            transform: "none",
          }
        : style;

  const layoutMenuItems: MenuProps["items"] = useMemo(
    () => [
      {
        key: "bottom",
        label: t("browserWorkspace.panelBottom"),
        icon: <PanelBottom size={14} />,
        extra: mode === "bottom" ? <Check size={14} /> : undefined,
      },
      {
        key: "right",
        label: t("browserWorkspace.panelRight"),
        icon: <PanelRight size={14} />,
        extra: mode === "right" ? <Check size={14} /> : undefined,
      },
      {
        key: "popup",
        label: t("browserWorkspace.panelPopup"),
        icon: <PictureInPicture2 size={14} />,
        extra: mode === "popup" ? <Check size={14} /> : undefined,
      },
    ],
    [mode, t],
  );

  const panel = (
    <div
      ref={panelRef}
      data-dock-panel=""
      className={`${styles.chatBrowserPanel} ${styles[mode]} ${
        popupPos && !popupFullscreen ? styles.popupPlaced : ""
      } ${isPopupDragging ? styles.popupDragging : ""} ${
        isPopupResizing ? styles.popupResizing : ""
      } ${popupFullscreen ? styles.popupFullscreen : ""}`}
      style={popupStyle}
    >
      <div
        className={styles.toolbar}
        onPointerDown={handlePopupDragStart}
        style={popupFullscreen ? { cursor: "default" } : undefined}
      >
        <div className={styles.toolbarTitle}>{title}</div>
        <div className={styles.toolbarSpacer} />
        {toolbarActions ? (
          <div className={styles.toolbarActions}>{toolbarActions}</div>
        ) : null}
        <div className={styles.toolbarModes}>
          {mode === "popup" && (
            <Tooltip
              title={
                popupFullscreen
                  ? t("browserWorkspace.exitFullscreen", "退出全屏")
                  : t("browserWorkspace.enterFullscreen", "全屏")
              }
            >
              <button
                type="button"
                className={styles.toolbarIconBtn}
                onClick={togglePopupFullscreen}
                onPointerDown={(e) => e.stopPropagation()}
                aria-label={
                  popupFullscreen
                    ? t("browserWorkspace.exitFullscreen", "退出全屏")
                    : t("browserWorkspace.enterFullscreen", "全屏")
                }
                aria-pressed={popupFullscreen}
              >
                {popupFullscreen ? (
                  <Minimize2 size={16} strokeWidth={1.8} />
                ) : (
                  <Maximize2 size={16} strokeWidth={1.8} />
                )}
              </button>
            </Tooltip>
          )}
          <Dropdown
            menu={{
              items: layoutMenuItems,
              selectedKeys: [mode],
              onClick: ({ key }) => applyLayoutMode(key as PanelMode),
            }}
            trigger={["click"]}
            placement="bottomRight"
            getPopupContainer={() => document.body}
            open={layoutMenuOpen}
            onOpenChange={setLayoutMenuOpen}
            overlayStyle={
              mode === "popup" ? { zIndex: POPUP_Z.menu } : undefined
            }
            overlayClassName={
              mode === "popup" ? styles.popupLayoutDropdown : undefined
            }
          >
            <button
              type="button"
              className={styles.toolbarIconBtn}
              aria-label={t("browserWorkspace.panelLayout", "面板布局")}
              onPointerDown={(e) => e.stopPropagation()}
            >
              <MoreVertical size={16} strokeWidth={1.8} />
            </button>
          </Dropdown>
          <button
            type="button"
            className={styles.toolbarIconBtn}
            onClick={onClose}
            onPointerDown={(e) => e.stopPropagation()}
            aria-label={t("common.close", "关闭")}
          >
            <X size={14} strokeWidth={1.8} />
          </button>
        </div>
      </div>
      {children}
      {mode === "popup" && !popupFullscreen && (
        <div
          className={styles.popupResizeHandle}
          onPointerDown={handlePopupResizeStart}
          role="separator"
          aria-orientation="horizontal"
          aria-label={t("chat.resizePopup", "调整窗口大小")}
        />
      )}
    </div>
  );

  if (mode !== "popup") {
    return panel;
  }

  return (
    <>
      <div
        className={`${styles.popupMask} ${
          popupFullscreen ? styles.popupMaskFullscreen : ""
        }`}
        onClick={handleMaskClick}
        aria-hidden
        style={
          layoutMenuOpen || popupFullscreen
            ? { pointerEvents: "none" }
            : undefined
        }
      />
      {panel}
    </>
  );
};

export default ChatDockPanelShell;
