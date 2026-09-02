import { useCallback, useEffect, useState } from "react";
import {
  trajectoryApi,
  type TrajectoryEvent,
} from "../../../api/modules/trajectory";

interface UseTrajectorySessionOptions {
  agentId?: string;
  threadId?: string | null;
  visible?: boolean;
}

interface TrajectorySessionState {
  events: TrajectoryEvent[];
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

export function useTrajectorySession({
  agentId,
  threadId,
  visible = true,
}: UseTrajectorySessionOptions): TrajectorySessionState {
  const [events, setEvents] = useState<TrajectoryEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [nextBeforeSeq, setNextBeforeSeq] = useState<number | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  const retry = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  const refresh = useCallback(() => {
    setEvents([]);
    setHasMore(false);
    setNextBeforeSeq(null);
    setReloadToken((token) => token + 1);
  }, []);

  const loadEarlier = useCallback(async () => {
    if (!agentId || !threadId || nextBeforeSeq == null) return;

    const page = await trajectoryApi.history(agentId, threadId, {
      beforeSeq: nextBeforeSeq,
    });
    setHasMore(page.has_more);
    setNextBeforeSeq(page.next_before_seq);
    setEvents((prev) => {
      const seen = new Set(prev.map((row) => row.event_id));
      const older = page.events.filter((row) => !seen.has(row.event_id));
      return [...older, ...prev];
    });
  }, [agentId, threadId, nextBeforeSeq]);

  useEffect(() => {
    setEvents([]);
    setError(false);
    setHasMore(false);
    setNextBeforeSeq(null);
  }, [agentId, threadId]);

  useEffect(() => {
    if (!visible || !agentId || !threadId) return;

    let cancelled = false;
    let source: EventSource | null = null;

    const openStream = (afterSeq?: number) => {
      if (cancelled) return;
      source = new EventSource(
        trajectoryApi.streamUrl(agentId, threadId, afterSeq),
      );
      source.addEventListener("event", (raw) => {
        const message = raw as MessageEvent<string>;
        let parsed: unknown;
        try {
          parsed = JSON.parse(message.data);
        } catch {
          return;
        }
        if (!isTrajectoryEvent(parsed)) return;
        const incoming = parsed;
        setEvents((prev) => {
          if (prev.some((row) => row.event_id === incoming.event_id)) {
            return prev;
          }
          return [...prev, incoming];
        });
      });
    };

    setLoading(true);
    setError(false);
    void trajectoryApi
      .history(agentId, threadId)
      .then((page) => {
        if (cancelled) return;
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

  return { events, loading, error, hasMore, retry, loadEarlier, refresh };
}
