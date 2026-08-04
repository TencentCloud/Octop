/**
 * Terminal session manager — process-scoped singleton.
 *
 * Workbench keep-alive and the chat dock both mount <TerminalPage>.
 * Sharing one Map of WebSocket sessions avoids dual PTYs and prevents
 * unmount of one surface from closing shells the other still needs.
 * Output is multi-cast to every registered UI listener.
 */
import { useCallback, useEffect, useSyncExternalStore } from "react";
import { getAuthToken } from "../../../api/request";

// ─── Types ────────────────────────────────────────────────────────────────────

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
  /** Live UI listeners (chat dock + workbench may both attach). */
  listeners: Set<TerminalCallbacks>;
  /**
   * Client-side scrollback for late joiners (second surface mounts while WS
   * is already up). Capped — not a full xterm buffer.
   */
  scrollback: string;
  /** Cached terminal dimensions, synced to the PTY on (re)connect. */
  pendingCols?: number;
  pendingRows?: number;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = "octop:terminal-sessions";
const STORAGE_VERSION = 1;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
const RESIZE_DEBOUNCE_MS = 150;
const SCROLLBACK_MAX_CHARS = 200_000;

interface StoredTab {
  id: string;
  agentId: string;
}

interface StoredState {
  version: number;
  tabs: StoredTab[];
  activeId: string | null;
}

// ─── Persistence ──────────────────────────────────────────────────────────────

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

function writePersist(tabs: StoredTab[], activeId: string | null) {
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
  // Same id re-attaches to the backend shell.
  params.set("session_id", sessionId);
  return `${base}?${params.toString()}`;
}

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

function emptySession(id: string, agentId = ""): TerminalSession {
  return {
    id,
    agentId,
    ws: null,
    connState: "connecting",
    exited: false,
    reconnectAttempts: 0,
    reconnectTimer: null,
    listeners: new Set(),
    scrollback: "",
  };
}

// ─── Module store ─────────────────────────────────────────────────────────────

const sessions = new Map<string, TerminalSession>();
const resizeTimers = new Map<string, ReturnType<typeof setTimeout>>();
const storeListeners = new Set<() => void>();
const validAgentIds = new Set<string>();

type Snapshot = { sessionIds: string[]; activeId: string | null };

let sessionIds: string[] = [];
let activeId: string | null = null;
let snapshot: Snapshot = { sessionIds: [], activeId: null };
let consumerCount = 0;
let hydrated = false;

function emitStore() {
  snapshot = { sessionIds: [...sessionIds], activeId };
  for (const l of storeListeners) l();
}

function subscribeStore(onChange: () => void): () => void {
  storeListeners.add(onChange);
  return () => {
    storeListeners.delete(onChange);
  };
}

function getStoreSnapshot(): Snapshot {
  return snapshot;
}

function persistNow() {
  const tabs = [...sessions.values()]
    .filter((s) => s.agentId)
    .map((s) => ({ id: s.id, agentId: s.agentId }));
  writePersist(tabs, activeId);
}

function clearReconnectTimer(session: TerminalSession) {
  if (session.reconnectTimer) {
    clearTimeout(session.reconnectTimer);
    session.reconnectTimer = null;
  }
}

function fanOut(
  session: TerminalSession,
  fn: (cbs: TerminalCallbacks) => void,
) {
  for (const cbs of session.listeners) {
    try {
      fn(cbs);
    } catch {
      // ignore listener errors
    }
  }
}

function setConnState(session: TerminalSession, state: TerminalConnState) {
  session.connState = state;
  fanOut(session, (cbs) => cbs.onStateChange?.(state));
  emitStore();
}

function appendScrollback(session: TerminalSession, data: string) {
  if (!data) return;
  const next = session.scrollback + data;
  session.scrollback =
    next.length > SCROLLBACK_MAX_CHARS
      ? next.slice(-SCROLLBACK_MAX_CHARS)
      : next;
}

function scheduleReconnect(session: TerminalSession) {
  clearReconnectTimer(session);
  if (session.exited) {
    setConnState(session, "disconnected");
    return;
  }
  if (session.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
    setConnState(session, "disconnected");
    return;
  }
  const attempt = session.reconnectAttempts;
  session.reconnectAttempts += 1;
  setConnState(session, "reconnecting");
  const delay = Math.min(RECONNECT_BASE_MS * 2 ** attempt, RECONNECT_MAX_MS);
  session.reconnectTimer = setTimeout(() => {
    session.reconnectTimer = null;
    if (session.exited) return;
    openWs(session);
  }, delay);
}

