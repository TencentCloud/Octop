import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button, Input, Select, Tag, Tooltip, Space } from "antd";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowLeftRight,
  ArrowRight,
  Globe,
  Loader2,
  Monitor,
  PanelBottom,
  PanelRight,
  PictureInPicture2,
  RefreshCw,
  User,
  X,
} from "lucide-react";
import { api } from "../../api";
import type {
  BrowserSession,
  DisplayEnvironment,
} from "../../api/types/browser";
import { useBrowserStream } from "../../hooks/useBrowserStream";
import {
  useViewportMode,
  VIEWPORT_MODE_OPTIONS,
} from "../../hooks/useViewportMode";
import { normalizeUrl } from "../../utils/normalizeUrl";
import { paintBase64JpegToCanvas } from "../../utils/browserCanvas";
import { viewportModeLabel } from "../../utils/browserViewport";
import { useBrowserCanvasInteraction } from "../../hooks/useBrowserCanvasInteraction";
import { showApiError } from "../../utils/showApiToast";
import styles from "./index.module.less";

export type PanelMode = "hidden" | "bottom" | "right" | "popup";

const PANEL_MODE_KEY = "finnie:browser-panel:mode";
const DEFAULT_URL = "https://cloud.tencent.com";

const loadSavedMode = (): PanelMode => {
  try {
    const saved = localStorage.getItem(PANEL_MODE_KEY);
    if (saved === "bottom" || saved === "right" || saved === "popup") {
      return saved;
    }
  } catch {
    // Ignore
  }
  return "popup";
};

const savePanelMode = (mode: PanelMode) => {
  try {
    if (mode !== "hidden") {
      localStorage.setItem(PANEL_MODE_KEY, mode);
    }
  } catch {
    // Ignore
  }
};

interface BrowserWorkspaceProps {
  /** Conversation/session id used to attach the screencast to the agent's
   *  Chrome. Falls back to "default" on the backend when absent. */
  sessionId?: string | null;
  environment?: DisplayEnvironment;
  initialMode?: PanelMode;
  onModeChange?: (mode: PanelMode) => void;
  onClose?: () => void;
  style?: React.CSSProperties;
}

