import { useEffect, useRef, useCallback, useState, useMemo, memo } from "react";
import { useTranslation } from "react-i18next";
import { Button, Dropdown, Tabs, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  Plus,
  X,
  SquareTerminal,
  SquareDashedBottom,
  Loader,
  Palette,
  Bot,
  RefreshCw,
} from "lucide-react";
import AiPanel, { type AiPanelLayout } from "./components/AiPanel";
import TerminalView, {
  type TerminalViewHandle,
} from "./components/TerminalView";
import { useTerminal, type TerminalConnState } from "./useTerminal";
import { createTerminalOutputBuffer } from "./terminalOutputBuffer";
import {
  TERMINAL_THEMES,
  TERMINAL_THEME_STORAGE_KEY,
  DEFAULT_THEME,
  getTerminalTheme,
  type TerminalThemeDefinition,
} from "./terminalThemes";
import { useTheme } from "../../../context/ThemeContext";
import { useAgent } from "../../../context/AgentContext";
import { useIsMobile } from "../../../hooks/useIsMobile";
import styles from "./index.module.less";

const AI_PANEL_LAYOUT_KEY = "octop:terminal-ai-layout";
const AI_PANEL_WIDTH_KEY = "octop:terminal-ai-width";
const AI_PANEL_HEIGHT_KEY = "octop:terminal-ai-height";
const AI_PANEL_MIN_WIDTH = 220;
const AI_PANEL_MAX_WIDTH = 720;
const AI_PANEL_MIN_HEIGHT = 160;
const AI_PANEL_MAX_HEIGHT = 600;

function ConnBadge({ state }: { state: TerminalConnState }) {
  const { t } = useTranslation();
  if (state === "connected") {
    return (
      <Tooltip title={t("terminal.connected")}>
        <SquareTerminal size={12} color="var(--fn-color-success, #22c55e)" />
      </Tooltip>
    );
  }
  if (state === "connecting" || state === "reconnecting") {
    return (
      <Tooltip
        title={t(
          state === "reconnecting"
            ? "terminal.reconnecting"
            : "terminal.connecting",
        )}
      >
        <Loader
          size={12}
          className={styles.spinning}
          color="var(--fn-color-brand)"
        />
      </Tooltip>
    );
  }
  return (
    <Tooltip title={t("terminal.disconnected")}>
      <SquareDashedBottom
        size={12}
        color="var(--fn-text-quaternary, #9ca3af)"
      />
    </Tooltip>
  );
}

/**
 * TerminalTab renders a single terminal session.
 *
 * Key design: the `onOutput` callback is stored in a ref so it is always
 * up-to-date even after TerminalView mounts its xterm instance. This avoids
 * a race condition where connect() is called before xterm is ready.
 */
