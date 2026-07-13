import { useState, useRef, useCallback, useEffect } from "react";
import { getAuthToken } from "../../../api/request";

export type TerminalConnState =
  | "connecting"
  | "reconnecting"
  | "connected"
  | "disconnected"
  | "error";

export interface TerminalCallbacks {
  onOutput: (data: string) => void;
  /** Scrollback replay from the server (on re-attach). Reset + write. */
  onHistory?: (data: string) => void;
  onExit?: (code: number) => void;
  onStateChange?: (state: TerminalConnState) => void;
}

export interface TerminalSession {
  id: string;
  /** Agent this shell is rooted at. Captured at connect time, reused on reconnect. */
  agentId: string;
  ws: WebSocket | null;
  connState: TerminalConnState;
  /** True once the shell exited — suppresses auto-reconnect. */
  exited: boolean;
  reconnectAttempts: number;
  reconnectTimer: ReturnType<typeof setTimeout> | null;
  /** Callbacks captured at connect() time, reused across reconnects. */
  cbs?: TerminalCallbacks;
  onOutput?: (data: string) => void;
  onHistory?: (data: string) => void;
  onExit?: (code: number) => void;
  /** Cached terminal dimensions, synced to the PTY on (re)connect. */
  pendingCols?: number;
  pendingRows?: number;
}

const STORAGE_KEY = "octop:terminal-sessions";
const STORAGE_VERSION = 1;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
const RESIZE_DEBOUNCE_MS = 150;

interface StoredTab {
  id: string;
  agentId: string;
}

interface StoredState {
  version: number;
  tabs: StoredTab[];
  activeId: string | null;
}

function loadStored(): StoredState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as StoredState;
    if (data.version !== STORAGE_VERSION) return null;
    return data;
  } catch {
    return null;
  }
}

function persist(tabs: StoredTab[], activeId: string | null) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: STORAGE_VERSION, tabs, activeId }),
    );
  } catch {
    // Ignore quota / privacy-mode errors.
  }
}

function generateId(): string {
  // Stable across reconnect/refresh — reused as the backend session_id so the
  // same shell can be resumed.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function buildWsUrl(agentId: string, sessionId: string): string {
  const token = getAuthToken();
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const base = `${protocol}://${
    window.location.host
  }/api/agents/${encodeURIComponent(agentId)}/terminal/ws`;
  const params = new URLSearchParams();
  if (token) params.set("token", token);
  // Opt into backend session persistence: same id re-attaches to the shell.
  params.set("session_id", sessionId);
  return `${base}?${params.toString()}`;
}

type SessionMap = Map<string, TerminalSession>;

function pickAgentId(
  session: TerminalSession,
  currentAgentId: string,
  validAgentIds: ReadonlySet<string>,
): string {
  const resolve = (id: string) => {
    if (!id) return "";
    if (validAgentIds.has(id)) return id;
    for (const full of validAgentIds) {
      if (full.endsWith(id)) return full;
    }
    return "";
  };
  return resolve(session.agentId) || resolve(currentAgentId);
}

/** Restore persisted tabs into the sessions map, returning their ids. */
function restoreAndSeed(sessionsRef: { current: SessionMap }): string[] {
  const stored = loadStored();
  if (!stored?.tabs.length) return [];
  for (const tab of stored.tabs) {
    sessionsRef.current.set(tab.id, {
      id: tab.id,
      agentId: tab.agentId,
      ws: null,
      connState: "connecting",
      exited: false,
      reconnectAttempts: 0,
      reconnectTimer: null,
    });
  }
  return stored.tabs.map((t) => t.id);
}

/**
 * Manages multiple interactive terminal WebSocket sessions with persistence.
 *
 * Each tab maps to one session. The session id is sent to the backend
 * (``session_id=``) so the shell survives disconnects/refreshes; on re-attach
 * the server replays scrollback via a ``history`` message. Auto-reconnect with
 * capped backoff handles transient drops; a manual ``reconnect`` is exposed for
 * recovery / post-exit restart.
 */