const BrowserWorkspace: React.FC<BrowserWorkspaceProps> = ({
  sessionId,
  environment = "desktop",
  initialMode,
  onModeChange,
  onClose,
  style,
}) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState<PanelMode>(
    () => initialMode ?? loadSavedMode(),
  );
  // Chat popup defaults to a fixed 1280×800 — the pane is too small for
  // ``auto`` to render most desktop sites legibly.
  const {
    mode: vpMode,
    setMode: setVpMode,
    resolve: resolveViewport,
  } = useViewportMode("finnie:browser-panel:viewport-mode", "1280x800");
  const {
    status,
    tabs,
    sessionInfo,
    connect,
    sendEvent,
    navigate: streamNavigate,
    switchTab,
    closeTab,
    newTab,
    stop,
    disconnect,
  } = useBrowserStream();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const canvasContainerRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const [url, setUrl] = useState(DEFAULT_URL);
  const urlEditingRef = useRef(false);
  const [session, setSession] = useState<BrowserSession | null>(null);
  const [authAlert, setAuthAlert] = useState<string | null>(null);

  // Popup drag-to-move state
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

  const isStreaming = status === "streaming";
  const isConnecting = status === "connecting" || status === "browser_started";

  const viewportSelectOptions = useMemo(
    () =>
      VIEWPORT_MODE_OPTIONS.map((o) => ({
        value: o.value,
        label: viewportModeLabel(o.value, t),
      })),
    [t],
  );

  // -------------------------------------------------------------------------
  // Frame rendering — match RemoteBrowser/index.tsx exactly so behaviour stays
  // identical between the standalone page and the chat popup.
  // -------------------------------------------------------------------------
  const handleFrame = useCallback((base64Data: string) => {
    paintBase64JpegToCanvas(canvasRef.current, base64Data);
  }, []);

  // -------------------------------------------------------------------------
  // Auto-connect when the panel opens — the user is opening the popup to
  // *watch* the agent, so don't make them click "start". We pass an empty
  // url so the backend skips navigation and just attaches to whatever tab
  // the agent already opened (see screencast.start: only navigates when
  // initial_url is set and != "about:blank").
  // -------------------------------------------------------------------------
  const startStream = useCallback(
    (targetUrl: string) => {
      const containerEl = canvasContainerRef.current;
      const cw = containerEl?.clientWidth ?? 0;
      const ch = containerEl?.clientHeight ?? 0;
      const vp = resolveViewport(cw, ch) ?? { width: 1440, height: 900 };
      connect(
        targetUrl,
        vp.width,
        vp.height,
        {
          onFrame: handleFrame,
          onError: (msg) =>
            showApiError(msg, t("browserWorkspace.streamError"), t),
        },
        { sessionId: sessionId ?? undefined },
      );
    },
    [connect, handleFrame, sessionId, resolveViewport, t],
  );

  // First connect on mount (or when sessionId / panel mode / viewport mode changes).
  useEffect(() => {
    if (mode === "hidden") return;
    // Use empty string to "attach without navigating" — the backend's
    // BrowserStreamSession will pick whichever tab the agent has open.
    startStream("");
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, sessionId, vpMode]);

  // Keep the URL bar in sync with the active tab — but never stomp while typing.
  useEffect(() => {
    if (urlEditingRef.current) return;
    const activeTab = tabs.find((t) => t.active);
    if (activeTab && activeTab.url && activeTab.url !== "about:blank") {
      setUrl(activeTab.url);
    }
  }, [tabs]);

  useEffect(() => {
    if (urlEditingRef.current) return;
    const fromSession = session?.current_url ?? sessionInfo?.current_url ?? "";
    if (fromSession && fromSession !== "about:blank") {
      setUrl(fromSession);
    }
  }, [session?.current_url, sessionInfo?.current_url]);

  // In ``auto`` mode, forward container size changes so Chrome's viewport
  // tracks the panel size live (no letterboxing, no upscale blur). In fixed
  // modes, the viewport stays pinned to the user's preset; container resize
  // just rescales the canvas via CSS.
  useEffect(() => {
    if (vpMode !== "auto") return;
    const containerEl = canvasContainerRef.current;
    if (!containerEl) return;

    let lastSent = { w: 0, h: 0 };
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;

    const flushResize = () => {
      const w = containerEl.clientWidth;
      const h = containerEl.clientHeight;
      if (w === 0 || h === 0) return;
      if (isStreaming && (w !== lastSent.w || h !== lastSent.h)) {
        lastSent = { w, h };
        sendEvent({ type: "resize", width: w, height: h });
      }
    };

    const onResize = () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(flushResize, 150);
    };

    flushResize();
    const ro = new ResizeObserver(onResize);
    ro.observe(containerEl);
    window.addEventListener("resize", onResize);
    return () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
    };
  }, [isStreaming, sendEvent, vpMode]);

  // Apply session_update events from the backend (auth state, control owner).
  useEffect(() => {
    if (!sessionInfo) return;
    if (sessionId && sessionInfo.session_id !== sessionId) return;
    setSession((prev) => {
      if (prev && prev.session_id === sessionInfo.session_id) {
        return {
          ...prev,
          state: sessionInfo.state || prev.state,
          control_owner: sessionInfo.control_owner ?? prev.control_owner,
          current_url: sessionInfo.current_url || prev.current_url,
        };
      }
      return {
        session_id: sessionInfo.session_id,
        profile_name: "default",
        conversation_id: sessionInfo.conversation_id,
        channel_source: sessionInfo.channel_source,
        state: sessionInfo.state || "idle",
        control_owner: sessionInfo.control_owner ?? "agent",
        current_url: sessionInfo.current_url ?? "",
        created_at: Date.now(),
        last_activity_at: Date.now(),
      };
    });
    const s = sessionInfo.state ?? "";
    if (s === "awaiting_user_auth") {
      setAuthAlert(t("browserWorkspace.awaitingUserAuth"));
    } else if (s === "authenticating") {
      setAuthAlert(t("browserWorkspace.authenticating"));
    } else {
      setAuthAlert(null);
    }
  }, [sessionInfo, sessionId, t]);

  // Initial HTTP fetch for session metadata (handoff buttons, current URL).
  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.getSessions();
        if (cancelled) return;
        if (resp.ok) {
          const found = resp.sessions.find((s) => s.session_id === sessionId);
          if (found) setSession(found);
        }
      } catch {
        // Ignore
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const controlOwner: "agent" | "user" = session?.control_owner ?? "agent";
  const stateLabel = session?.state ?? "idle";
  const profileName = session?.profile_name ?? "default";
  const isInteractive = controlOwner === "user";
  const isAuthNeeded =
    stateLabel === "awaiting_user_auth" || stateLabel === "authenticating";

  const sendPanScroll = useCallback(
    (x: number, y: number, deltaX: number, deltaY: number) => {
      sendEvent({ type: "scroll", x, y, deltaX, deltaY });
    },
    [sendEvent],
  );

  const sendPanClick = useCallback(
    (x: number, y: number) => {
      sendEvent({ type: "click", x, y });
    },
    [sendEvent],
  );

  const sendPanDoubleClick = useCallback(
    (x: number, y: number) => {
      sendEvent({ type: "dblclick", x, y });
    },
    [sendEvent],
  );

  const {
    handleWheel,
    onPointerDown: handlePanPointerDown,
    onDoubleClick: handleDoubleClick,
    isDragging,
  } = useBrowserCanvasInteraction({
    enabled: isStreaming && isInteractive,
    canvasRef,
    onScroll: sendPanScroll,
    onClick: sendPanClick,
    onDoubleClick: sendPanDoubleClick,
  });

  // Keyboard input — only forward when the user is in control.
  useEffect(() => {
    if (!isStreaming || !isInteractive) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      // Only when the panel itself is focused (avoids capturing chat input).
      if (!panelRef.current?.contains(document.activeElement)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        sendEvent({ type: "type", text: e.key });
      } else {
        sendEvent({ type: "keydown", key: e.key });
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isStreaming, isInteractive, sendEvent]);

  // -------------------------------------------------------------------------
  // Top URL bar — "Go" button so the user can navigate the agent's browser.
  // -------------------------------------------------------------------------
  const handleNavigate = useCallback(() => {
    const target = normalizeUrl(url);
    if (!target) return;
    setUrl(target);
    if (isStreaming) {
      streamNavigate(target);
    } else {
      startStream(target);
    }
  }, [url, isStreaming, streamNavigate, startStream]);

  // -------------------------------------------------------------------------
  // Handoff
  // -------------------------------------------------------------------------
  const handleHandoff = useCallback(
    async (target: "agent" | "user") => {
      const sid = sessionId ?? sessionInfo?.session_id;
      if (!sid) return;
      try {
        const resp = await api.handoff(sid, target, "user_button");
        if (resp.ok) setSession(resp.session);
      } catch (err) {
        console.error("Handoff failed:", err);
        showApiError(err, t("browserWorkspace.handoffFailed"), t);
      }
    },
    [sessionId, sessionInfo, t],
  );

  // -------------------------------------------------------------------------
  // Mode switching + popup drag
  // -------------------------------------------------------------------------
  const switchMode = useCallback(
    (newMode: PanelMode) => {
      setMode(newMode);
      savePanelMode(newMode);
      onModeChange?.(newMode);
      if (newMode === "popup") setPopupPos(null);
    },
    [onModeChange],
  );

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
      let newX = popupDragRef.current.origX + dx;
      let newY = popupDragRef.current.origY + dy;
      const panel = panelRef.current;
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

  const handleClose = useCallback(() => {
    stop();
    setMode("hidden");
    onClose?.();
  }, [stop, onClose]);

  const handleRetry = useCallback(() => {
    // Pass an empty url so the backend reattaches to whatever tab the
    // agent already has open instead of force-navigating to DEFAULT_URL.
    // The user can still explicitly navigate via the URL bar (which calls
    // streamNavigate / startStream(finalUrl)).
    disconnect();
    startStream("");
  }, [disconnect, startStream]);

  const sessionStateLabel = useMemo(() => {
    if (controlOwner === "user") return t("browserWorkspace.userTakeoverShort");
    const key = `browserWorkspace.state.${stateLabel}`;
    const translated = t(key);
    return translated !== key ? translated : stateLabel;
  }, [controlOwner, stateLabel, t]);

  if (mode === "hidden") return null;

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

  const hasSession = !!(sessionId ?? sessionInfo?.session_id);
  const currentUrl = session?.current_url ?? sessionInfo?.current_url ?? "";

  return (
    <div
      ref={panelRef}
      className={`${styles.browserWorkspace} ${styles[mode]} ${
        isPopupDragging ? styles.popupDragging : ""
      }`}
      style={popupStyle}
    >
      {/* Header — draggable in popup mode */}
      <div
        className={`${styles.header} ${
          mode === "popup" ? styles.headerDraggable : ""
        }`}
        onMouseDown={handlePopupDragStart}
      >
        <div className={styles.headerLeft}>
          {hasSession ? (
            <>
              <span
                className={styles.profileBadge}
                style={{ background: isAuthNeeded ? "#faad14" : "#FF6B35" }}
              >
                <Monitor size={14} />
                {profileName}
              </span>
              <span className={`${styles.statusDot} ${styles[controlOwner]}`} />
              <span
                className={`${styles.controlLabel} ${
                  controlOwner === "user" ? styles.takeoverActive : ""
                }`}
              >
                {controlOwner === "agent"
                  ? t("browserWorkspace.agentControl")
                  : t("browserWorkspace.userTakeover")}
              </span>
              {isInteractive && (
                <Tag color="blue" className={styles.interactiveTag}>
                  {t("browserWorkspace.interactive")}
                </Tag>
              )}
              {isAuthNeeded && (
                <Tag color="warning" className={styles.authTag}>
                  {t("browserWorkspace.needLogin")}
                </Tag>
              )}
              <Tooltip title={currentUrl}>
                <span className={styles.currentUrl}>{currentUrl}</span>
              </Tooltip>
            </>
          ) : (
            <span className={styles.emptyHeaderTitle}>
              <Globe size={14} style={{ marginRight: 6 }} />
              {t("browserWorkspace.title")}
            </span>
          )}
        </div>
        <div className={styles.headerRight}>
          <Tooltip title={t("browserWorkspace.resolution")}>
            <Select
              size="small"
              value={vpMode}
              onChange={setVpMode}
              options={viewportSelectOptions}
              style={{ width: 96 }}
            />
          </Tooltip>
          <Tooltip title={t("browserWorkspace.reconnect")}>
            <Button
              type="text"
              size="small"
              icon={<RefreshCw size={14} />}
              onClick={handleRetry}
            />
          </Tooltip>
          <Tooltip title={t("browserWorkspace.panelBottom")}>
            <Button
              type="text"
              size="small"
              icon={<PanelBottom size={14} />}
              className={mode === "bottom" ? styles.modeActive : ""}
              onClick={() => switchMode("bottom")}
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
              onClick={() => switchMode("right")}
            />
          </Tooltip>
          <Tooltip title={t("browserWorkspace.panelPopup")}>
            <Button
              type="text"
              size="small"
              icon={<PictureInPicture2 size={14} />}
              className={mode === "popup" ? styles.modeActive : ""}
              onClick={() => switchMode("popup")}
            />
          </Tooltip>
          <Button
            type="text"
            size="small"
            icon={<X size={14} />}
            onClick={handleClose}
          />
        </div>
      </div>

      {/* Auth alert banner */}
      {authAlert && isAuthNeeded && (
        <div className={styles.authBanner}>
          <AlertTriangle size={14} style={{ marginRight: 8 }} />
          {authAlert}
          <button
            className={styles.authBannerClose}
            onClick={() => setAuthAlert(null)}
          >
            ×
          </button>
        </div>
      )}

      {/* URL bar — lets the user navigate the agent's browser when needed */}
      <div className={styles.urlBar}>
        <Input
          className={styles.urlBarInput}
          size="small"
          value={url}
          placeholder={t("browserWorkspace.urlPlaceholder")}
          onFocus={() => {
            urlEditingRef.current = true;
          }}
          onBlur={() => {
            urlEditingRef.current = false;
          }}
          onChange={(e) => setUrl(e.target.value)}
          onPressEnter={handleNavigate}
          suffix={
            <Tooltip title={t("browserWorkspace.visit")}>
              <Button
                type="text"
                size="small"
                icon={<ArrowRight size={14} />}
                onClick={handleNavigate}
              />
            </Tooltip>
          }
        />
      </div>

      {/* Tab bar */}
      {tabs.length > 0 && (
        <div className={styles.tabBar}>
          {tabs.map((tab) => {
            const hostname = tab.url
              ? tab.url.replace(/^https?:\/\/(www\.)?/, "").split("/")[0]
              : "";
            const label = tab.title || hostname || String(tab.id);
            return (
              <div
                key={tab.id}
                className={`${styles.tab} ${
                  tab.active ? styles.tabActive : ""
                }`}
                onClick={() => switchTab(tab.id)}
                title={tab.url}
              >
                <Globe size={11} style={{ flexShrink: 0 }} />
                <span className={styles.tabLabel}>{label}</span>
                {tabs.length > 1 && (
                  <span
                    className={styles.tabClose}
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                    title={t("common.close")}
                  >
                    ×
                  </span>
                )}
              </div>
            );
          })}
          <div
            className={styles.tabNew}
            onClick={() => newTab()}
            title={t("browserWorkspace.newTab")}
          >
            +
          </div>
        </div>
      )}

      {/* Viewport — canvas-based, exact same approach as RemoteBrowser */}
      <div
        ref={canvasContainerRef}
        className={`${styles.viewportContainer} ${
          isInteractive ? styles.viewportInteractive : ""
        }`}
      >
        {status === "error" ? (
          <div className={styles.placeholder}>
            <AlertTriangle
              size={24}
              style={{ marginBottom: 8, color: "#faad14" }}
            />
            <div style={{ marginBottom: 12 }}>
              {t("browserWorkspace.connectFailed")}
            </div>
            <Button type="primary" size="small" onClick={handleRetry}>
              {t("browserWorkspace.reconnect")}
            </Button>
          </div>
        ) : isConnecting ? (
          <div className={styles.placeholder}>
            <Loader2 size={24} style={{ marginBottom: 8 }} />
            <div>
              {status === "connecting"
                ? t("browserWorkspace.connecting")
                : t("browserWorkspace.waitingScreenshot")}
            </div>
            <div
              style={{
                fontSize: 12,
                color: "rgba(255,255,255,0.45)",
                marginTop: 4,
              }}
            >
              {hasSession
                ? t("browserWorkspace.firstConnectHint")
                : t("browserWorkspace.waitingAgentHint")}
            </div>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            style={{
              cursor: isDragging
                ? "grabbing"
                : isInteractive
                ? "grab"
                : "default",
            }}
            onPointerDown={handlePanPointerDown}
            onDoubleClick={handleDoubleClick}
            onWheel={handleWheel}
          />
        )}
        {isInteractive && isStreaming && (
          <div className={styles.interactiveHint}>
            {t("browserWorkspace.interactiveHint")}
          </div>
        )}
      </div>

      {/* Footer with handoff actions */}
      <div className={styles.footer}>
        {hasSession ? (
          <>
            <Tag
              className={`${styles.stateTag} ${
                controlOwner === "user" ? styles.stateTagTakeover : ""
              }`}
            >
              {sessionStateLabel}
            </Tag>
            <Space>
              {controlOwner === "user" ? (
                <Button
                  size="small"
                  icon={<ArrowLeftRight size={14} />}
                  onClick={() => handleHandoff("agent")}
                >
                  {t("browserWorkspace.returnToAgent")}
                </Button>
              ) : (
                <Button
                  size="small"
                  icon={<User size={14} />}
                  onClick={() => handleHandoff("user")}
                >
                  {t("browserWorkspace.takeover")}
                </Button>
              )}
              {environment === "desktop" && (
                <Tooltip title={t("browserWorkspace.openDesktopChrome")}>
                  <Button size="small" icon={<Monitor size={14} />}>
                    {t("browserWorkspace.openBrowserWindow")}
                  </Button>
                </Tooltip>
              )}
            </Space>
          </>
        ) : (
          <span className={styles.emptyFooterHint}>
            {t("browserWorkspace.emptyFooterHint")}
          </span>
        )}
      </div>
    </div>
  );
};

export default BrowserWorkspace;
