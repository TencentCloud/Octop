import { useState, useEffect, useRef, useCallback } from "react";
import api from "../api";
import { getWsUrl } from "../api/config";
import { getAuthToken } from "../api/request";
import type { BrowserSession, DisplayEnvironment } from "../api/types/browser";
import { DEFAULT_BROWSER_PROFILE } from "../utils/browserProfile";

/**
 * Session update event pushed over WebSocket from the backend.
 */
interface SessionUpdateEvent {
  type: "session_update";
  session_id: string;
  conversation_id: string;
  state: string;
  control_owner: "agent" | "user";
  current_url: string;
  channel_source: string;
}

export interface BrowserSessionState {
  /** The session bound to the current conversation (if any). */
  session: BrowserSession | null;
  /** Shorthand for session.session_id. */
  sessionId: string | null;
  /** Current session state (idle, awaiting_user_auth, etc.). */
  state: string;
  /** Who has control — agent or user. */
  controlOwner: "agent" | "user";
  /** The page URL the browser is currently on. */
  currentUrl: string;
  /** Desktop or headless-server. */
  environment: DisplayEnvironment;
  /** Whether the WebSocket is connected and receiving events. */
  isConnected: boolean;
  /** Force a one-shot HTTP refresh (e.g. after WS reconnect). */
  refresh: () => Promise<void>;
}

/**
 * Unified hook for tracking browser session state.
 *
 * - On mount, makes a single HTTP GET to seed state.
 * - Opens a lightweight WebSocket to `/browser-stream/ws` to receive
 *   `session_update` events in real-time.
 * - When `conversationId` changes, re-fetches via HTTP.
 * - Auto-reconnects on WS disconnect with exponential backoff.
 *
 * Pass `enabled: false` to disable all activity (no HTTP fetch, no WS
 * connection).  This lets callers unconditionally invoke the hook while
 * respecting a feature flag without violating the Rules of Hooks.
 *
 * This replaces the 3–5 s polling in Chat, BrowserWorkspace, and
 * RemoteBrowser pages.
 */
export function useBrowserSessionState(
  conversationId?: string,
  enabled = true,
): BrowserSessionState {
  const [session, setSession] = useState<BrowserSession | null>(null);
  const [environment, setEnvironment] =
    useState<DisplayEnvironment>("headless-server");
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttempt = useRef(0);
  const unmountedRef = useRef(false);
  const conversationIdRef = useRef(conversationId);
  conversationIdRef.current = conversationId;

  // ── HTTP fetch (initial + fallback) ──────────────────────────────────

  const fetchSessions = useCallback(async () => {
    try {
      const resp = await api.getSessions(conversationIdRef.current);
      if (unmountedRef.current) return;
      if (resp.ok) {
        setEnvironment(resp.environment);
        if (resp.sessions.length > 0) {
          const sorted = [...resp.sessions].sort(
            (a, b) => (b.last_activity_at ?? 0) - (a.last_activity_at ?? 0),
          );
          setSession(sorted[0]);
        } else {
          setSession(null);
        }
      }
    } catch {
      // harness-browser may be unavailable — ignore
    }
  }, []);

  // ── WebSocket connection ─────────────────────────────────────────────

  const connectWsRef = useRef<() => void>(() => {});

  const scheduleReconnect = useCallback(() => {
    if (unmountedRef.current) return;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempt.current), 16000);
    reconnectAttempt.current += 1;
    reconnectTimer.current = setTimeout(() => connectWsRef.current(), delay);
  }, []);

  const connectWs = useCallback(() => {
    if (unmountedRef.current) return;

    // Clean up any previous connection
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }

    const token = getAuthToken();
    const params = new URLSearchParams({
      width: "1",
      height: "1",
      listen_only: "1",
    });
    if (token) params.set("token", token);
    const wsUrl = `${getWsUrl("/browser-stream/ws")}?${params.toString()}`;

    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl);
    } catch {
      // Schedule reconnect
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      if (unmountedRef.current) {
        ws.close();
        return;
      }
      setIsConnected(true);
      reconnectAttempt.current = 0;
      // Compensate: fetch once after reconnect to cover missed events
      fetchSessions();
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as SessionUpdateEvent & {
          type: string;
        };
        if (msg.type === "session_update") {
          // Only apply updates for the current conversation
          const cid = conversationIdRef.current;
          if (!cid || msg.conversation_id === cid) {
            setSession((prev) => {
              if (!prev) {
                // No session yet — bootstrap one from the WS event so the
                // browser icon lights up immediately without waiting for the
                // HTTP fetch to complete.
                return {
                  session_id: msg.session_id,
                  profile_name: DEFAULT_BROWSER_PROFILE,
                  conversation_id: msg.conversation_id,
                  channel_source: msg.channel_source,
                  state: msg.state,
                  control_owner: msg.control_owner,
                  current_url: msg.current_url,
                  created_at: Date.now(),
                  last_activity_at: Date.now(),
                };
              }
              if (prev.session_id === msg.session_id) {
                // Update the existing session in-place
                return {
                  ...prev,
                  state: msg.state,
                  control_owner: msg.control_owner,
                  current_url: msg.current_url,
                };
              }
              return prev;
            });
          }
        }
        // Ignore other message types (frame, status, tabs, ping, etc.)
      } catch {
        // Non-JSON or irrelevant — ignore
      }
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (!unmountedRef.current) {
        scheduleReconnect();
      }
    };

    wsRef.current = ws;
  }, [fetchSessions, scheduleReconnect]);

  useEffect(() => {
    connectWsRef.current = connectWs;
  }, [connectWs]);

  // ── Lifecycle ────────────────────────────────────────────────────────

  // Initial HTTP fetch + WS connect
  useEffect(() => {
    if (!enabled) return;
    unmountedRef.current = false;
    fetchSessions();
    connectWs();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        try {
          wsRef.current.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
    };
  }, [enabled, fetchSessions, connectWs]);

  // Re-fetch when conversationId changes
  useEffect(() => {
    if (!enabled) return;
    fetchSessions();
  }, [enabled, conversationId, fetchSessions]);

  return {
    session,
    sessionId: session?.session_id ?? null,
    state: session?.state ?? "idle",
    controlOwner: session?.control_owner ?? "agent",
    currentUrl: session?.current_url ?? "",
    environment,
    isConnected,
    refresh: fetchSessions,
  };
}
