import { useEffect, useRef, useCallback, useState, useMemo, memo } from "react";
import { useTranslation } from "react-i18next";
import { Button, Dropdown, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  Plus,
  SquareTerminal,
  SquareDashedBottom,
  Loader,
  Palette,
  Bot,
  RefreshCw,
} from "lucide-react";
import cx from "classnames";
import { ChromeTabBar } from "../../../components/ChromeTabBar";
import AiPanel from "./components/AiPanel";
import TerminalView, {
  type TerminalViewHandle,
} from "./components/TerminalView";
import {
  useTerminal,
  type TerminalCallbacks,
  type TerminalConnState,
} from "./useTerminal";
import { createTerminalOutputBuffer } from "./terminalOutputBuffer";
import {
  TERMINAL_THEMES,
  TERMINAL_THEME_STORAGE_KEY,
  DEFAULT_THEME,
  getTerminalTheme,
  type TerminalThemeDefinition,
} from "./terminalThemes";
import { useTheme } from "../../../context/ThemeContext";
import { formatOpsEnsureError, useOpsEngineer } from "./useOpsEngineer";
import { useIsMobile } from "../../../hooks/useIsMobile";
import {
  readAssistantPlacement,
  type AssistantPlacement,
} from "../../../components/AssistantFrame/AssistantFrame";
import styles from "./index.module.less";

const AI_PANEL_LAYOUT_KEY = "octop:terminal-ai-layout-v2";
const TERMINAL_PLACEMENTS = ["bottom", "right", "float"] as const;

