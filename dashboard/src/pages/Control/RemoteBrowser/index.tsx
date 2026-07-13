/**
 * Remote Browser page — harness-browser sessions (same backend as chat).
 *
 * UI matches the original Playwright page: install flow, address bar,
 * tab bar, canvas interaction, viewport / refresh controls.
 *
 * Frames arrive over WebSocket (/browser-stream/ws) instead of screenshot polling.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Button,
  Drawer,
  Input,
  Modal,
  Result,
  Select,
  Space,
  Spin,
  Tooltip,
  Typography,
  message as antMessage,
} from "antd";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  CheckCircle2,
  Globe,
  Maximize2,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Square,
  Sparkles,
  Star,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import StreamEdgeControls from "../../../components/StreamEdgeControls/StreamEdgeControls";
import StreamSetupGuide from "../../../components/StreamSetupGuide/StreamSetupGuide";
import PageShell from "../../../layouts/PageShell";
import BrowserAiPanel from "../../../components/BrowserAiPanel";
import SkillRecordGuideModal from "../../../components/SkillRecordGuideModal";
import { useAgent } from "../../../context/AgentContext";
import { browserApi } from "../../../api/modules/browser";
import * as chatStore from "../../Chat/hooks/chatStore";
import type { BrowserSession as HarnessSession } from "../../../api/types/browser";
import { request } from "../../../api/request";
import { normalizeUrl } from "../../../utils/normalizeUrl";
import {
  clearCanvas,
  paintBase64JpegToCanvas,
} from "../../../utils/browserCanvas";
import {
  REFRESH_INTERVAL_PRESETS,
  refreshIntervalLabel,
  viewportModeLabel,
} from "../../../utils/browserViewport";
import { useBrowserCanvasInteraction } from "../../../hooks/useBrowserCanvasInteraction";
import { useBrowserStream } from "../../../hooks/useBrowserStream";
import { useRemoteBrowserBookmarks } from "../../../hooks/useRemoteBrowserBookmarks";
import type { RemoteBrowserBookmark } from "../../../api/modules/preferences";
import { showApiError } from "../../../utils/showApiToast";
import {
  useViewportMode,
  VIEWPORT_MODE_OPTIONS,
  type ViewportMode,
} from "../../../hooks/useViewportMode";
import { useIsMobile } from "../../../hooks/useIsMobile";
import { useLandscapeFullscreen } from "../../../hooks/useLandscapeFullscreen";
import styles from "./index.module.less";

const { Text } = Typography;

interface BrowserTab {
  idx: number;
  id: number | string;
  url: string;
  title: string;
  active: boolean;
}

interface ViewSession {
  id: string;
  url: string;
  tabs: BrowserTab[];
}

interface EnvStatus {
  playwright: boolean;
  browsers_ok: boolean;
  harness_browser: boolean;
  /** True when Playwright-managed Chromium dirs exist (uninstall target). */
  playwright_chromium?: boolean;
  chrome_path?: string | null;
  /** "system" | "playwright" when browsers_ok */
  chrome_source?: "system" | "playwright" | null;
  error: string | null;
}

type InstallPhase =
  | "idle"
  | "installing"
  | "install_success"
  | "install_failed";

const REFRESH_STORAGE_KEY = "octop:remote-browser:refresh-interval";
const PROFILE_STORAGE_KEY = "octop:remote-browser:harness-profile";
const LEGACY_SESSION_STORAGE_KEY = "octop:remote-browser:session-id";
/** Whether the user left the remote-browser stream open last time. */
const STREAM_ACTIVE_KEY = "octop:remote-browser:stream-active";
const DEFAULT_REFRESH_INTERVAL = 500;
const DEFAULT_START_URL = "https://cloud.tencent.com";
const BROWSER_AI_PANEL_KEY = "octop:remote-browser:ai-panel-open";
const BROWSER_AI_PANEL_WIDTH_KEY = "octop:remote-browser:ai-panel-width";
const BROWSER_AI_PANEL_HEIGHT_KEY = "octop:remote-browser:ai-panel-height";
const BROWSER_AI_PANEL_MIN_WIDTH = 260;
const BROWSER_AI_PANEL_MAX_WIDTH = 620;
const BROWSER_AI_PANEL_MIN_HEIGHT = 200;
const BROWSER_AI_PANEL_MAX_HEIGHT = 520;

function readStoredProfile(): string | null {
  try {
    return (
      localStorage.getItem(PROFILE_STORAGE_KEY) ??
      localStorage.getItem(LEGACY_SESSION_STORAGE_KEY)
    );
  } catch {
    return null;
  }
}

function persistProfile(profile: string) {
  try {
    localStorage.setItem(PROFILE_STORAGE_KEY, profile);
    localStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

function readStreamActive(): boolean {
  try {
    return localStorage.getItem(STREAM_ACTIVE_KEY) === "1";
  } catch {
    return false;
  }
}

function setStreamActive(active: boolean) {
  try {
    if (active) {
      localStorage.setItem(STREAM_ACTIVE_KEY, "1");
    } else {
      localStorage.removeItem(STREAM_ACTIVE_KEY);
    }
  } catch {
    /* ignore */
  }
}

function pickProfile(
  sessions: HarnessSession[],
  threadFromUrl?: string,
  stored?: string | null,
): string {
  if (threadFromUrl) return threadFromUrl;
  if (stored && sessions.some((s) => s.session_id === stored)) return stored;
  if (sessions.length > 0) {
    const sorted = [...sessions].sort(
      (a, b) => (b.last_activity_at ?? 0) - (a.last_activity_at ?? 0),
    );
    return sorted[0].session_id;
  }
  return stored ?? "default";
}

function tabsFromStream(
  streamTabs: {
    id: number | string;
    url: string;
    title: string;
    active: boolean;
  }[],
): BrowserTab[] {
  return streamTabs.map((t, idx) => ({
    idx,
    id: t.id,
    url: t.url,
    title: t.title,
    active: t.active,
  }));
}

function viewFromProfile(profileId: string, tabs: BrowserTab[]): ViewSession {
  const active = tabs.find((t) => t.active);
  return {
    id: profileId,
    url: active?.url && active.url !== "about:blank" ? active.url : "",
    tabs,
  };
}

// ---------- BookmarkBar ----------

function BookmarkBar({
  bookmarks,
  onOpen,
  onRemove,
}: {
  bookmarks: RemoteBrowserBookmark[];
  onOpen: (url: string) => void;
  onRemove: (url: string) => void;
}) {
  const { t } = useTranslation();

  return (
    <div
      role="navigation"
      aria-label={t("remoteBrowser.bookmarkBarTitle", "书签栏")}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 4,
        overflowX: "auto",
        padding: "2px 8px",
        scrollbarWidth: "none",
        background: "var(--fn-bg-secondary)",
        borderBottom: "1px solid var(--fn-border-secondary)",
        minHeight: 28,
      }}
    >
      {bookmarks.map((bm) => (
        <Tooltip key={bm.url} title={bm.url} mouseEnterDelay={0.5}>
          <div
            onClick={() => onOpen(bm.url)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 8px",
              borderRadius: 4,
              cursor: "pointer",
              whiteSpace: "nowrap",
              maxWidth: 160,
              fontSize: 12,
              background: "var(--fn-bg-primary)",
              border: "1px solid var(--fn-border-secondary)",
              color: "var(--fn-text-secondary)",
              userSelect: "none",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "var(--fn-text-primary)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "var(--fn-text-secondary)";
            }}
          >
            <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
              {bm.title}
            </span>
            <button
              type="button"
              aria-label={t("remoteBrowser.bookmarkRemove", "移除书签")}
              onClick={(e) => {
                e.stopPropagation();
                onRemove(bm.url);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                padding: 0,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                color: "inherit",
                opacity: 0.7,
                flexShrink: 0,
              }}
            >
              <X size={12} />
            </button>
          </div>
        </Tooltip>
      ))}
    </div>
  );
}