function openWs(session: TerminalSession) {
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
    scheduleReconnect(session);
    return;
  }
  setConnState(session, "connecting");

  const isStale = () => session.ws !== ws;

  ws.onopen = () => {
    if (isStale()) return;
    session.reconnectAttempts = 0;
    setConnState(session, "connected");
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
        appendScrollback(session, msg.data);
        fanOut(session, (cbs) => cbs.onOutput(msg.data as string));
      } else if (msg.type === "history" && msg.data !== undefined) {
        // Authoritative server replay — replace buffer, still cap for late joiners.
        session.scrollback = "";
        appendScrollback(session, msg.data);
        fanOut(session, (cbs) => cbs.onHistory?.(session.scrollback));
      } else if (msg.type === "session") {
        // Server confirms session_id — no-op.
      } else if (msg.type === "exit") {
        session.exited = true;
        clearReconnectTimer(session);
        setConnState(session, "disconnected");
        fanOut(session, (cbs) => cbs.onExit?.(msg.code ?? 0));
      } else if (msg.type === "error") {
        console.error("[Terminal] Server error:", msg.message);
        session.exited = true;
        clearReconnectTimer(session);
        setConnState(session, "error");
        fanOut(session, (cbs) => cbs.onExit?.(-1));
      }
    } catch {
      // Non-JSON — ignore.
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
    if (ev.code === 1011 || (ev.code >= 4000 && ev.code < 5000)) {
      session.exited = true;
      clearReconnectTimer(session);
      setConnState(session, "error");
      fanOut(session, (cbs) => cbs.onExit?.(ev.code));
      return;
    }
    scheduleReconnect(session);
  };

  session.ws = ws;
  sessions.set(session.id, session);
}

function ensureHydrated() {
  if (hydrated) return;
  hydrated = true;
  const stored = loadStored();
  if (stored?.tabs.length) {
    sessionIds = stored.tabs.map((t) => t.id);
    for (const tab of stored.tabs) {
      sessions.set(tab.id, emptySession(tab.id, tab.agentId));
    }
    const valid =
      stored.activeId && sessionIds.includes(stored.activeId)
        ? stored.activeId
        : sessionIds[0] ?? null;
    activeId = valid;
  }
  emitStore();
}

function softTeardownSockets() {
  resizeTimers.forEach((timer) => clearTimeout(timer));
  resizeTimers.clear();
  for (const s of sessions.values()) {
    clearReconnectTimer(s);
    s.listeners.clear();
    // Do not mark exited — allow re-attach when a surface remounts.
    try {
      s.ws?.close();
    } catch {
      // ignore
    }
    s.ws = null;
    s.connState = "disconnected";
    s.reconnectAttempts = 0;
  }
}

function acquireConsumer() {
  ensureHydrated();
  consumerCount += 1;
}

function releaseConsumer() {
  consumerCount = Math.max(0, consumerCount - 1);
  if (consumerCount > 0) return;
  // Last TerminalPage unmounted — close sockets, keep tab metadata for restore.
  softTeardownSockets();
  persistNow();
  emitStore();
}

// ─── Public API (module) ──────────────────────────────────────────────────────

function reconcileAgentIds(
  validIds: Iterable<string>,
  fallbackAgentId: string,
) {
  ensureHydrated();
  validAgentIds.clear();
  for (const id of validIds) validAgentIds.add(id);
  let changed = false;
  for (const session of sessions.values()) {
    const next = pickAgentId(session, fallbackAgentId, validAgentIds);
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
    emitStore();
    for (const session of sessions.values()) {
      if (session.listeners.size > 0 && session.agentId) {
        openWs(session);
      }
    }
  }
}

function connect(id: string, agentId: string, cbs: TerminalCallbacks) {
  ensureHydrated();
  const session = sessions.get(id);
  if (!session) return;

  session.listeners.add(cbs);

  if (validAgentIds.size > 0) {
    session.agentId = pickAgentId(session, agentId, validAgentIds);
    if (!session.agentId) {
      setConnState(session, "disconnected");
      return;
    }
  } else {
    session.agentId = agentId || session.agentId;
    if (!session.agentId) {
      setConnState(session, "disconnected");
      return;
    }
  }

  cbs.onStateChange?.(session.connState);

  // Late joiner: replay client scrollback without tearing down the live WS.
  if (
    session.ws &&
    session.ws.readyState < WebSocket.CLOSING &&
    session.scrollback
  ) {
    try {
      cbs.onHistory?.(session.scrollback);
    } catch {
      // ignore
    }
    return;
  }

  if (session.ws && session.ws.readyState < WebSocket.CLOSING) {
    return;
  }

  session.exited = false;
  session.reconnectAttempts = 0;
  clearReconnectTimer(session);
  persistNow();
  openWs(session);
}

/** Remove one UI listener; does not close the shared socket. */
function unbind(id: string, cbs: TerminalCallbacks) {
  const session = sessions.get(id);
  if (!session) return;
  session.listeners.delete(cbs);
}