function ConnBadge({ state }: { state: TerminalConnState }) {
  const { t } = useTranslation();
  // Match BrowserViewer tab leading icon: fixed size, gray by default.
  const iconProps = {
    size: 11 as const,
    strokeWidth: 2 as const,
    className: styles.tabLeadIcon,
    "aria-hidden": true as const,
  };
  if (state === "connected") {
    return (
      <Tooltip title={t("terminal.connected")}>
        <SquareTerminal {...iconProps} />
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
          {...iconProps}
          className={cx(styles.spinning, styles.tabLeadIcon)}
        />
      </Tooltip>
    );
  }
  return (
    <Tooltip title={t("terminal.disconnected")}>
      <SquareDashedBottom {...iconProps} />
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
  unbind,
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
  connect: (id: string, agentId: string, cbs: TerminalCallbacks) => void;
  unbind: (id: string, cbs: TerminalCallbacks) => void;
  onReconnect: (id: string) => void;
  themeDefinition: TerminalThemeDefinition;
  /** 运维工程师。终端进程挂在这个 agent 的工作区上。 */
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
  const callbacksRef = useRef<TerminalCallbacks | null>(null);

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

    const cbs: TerminalCallbacks = {
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
    };
    callbacksRef.current = cbs;
    connect(sessionId, agentId, cbs);
  }, [connect, sessionId, agentId, onConnStateChange, onOutputCapture, t]);

  // Drop UI listener on unmount without closing the shared PTY socket.
  useEffect(() => {
    return () => {
      const cbs = callbacksRef.current;
      if (cbs) unbind(sessionId, cbs);
    };
  }, [unbind, sessionId]);

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
  const {
    agent: opsAgent,
    ensuring: opsEnsuring,
    ensureError: opsEnsureError,
    retry: retryOpsEngineer,
  } = useOpsEngineer(isVisible);
  const {
    sessionIds,
    activeId,
    setActiveId,
    createSession,
    ensureDefaultSession,
    reconcileAgentIds,
    connect,
    unbind,
    reconnect,
    sendInput,
    sendResize,
    closeSession,
  } = useTerminal();

  // Track whether this surface has been shown at least once so we only seed
  // the default session on first visit (not on app startup / keep-alive hide).
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

  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [panelLayout, setPanelLayout] = useState<AssistantPlacement>(() =>
    readAssistantPlacement(AI_PANEL_LAYOUT_KEY, "right"),
  );
  const effectivePanelLayout: AssistantPlacement = isMobile
    ? "bottom"
    : panelLayout;

  const handleConnStateChange = useCallback(
    (id: string, state: TerminalConnState) => {
      setConnStates((prev) => ({ ...prev, [id]: state }));
    },
    [],
  );

  // 终端只连运维工程师。侧栏当前专家不接管这个页面的 shell。
  useEffect(() => {
    const opsId = opsAgent?.agent_id;
    if (!opsId) return;
    reconcileAgentIds([opsId], opsId);
  }, [opsAgent?.agent_id, reconcileAgentIds]);

  // Create the first tab on first visit (not on app startup). Uses the live
  // store so a remounted chat-dock TerminalPage cannot race-create extras.
  useEffect(() => {
    if (!isVisible) return;
    if (hasBeenVisibleRef.current) return;
    hasBeenVisibleRef.current = true;
    ensureDefaultSession();
  }, [isVisible, ensureDefaultSession]);

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

  // ── Chrome tabs + session panes ────────────────────────────────────────────

  const chromeTabs = sessionIds.map((id, index) => {
    const state = connStates[id] ?? "connecting";
    return {
      key: id,
      leading: <ConnBadge state={state} />,
      label: `${t("terminal.session")} ${index + 1}`,
      closable: sessionIds.length > 1,
    };
  });

  const tabBarExtra = (
    <div className={styles.tabBarActions}>
      <Tooltip title={t("terminal.ai.togglePanel")}>
        <Button
          type={isPanelOpen ? "primary" : "default"}
          icon={<Bot size={14} />}
          size="small"
          aria-pressed={isPanelOpen}
          onClick={() => setIsPanelOpen((v) => !v)}
        />
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
    </div>
  );

  const contentAreaClass = cx(
    styles.contentArea,
    isPanelOpen &&
      effectivePanelLayout === "bottom" &&
      styles.contentAreaBottom,
  );

  const tabsCardClass = cx(
    styles.tabsCard,
    isPanelOpen && styles.tabsCardWithPanel,
  );

  return (
    <div
      className={cx(
        styles.terminalPage,
        embedded && styles.terminalPageEmbedded,
      )}
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
          {opsEnsureError ? (
            <div className={styles.opsNotice} role="alert">
              <span className={styles.opsNoticeText}>
                {formatOpsEnsureError(opsEnsureError, t)}
              </span>
              <Button
                size="small"
                loading={opsEnsuring}
                onClick={retryOpsEngineer}
              >
                {t("terminal.ai.gateCreate")}
              </Button>
            </div>
          ) : null}
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
            <>
              <ChromeTabBar
                tabs={chromeTabs}
                activeKey={activeId ?? undefined}
                onChange={setActiveId}
                onClose={handleCloseTab}
                onNewTab={handleAddTab}
                newTabTitle={t("terminal.newTab")}
                trailing={tabBarExtra}
              />
              <div className={styles.sessionPanes}>
                {sessionIds.map((id) => (
                  <div
                    key={id}
                    className={cx(
                      styles.sessionPane,
                      id !== activeId && styles.sessionPaneHidden,
                    )}
                    role="tabpanel"
                    aria-hidden={id !== activeId}
                  >
                    <TerminalTab
                      sessionId={id}
                      isActive={activeId === id}
                      isPageVisible={isVisible}
                      connState={connStates[id] ?? "connecting"}
                      onConnStateChange={handleConnStateChange}
                      sendInput={sendInput}
                      sendResize={sendResize}
                      connect={connect}
                      unbind={unbind}
                      onReconnect={reconnect}
                      themeDefinition={themeDefinition}
                      agentId={opsAgent?.agent_id || ""}
                      onOutputCapture={handleOutputCapture}
                    />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        {isPanelOpen && (
          <AiPanel
            agent={opsAgent}
            ensuring={opsEnsuring}
            ensureError={opsEnsureError}
            onEnsureRetry={retryOpsEngineer}
            activeTerminalSessionId={activeId}
            activeTerminalSessionIndex={
              activeId ? sessionIds.indexOf(activeId) + 1 : 0
            }
            placement={effectivePanelLayout}
            placementLocked={isMobile}
            placements={TERMINAL_PLACEMENTS}
            hidden={!isVisible}
            onPlacementChange={setPanelLayout}
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
          />
        )}
      </div>
    </div>
  );
}