// ---------- Main Page ----------

export default function RemoteBrowserPage() {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const { activeAgent, activeAgentId, agents } = useAgent();
  const [searchParams] = useSearchParams();
  const threadFromUrl =
    searchParams.get("thread") ??
    searchParams.get("conversation_id") ??
    undefined;

  const [envStatus, setEnvStatus] = useState<EnvStatus | null>(null);
  const [envLoading, setEnvLoading] = useState(true);

  const [installPhase, setInstallPhase] = useState<InstallPhase>("idle");
  const [installLogs, setInstallLogs] = useState<string[]>([]);
  const [uninstalling, setUninstalling] = useState(false);
  const [uninstallLogs, setUninstallLogs] = useState<string[]>([]);
  const [envModalOpen, setEnvModalOpen] = useState(false);
  const [controlsOpen, setControlsOpen] = useState(false);
  const [frameReady, setFrameReady] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const installLogRef = useRef<HTMLDivElement | null>(null);
  const installAbortRef = useRef<AbortController | null>(null);
  const uninstallAbortRef = useRef<AbortController | null>(null);

  const { bookmarks, isBookmarked, toggle, remove } =
    useRemoteBrowserBookmarks();

  const [session, setSession] = useState<ViewSession | null>(null);
  const [creating, setCreating] = useState(false);
  const [navUrl, setNavUrl] = useState(DEFAULT_START_URL);
  const urlEditingRef = useRef(false);
  const [isAiPanelOpen, setIsAiPanelOpen] = useState(() => {
    try {
      if (typeof window !== "undefined" && window.innerWidth < 768) {
        return false;
      }
      return localStorage.getItem(BROWSER_AI_PANEL_KEY) !== "false";
    } catch {
      return true;
    }
  });
  const [aiPanelWidth, setAiPanelWidth] = useState(() => {
    try {
      const saved = localStorage.getItem(BROWSER_AI_PANEL_WIDTH_KEY);
      const n = saved ? Number(saved) : 340;
      if (Number.isFinite(n)) {
        return Math.min(
          Math.max(n, BROWSER_AI_PANEL_MIN_WIDTH),
          BROWSER_AI_PANEL_MAX_WIDTH,
        );
      }
    } catch {
      /* ignore */
    }
    return 340;
  });
  const [aiPanelHeight, setAiPanelHeight] = useState(() => {
    try {
      const saved = localStorage.getItem(BROWSER_AI_PANEL_HEIGHT_KEY);
      const n = saved ? Number(saved) : 320;
      if (Number.isFinite(n)) {
        return Math.min(
          Math.max(n, BROWSER_AI_PANEL_MIN_HEIGHT),
          BROWSER_AI_PANEL_MAX_HEIGHT,
        );
      }
    } catch {
      /* ignore */
    }
    return 320;
  });
  const aiDragRef = useRef<{
    startX: number;
    startY: number;
    startSize: number;
  } | null>(null);

  const {
    mode: viewportMode,
    setMode: setViewportMode,
    resolve: resolveViewport,
  } = useViewportMode("octop:remote-browser:viewport", "auto");

  const viewportSelectOptions = useMemo(
    () =>
      VIEWPORT_MODE_OPTIONS.map((o) => ({
        value: o.value,
        label: viewportModeLabel(o.value, t),
      })),
    [t],
  );

  const refreshSelectOptions = useMemo(
    () =>
      REFRESH_INTERVAL_PRESETS.map((ms) => ({
        value: ms,
        label: refreshIntervalLabel(ms, t),
      })),
    [t],
  );

  const [refreshInterval, setRefreshInterval] = useState<number>(() => {
    try {
      const saved = localStorage.getItem(REFRESH_STORAGE_KEY);
      if (saved !== null) {
        const n = Number(saved);
        if (REFRESH_INTERVAL_PRESETS.some((v) => v === n)) return n;
      }
    } catch {
      /* ignore */
    }
    return DEFAULT_REFRESH_INTERVAL;
  });

  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const profileIdRef = useRef<string | null>(null);

  const {
    status,
    tabs: streamTabs,
    connect,
    disconnect,
    sendEvent,
    navigate: streamNavigate,
    switchTab,
    closeTab,
    newTab,
  } = useBrowserStream();

  const isStreaming = status === "streaming" || status === "browser_started";
  const effectiveActiveAgent =
    activeAgent ??
    (activeAgentId
      ? agents.find((agent) => agent.agent_id === activeAgentId) ?? null
      : null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    installLogRef.current?.scrollTo({
      top: installLogRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [installLogs, uninstallLogs]);

  useEffect(
    () => () => {
      installAbortRef.current?.abort();
      uninstallAbortRef.current?.abort();
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
      disconnect();
    },
    [disconnect],
  );

  const handleFrame = useCallback((base64Data: string) => {
    paintBase64JpegToCanvas(canvasRef.current, base64Data);
    setFrameReady(true);
  }, []);

  const resolveDimensions = useCallback(() => {
    const containerEl = containerRef.current;
    const cw = containerEl?.clientWidth ?? 0;
    const ch = containerEl?.clientHeight ?? 0;
    if (isMobile) {
      if (cw > 0 && ch > 0) return { width: cw, height: ch };
      return { width: 390, height: 700 };
    }
    return resolveViewport(cw, ch) ?? { width: 1280, height: 800 };
  }, [resolveViewport, isMobile]);

  const attachProfile = useCallback((profileId: string, tabs: BrowserTab[]) => {
    profileIdRef.current = profileId;
    const view = viewFromProfile(profileId, tabs);
    setSession(view);
    persistProfile(profileId);
    if (urlEditingRef.current) return;
    if (view.url) setNavUrl(view.url);
  }, []);

  const startStream = useCallback(
    (profileId: string, targetUrl = "") => {
      setFrameReady(false);
      setStreamActive(true);
      const { width, height } = resolveDimensions();
      connect(
        targetUrl,
        width,
        height,
        {
          onFrame: handleFrame,
          onError: (msg) =>
            showApiError(msg, t("browserWorkspace.streamError"), t),
        },
        { sessionId: profileId },
      );
      attachProfile(profileId, []);
    },
    [attachProfile, connect, handleFrame, resolveDimensions, t],
  );

  // Keep view session in sync with stream tab updates
  useEffect(() => {
    const profileId = profileIdRef.current;
    if (!profileId) return;
    const tabs = tabsFromStream(streamTabs);
    const view = viewFromProfile(profileId, tabs);
    setSession(view);
    if (!urlEditingRef.current && view.url) setNavUrl(view.url);
  }, [streamTabs]);

  const refreshEnv = useCallback(async (): Promise<EnvStatus | null> => {
    setEnvLoading(true);
    try {
      const env = await request<EnvStatus>("/browser/env-status");
      setEnvStatus(env);
      return env;
    } catch (err: unknown) {
      showApiError(err, t("remoteBrowser.envProbeFailed"), t);
      return null;
    } finally {
      setEnvLoading(false);
    }
  }, [t]);

  const refreshSessions = useCallback(async (): Promise<string | null> => {
    try {
      const resp = await browserApi.getSessions();
      const sessions = resp.ok ? resp.sessions : [];
      const profile = pickProfile(sessions, threadFromUrl, readStoredProfile());
      // Restore stream only when the user left it open, or when deep-linked
      // via ?thread=… — do not auto-open just because Chrome is still alive.
      if (threadFromUrl || readStreamActive()) {
        startStream(profile);
        return profile;
      }
      return null;
    } catch {
      return null;
    }
  }, [startStream, threadFromUrl]);

  useEffect(() => {
    void refreshEnv();
    void refreshSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- install / uninstall ---

  const startInstall = useCallback(() => {
    setInstallPhase("installing");
    setInstallLogs([]);
    setEnvModalOpen(false);
    installAbortRef.current = browserApi.installBrowser(
      (line) => setInstallLogs((p) => [...p, line]),
      (success) => {
        installAbortRef.current = null;
        if (!success) {
          setInstallPhase("install_failed");
          setEnvModalOpen(true);
          return;
        }
        setInstallPhase("idle");
        setEnvModalOpen(false);
        void refreshEnv();
        antMessage.success(t("remoteBrowser.installSuccess", "浏览器安装成功"));
      },
    );
  }, [refreshEnv, t]);

  const cancelInstall = useCallback(() => {
    installAbortRef.current?.abort();
    installAbortRef.current = null;
    setInstallPhase("idle");
    setInstallLogs([]);
    antMessage.info(
      t(
        "remoteBrowser.installCancelHint",
        "已取消安装请求，服务端可能仍在继续安装，请稍后刷新状态。",
      ),
    );
  }, [t]);

  const handleUninstall = useCallback(() => {
    if (!envStatus?.playwright_chromium || uninstalling) return;
    Modal.confirm({
      title: t("remoteBrowser.uninstallTitle", "卸载远程浏览器"),
      content: t(
        "remoteBrowser.uninstallConfirm",
        "将关闭 Octop 浏览器会话，并删除通过 Playwright 安装的 Chromium。不会影响本机已有的 Chrome/Chromium。是否继续？",
      ),
      okText: t("remoteBrowser.uninstall", "卸载"),
      okButtonProps: { danger: true },
      cancelText: t("common.cancel"),
      onOk: () =>
        new Promise<void>((resolve, reject) => {
          if (session) {
            disconnect();
            profileIdRef.current = null;
            setSession(null);
            setFrameReady(false);
          }
          setUninstalling(true);
          setUninstallLogs([]);
          const hide = antMessage.loading(
            t("remoteBrowser.uninstalling", "正在卸载…"),
            0,
          );
          uninstallAbortRef.current = browserApi.uninstallBrowser(
            (line) => setUninstallLogs((prev) => [...prev, line]),
            (success) => {
              uninstallAbortRef.current = null;
              setUninstalling(false);
              hide();
              void refreshEnv().then((data) => {
                const removed = success || !data?.playwright_chromium;
                if (removed) {
                  setUninstallLogs([]);
                  antMessage.success(
                    t(
                      "remoteBrowser.uninstallSuccess",
                      "已删除 Playwright Chromium",
                    ),
                  );
                  resolve();
                  return;
                }
                antMessage.error(
                  t("remoteBrowser.uninstallFailed", "卸载失败"),
                );
                reject(new Error("uninstall failed"));
              });
            },
          );
        }),
    });
  }, [
    disconnect,
    envStatus?.playwright_chromium,
    refreshEnv,
    session,
    t,
    uninstalling,
  ]);

  const openEnvModal = useCallback(() => {
    setEnvModalOpen(true);
    if (installPhase !== "installing") {
      setInstallPhase("idle");
      setInstallLogs([]);
    }
    void refreshEnv();
  }, [refreshEnv, installPhase]);

  const closeEnvModal = useCallback(() => {
    if (installPhase === "installing") {
      installAbortRef.current?.abort();
      installAbortRef.current = null;
      setInstallPhase("idle");
    }
    setEnvModalOpen(false);
    if (
      installPhase === "install_success" ||
      installPhase === "install_failed"
    ) {
      setInstallPhase("idle");
      setInstallLogs([]);
    }
  }, [installPhase]);

  // --- session ---

  const handleViewportChange = useCallback(
    (mode: ViewportMode) => {
      setViewportMode(mode);
    },
    [setViewportMode],
  );

  const handleRefreshIntervalChange = useCallback((ms: number) => {
    setRefreshInterval(ms);
    try {
      localStorage.setItem(REFRESH_STORAGE_KEY, String(ms));
    } catch {
      /* ignore */
    }
  }, []);

  const createSession = useCallback(async () => {
    setCreating(true);
    try {
      const resp = await browserApi.getSessions();
      const profile = pickProfile(
        resp.ok ? resp.sessions : [],
        threadFromUrl,
        readStoredProfile(),
      );
      startStream(profile, normalizeUrl(navUrl) || DEFAULT_START_URL);
    } catch (err: unknown) {
      showApiError(err, t("remoteBrowser.createSessionFailed"), t);
    } finally {
      setCreating(false);
    }
  }, [navUrl, startStream, t, threadFromUrl]);

  const closeSession = useCallback(() => {
    disconnect();
    profileIdRef.current = null;
    setSession(null);
    setFrameReady(false);
    setStreamActive(false);
    try {
      localStorage.removeItem(PROFILE_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    clearCanvas(canvasRef.current);
  }, [disconnect]);

  const refreshView = useCallback(async () => {
    const profileId = profileIdRef.current;
    if (!profileId) return;
    disconnect();
    startStream(profileId);
  }, [disconnect, startStream]);

  // Periodic reconnect fallback when stream stalls (manual interval presets)
  useEffect(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
    if (session && refreshInterval > 0 && status === "stopped") {
      refreshTimerRef.current = setInterval(
        () => void refreshView(),
        refreshInterval,
      );
    }
    return () => {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    };
  }, [session, refreshInterval, refreshView, status]);

  // Reconnect when viewport preset changes (desktop fixed modes only).
  useEffect(() => {
    if (!session || isMobile) return;
    void refreshView();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewportMode]);

  // In auto mode (always on mobile), keep Chrome viewport aligned with the
  // visible canvas area so text stays legible instead of CSS-downscaled.
  useEffect(() => {
    if (!session) return;
    const useAuto = isMobile || viewportMode === "auto";
    if (!useAuto) return;
    const containerEl = containerRef.current;
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
  }, [isStreaming, isMobile, sendEvent, session, viewportMode]);

  const sendAction = useCallback(
    (body: Record<string, unknown>) => {
      const type = body.type as string;
      if (type === "navigate") {
        const url = normalizeUrl(String(body.url ?? ""));
        if (url) streamNavigate(url);
        return;
      }
      sendEvent(body);
    },
    [sendEvent, streamNavigate],
  );

  const handleNewTab = useCallback(() => {
    if (!session) return;
    newTab();
  }, [newTab, session]);

  const handleCloseTab = useCallback(
    (idx: number) => {
      const tab = session?.tabs.find((t) => t.idx === idx);
      if (tab) closeTab(tab.id);
    },
    [closeTab, session?.tabs],
  );

  const handleSwitchTab = useCallback(
    (idx: number) => {
      const tab = session?.tabs.find((t) => t.idx === idx);
      if (tab) switchTab(tab.id);
    },
    [session?.tabs, switchTab],
  );

  const handleAiPanelToggle = useCallback(() => {
    setIsAiPanelOpen((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(BROWSER_AI_PANEL_KEY, String(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const handleAiPanelClose = useCallback(() => {
    setIsAiPanelOpen(false);
    try {
      localStorage.setItem(BROWSER_AI_PANEL_KEY, "false");
    } catch {
      /* ignore */
    }
  }, []);

  const handleAiResizeMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (isMobile) {
        aiDragRef.current = {
          startX: e.clientX,
          startY: e.clientY,
          startSize: aiPanelHeight,
        };
        const onMove = (mv: MouseEvent) => {
          if (!aiDragRef.current) return;
          const delta = aiDragRef.current.startY - mv.clientY;
          const next = Math.min(
            Math.max(
              aiDragRef.current.startSize + delta,
              BROWSER_AI_PANEL_MIN_HEIGHT,
            ),
            BROWSER_AI_PANEL_MAX_HEIGHT,
          );
          setAiPanelHeight(next);
        };
        const onUp = (mv: MouseEvent) => {
          if (!aiDragRef.current) return;
          const delta = aiDragRef.current.startY - mv.clientY;
          const next = Math.min(
            Math.max(
              aiDragRef.current.startSize + delta,
              BROWSER_AI_PANEL_MIN_HEIGHT,
            ),
            BROWSER_AI_PANEL_MAX_HEIGHT,
          );
          setAiPanelHeight(next);
          try {
            localStorage.setItem(BROWSER_AI_PANEL_HEIGHT_KEY, String(next));
          } catch {
            /* ignore */
          }
          aiDragRef.current = null;
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
        return;
      }

      aiDragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startSize: aiPanelWidth,
      };
      const onMove = (mv: MouseEvent) => {
        if (!aiDragRef.current) return;
        const delta = aiDragRef.current.startX - mv.clientX;
        const next = Math.min(
          Math.max(
            aiDragRef.current.startSize + delta,
            BROWSER_AI_PANEL_MIN_WIDTH,
          ),
          BROWSER_AI_PANEL_MAX_WIDTH,
        );
        setAiPanelWidth(next);
      };
      const onUp = (mv: MouseEvent) => {
        if (!aiDragRef.current) return;
        const delta = aiDragRef.current.startX - mv.clientX;
        const next = Math.min(
          Math.max(
            aiDragRef.current.startSize + delta,
            BROWSER_AI_PANEL_MIN_WIDTH,
          ),
          BROWSER_AI_PANEL_MAX_WIDTH,
        );
        setAiPanelWidth(next);
        try {
          localStorage.setItem(BROWSER_AI_PANEL_WIDTH_KEY, String(next));
        } catch {
          /* ignore */
        }
        aiDragRef.current = null;
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [aiPanelHeight, aiPanelWidth, isMobile],
  );

  const sendActionScroll = useCallback(
    (x: number, y: number, deltaX: number, deltaY: number) => {
      sendEvent({ type: "scroll", x, y, deltaX, deltaY });
    },
    [sendEvent],
  );

  const sendActionClick = useCallback(
    (x: number, y: number) => {
      canvasRef.current?.focus();
      sendEvent({ type: "click", x, y });
    },
    [sendEvent],
  );

  const sendActionDoubleClick = useCallback(
    (x: number, y: number) => {
      canvasRef.current?.focus();
      sendEvent({ type: "dblclick", x, y });
    },
    [sendEvent],
  );

  const {
    handleWheel: handleCanvasWheel,
    onPointerDown: handleCanvasPointerDown,
    onDoubleClick: handleCanvasDblClick,
    isDragging,
    pointerStyle,
  } = useBrowserCanvasInteraction({
    enabled: !!session,
    canvasRef,
    onScroll: sendActionScroll,
    onClick: sendActionClick,
    onDoubleClick: sendActionDoubleClick,
  });

  const handleCanvasKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        sendEvent({ type: "type", text: e.key });
      } else {
        sendEvent({ type: "keydown", key: e.key });
      }
    },
    [sendEvent],
  );

  const goto = useCallback(() => {
    const target = normalizeUrl(navUrl);
    if (!target) return;
    setNavUrl(target);
    sendAction({ type: "navigate", url: target });
  }, [navUrl, sendAction]);

  // --- Skill recording guide ---
  const [browserRecording, setBrowserRecording] = useState(false);
  const [browserRecordingId, setBrowserRecordingId] = useState<string | null>(
    null,
  );
  const [browserLastRecordingId, setBrowserLastRecordingId] = useState<
    string | null
  >(null);
  const [skillGuideOpen, setSkillGuideOpen] = useState(false);

  const openSkillGuide = useCallback(() => {
    setSkillGuideOpen(true);
  }, []);

  // Skill name (task objective) — set later by user in AI chat panel
  const [skillName, setSkillName] = useState<string>("");

  const handleStartRecording = useCallback(async () => {
    setSkillGuideOpen(false);

    // Force-open the AI panel so the user can see the conversation
    setIsAiPanelOpen(true);
    try {
      localStorage.setItem(BROWSER_AI_PANEL_KEY, "true");
    } catch {
      /* ignore */
    }

    const profileId = profileIdRef.current || "default";
    try {
      const data = await browserApi.startRecording({
        profile: profileId,
        agentProfile: profileId,
        name: `browser-skill-${Date.now()}`,
      });
      if (data.ok) {
        setBrowserRecording(true);
        const rid = data.recordingId ?? null;
        setBrowserRecordingId(rid);
        if (rid) setBrowserLastRecordingId(rid);
        antMessage.success(
          t("browser.recordReplay.started", "已开始浏览器录制"),
        );

        // Push a prompt asking the user to input their task objective
        chatStore.appendPushMessage(
          '🎬 录制已开始！\n\n请输入你的 **任务目标**（这将成为技能名称和触发关键词），例如："登录OA系统"、"查询天气"等。',
        );
      } else {
        antMessage.error(
          data.error || t("browser.recordReplay.startFailed", "开始录制失败"),
        );
      }
    } catch (err) {
      antMessage.error(
        err instanceof Error
          ? err.message
          : t("browser.recordReplay.startFailed", "开始录制失败"),
      );
    }
  }, [t]);

  const envReady = Boolean(envStatus?.browsers_ok);
  const showEdgeControls = Boolean(session) && isStreaming && frameReady;

  const renderInstallLog = (maxHeight?: number, extraClass?: string) => (
    <div
      ref={installLogRef}
      className={`${styles.installLog} ${extraClass ?? ""}`}
      style={maxHeight !== undefined ? { maxHeight } : undefined}
    >
      {installLogs.length === 0 ? (
        <div>{t("remoteBrowser.installing", "正在启动安装...")}</div>
      ) : (
        installLogs.map((line, i) => <div key={i}>{line}</div>)
      )}
      <div ref={logEndRef} />
    </div>
  );

  const renderViewportUninstallProgress = () => (
    <div className={styles.installProgress}>
      <RefreshCw size={32} className={styles.streamLoadingIcon} />
      <div className={styles.installProgressTitle}>
        {t("remoteBrowser.uninstalling", "正在卸载…")}
      </div>
      <div className={styles.installLog}>
        {uninstallLogs.length === 0 ? (
          <div>{t("remoteBrowser.uninstalling", "正在卸载…")}</div>
        ) : (
          uninstallLogs.map((line, i) => <div key={i}>{line}</div>)
        )}
      </div>
    </div>
  );

  const renderViewportInstallProgress = () => (
    <div className={styles.installProgress}>
      <RefreshCw size={32} className={styles.streamLoadingIcon} />
      <div className={styles.installProgressTitle}>
        {t("remoteBrowser.installProgress", "正在安装中…")}
      </div>
      {renderInstallLog()}
      <div className={styles.installProgressActions}>
        <Button onClick={cancelInstall}>{t("common.cancel")}</Button>
      </div>
    </div>
  );

  const renderEnvModalContent = () => {
    if (envLoading && installPhase === "idle") {
      return (
        <div style={{ display: "flex", justifyContent: "center", padding: 32 }}>
          <Spin />
        </div>
      );
    }

    if (installPhase === "installing") {
      return (
        <div>
          <div style={{ textAlign: "center", marginBottom: 12 }}>
            <Spin />
            <Text style={{ marginLeft: 8 }}>
              {t("remoteBrowser.installingBrowser", "正在安装...")}
            </Text>
          </div>
          {renderInstallLog()}
        </div>
      );
    }

    if (installPhase === "install_success") {
      return (
        <Result
          icon={
            <CheckCircle2 size={40} color="var(--fn-color-success,#52c41a)" />
          }
          title={t("remoteBrowser.installSuccess", "安装成功")}
          subTitle={t(
            "remoteBrowser.installSuccessHint",
            "浏览器已就绪，可启动会话",
          )}
          style={{ padding: "8px 0" }}
        />
      );
    }

    if (installPhase === "install_failed") {
      return (
        <div>
          <Result
            icon={<Terminal size={40} color="var(--fn-color-error,#ff4d4f)" />}
            title={t("remoteBrowser.installFailed", "安装失败")}
            subTitle={t(
              "remoteBrowser.installFailedHint",
              "可重试或手动运行 playwright install chromium",
            )}
            style={{ padding: "8px 0" }}
          />
          {installLogs.length > 0 && (
            <details open>
              <summary
                style={{
                  cursor: "pointer",
                  fontSize: 12,
                  color: "var(--fn-text-tertiary)",
                  marginBottom: 6,
                }}
              >
                {t("remoteBrowser.installLog", "安装日志")}
              </summary>
              {renderInstallLog(180)}
            </details>
          )}
        </div>
      );
    }

    if (envReady) {
      const harnessOk = envStatus?.harness_browser;
      const pwOk = envStatus?.playwright;
      const subTitle =
        harnessOk && pwOk
          ? t(
              "remoteBrowser.envReadyBoth",
              "harness-browser 与 Playwright 均可用",
            )
          : harnessOk
          ? t("remoteBrowser.envReadyHarness", "harness-browser (CDP) 已就绪")
          : t("remoteBrowser.envReady", "Playwright 与 Chromium 均可用");
      return (
        <Result
          icon={
            <CheckCircle2 size={40} color="var(--fn-color-success,#52c41a)" />
          }
          title={t("remoteBrowser.browserAlreadyInstalled", "浏览器已安装")}
          subTitle={subTitle}
          style={{ padding: "8px 0" }}
        />
      );
    }

    if (!envStatus?.playwright) {
      // harness-browser works without Playwright, so this is informational
      // rather than a blocking error
      if (envStatus?.harness_browser) {
        return (
          <Alert
            type="info"
            showIcon
            message={t(
              "remoteBrowser.playwrightOptional",
              "playwright 包未安装（可选）",
            )}
            description={t(
              "remoteBrowser.playwrightOptionalDesc",
              "harness-browser (CDP) 已就绪，浏览器功能可用。如需 Playwright 备用模式，可安装 octop[browser] extras。",
            )}
          />
        );
      }
      return (
        <Alert
          type="error"
          showIcon
          message={t("remoteBrowser.playwrightMissing", "playwright 包未安装")}
          description={envStatus?.error ?? undefined}
        />
      );
    }

    return (
      <Alert
        type="warning"
        showIcon
        message={t("remoteBrowser.notInstalled", "Chromium 未安装")}
        description={
          envStatus?.error ?? t("remoteBrowser.notInstalledHint", "点击安装")
        }
      />
    );
  };

  const envModalFooter = () => {
    if (installPhase === "installing") {
      return <Button onClick={closeEnvModal}>{t("common.cancel")}</Button>;
    }
    if (installPhase === "install_failed") {
      return (
        <Space>
          <Button onClick={closeEnvModal}>{t("common.close")}</Button>
          <Button type="primary" onClick={startInstall}>
            {t("remoteBrowser.installRetry", "重新安装")}
          </Button>
        </Space>
      );
    }
    if (installPhase === "install_success") {
      return (
        <Button type="primary" onClick={closeEnvModal}>
          {t("common.close")}
        </Button>
      );
    }
    if (!envReady) {
      return (
        <Space>
          <Button onClick={closeEnvModal}>{t("common.close")}</Button>
          <Button type="primary" onClick={startInstall}>
            {t("remoteBrowser.install", "安装浏览器")}
          </Button>
        </Space>
      );
    }
    return (
      <Button type="primary" onClick={closeEnvModal}>
        {t("common.close")}
      </Button>
    );
  };

  const tabs = useMemo(() => session?.tabs ?? [], [session?.tabs]);

  const activeTabTitle = useMemo(() => {
    const active = tabs.find((tab) => tab.active);
    return active?.title ?? "";
  }, [tabs]);

  const navUrlNormalized = normalizeUrl(navUrl);
  const currentBookmarked = isBookmarked(navUrl);

  const openBookmark = useCallback(
    (url: string) => {
      const target = normalizeUrl(url);
      if (!target) return;
      setNavUrl(target);
      sendAction({ type: "navigate", url: target });
    },
    [sendAction],
  );

  const handleFullscreen = useLandscapeFullscreen(containerRef, {
    isMobile,
    onError: () =>
      antMessage.error(t("remoteBrowser.fullscreenFailed", "无法进入全屏")),
  });

  const openControlsDrawer = useCallback(() => setControlsOpen(true), []);
  const closeControlsDrawer = useCallback(() => setControlsOpen(false), []);

  const renderControlsDrawer = () => (
    <div className={styles.controlsDrawer}>
      <div className={styles.controlsSection}>
        <span className={styles.controlsLabel}>
          {t("remoteBrowser.autoRefresh", "自动刷新")}
        </span>
        <Select
          size="middle"
          className={styles.controlsSelectFull}
          value={refreshInterval}
          onChange={handleRefreshIntervalChange}
          options={refreshSelectOptions}
        />
      </div>
      <div className={styles.controlsSection}>
        <span className={styles.controlsLabel}>
          {t("remoteBrowser.viewportMode", "视口模式")}
        </span>
        <Select
          size="middle"
          className={styles.controlsSelectFull}
          value={viewportMode}
          onChange={handleViewportChange}
          options={viewportSelectOptions}
        />
      </div>
      <div className={styles.controlsActions}>
        <Button
          block
          icon={<Maximize2 size={14} />}
          onClick={() => {
            closeControlsDrawer();
            void handleFullscreen();
          }}
        >
          {t("remoteBrowser.fullscreen", "全屏")}
        </Button>
      </div>
    </div>
  );

  return (
    <PageShell
      title={t("pageShell.browser.title", "浏览器 AI+")}
      subtitle={t(
        "pageShell.browser.subtitle",
        "基于 Chromium 的无头浏览器会话",
      )}
      fill
      actions={
        <Space size={8} wrap>
          <Tooltip
            title={t(
              "remoteBrowser.checkInstallTip",
              "检查 Playwright 浏览器是否已安装，未安装则可安装",
            )}
          >
            <Button
              size={isMobile ? "small" : "middle"}
              icon={<Globe size={14} />}
              onClick={openEnvModal}
              type={envReady ? "default" : "primary"}
            >
              {t("remoteBrowser.checkInstallShort", "检查")}
              {envReady && !envLoading && (
                <CheckCircle2
                  size={14}
                  style={{
                    marginLeft: 4,
                    color: "var(--fn-color-success,#52c41a)",
                  }}
                />
              )}
            </Button>
          </Tooltip>
          {session ? (
            <Tooltip title={t("remoteBrowser.stop", "停止")}>
              <Button
                size={isMobile ? "small" : "middle"}
                danger
                icon={<Square size={14} />}
                onClick={closeSession}
                aria-label={t("remoteBrowser.stop", "停止")}
              >
                {!isMobile && t("remoteBrowser.stop", "停止")}
              </Button>
            </Tooltip>
          ) : (
            <Tooltip
              title={
                envReady
                  ? undefined
                  : t(
                      "remoteBrowser.startBrowserDisabled",
                      "请先完成浏览器环境检查与安装",
                    )
              }
            >
              <Button
                size={isMobile ? "small" : "middle"}
                type="primary"
                icon={<Play size={14} />}
                loading={creating}
                disabled={!envReady}
                onClick={() => void createSession()}
                aria-label={t("remoteBrowser.startBrowser", "启动浏览器")}
              >
                {!isMobile &&
                  (creating
                    ? t("remoteBrowser.ai.startingBrowser", "正在启动...")
                    : t("remoteBrowser.startBrowser", "启动浏览器"))}
              </Button>
            </Tooltip>
          )}
        </Space>
      }
    >
      <Modal
        title={t("remoteBrowser.checkInstall", "检查浏览器")}
        open={envModalOpen}
        onCancel={closeEnvModal}
        footer={envModalFooter()}
        width={isMobile ? "100%" : 520}
        style={isMobile ? { top: 20, maxWidth: "100vw" } : undefined}
        destroyOnClose
        maskClosable={installPhase !== "installing"}
      >
        {renderEnvModalContent()}
      </Modal>

      <SkillRecordGuideModal
        open={skillGuideOpen}
        onCancel={() => setSkillGuideOpen(false)}
        onStartRecording={handleStartRecording}
        envReady={envReady}
      />

      <Drawer
        title={t("remoteBrowser.controlsTitle", "控制面板")}
        placement={isMobile ? "bottom" : "right"}
        open={controlsOpen}
        onClose={closeControlsDrawer}
        height={isMobile ? "min(70vh, 520px)" : undefined}
        width={isMobile ? "100%" : 320}
        destroyOnClose={false}
        styles={{ body: { padding: "12px 16px 16px" } }}
      >
        {renderControlsDrawer()}
      </Drawer>

      <div className={styles.pageBody}>
        {session && (
          <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
            {/* Tab bar */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                background: "var(--fn-bg-secondary)",
                borderRadius: "6px 6px 0 0",
                borderBottom: "1px solid var(--fn-border-secondary)",
                padding: "4px 4px 0",
                gap: 2,
                overflowX: "auto",
                scrollbarWidth: "none",
              }}
            >
              {tabs.map((tab) => (
                <Tooltip
                  key={String(tab.id)}
                  title={tab.url}
                  mouseEnterDelay={0.8}
                >
                  <div
                    onClick={() => handleSwitchTab(tab.idx)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                      padding: "4px 10px",
                      borderRadius: "4px 4px 0 0",
                      cursor: "pointer",
                      whiteSpace: "nowrap",
                      maxWidth: 200,
                      fontSize: 12,
                      background: tab.active
                        ? "var(--fn-bg-primary)"
                        : "transparent",
                      borderTop: tab.active
                        ? "2px solid var(--fn-color-brand, #635bff)"
                        : "2px solid transparent",
                      color: tab.active
                        ? "var(--fn-text-primary)"
                        : "var(--fn-text-secondary)",
                      userSelect: "none",
                    }}
                  >
                    <span
                      style={{
                        flex: 1,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        minWidth: 0,
                      }}
                    >
                      {tab.title || tab.url || "New Tab"}
                    </span>
                    <span
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCloseTab(tab.idx);
                      }}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        opacity: 0.5,
                        borderRadius: 3,
                        padding: "1px 2px",
                        flexShrink: 0,
                      }}
                    >
                      <X size={10} />
                    </span>
                  </div>
                </Tooltip>
              ))}
              <Tooltip title={t("browserWorkspace.newTab", "新建标签页")}>
                <button
                  type="button"
                  onClick={handleNewTab}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                    color: "var(--fn-text-tertiary)",
                    padding: "4px 6px",
                    borderRadius: 4,
                    flexShrink: 0,
                  }}
                >
                  <Plus size={12} />
                </button>
              </Tooltip>
            </div>
            {/* Navigation bar */}
            <div
              className={`${styles.toolbarRow} ${
                isMobile ? styles.toolbarRowMobile : ""
              }`}
            >
              <Button
                size="small"
                icon={<ArrowLeft size={14} />}
                title={t("remoteBrowser.goBack")}
                onClick={() => sendAction({ type: "goback" })}
              />
              <Button
                size="small"
                icon={<ArrowRight size={14} />}
                title={t("remoteBrowser.goForward")}
                onClick={() => sendAction({ type: "goforward" })}
              />
              <Button
                size="small"
                icon={<RotateCcw size={14} />}
                title={t("remoteBrowser.reloadPage")}
                onClick={() => sendAction({ type: "reload" })}
              />
              <Input
                size="small"
                className={styles.urlInput}
                value={navUrl}
                onChange={(e) => setNavUrl(e.target.value)}
                onFocus={() => {
                  urlEditingRef.current = true;
                }}
                onBlur={() => {
                  urlEditingRef.current = false;
                }}
                placeholder={t("remoteBrowser.urlPlaceholderExtended")}
                onPressEnter={() => goto()}
                prefix={<Globe size={13} />}
                suffix={
                  <Tooltip
                    title={
                      currentBookmarked
                        ? t("remoteBrowser.bookmarkRemove", "移除书签")
                        : t("remoteBrowser.bookmarkAdd", "添加书签")
                    }
                  >
                    <button
                      type="button"
                      className={`${styles.urlBarBookmark} ${
                        currentBookmarked ? styles.urlBarBookmarkActive : ""
                      }`}
                      disabled={!navUrlNormalized}
                      aria-label={
                        currentBookmarked
                          ? t("remoteBrowser.bookmarkRemove", "移除书签")
                          : t("remoteBrowser.bookmarkAdd", "添加书签")
                      }
                      onClick={() => toggle(navUrl, activeTabTitle)}
                    >
                      <Star
                        size={14}
                        fill={currentBookmarked ? "currentColor" : "none"}
                      />
                    </button>
                  </Tooltip>
                }
              />
              <Button size="small" type="primary" onClick={() => goto()}>
                {t("remoteBrowser.go")}
              </Button>
              <Button
                size="small"
                type={isAiPanelOpen ? "primary" : "default"}
                icon={<Bot size={14} />}
                onClick={handleAiPanelToggle}
                aria-label={t("remoteBrowser.ai.title", "AI 助手")}
                title={t("remoteBrowser.ai.title", "AI 助手")}
              >
                {isMobile ? null : t("remoteBrowser.ai.title", "AI 助手")}
              </Button>
              <Tooltip
                title={t(
                  "skillRecordGuide.buttonTip",
                  "录制浏览器操作，生成可复用的技能脚本",
                )}
              >
                <Button
                  size="small"
                  icon={<Sparkles size={14} />}
                  onClick={openSkillGuide}
                  aria-label={t("skillRecordGuide.buttonLabel", "技能录制")}
                >
                  {isMobile
                    ? null
                    : t("skillRecordGuide.buttonLabel", "技能录制")}
                </Button>
              </Tooltip>
            </div>
            {/* Bookmark bar */}
            {bookmarks.length > 0 && (
              <BookmarkBar
                bookmarks={bookmarks}
                onOpen={openBookmark}
                onRemove={remove}
              />
            )}
          </div>
        )}

        <div
          className={`${styles.mainRow} ${
            isMobile ? styles.mainRowMobile : ""
          }`}
        >
          <div className={styles.browserColumn}>
            {session ? (
              <div
                style={{
                  flex: 1,
                  minHeight: 0,
                  display: "flex",
                  flexDirection: "column",
                  border: "1px solid var(--fn-border-secondary)",
                  borderTop: "none",
                  borderRadius: "0 0 6px 6px",
                  overflow: "hidden",
                }}
              >
                <div ref={containerRef} className={styles.canvasViewport}>
                  {!frameReady && (
                    <div
                      style={{
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: 8,
                        zIndex: 1,
                      }}
                    >
                      <RefreshCw
                        size={28}
                        className={styles.streamLoadingIcon}
                      />
                      <Text type="secondary">
                        {isStreaming
                          ? t("remoteBrowser.streaming", "推流中")
                          : t("remoteBrowser.connecting", "连接中")}
                      </Text>
                    </div>
                  )}
                  <canvas
                    ref={canvasRef}
                    tabIndex={0}
                    className={`${styles.canvas} ${
                      isMobile ? styles.canvasMobile : ""
                    } ${!frameReady ? styles.canvasHidden : ""}`}
                    style={{
                      cursor: isDragging ? "grabbing" : "grab",
                      ...pointerStyle,
                    }}
                    onPointerDown={handleCanvasPointerDown}
                    onDoubleClick={handleCanvasDblClick}
                    onWheel={handleCanvasWheel}
                    onKeyDown={handleCanvasKeyDown}
                  />
                  <StreamEdgeControls
                    visible={showEdgeControls}
                    isMobile={isMobile}
                    fullscreenLabel={t("remoteBrowser.fullscreen", "全屏")}
                    controlsLabel={t(
                      "remoteBrowser.openControls",
                      "控制与快捷操作",
                    )}
                    streamingLabel={
                      isStreaming
                        ? t("remoteBrowser.streaming", "推流中")
                        : t("remoteBrowser.connecting", "连接中")
                    }
                    onFullscreen={() => void handleFullscreen()}
                    onOpenControls={openControlsDrawer}
                  />
                </div>

                <div
                  style={{
                    fontSize: 11,
                    color: "var(--fn-text-tertiary)",
                    padding: "3px 8px",
                    borderTop: "1px solid var(--fn-border-secondary)",
                    background: "var(--fn-bg-primary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <span>{tabs.length} tabs</span>
                  <span style={{ color: "var(--fn-text-quaternary, #bbb)" }}>
                    {session.id}
                  </span>
                </div>
              </div>
            ) : (
              <div ref={containerRef} className={styles.idleViewport}>
                {installPhase === "installing" ? (
                  renderViewportInstallProgress()
                ) : uninstalling ? (
                  renderViewportUninstallProgress()
                ) : (
                  <StreamSetupGuide
                    icon={<Globe size={48} strokeWidth={1.5} />}
                    title={
                      envReady
                        ? t("remoteBrowser.startBrowserTitle", "启动远程浏览器")
                        : t("remoteBrowser.setupTitle", "需要配置浏览器环境")
                    }
                    description={
                      envReady
                        ? t(
                            "remoteBrowser.startBrowserDesc",
                            "环境已就绪，按以下步骤开始远程浏览与操控",
                          )
                        : envStatus?.error ||
                          t(
                            "remoteBrowser.setupDesc",
                            "按以下步骤完成 Playwright / Chromium 环境配置",
                          )
                    }
                    steps={
                      envReady
                        ? [
                            {
                              label: t(
                                "remoteBrowser.startBrowserIdleStep1",
                                "点击右上角「启动浏览器」建立会话",
                              ),
                            },
                            {
                              label: t(
                                "remoteBrowser.startBrowserIdleStep2",
                                "在地址栏输入网址并访问，也可使用收藏夹与 AI 助手",
                              ),
                            },
                          ]
                        : [
                            {
                              label: t(
                                "remoteBrowser.setupStep1",
                                "点击「检查」，检测 Playwright 与 Chromium 是否可用",
                              ),
                            },
                            {
                              label: t(
                                "remoteBrowser.setupStep2",
                                "若组件缺失，在弹窗中一键安装浏览器环境",
                              ),
                            },
                            {
                              label: t(
                                "remoteBrowser.setupStep3",
                                "安装完成后，点击「启动浏览器」开始会话",
                              ),
                            },
                          ]
                    }
                    primaryAction={
                      envReady
                        ? {
                            label: creating
                              ? t(
                                  "remoteBrowser.ai.startingBrowser",
                                  "正在启动...",
                                )
                              : t("remoteBrowser.startBrowser", "启动浏览器"),
                            onClick: () => void createSession(),
                            loading: creating,
                            disabled: !envReady,
                            icon: <Play size={14} />,
                          }
                        : {
                            label: t("remoteBrowser.checkInstallShort", "检查"),
                            onClick: openEnvModal,
                            icon: <Globe size={14} />,
                          }
                    }
                    secondaryAction={
                      envStatus?.playwright_chromium
                        ? {
                            label: t("remoteBrowser.uninstall", "卸载"),
                            onClick: handleUninstall,
                            icon: <Trash2 size={14} />,
                            loading: uninstalling,
                            disabled: uninstalling || envLoading,
                            danger: true,
                          }
                        : undefined
                    }
                  />
                )}
              </div>
            )}
          </div>

          {isAiPanelOpen && (
            <div
              className={isMobile ? styles.aiPanelBottom : styles.aiPanelRight}
              style={
                isMobile ? { height: aiPanelHeight } : { width: aiPanelWidth }
              }
            >
              <div
                className={
                  isMobile ? styles.resizeHandleTop : styles.resizeHandleLeft
                }
                onMouseDown={handleAiResizeMouseDown}
              />
              <BrowserAiPanel
                activeAgent={effectiveActiveAgent}
                tabs={tabs}
                currentUrl={session?.url || navUrl}
                profileId={profileIdRef.current}
                layout={isMobile ? "bottom" : "right"}
                onClose={handleAiPanelClose}
                browserRecording={browserRecording}
                browserRecordingId={browserRecordingId}
                browserLastRecordingId={browserLastRecordingId}
                setBrowserRecording={setBrowserRecording}
                setBrowserRecordingId={setBrowserRecordingId}
                setBrowserLastRecordingId={setBrowserLastRecordingId}
                skillName={skillName}
                onSkillNameSet={setSkillName}
                browserSessionActive={!!session}
                browserStarting={creating}
                onStartBrowser={() => void createSession()}
              />
            </div>
          )}
        </div>
      </div>
    </PageShell>
  );
}
