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

    const loadGen = sessionGenRef.current;
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
  }, [agentId, threadId, nextBeforeSeq]);

  useEffect(() => {
    sessionGenRef.current += 1;
    setEvents([]);
    setMetrics(null);
    setError(false);
    setHasMore(false);
    setNextBeforeSeq(null);
  }, [agentId, threadId]);

  useEffect(() => {
    if (!visible || !agentId || !threadId) return;

    sessionGenRef.current += 1;
    const fetchGen = sessionGenRef.current;
    let cancelled = false;
    let source: EventSource | null = null;

    const openStream = (afterSeq?: number) => {
      if (cancelled) return;
      source = new EventSource(
        trajectoryApi.streamUrl(agentId, threadId, afterSeq),
      );
      source.addEventListener("event", (raw) => {
        const parsed = parseSseData(raw as MessageEvent<string>);
        if (!isTrajectoryEvent(parsed)) return;
        setEvents((prev) => upsertByEventId(prev, parsed));
      });
      source.addEventListener("metrics", (raw) => {
        const parsed = parseSseData(raw as MessageEvent<string>);
        if (!isTrajectoryMetrics(parsed)) return;
        setMetrics(parsed);
      });
    };

    setLoading(true);
    setError(false);
    void trajectoryApi
      .history(agentId, threadId)
      .then((page) => {
        if (cancelled || fetchGen !== sessionGenRef.current) return;
        setEvents(page.events);
        setHasMore(page.has_more);
        setNextBeforeSeq(page.next_before_seq);
        const lastSeq = page.events[page.events.length - 1]?.seq;
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
