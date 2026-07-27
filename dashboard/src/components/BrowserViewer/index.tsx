import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type KeyboardEventHandler,
  type ReactNode,
} from "react";
import { Button, Input, Tooltip } from "antd";
import {
  ArrowLeft,
  ArrowRight,
  Globe,
  Plus,
  RotateCcw,
  Star,
  X,
  AlertTriangle,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type {
  BrowserStreamState,
  BrowserTab as StreamTab,
} from "../../hooks/useBrowserStream";
import { useBrowserCanvasInteraction } from "../../hooks/useBrowserCanvasInteraction";
import { paintBase64JpegToCanvas } from "../../utils/browserCanvas";
import { normalizeUrl } from "../../utils/normalizeUrl";
import StreamConnectingIndicator from "../StreamConnectingIndicator";
import styles from "./index.module.less";

/** Imperative handle so the parent can paint incoming frames onto the canvas. */
export interface BrowserViewerHandle {
  paintFrame: (base64Data: string) => void;
}

interface BrowserViewerProps {
  // --- stream state & actions (from useBrowserStream) ---
  status: BrowserStreamState;
  tabs: StreamTab[];
  switchTab: (tabId: number | string) => void;
  closeTab: (tabId: number | string) => void;
  newTab: () => void;
  sendEvent: (event: Record<string, unknown>) => boolean;

  // --- address bar (controlled by parent) ---
  navUrl: string;
  onNavUrlChange: (value: string) => void;
  onNavigate: (url: string) => void;

  /** Whether the canvas forwards mouse/scroll input. */
  interactive: boolean;

  /** Bookmark toggle for the current URL (address-bar star button). */
  bookmarked?: boolean;
  onToggleBookmark?: (url: string, title: string) => void;

  /** Extra actions rendered after the Go button (e.g. AI / skill buttons). */
  addressBarExtra?: ReactNode;

  /** Optional overlay rendered on top of the canvas (e.g. edge controls). */
  overlay?: ReactNode;

  /** Forwarded to the canvas keydown handler (optional). */
  onCanvasKeyDown?: KeyboardEventHandler<HTMLCanvasElement>;

  /** Called whenever a frame is painted (parent tracks readiness). */
  onFrameReadyChange?: (ready: boolean) => void;

  /** Reconnect handler shown in the error / connecting placeholder. */
  onReconnect?: () => void;

  /** Page-specific hint shown under the connecting placeholder. */
  connectingHint?: ReactNode;
}

function activeTabTitle(tabs: StreamTab[]): string {
  const active = tabs.find((t) => t.active);
  return active?.title ?? "";
}

/**
 * Shared browser view: canvas screencast preview, address bar (with bookmark
 * button) and tab management. Used by both the standalone /remote-browser page
 * and the chat BrowserWorkspace popup so their previews stay identical.
 *
 * Personalized features (install flow, AI panel, handoff, panel mode) live in
 * the callers.
 */
export const BrowserViewer = forwardRef<
  BrowserViewerHandle,
  BrowserViewerProps
>(function BrowserViewer(
  {
    status,
    tabs,
    switchTab,
    closeTab,
    newTab,
    sendEvent,
    navUrl,
    onNavUrlChange,
    onNavigate,
    interactive,
    bookmarked = false,
    onToggleBookmark,
    addressBarExtra,
    overlay,
    onCanvasKeyDown,
    onFrameReadyChange,
    onReconnect,
    connectingHint,
  },
  ref,
) {
  const { t } = useTranslation();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [frameReady, setFrameReady] = useState(false);

  const paintFrame = useCallback((base64Data: string) => {
    paintBase64JpegToCanvas(canvasRef.current, base64Data);
    setFrameReady(true);
  }, []);

  useImperativeHandle(ref, () => ({ paintFrame }), [paintFrame]);

  // Notify the parent whenever a frame is painted (parent tracks readiness).
  useEffect(() => {
    onFrameReadyChange?.(frameReady);
  }, [frameReady, onFrameReadyChange]);

  const forwardCanvasEvent = useCallback(
    (event: Record<string, unknown>) => {
      if (
        event.type === "click" ||
        event.type === "dblclick" ||
        event.type === "mousedown"
      ) {
        canvasRef.current?.focus();
      }
      sendEvent(event);
    },
    [sendEvent],
  );

  const {
    handleWheel,
    onPointerDown: handlePanPointerDown,
    onPointerMove: handlePointerMove,
    onPointerLeave: handlePointerLeave,
    onDoubleClick: handlePanDoubleClick,
    onContextMenu: handleContextMenu,
    isDragging,
    pointerStyle,
  } = useBrowserCanvasInteraction({
    enabled: interactive,
    canvasRef,
    onEvent: forwardCanvasEvent,
  });

  const isStreaming = status === "streaming" || status === "browser_started";
  const isConnecting = status === "connecting" || status === "browser_started";
  const isError = status === "error";

  const navUrlNormalized = normalizeUrl(navUrl);

  const handleGo = useCallback(() => {
    const target = normalizeUrl(navUrl);
    if (!target) return;
    onNavigate(target);
  }, [navUrl, onNavigate]);

  const handleNavInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleGo();
      }
    },
    [handleGo],
  );

  return (
    <div className={styles.browserViewer}>
      {/* Tab bar */}
      <div className={styles.tabBar}>
        {tabs.map((tab) => (
          <Tooltip key={String(tab.id)} title={tab.url} mouseEnterDelay={0.8}>
            <div
              className={`${styles.tab} ${tab.active ? styles.tabActive : ""}`}
              onClick={() => switchTab(tab.id)}
            >
              <Globe size={11} style={{ flexShrink: 0 }} />
              <span className={styles.tabLabel}>
                {tab.title || tab.url || tab.id}
              </span>
              {tabs.length > 1 && (
                <span
                  className={styles.tabClose}
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  title={t("browserViewer.closeTab")}
                >
                  <X size={10} />
                </span>
              )}
            </div>
          </Tooltip>
        ))}
        <Tooltip title={t("browserViewer.newTab")}>
          <div
            className={styles.tabNew}
            onClick={() => newTab()}
            title={t("browserViewer.newTab")}
          >
            <Plus size={12} />
          </div>
        </Tooltip>
      </div>

      {/* Address bar */}
      <div className={styles.addressBar}>
        <Tooltip title={t("browserViewer.goBack")}>
          <Button
            size="small"
            icon={<ArrowLeft size={14} />}
            onClick={() => sendEvent({ type: "goback" })}
          />
        </Tooltip>
        <Tooltip title={t("browserViewer.goForward")}>
          <Button
            size="small"
            icon={<ArrowRight size={14} />}
            onClick={() => sendEvent({ type: "goforward" })}
          />
        </Tooltip>
        <Tooltip title={t("browserViewer.reload")}>
          <Button
            size="small"
            icon={<RotateCcw size={14} />}
            onClick={() => sendEvent({ type: "reload" })}
          />
        </Tooltip>
        <Input
          size="small"
          className={styles.urlInput}
          value={navUrl}
          placeholder={t("browserViewer.urlPlaceholder")}
          onChange={(e) => onNavUrlChange(e.target.value)}
          onKeyDown={handleNavInputKeyDown}
          prefix={<Globe size={13} />}
          suffix={
            onToggleBookmark && (
              <Tooltip
                title={
                  bookmarked
                    ? t("browserViewer.bookmarkRemove")
                    : t("browserViewer.bookmarkAdd")
                }
              >
                <button
                  type="button"
                  className={`${styles.bookmarkBtn} ${
                    bookmarked ? styles.bookmarkBtnActive : ""
                  }`}
                  disabled={!navUrlNormalized}
                  aria-label={
                    bookmarked
                      ? t("browserViewer.bookmarkRemove")
                      : t("browserViewer.bookmarkAdd")
                  }
                  onClick={() => onToggleBookmark(navUrl, activeTabTitle(tabs))}
                >
                  <Star size={14} fill={bookmarked ? "currentColor" : "none"} />
                </button>
              </Tooltip>
            )
          }
        />
        <Button
          size="small"
          type="primary"
          onClick={handleGo}
          disabled={!navUrlNormalized}
        >
          {t("browserViewer.go")}
        </Button>
        {addressBarExtra}
      </div>

      {/* Viewport (canvas screencast) */}
      <div
        className={`${styles.viewportContainer} ${
          interactive ? styles.viewportInteractive : ""
        }`}
      >
        {isError ? (
          <div className={styles.placeholder}>
            <AlertTriangle
              size={24}
              style={{ marginBottom: 8, color: "#faad14" }}
            />
            <div style={{ marginBottom: 12 }}>
              {t("browserViewer.connectFailed")}
            </div>
            {onReconnect && (
              <Button type="primary" size="small" onClick={onReconnect}>
                {t("browserViewer.reconnect")}
              </Button>
            )}
          </div>
        ) : isConnecting && !frameReady ? (
          <div className={styles.placeholder}>
            <StreamConnectingIndicator
              label={
                isStreaming
                  ? t("browserViewer.streaming")
                  : t("browserViewer.connecting")
              }
              hint={connectingHint}
            />
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            tabIndex={0}
            className={`${styles.canvas} ${
              interactive ? styles.canvasInteractive : ""
            } ${!frameReady ? styles.canvasHidden : ""}`}
            style={{
              cursor: isDragging ? "grabbing" : "default",
              ...pointerStyle,
            }}
            onPointerDown={handlePanPointerDown}
            onPointerMove={handlePointerMove}
            onPointerLeave={handlePointerLeave}
            onDoubleClick={handlePanDoubleClick}
            onContextMenu={handleContextMenu}
            onWheel={handleWheel}
            onKeyDown={onCanvasKeyDown}
          />
        )}
        {overlay}
        {interactive && isStreaming && (
          <div className={styles.interactiveHint}>
            {t("browserViewer.interactiveHint")}
          </div>
        )}
      </div>
    </div>
  );
});

export default BrowserViewer;
