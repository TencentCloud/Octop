import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button, Select, Tag, Tooltip, Space } from "antd";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowLeftRight,
  Globe,
  Monitor,
  RefreshCw,
  User,
} from "lucide-react";
import { api } from "../../api";
import type {
  BrowserSession,
  DisplayEnvironment,
} from "../../api/types/browser";
import { useBrowserStream } from "../../hooks/useBrowserStream";
import { useAutoViewportResize } from "../../hooks/useAutoViewportResize";
import {
  useBrowserViewController,
  deriveActiveTabUrl,
} from "../../hooks/useBrowserViewController";
import {
  useViewportMode,
  VIEWPORT_MODE_OPTIONS,
} from "../../hooks/useViewportMode";
import { normalizeUrl } from "../../utils/normalizeUrl";
import { viewportModeLabel } from "../../utils/browserViewport";
import { DEFAULT_BROWSER_PROFILE } from "../../utils/browserProfile";
import { showApiError } from "../../utils/showApiToast";
import BrowserViewer, { type BrowserViewerHandle } from "../BrowserViewer";
import styles from "./index.module.less";

export type PanelMode = "hidden" | "bottom" | "right" | "popup";

const DEFAULT_URL = "https://cloud.tencent.com";

interface BrowserWorkspaceProps {
  /** Conversation/session id used to attach the screencast to the agent's
   *  Chrome. Falls back to "default" on the backend when absent. */
  sessionId?: string | null;
  environment?: DisplayEnvironment;
  style?: React.CSSProperties;
  /** Bookmark state for the current URL (forwarded to the address bar). */
  bookmarked?: boolean;
  onToggleBookmark?: (url: string, title: string) => void;
}

const BrowserWorkspace: React.FC<BrowserWorkspaceProps> = ({
  sessionId,
  environment = "desktop",
  style,
  bookmarked = false,
  onToggleBookmark,
}) => {
  const { t } = useTranslation();
  // Viewport defaults to a fixed 1280×800 — suitable when the view is small
  // and ``auto`` would render most desktop sites too small to read.
  const {
    mode: vpMode,
    setMode: setVpMode,
    resolve: resolveViewport,
  } = useViewportMode("octop:browser-panel:viewport-mode", "1280x800");
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
    disconnect,
  } = useBrowserStream();

  const viewerRef = useRef<BrowserViewerHandle>(null);
  const canvasContainerRef = useRef<HTMLDivElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);

  const [url, setUrl] = useState(DEFAULT_URL);
  const urlEditingRef = useRef(false);
  const [session, setSession] = useState<BrowserSession | null>(null);
  const [authAlert, setAuthAlert] = useState<string | null>(null);

  const isStreaming = status === "streaming";

  const viewportSelectOptions = useMemo(
    () =>
      VIEWPORT_MODE_OPTIONS.map((o) => ({
        value: o.value,
        label: viewportModeLabel(o.value, t),
      })),
    [t],
  );

  // Shared stream controller: measure container, resolve viewport, open the
  // WebSocket, and paint frames onto the BrowserViewer canvas. The chat panel
  // defaults to a fixed 1440×900 canvas (the pane is too small for ``auto``).
  const { startStream } = useBrowserViewController({
    containerRef: canvasContainerRef,
    viewerRef,
    connect,
    resolveViewport,
    defaultViewport: { width: 1440, height: 900 },
    onError: (msg) => showApiError(msg, t("browserViewer.connectFailed"), t),
  });

  // Connect on mount and whenever the attached session or viewport mode
  // changes. The caller controls visibility by mounting/unmounting.
  useEffect(() => {
    // Use empty string to "attach without navigating" — the backend's
    // BrowserStreamSession will pick whichever tab the agent has open.
    startStream(sessionId ?? "", "");
    return () => {
      disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, vpMode]);

  // Keep the URL bar in sync with the active tab — but never stomp while typing.
  useEffect(() => {
    if (urlEditingRef.current) return;
    const target = deriveActiveTabUrl(tabs);
    if (target) setUrl(target);
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
  // just rescales the canvas via CSS. Shared with /remote-browser via hook.
  useAutoViewportResize({
    enabled: vpMode === "auto",
    containerRef: canvasContainerRef,
    isStreaming,
    sendEvent,
  });

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
        profile_name: DEFAULT_BROWSER_PROFILE,
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
      startStream(sessionId ?? "", target);
    }
  }, [url, isStreaming, sessionId, streamNavigate, startStream]);

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

  const handleRetry = useCallback(() => {
    // Pass an empty url so the backend reattaches to whatever tab the
    // agent already has open instead of force-navigating to DEFAULT_URL.
    // The user can still explicitly navigate via the URL bar (which calls
    // streamNavigate / startStream(finalUrl)).
    disconnect();
    startStream(sessionId ?? "", "");
  }, [disconnect, sessionId, startStream]);

  const sessionStateLabel = useMemo(() => {
    if (controlOwner === "user") return t("browserWorkspace.userTakeoverShort");
    const key = `browserWorkspace.state.${stateLabel}`;
    const translated = t(key);
    return translated !== key ? translated : stateLabel;
  }, [controlOwner, stateLabel, t]);

  const hasSession = !!(sessionId ?? sessionInfo?.session_id);

  return (
    <div ref={panelRef} className={styles.browserWorkspace} style={style}>
      {/* Header — profile / status / viewport controls */}
      <div className={styles.header}>
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

      {/* Shared browser view: tab bar + address bar + canvas preview.
          Chat-specific chrome (panel mode / drag / close) lives in ChatBrowserPanel. */}
      <div
        ref={canvasContainerRef}
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          overflow: "hidden",
        }}
      >
        <BrowserViewer
          ref={viewerRef}
          status={status}
          tabs={tabs}
          switchTab={switchTab}
          closeTab={closeTab}
          newTab={newTab}
          sendEvent={sendEvent}
          navUrl={url}
          onNavUrlChange={setUrl}
          onNavigate={handleNavigate}
          interactive={isStreaming && isInteractive}
          onReconnect={handleRetry}
          bookmarked={bookmarked}
          onToggleBookmark={onToggleBookmark}
          connectingHint={
            hasSession
              ? t("browserWorkspace.firstConnectHint")
              : t("browserWorkspace.waitingAgentHint")
          }
        />
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
