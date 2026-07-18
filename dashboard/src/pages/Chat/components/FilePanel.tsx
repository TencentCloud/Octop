import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, Tooltip } from "antd";
import { useTranslation } from "react-i18next";
import { PanelBottom, PanelRight, PictureInPicture2, X } from "lucide-react";
import type { PanelMode } from "../../../components/BrowserWorkspace";
import FilePanelContent from "./FilePanelContent";
import styles from "../../../components/BrowserWorkspace/ChatBrowserPanel.module.less";

interface FilePanelProps {
  agentId: string;
  /** All workspace files written by the agent in this thread. */
  filePaths: string[];
  /** When set, opens on this path instead of the latest written one. */
  initialPath?: string | null;
  /** Controlled layout mode (owned by the chat shell, persisted there). */
  mode: PanelMode;
  onModeChange: (mode: PanelMode) => void;
  onClose: () => void;
  style?: React.CSSProperties;
}

/**
 * Docked file viewer/editor for the chat page — mirrors ``ChatBrowserPanel``
 * (mode switch: bottom / right / popup, popup drag, close) but renders the
 * shared ``FilePanelContent`` instead of a browser.
 */
const FilePanel: React.FC<FilePanelProps> = ({
  agentId,
  filePaths,
  initialPath,
  mode,
  onModeChange,
  onClose,
  style,
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
      <div className={styles.toolbar} onMouseDown={handlePopupDragStart}>
        <span className={styles.toolbarTitle}>{t("chat.openFile")}</span>
        <div className={styles.toolbarActions}>
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
          <Button
            type="text"
            size="small"
            icon={<X size={14} />}
            onClick={onClose}
          />
        </div>
      </div>
      <FilePanelContent
        agentId={agentId}
        filePaths={filePaths}
        initialPath={initialPath}
      />
    </div>
  );
};

export default FilePanel;