const TerminalTab = memo(function TerminalTab({
  sessionId,
  isActive,
  isPageVisible,
  connState,
  onConnStateChange,
  sendInput,
  sendResize,
  connect,
  onReconnect,
  themeDefinition,
  agentId,
  onOutputCapture,
}: {
  sessionId: string;
  isActive: boolean;
  /** Mirrors the TerminalPage isVisible prop so we can re-fit on page show. */
  isPageVisible: boolean;
  /** Current connection state — drives the reconnect overlay. */
  connState: TerminalConnState;
  onConnStateChange: (id: string, state: TerminalConnState) => void;
  sendInput: (id: string, data: string) => void;
  sendResize: (id: string, cols: number, rows: number) => void;
  connect: (
    id: string,
    agentId: string,
    cbs: {
      onOutput: (data: string) => void;
      onHistory?: (data: string) => void;
      onExit?: (code: number) => void;
      onStateChange?: (state: TerminalConnState) => void;
    },
  ) => void;
  onReconnect: (id: string) => void;
  themeDefinition: TerminalThemeDefinition;
  /** Active agent — terminal is rooted at this agent's workspace_dir. */
  agentId: string;
  /** Capture PTY output for AI autopilot heuristics. */
  onOutputCapture?: (sessionId: string, data: string) => void;
}) {
  const { t } = useTranslation();
  // termRef is set by TerminalView once xterm is initialised
  const termRef = useRef<TerminalViewHandle | null>(null);

  // Keep a stable ref to the latest termRef so closures always see current value
  const termRefStable = useRef(termRef);
  termRefStable.current = termRef;

  // Track whether the WS has been connected already
  const connectedRef = useRef(false);

  const handleData = useCallback(
    (data: string) => {
      sendInput(sessionId, data);
    },
    [sendInput, sessionId],
  );

  const handleResize = useCallback(
    (cols: number, rows: number) => {
      sendResize(sessionId, cols, rows);
    },
    [sendResize, sessionId],
  );

  // Called by TerminalView after xterm is open — this is the right time to
  // open the WebSocket because the xterm write handle is now available.
  const handleTerminalReady = useCallback(() => {
    if (connectedRef.current) return;
    connectedRef.current = true;

    connect(sessionId, agentId, {
      onOutput: (data) => {
        onOutputCapture?.(sessionId, data);
        termRefStable.current.current?.write(data);
      },
      onHistory: (data) => {
        // Authoritative scrollback replay: reset then rewrite so a fresh xterm
        // (after refresh) and a reconnect (filling the drop gap) both converge.
        const term = termRefStable.current.current;
        term?.reset();
        term?.write(data);
      },
      onStateChange: (state) => {
        onConnStateChange(sessionId, state);
      },
      onExit: (code) => {
        termRefStable.current.current?.write(
          `\r\n\x1b[90m[${t("terminal.processExited")} (${code})]\x1b[0m\r\n`,
        );
      },
    });
  }, [connect, sessionId, agentId, onConnStateChange, onOutputCapture, t]);

  // Auto-focus and re-fit when this tab becomes active or when the page
  // becomes visible after being hidden (display:none → display:flex).
  // Re-fitting corrects the stale row count xterm reports after the outer
  // container transitions from display:none — manifests as one missing row.
  useEffect(() => {
    if (isActive && isPageVisible) {
      const t = setTimeout(() => {
        termRef.current?.fit();
        termRef.current?.focus();
      }, 80);
      return () => clearTimeout(t);
    }
  }, [isActive, isPageVisible]);

  const needsReconnect = connState === "disconnected" || connState === "error";

  return (
    <div
      className={styles.terminalWrapper}
      style={{ backgroundColor: themeDefinition.theme.background as string }}
    >
      <TerminalView
        terminalRef={termRef}
        onData={handleData}
        onResize={handleResize}
        onReady={handleTerminalReady}
        themeDefinition={themeDefinition}
      />
      {needsReconnect && (
        <div className={styles.reconnectOverlay}>
          <div className={styles.reconnectCard}>
            <RefreshCw size={22} />
            <span className={styles.reconnectTitle}>
              {t("terminal.connectionLost")}
            </span>
            <Button
              size="small"
              type="primary"
              icon={<RefreshCw size={14} />}
              onClick={() => onReconnect(sessionId)}
            >
              {t("terminal.reconnect")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
});

// ─── Theme Picker ─────────────────────────────────────────────────────────────

function ThemeColorDot({ color, size = 14 }: { color: string; size?: number }) {
  return (
    <span
      className={styles.colorDot}
      style={{
        backgroundColor: color,
        width: size,
        height: size,
      }}
    />
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

interface TerminalPageProps {
  /** When true the page is currently visible; used to defer first session creation. */
  isVisible?: boolean;
  /** Hide standalone page chrome when hosted inside Workbench. */
  embedded?: boolean;
}

export default function TerminalPage({
  isVisible = true,
  embedded = false,
}: TerminalPageProps) {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const isMobile = useIsMobile();
  const { activeAgentId, agents, loading: agentsLoading, refresh } = useAgent();
  const {
    sessionIds,
    activeId,
    setActiveId,
    createSession,
    reconcileAgentIds,
    connect,
    reconnect,
    sendInput,
    sendResize,
    closeSession,
  } = useTerminal();

  // Track whether the page has been shown at least once so we only create the
  // initial terminal session on first visit, not on app startup.
  const hasBeenVisibleRef = useRef(false);

  const [connStates, setConnStates] = useState<
    Record<string, TerminalConnState>
  >({});

  const outputBufferRef = useRef(createTerminalOutputBuffer());

  const handleOutputCapture = useCallback((sessionId: string, data: string) => {
    outputBufferRef.current.append(sessionId, data);
  }, []);

  // Terminal theme state — persisted to localStorage, defaults to dark theme
  const [themeKey, setThemeKey] = useState<string>(() => {
    return localStorage.getItem(TERMINAL_THEME_STORAGE_KEY) ?? DEFAULT_THEME;
  });

  const themeDefinition = useMemo(
    () => getTerminalTheme(themeKey || null, isDark),
    [themeKey, isDark],
  );

  const handleThemeChange = useCallback((key: string) => {
    setThemeKey(key);
    localStorage.setItem(TERMINAL_THEME_STORAGE_KEY, key);
  }, []);

  // AI panel state
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [panelLayout, setPanelLayout] = useState<AiPanelLayout>(() => {
    const stored = localStorage.getItem(AI_PANEL_LAYOUT_KEY);
    return stored === "bottom" ? "bottom" : "right";
  });
  const [panelWidth, setPanelWidth] = useState(() => {
    const stored = localStorage.getItem(AI_PANEL_WIDTH_KEY);
    const n = stored ? parseInt(stored, 10) : 340;
    return Math.min(Math.max(n, AI_PANEL_MIN_WIDTH), AI_PANEL_MAX_WIDTH);
  });
  const [panelHeight, setPanelHeight] = useState(() => {
    const stored = localStorage.getItem(AI_PANEL_HEIGHT_KEY);
    const n = stored ? parseInt(stored, 10) : 280;
    return Math.min(Math.max(n, AI_PANEL_MIN_HEIGHT), AI_PANEL_MAX_HEIGHT);
  });

  const effectivePanelLayout: AiPanelLayout = isMobile ? "bottom" : panelLayout;

  // Drag-resize handle for the AI panel
  const dragRef = useRef<{
    startX: number;
    startY: number;
    startSize: number;
  } | null>(null);
  const handleResizeMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      if (effectivePanelLayout === "right") {
        dragRef.current = {
          startX: e.clientX,
          startY: e.clientY,
          startSize: panelWidth,
        };
        const onMove = (mv: MouseEvent) => {
          if (!dragRef.current) return;
          const delta = dragRef.current.startX - mv.clientX;
          const next = Math.min(
            Math.max(dragRef.current.startSize + delta, AI_PANEL_MIN_WIDTH),
            AI_PANEL_MAX_WIDTH,
          );
          setPanelWidth(next);
        };
        const onUp = (mv: MouseEvent) => {
          if (!dragRef.current) return;
          const delta = dragRef.current.startX - mv.clientX;
          const next = Math.min(
            Math.max(dragRef.current.startSize + delta, AI_PANEL_MIN_WIDTH),
            AI_PANEL_MAX_WIDTH,
          );
          localStorage.setItem(AI_PANEL_WIDTH_KEY, String(next));
          dragRef.current = null;
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      } else {
        dragRef.current = {
          startX: e.clientX,
          startY: e.clientY,
          startSize: panelHeight,
        };
        const onMove = (mv: MouseEvent) => {
          if (!dragRef.current) return;
          const delta = dragRef.current.startY - mv.clientY;
          const next = Math.min(
            Math.max(dragRef.current.startSize + delta, AI_PANEL_MIN_HEIGHT),
            AI_PANEL_MAX_HEIGHT,
          );
          setPanelHeight(next);
        };
        const onUp = (mv: MouseEvent) => {
          if (!dragRef.current) return;
          const delta = dragRef.current.startY - mv.clientY;
          const next = Math.min(
            Math.max(dragRef.current.startSize + delta, AI_PANEL_MIN_HEIGHT),
            AI_PANEL_MAX_HEIGHT,
          );
          localStorage.setItem(AI_PANEL_HEIGHT_KEY, String(next));
          dragRef.current = null;
          window.removeEventListener("mousemove", onMove);
          window.removeEventListener("mouseup", onUp);
        };
        window.addEventListener("mousemove", onMove);
        window.addEventListener("mouseup", onUp);
      }
    },
    [effectivePanelLayout, panelWidth, panelHeight],
  );

  const handleConnStateChange = useCallback(
    (id: string, state: TerminalConnState) => {
      setConnStates((prev) => ({ ...prev, [id]: state }));
    },
    [],
  );

  // Drop stale agent ids from restored terminal tabs (e.g. after an agent delete).
  useEffect(() => {
    if (agentsLoading || agents.length === 0) return;
    const fallback = activeAgentId ?? agents[0]?.agent_id ?? "";
    if (!fallback) return;
    reconcileAgentIds(
      agents.map((a) => a.agent_id),
      fallback,
    );
  }, [agents, agentsLoading, activeAgentId, reconcileAgentIds]);

  // Create the first tab on first visit (not on app startup)
  useEffect(() => {
    if (!isVisible) return;
    if (hasBeenVisibleRef.current) return;
    hasBeenVisibleRef.current = true;
    // Skip if tabs were restored from a previous session.
    if (sessionIds.length === 0) {
      createSession();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible]);

  const handleAddTab = () => {
    createSession();
  };

  const handleCloseTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    closeSession(id);
    setConnStates((prev) => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  // ── Theme dropdown menu ───────────────────────────────────────────────────

  const themeMenuItems: MenuProps["items"] = useMemo(() => {
    const darkThemes = TERMINAL_THEMES.filter((th) => th.isDark);
    const lightThemes = TERMINAL_THEMES.filter((th) => !th.isDark);

    const items: MenuProps["items"] = [];

    // Dark group
    items.push({
      key: "dark-group-label",
      type: "group",
      label: t("terminal.themes.darkGroup"),
    });
    darkThemes.forEach((th) => {
      items.push({
        key: th.key,
        label: (
          <span className={styles.themeMenuItem}>
            <ThemeColorDot color={th.theme.background as string} />
            <ThemeColorDot color={th.theme.foreground as string} />
            <span>{t(th.labelKey)}</span>
          </span>
        ),
        onClick: () => handleThemeChange(th.key),
      });
    });

    // Divider
    items.push({ key: "divider", type: "divider" });

    // Light group
    items.push({
      key: "light-group-label",
      type: "group",
      label: t("terminal.themes.lightGroup"),
    });
    lightThemes.forEach((th) => {
      items.push({
        key: th.key,
        label: (
          <span className={styles.themeMenuItem}>
            <ThemeColorDot color={th.theme.background as string} />
            <ThemeColorDot color={th.theme.foreground as string} />
            <span>{t(th.labelKey)}</span>
          </span>
        ),
        onClick: () => handleThemeChange(th.key),
      });
    });

    return items;
  }, [t, handleThemeChange]);

  // ── Tab items ─────────────────────────────────────────────────────────────

  const tabItems = sessionIds.map((id, index) => {
    const state = connStates[id] ?? "connecting";
    return {
      key: id,
      label: (
        <span className={styles.tabLabel}>
          <ConnBadge state={state} />
          <span>{`${t("terminal.session")} ${index + 1}`}</span>
          {sessionIds.length > 1 && (
            <button
              className={styles.closeBtn}
              onClick={(e) => handleCloseTab(id, e)}
              title={t("common.close")}
            >
              <X size={11} />
            </button>
          )}
        </span>
      ),
      children: (
        <TerminalTab
          key={id}
          sessionId={id}
          isActive={activeId === id}
          isPageVisible={isVisible}
          connState={state}
          onConnStateChange={handleConnStateChange}
          sendInput={sendInput}
          sendResize={sendResize}
          connect={connect}
          onReconnect={reconnect}
          themeDefinition={themeDefinition}
          agentId={activeAgentId || ""}
          onOutputCapture={handleOutputCapture}
        />
      ),
    };
  });

  const tabBarExtra = (
    <div className={styles.tabBarActions}>
      <Tooltip title={t("terminal.ai.togglePanel")}>
        <div className={styles.aiBtnWrap}>
          <Button
            type={isPanelOpen ? "primary" : "default"}
            icon={<Bot size={16} />}
            size="small"
            className={isPanelOpen ? styles.aiBtnActive : styles.aiBtnIdle}
            onClick={() => setIsPanelOpen((v) => !v)}
          />
          {!isPanelOpen && <span className={styles.aiBtnBadge}>NEW</span>}
        </div>
      </Tooltip>
      <Dropdown
        menu={{
          items: themeMenuItems,
          selectedKeys: [themeDefinition.key],
        }}
        placement="bottomRight"
        trigger={["click"]}
      >
        <Tooltip title={t("terminal.themes.label")}>
          <Button type="text" icon={<Palette size={14} />} size="small" />
        </Tooltip>
      </Dropdown>
      <Tooltip title={t("terminal.newTab")}>
        <Button
          type="text"
          icon={<Plus size={14} />}
          size="small"
          onClick={handleAddTab}
        />
      </Tooltip>
    </div>
  );

  const contentAreaClass = [
    styles.contentArea,
    isPanelOpen && effectivePanelLayout === "bottom"
      ? styles.contentAreaBottom
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  const tabsCardClass = [
    styles.tabsCard,
    isPanelOpen ? styles.tabsCardWithPanel : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={`${styles.terminalPage}${
        embedded ? ` ${styles.terminalPageEmbedded}` : ""
      }`}
    >
      {!embedded && (
        <div className={styles.header}>
          <div className={styles.headerInfo}>
            <div className={styles.title}>{t("terminal.title")}</div>
            <p className={styles.description}>{t("terminal.description")}</p>
          </div>
          <Button
            type={isPanelOpen ? "primary" : "default"}
            danger={!isPanelOpen}
            icon={<Bot size={16} />}
            className={
              isPanelOpen ? styles.headerAiBtnActive : styles.headerAiBtn
            }
            onClick={() => setIsPanelOpen((v) => !v)}
          >
            {t("terminal.ai.togglePanel")}
          </Button>
        </div>
      )}

      <div className={contentAreaClass}>
        <div className={tabsCardClass}>
          {sessionIds.length === 0 ? (
            <div className={styles.emptyState}>
              <Button
                type="primary"
                icon={<Plus size={14} />}
                onClick={handleAddTab}
              >
                {t("terminal.newTab")}
              </Button>
            </div>
          ) : (
            <Tabs
              type="card"
              activeKey={activeId ?? undefined}
              onChange={setActiveId}
              tabBarExtraContent={tabBarExtra}
              items={tabItems}
              className={styles.terminalTabs}
              destroyOnHidden={false}
              animated={false}
            />
          )}
        </div>

        {isPanelOpen && (
          <div
            className={
              effectivePanelLayout === "right"
                ? styles.aiPanelRight
                : styles.aiPanelBottom
            }
            style={
              effectivePanelLayout === "right"
                ? { width: panelWidth }
                : { height: panelHeight }
            }
          >
            {/* Drag resize handle */}
            <div
              className={
                effectivePanelLayout === "right"
                  ? styles.resizeHandleLeft
                  : styles.resizeHandleTop
              }
              onMouseDown={handleResizeMouseDown}
            />
            <AiPanel
              activeAgent={
                activeAgentId
                  ? agents.find((a) => a.agent_id === activeAgentId) ?? null
                  : null
              }
              agents={agents}
              activeTerminalSessionId={activeId}
              activeTerminalSessionIndex={
                activeId ? sessionIds.indexOf(activeId) + 1 : 0
              }
              layout={effectivePanelLayout}
              layoutSwitchable={!isMobile}
              onLayoutChange={(layout) => {
                setPanelLayout(layout);
                localStorage.setItem(AI_PANEL_LAYOUT_KEY, layout);
              }}
              onClose={() => setIsPanelOpen(false)}
              onExecuteCommand={(cmd) => {
                if (!activeId) return;
                for (const line of cmd.split("\n")) {
                  const trimmed = line.trimEnd();
                  if (trimmed) sendInput(activeId, trimmed + "\r");
                }
              }}
              getRecentTerminalOutput={() =>
                activeId ? outputBufferRef.current.getRecent(activeId) : ""
              }
              snapshotTerminalOutput={() =>
                activeId ? outputBufferRef.current.snapshot(activeId) : ""
              }
              onAgentCreated={() => {
                void refresh();
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
