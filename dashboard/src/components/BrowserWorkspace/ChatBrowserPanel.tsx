import React, {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Button, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import {
  PanelBottom,
  PanelRight,
  PictureInPicture2,
  X,
} from "lucide-react";
import BrowserWorkspace, {
  type PanelMode,
} from "./index";
import type { DisplayEnvironment } from "../../api/types/browser";
import styles from "./ChatBrowserPanel.module.less";

interface ChatBrowserPanelProps {
  /** Profile/session id forwarded to the browser view. */
  sessionId?: string | null;
  environment?: DisplayEnvironment;
  /** Controlled layout mode (owned by the chat shell, persisted there). */
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
  /** Bookmark state for the current URL (forwarded to the address bar). */
  bookmarked?: boolean;
  onToggleBookmark?: (url: string, title: string) => void;
}

/**
 * Chat-specific chrome around the shared BrowserWorkspace: panel-mode
 * switching (bottom / right / popup), popup drag-to-move, and close.
 *
 * All browser-view logic (connect, paint, session metadata, handoff) stays in
 * BrowserWorkspace so it can be reused by other surfaces without dragging
 * chat-specific UI along.
 */
const ChatBrowserPanel: React.FC<ChatBrowserPanelProps> = ({
  sessionId,
  environment,
  mode,
  onModeChange,
  onClose,
  style,
  bookmarked,
  onToggleBookmark,
}) => {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [isPopupDragging, setIsPopupDragging] = useState(false);
  const popupDragRef = useRef<{
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);

  const handlePopupDragStart = useCallback(
    (e: React.MouseEvent) => {
      if (mode !== "popup" || e.button !== 0) return;
      const target = e.target as HTMLElement;
      if (
        target.closest("button") ||
        target.closest("input") ||
        target.closest("a") ||
        target.closest('[role="button"]')
      ) {
        return;
      }
      e.preventDefault();
      setIsPopupDragging(true);
      const panel = panelRef.current;
      if (panel) {
        const rect = panel.getBoundingClientRect();
        popupDragRef.current = {
          startX: e.clientX,
          startY: e.clientY,
          origX: rect.left,
          origY: rect.top,
        };
      }
    },
    [mode],
  );

  useEffect(() => {
    if (!isPopupDragging) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!popupDragRef.current) return;
      const dx = e.clientX - popupDragRef.current.startX;
      const dy = e.clientY - popupDragRef.current.startY;
      const panel = panelRef.current;
      let newX = popupDragRef.current.origX + dx;
      let newY = popupDragRef.current.origY + dy;
      if (panel) {
        const w = panel.offsetWidth;
        const h = panel.offsetHeight;
        newX = Math.max(0, Math.min(newX, window.innerWidth - w));
        newY = Math.max(0, Math.min(newY, window.innerHeight - h));
      }
      setPopupPos({ x: newX, y: newY });
    };
    const handleMouseUp = () => {
      setIsPopupDragging(false);
      popupDragRef.current = null;
    };
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isPopupDragging]);

  const popupStyle: React.CSSProperties | undefined =
    mode === "popup" && popupPos
      ? {
          ...style,
          left: popupPos.x,
          top: popupPos.y,
          right: "auto",
          bottom: "auto",
        }
      : style;

  return (
    <div
      ref={panelRef}
      className={`${styles.chatBrowserPanel} ${styles[mode]} ${
        isPopupDragging ? styles.popupDragging : ""
      }`}
      style={popupStyle}
    >
      {/* Toolbar: layout switch + close. Draggable only in popup mode. */}
      <div className={styles.toolbar} onMouseDown={handlePopupDragStart}>
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
            icon={
              <PanelRight size={14} style={{ transform: "rotate(-90deg)" }} />
            }
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
        <Button
          type="text"
          size="small"
          icon={<X size={14} />}
          onClick={onClose}
        />
      </div>
      <BrowserWorkspace
        sessionId={sessionId}
        environment={environment}
        style={{ flex: 1, minHeight: 0 }}
        bookmarked={bookmarked}
        onToggleBookmark={onToggleBookmark}
      />
    </div>
  );
};

export default ChatBrowserPanel;