export function useTerminal() {
  const sessionsRef = useRef<SessionMap>(new Map());
  const validAgentIdsRef = useRef<Set<string>>(new Set());
  const resizeTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(
    new Map(),
  );

  const [sessionIds, setSessionIds] = useState<string[]>(() =>
    restoreAndSeed(sessionsRef),
  );
  const [activeId, setActiveIdState] = useState<string | null>(() => {
    const stored = loadStored();
    if (!stored?.activeId) return null;
    const valid = stored.tabs.some((t) => t.id === stored.activeId);
    return valid ? stored.activeId : stored.tabs[0]?.id ?? null;
  });

  // Ref mirrors so stable callbacks always see the latest values.
  const activeRef = useRef(activeId);
  activeRef.current = activeId;

  const forceRender = useCallback(() => setSessionIds((ids) => [...ids]), []);

  const setConnState = useCallback(
    (session: TerminalSession, state: TerminalConnState) => {
      session.connState = state;
      session.cbs?.onStateChange?.(state);
      forceRender();
    },
    [forceRender],
  );

  const persistNow = useCallback(() => {
    const tabs = [...sessionsRef.current.values()]
      .filter((s) => s.agentId)
      .map((s) => ({ id: s.id, agentId: s.agentId }));
    persist(tabs, activeRef.current);
  }, []);

  const clearReconnectTimer = useCallback((session: TerminalSession) => {
    if (session.reconnectTimer) {
      clearTimeout(session.reconnectTimer);
      session.reconnectTimer = null;
    }
  }, []);

  // Refs break the openWs <-> scheduleReconnect mutual reference so both can
  // stay stable (empty-deps) without stale closures.
  const openWsRef = useRef<(s: TerminalSession) => void>(() => {});
  const scheduleReconnectRef = useRef<(s: TerminalSession) => void>(() => {});

  const scheduleReconnect = useCallback(
    (session: TerminalSession) => {
      clearReconnectTimer(session);
      if (session.exited) {
        setConnState(session, "disconnected");
        return;
      }
      if (session.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        // Give up auto-retry; the manual reconnect button takes over.
        setConnState(session, "disconnected");
        return;
      }
      const attempt = session.reconnectAttempts;
      session.reconnectAttempts += 1;
      // Distinguish an auto-retry after a drop from the initial connect so the
      // tab badge can surface "reconnecting" instead of a plain "connecting".
      setConnState(session, "reconnecting");
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** attempt,
        RECONNECT_MAX_MS,
      );
      session.reconnectTimer = setTimeout(() => {
        session.reconnectTimer = null;
        if (session.exited) return;
        openWsRef.current(session);
      }, delay);
    },
    [clearReconnectTimer, setConnState],
  );

  const openWs = useCallback(
    (session: TerminalSession) => {
      if (!session.agentId) {
        setConnState(session, "disconnected");
        return;
      }
      if (session.ws && session.ws.readyState < WebSocket.CLOSING) {
        try {
          session.ws.close();
        } catch {
          // ignore
        }
      }
      let ws: WebSocket;
      try {
        ws = new WebSocket(buildWsUrl(session.agentId, session.id));
      } catch (err) {
        console.error("[Terminal] Failed to create WebSocket:", err);
        setConnState(session, "error");
        scheduleReconnectRef.current(session);
        return;
      }
      setConnState(session, "connecting");

      // Guard against stale handlers. Closing the previous socket in a manual
      // reconnect fires its async `onclose` *after* `session.ws` already points
      // at this new socket; without this check that stale handler would null out
      // the live `session.ws` (breaking input) and schedule a bogus reconnect.
      const isStale = () => session.ws !== ws;

      ws.onopen = () => {
        if (isStale()) return;
        session.reconnectAttempts = 0;
        setConnState(session, "connected");
        // Sync the cached terminal size so the resumed PTY matches the display.
        if (session.pendingCols && session.pendingRows) {
          try {
            ws.send(
              JSON.stringify({
                type: "resize",
                cols: session.pendingCols,
                rows: session.pendingRows,
              }),
            );
          } catch {
            // ignore
          }
        }
      };

      ws.onmessage = (ev) => {
        if (isStale()) return;
        try {
          const msg = JSON.parse(ev.data as string) as {
            type: string;
            data?: string;
            code?: number;
            message?: string;
          };
          if (msg.type === "output" && msg.data !== undefined) {
            session.onOutput?.(msg.data);
          } else if (msg.type === "history" && msg.data !== undefined) {
            session.onHistory?.(msg.data);
          } else if (msg.type === "session") {
            // Server confirms the session_id (already matches) — no-op.
          } else if (msg.type === "exit") {
            session.exited = true;
            clearReconnectTimer(session);
            setConnState(session, "disconnected");
            session.onExit?.(msg.code ?? 0);
          } else if (msg.type === "error") {
            console.error("[Terminal] Server error:", msg.message);
            // Permanent server-side failure — stop the reconnect storm.
            session.exited = true;
            clearReconnectTimer(session);
            setConnState(session, "error");
            session.onExit?.(-1);
          }
        } catch {
          // Non-JSON frames — unlikely but ignore.
        }
      };

      ws.onerror = () => {
        if (isStale()) return;
        setConnState(session, "error");
      };

      ws.onclose = (ev) => {
        if (isStale()) return;
        session.ws = null;
        if (session.exited) {
          setConnState(session, "disconnected");
          return;
        }
        // Server permanent failures (auth / spawn / unsupported / capacity).
        // Stop the reconnect storm even if the error frame was missed.
        if (ev.code === 1011 || (ev.code >= 4000 && ev.code < 5000)) {
          session.exited = true;
          clearReconnectTimer(session);
          setConnState(session, "error");
          session.onExit?.(ev.code);
          return;
        }
        // Transient drop — auto-reconnect (capped). Manual button covers the rest.
        scheduleReconnectRef.current(session);
      };

      session.ws = ws;
      sessionsRef.current.set(session.id, session);
    },
    [setConnState, clearReconnectTimer],
  );

  openWsRef.current = openWs;
  scheduleReconnectRef.current = scheduleReconnect;

  const reconcileAgentIds = useCallback(
    (validIds: Iterable<string>, fallbackAgentId: string) => {
      const valid = new Set(validIds);
      validAgentIdsRef.current = valid;
      let changed = false;
      for (const session of sessionsRef.current.values()) {
        const next = pickAgentId(session, fallbackAgentId, valid);
        if (session.agentId !== next) {
          session.agentId = next;
          session.exited = false;
          session.reconnectAttempts = 0;
          clearReconnectTimer(session);
          if (session.ws) {
            try {
              session.ws.close();
            } catch {
              // ignore
            }
            session.ws = null;
          }
          changed = true;
        }
      }
      if (changed) {
        persistNow();
        forceRender();
        for (const session of sessionsRef.current.values()) {
          if (session.cbs && session.agentId) {
            openWsRef.current(session);
          }
        }
      }
    },
    [clearReconnectTimer, persistNow, forceRender],
  );

  const connect = useCallback(
    (id: string, agentId: string, cbs: TerminalCallbacks) => {
      const session = sessionsRef.current.get(id);
      if (!session) return;
      session.cbs = cbs;
      session.onOutput = cbs.onOutput;
      session.onHistory = cbs.onHistory;
      session.onExit = cbs.onExit;
      const valid = validAgentIdsRef.current;
      if (valid.size > 0) {
        session.agentId = pickAgentId(session, agentId, valid);
        if (!session.agentId) {
          setConnState(session, "disconnected");
          return;
        }
      } else {
        // Agents not loaded yet — prefer the live selection over stale storage.
        session.agentId = agentId || session.agentId;
        if (!session.agentId) {
          setConnState(session, "disconnected");
          return;
        }
      }
      session.exited = false;
      session.reconnectAttempts = 0;
      clearReconnectTimer(session);
      persistNow();
      openWs(session);
    },
    [clearReconnectTimer, persistNow, openWs, setConnState],
  );

  /** Manually (re)connect a session — immediate, resets the attempt counter. */
  const reconnect = useCallback(
    (id: string) => {
      const session = sessionsRef.current.get(id);
      if (!session || !session.agentId) return;
      session.exited = false;
      session.reconnectAttempts = 0;
      clearReconnectTimer(session);
      openWs(session);
    },
    [clearReconnectTimer, openWs],
  );

  const sendInput = useCallback((id: string, data: string) => {
    const session = sessionsRef.current.get(id);
    if (session?.ws?.readyState === WebSocket.OPEN) {
      try {
        session.ws.send(JSON.stringify({ type: "input", data }));
      } catch (err) {
        console.warn("[Terminal] Failed to send input:", err);
      }
    }
  }, []);

  const sendResize = useCallback((id: string, cols: number, rows: number) => {
    const session = sessionsRef.current.get(id);
    if (!session) return;
    // Always cache the latest dimensions — synced on (re)connect.
    session.pendingCols = cols;
    session.pendingRows = rows;
    const flushResize = () => {
      if (session.ws?.readyState === WebSocket.OPEN) {
        try {
          session.ws.send(
            JSON.stringify({
              type: "resize",
              cols: session.pendingCols,
              rows: session.pendingRows,
            }),
          );
        } catch {
          // ignore
        }
      }
    };
    if (session.ws?.readyState !== WebSocket.OPEN) {
      return;
    }
    const timers = resizeTimersRef.current;
    const existing = timers.get(id);
    if (existing) clearTimeout(existing);
    timers.set(
      id,
      setTimeout(() => {
        timers.delete(id);
        flushResize();
      }, RESIZE_DEBOUNCE_MS),
    );
  }, []);

  const createSession = useCallback(() => {
    const id = generateId();
    sessionsRef.current.set(id, {
      id,
      agentId: "",
      ws: null,
      connState: "connecting",
      exited: false,
      reconnectAttempts: 0,
      reconnectTimer: null,
    });
    setSessionIds((prev) => [...prev, id]);
    setActiveIdState(id);
    activeRef.current = id;
    return id;
  }, []);

  const closeSession = useCallback(
    (id: string) => {
      const session = sessionsRef.current.get(id);
      if (session) {
        // Mark exited so the close handler does not schedule a reconnect.
        session.exited = true;
        clearReconnectTimer(session);
        if (session.ws) {
          if (session.ws.readyState === WebSocket.OPEN) {
            try {
              // Ask the backend to reap the shell now (skip the grace window)
              // so closing a tab frees its session slot immediately.
              session.ws.send(JSON.stringify({ type: "close" }));
            } catch {
              // ignore
            }
          }
          try {
            session.ws.close();
          } catch {
            // ignore
          }
        }
      }
      sessionsRef.current.delete(id);
      setSessionIds((prev) => {
        const next = prev.filter((sid) => sid !== id);
        setActiveIdState((cur) =>
          cur === id ? (next.length > 0 ? next[next.length - 1] : null) : cur,
        );
        return next;
      });
      persistNow();
    },
    [clearReconnectTimer, persistNow],
  );

  const setActiveId = useCallback(
    (id: string | null) => {
      setActiveIdState(id);
      activeRef.current = id;
      persistNow();
    },
    [persistNow],
  );

  const getConnState = useCallback(
    (id: string): TerminalConnState =>
      sessionsRef.current.get(id)?.connState ?? "disconnected",
    [],
  );

  // Close every session on unmount.
  useEffect(() => {
    const sessions = sessionsRef.current;
    const resizeTimers = resizeTimersRef.current;
    return () => {
      resizeTimers.forEach((timer) => clearTimeout(timer));
      resizeTimers.clear();
      sessions.forEach((s) => {
        s.exited = true;
        clearReconnectTimer(s);
        try {
          s.ws?.close();
        } catch {
          // ignore
        }
      });
      sessions.clear();
    };
  }, [clearReconnectTimer]);

  return {
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
    getConnState,
  };
}