function reconnect(id: string) {
  const session = sessions.get(id);
  if (!session || !session.agentId) return;
  session.exited = false;
  session.reconnectAttempts = 0;
  clearReconnectTimer(session);
  openWs(session);
}

function sendInput(id: string, data: string) {
  const session = sessions.get(id);
  if (session?.ws?.readyState === WebSocket.OPEN) {
    try {
      session.ws.send(JSON.stringify({ type: "input", data }));
    } catch (err) {
      console.warn("[Terminal] Failed to send input:", err);
    }
  }
}

function sendResize(id: string, cols: number, rows: number) {
  const session = sessions.get(id);
  if (!session) return;
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
  const existing = resizeTimers.get(id);
  if (existing) clearTimeout(existing);
  resizeTimers.set(
    id,
    setTimeout(() => {
      resizeTimers.delete(id);
      flushResize();
    }, RESIZE_DEBOUNCE_MS),
  );
}

function createSession(): string {
  ensureHydrated();
  const id = generateId();
  sessions.set(id, emptySession(id));
  sessionIds = [...sessionIds, id];
  activeId = id;
  emitStore();
  return id;
}

/**
 * Seed the first tab on first visible visit. Reads the live module store
 * (not a React closure) so chat-dock remounts / dual TerminalPage surfaces
 * cannot race-create extra sessions.
 */
function ensureDefaultSession(): void {
  ensureHydrated();
  if (sessionIds.length > 0) return;
  createSession();
}

function closeSession(id: string) {
  const session = sessions.get(id);
  if (session) {
    session.exited = true;
    clearReconnectTimer(session);
    session.listeners.clear();
    if (session.ws) {
      if (session.ws.readyState === WebSocket.OPEN) {
        try {
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
  sessions.delete(id);
  const timer = resizeTimers.get(id);
  if (timer) {
    clearTimeout(timer);
    resizeTimers.delete(id);
  }
  sessionIds = sessionIds.filter((sid) => sid !== id);
  if (activeId === id) {
    activeId =
      sessionIds.length > 0 ? sessionIds[sessionIds.length - 1]! : null;
  }
  persistNow();
  emitStore();
}

function setActiveId(id: string | null) {
  activeId = id;
  persistNow();
  emitStore();
}

function getConnState(id: string): TerminalConnState {
  return sessions.get(id)?.connState ?? "disconnected";
}

// ─── React hook ───────────────────────────────────────────────────────────────

/**
 * Manages multiple interactive terminal WebSocket sessions with persistence.
 * All hook instances share one process-scoped session store.
 */
export function useTerminal() {
  const snap = useSyncExternalStore(
    subscribeStore,
    getStoreSnapshot,
    getStoreSnapshot,
  );

  useEffect(() => {
    acquireConsumer();
    return () => {
      releaseConsumer();
    };
  }, []);

  return {
    sessionIds: snap.sessionIds,
    activeId: snap.activeId,
    setActiveId: useCallback((id: string | null) => setActiveId(id), []),
    createSession: useCallback(() => createSession(), []),
    ensureDefaultSession: useCallback(() => ensureDefaultSession(), []),
    reconcileAgentIds: useCallback(
      (validIds: Iterable<string>, fallbackAgentId: string) =>
        reconcileAgentIds(validIds, fallbackAgentId),
      [],
    ),
    connect: useCallback(
      (id: string, agentId: string, cbs: TerminalCallbacks) =>
        connect(id, agentId, cbs),
      [],
    ),
    unbind: useCallback(
      (id: string, cbs: TerminalCallbacks) => unbind(id, cbs),
      [],
    ),
    reconnect: useCallback((id: string) => reconnect(id), []),
    sendInput: useCallback(
      (id: string, data: string) => sendInput(id, data),
      [],
    ),
    sendResize: useCallback(
      (id: string, cols: number, rows: number) => sendResize(id, cols, rows),
      [],
    ),
    closeSession: useCallback((id: string) => closeSession(id), []),
    getConnState: useCallback((id: string) => getConnState(id), []),
  };
}

/**
 * Vitest-only store controls. Application code must use ``useTerminal()``.
 * Prefer importing via ``./useTerminal.testUtils``.
 */
export const terminalStoreTestApi = {
  reset(): void {
    resizeTimers.forEach((timer) => clearTimeout(timer));
    resizeTimers.clear();
    for (const s of sessions.values()) {
      clearReconnectTimer(s);
      s.listeners.clear();
      try {
        s.ws?.close();
      } catch {
        // ignore
      }
    }
    sessions.clear();
    sessionIds = [];
    activeId = null;
    consumerCount = 0;
    hydrated = false;
    validAgentIds.clear();
    emitStore();
  },
  createSession,
  ensureDefaultSession,
  getSessionIds(): string[] {
    ensureHydrated();
    return [...sessionIds];
  },
};
