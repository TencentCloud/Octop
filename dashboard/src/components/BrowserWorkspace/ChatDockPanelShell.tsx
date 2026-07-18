import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { PanelBottom, PanelRight, PictureInPicture2, X } from "lucide-react";
import { beginPointerDragSession } from "../../hooks/usePointerDragSession";
import type { PanelMode } from "./index";
import styles from "./ChatBrowserPanel.module.less";

interface ChatDockPanelShellProps {
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  children: React.ReactNode;
}

const POPUP_MIN_W = 360;
const POPUP_MIN_H = 280;

/**
 * Shared chat dock chrome for file / browser panels: layout mode switch
 * (bottom / right / popup), centered-draggable popup, corner resize, and close.
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
  children,
}) => {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [isPopupDragging, setIsPopupDragging] = useState(false);
  const [isPopupResizing, setIsPopupResizing] = useState(false);
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

  // Leaving popup clears the drag offset so the next open recenters.
  useEffect(() => {
    if (mode !== "popup") {
      setPopupPos(null);
      setIsPopupDragging(false);
      setIsPopupResizing(false);
    }
  }, [mode]);

  const setResizingFlag = useCallback((on: boolean) => {
    const panel = panelRef.current;
    if (!panel) return;
    if (on) panel.setAttribute("data-dock-resizing", "1");
    else panel.removeAttribute("data-dock-resizing");
  }, []);

  const handlePopupDragStart = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== "popup" || e.button !== 0) return;
      const target = e.target as HTMLElement;
      if (
        target.closest("button") ||
        target.closest("input") ||
        target.closest("a") ||
        target.closest('[role="button"]') ||
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
    [mode, popupPos],
  );

  const handlePopupResizeStart = useCallback(
    (e: React.PointerEvent) => {
      if (mode !== "popup" || e.button !== 0) return;
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
    [mode, popupPos, setResizingFlag],
  );

  const handleMaskClick = useCallback(() => {
    if (suppressMaskCloseRef.current || isPopupDragging || isPopupResizing) {
      return;
    }
    onClose();
  }, [isPopupDragging, isPopupResizing, onClose]);

  const popupStyle: React.CSSProperties | undefined =
    mode === "popup" && popupPos
      ? {
          ...style,
          left: popupPos.x,
          top: popupPos.y,
          right: "auto",
          bottom: "auto",
          transform: "none",
        }
      : style;

  const panel = (
    <div
      ref={panelRef}
      data-dock-panel=""
      className={`${styles.chatBrowserPanel} ${styles[mode]} ${
        popupPos ? styles.popupPlaced : ""
      } ${isPopupDragging ? styles.popupDragging : ""} ${
        isPopupResizing ? styles.popupResizing : ""
      }`}
      style={popupStyle}
    >
      <div className={styles.toolbar} onPointerDown={handlePopupDragStart}>
        <div className={styles.toolbarModes}>
          <Tooltip title={t("browserWorkspace.panelBottom")}>
            <Button
              type="text"
              size="small"
              icon={<PanelBottom size={14} />}
              className={mode === "bottom" ? styles.modeActive : ""}
              onClick={() => onModeChange("bottom")}
            />
          </Tooltip>
          <Tooltip title={t("browserWorkspace.panelRight")}>
            <Button
              type="text"
              size="small"
              icon={<PanelRight size={14} />}
              className={mode === "right" ? styles.modeActive : ""}
              onClick={() => onModeChange("right")}
            />
          </Tooltip>
          <Tooltip title={t("browserWorkspace.panelPopup")}>
            <Button
              type="text"
              size="small"
              icon={<PictureInPicture2 size={14} />}
              className={mode === "popup" ? styles.modeActive : ""}
              onClick={() => onModeChange("popup")}
            />
          </Tooltip>
        </div>
        <div className={styles.toolbarSpacer} />
        <Button
          type="text"
          size="small"
          icon={<X size={14} />}
          onClick={onClose}
        />
      </div>
      {children}
      {mode === "popup" && (
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
      <div className={styles.popupMask} onClick={handleMaskClick} aria-hidden />
      {panel}
    </>
  );
};

export default ChatDockPanelShell;
