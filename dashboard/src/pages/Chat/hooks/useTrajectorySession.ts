import { useCallback, useEffect, useRef, useState } from "react";
import {
  trajectoryApi,
  type TrajectoryEvent,
  type TrajectoryMetrics,
} from "../../../api/modules/trajectory";

interface UseTrajectorySessionOptions {
  agentId?: string;
  threadId?: string | null;
  visible?: boolean;
}

interface TrajectorySessionState {
  events: TrajectoryEvent[];
  metrics: TrajectoryMetrics | null;
  loading: boolean;
  error: boolean;
  hasMore: boolean;
  retry: () => void;
  loadEarlier: () => Promise<void>;
  refresh: () => void;
}

function isTrajectoryEvent(value: unknown): value is TrajectoryEvent {
  if (value == null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.event_id === "string" && typeof record.kind === "string";
}

function isTrajectoryMetrics(value: unknown): value is TrajectoryMetrics {
  if (value == null || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return typeof record.turns === "number" && typeof record.steps === "number";
}

function parseSseData(raw: MessageEvent<string>): unknown {
  try {
    return JSON.parse(raw.data);
  } catch {
    return undefined;
  }
}

function upsertByEventId(
  prev: TrajectoryEvent[],
  incoming: TrajectoryEvent,
): TrajectoryEvent[] {
  const index = prev.findIndex((row) => row.event_id === incoming.event_id);
  if (index === -1) return [...prev, incoming];
  const next = prev.slice();
  next[index] = incoming;
  return next;
}

export function useTrajectorySession({
  agentId,
  threadId,
  visible = true,
}: UseTrajectorySessionOptions): TrajectorySessionState {
  const [events, setEvents] = useState<TrajectoryEvent[]>([]);
  const [metrics, setMetrics] = useState<TrajectoryMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextBeforeSeq, setNextBeforeSeq] = useState<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const sessionGenRef = useRef(0);
  const loadEarlierLockRef = useRef(false);
  const lastSeqRef = useRef<number | undefined>(undefined);

  const retry = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  const refresh = useCallback(() => {
    sessionGenRef.current += 1;
    setEvents([]);
    setMetrics(null);
    setHasMore(false);
    setNextBeforeSeq(null);
    setReloadToken((token) => token + 1);
  }, []);

  const loadEarlier = useCallback(async () => {
    if (!agentId || !threadId || nextBeforeSeq == null) return;
    if (loadEarlierLockRef.current) return;

    loadEarlierLockRef.current = true;
    const loadGen = sessionGenRef.current;
    try {
      const page = await trajectoryApi.history(agentId, threadId, {
        beforeSeq: nextBeforeSeq,
      });
      if (loadGen !== sessionGenRef.current) return;

      setHasMore(page.has_more);
      setNextBeforeSeq(page.next_before_seq);
      setEvents((prev) => {
        const seen = new Set(prev.map((row) => row.event_id));
        const older = page.events.filter((row) => !seen.has(row.event_id));
        return [...older, ...prev];
      });
    } catch {
      /* Keep the already-loaded page; caller can retry. */
    } finally {
      loadEarlierLockRef.current = false;
    }
  }, [agentId, threadId, nextBeforeSeq]);

  useEffect(() => {
    sessionGenRef.current += 1;
    setEvents([]);
    setMetrics(null);
    setError(false);
    setHasMore(false);
    setNextBeforeSeq(null);
    lastSeqRef.current = undefined;
  }, [agentId, threadId]);

  useEffect(() => {
    if (!visible || !agentId || !threadId) return;

    sessionGenRef.current += 1;
    const fetchGen = sessionGenRef.current;
    let cancelled = false;
    let source: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;

    const bindSource = (es: EventSource) => {
      es.addEventListener("event", (raw) => {
        const parsed = parseSseData(raw as MessageEvent<string>);
        if (!isTrajectoryEvent(parsed)) return;
        lastSeqRef.current = parsed.seq;
        setEvents((prev) => upsertByEventId(prev, parsed));
      });
      es.addEventListener("metrics", (raw) => {
        const parsed = parseSseData(raw as MessageEvent<string>);
        if (!isTrajectoryMetrics(parsed)) return;
        setMetrics(parsed);
      });
      es.onerror = () => {
        es.close();
        if (cancelled || fetchGen !== sessionGenRef.current) return;
        const delay =
          reconnectAttempt === 0
            ? 0
            : Math.min(1000 * 2 ** reconnectAttempt, 15_000);
        reconnectAttempt += 1;
        reconnectTimer = setTimeout(() => {
          if (cancelled || fetchGen !== sessionGenRef.current) return;
          openStream(lastSeqRef.current);
        }, delay);
      };
    };

    const openStream = (afterSeq?: number) => {
      if (cancelled) return;
      source?.close();
      source = new EventSource(
        trajectoryApi.streamUrl(agentId, threadId, afterSeq),
      );
      bindSource(source);
    };

    setLoading(true);
    setError(false);
    void trajectoryApi
      .history(agentId, threadId)
      .then(async (page) => {
        if (cancelled || fetchGen !== sessionGenRef.current) return;
        setEvents(page.events);
        setHasMore(page.has_more);
        setNextBeforeSeq(page.next_before_seq);
        const lastSeq = page.events[page.events.length - 1]?.seq;
        lastSeqRef.current = lastSeq;
        try {
          const snapshot = await trajectoryApi.metrics(agentId, threadId);
          if (!cancelled && fetchGen === sessionGenRef.current) {
            setMetrics(snapshot);
          }
        } catch {
          /* Live SSE metrics remain the primary source. */
        }
        openStream(lastSeq);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      if (reconnectTimer != null) clearTimeout(reconnectTimer);
      source?.close();
    };
  }, [visible, agentId, threadId, reloadToken]);

  return {
    events,
    metrics,
    loading,
    error,
    hasMore,
    retry,
    loadEarlier,
    refresh,
  };
}
