import { useCallback, useEffect, useMemo, useState } from "react";
import {
  octopThreadsApi,
  type ThreadSummaryRow,
} from "../../../api/modules/octopThreads";
import { onSessionEvent } from "./chatStore";
import { sortSessions, toSession, type Session } from "./useSessions";

/** One agent bucket of the cross-agent inbox (PLAN §8.1). */
export interface InboxAgentRow {
  agentId: string;
  sessionCount: number;
  hasActivity: boolean;
  lastActive: number;
  /** This agent's pinned sessions, already mapped through ``toSession``. */
  pinned: Session[];
}

export type InboxByAgent = Record<string, InboxAgentRow>;

/** Public contract returned by ``useSessionInbox`` (PLAN §8.1). */
export interface SessionInbox {
  inboxByAgent: InboxByAgent;
  /** Pinned rows across every agent, in ``sortSessions`` order. */
  pinnedSessions: Session[];
  patchSession: (threadId: string, patch: Partial<Session>) => void;
}

/**
 * Module-level snapshot keyed by ``agentKey``.
 *
 * A ``useRef`` is not enough: React 18 StrictMode mounts, unmounts and
 * remounts the component, which resets refs — the in-flight promise and the
 * result cache must outlive the mount so the aggregate request is sent
 * exactly once. ``agentKey`` unchanged ⇒ never re-request.
 */
let _cacheKey: string | null = null;
let _cache: ThreadSummaryRow[] | null = null;
let _inflightKey: string | null = null;
let _inflight: Promise<ThreadSummaryRow[]> | null = null;

/** Reset the module inbox snapshot between vitest cases. */
export function resetSessionInboxForTests() {
  _cacheKey = null;
  _cache = null;
  _inflightKey = null;
  _inflight = null;
}

/**
 * Load the inbox snapshot for ``key``, deduplicating by module-level state.
 *
 * Returns the cached rows when the key is unchanged, otherwise joins the
 * in-flight request (StrictMode remount) or starts exactly one new request.
 * ``force`` is reserved for the user-triggered refresh (S-10).
 */
export function loadSessionInbox(
  key: string,
  options: { force?: boolean } = {},
): Promise<ThreadSummaryRow[]> {
  const force = options.force === true;
  if (!force && _cacheKey === key && _cache) {
    return Promise.resolve(_cache);
  }
  if (!force && _inflight && _inflightKey === key) {
    return _inflight;
  }
  const request = octopThreadsApi.summary().then(
    (rows) => {
      _cacheKey = key;
      _cache = rows;
      if (_inflight === request) {
        _inflight = null;
        _inflightKey = null;
      }
      return rows;
    },
    (error: unknown) => {
      if (_inflight === request) {
        _inflight = null;
        _inflightKey = null;
      }
      throw error;
    },
  );
  _inflight = request;
  _inflightKey = key;
  return request;
}

/** Drop one thread from every agent bucket (``sessionDeleted``). */
function removeThread(rows: ThreadSummaryRow[], threadId: string) {
  return rows.map((row) => {
    const pinned = row.pinned.filter((p) => p.thread_id !== threadId);
    if (pinned.length === row.pinned.length) return row;
    return {
      ...row,
      session_count: Math.max(0, row.session_count - 1),
      pinned,
    };
  });
}

/**
 * Patch the inbox snapshot locally after a pin/rename. The pinned segment is a
 * page-entry snapshot (S-10), so pinning a thread that is not already in the
 * snapshot does not synthesise a row — the manual refresh does that.
 */
function patchRows(
  rows: ThreadSummaryRow[],
  threadId: string,
  patch: Partial<Session>,
) {
  let changed = false;
  const next = rows.map((row) => {
    if (!row.pinned.some((p) => p.thread_id === threadId)) return row;
    // Unpinning removes the row from the snapshot's pinned list.
    if (patch.pinned === false) {
      changed = true;
      return {
        ...row,
        session_count: Math.max(0, row.session_count - 1),
        pinned: row.pinned.filter((p) => p.thread_id !== threadId),
      };
    }
    const pinned = row.pinned.map((p) => {
      if (p.thread_id !== threadId) return p;
      const updated = { ...p };
      if (patch.pinned === true) updated.pinned = true;
      if (patch.name !== undefined) updated.title = patch.name;
      changed = true;
      return updated;
    });
    return { ...row, pinned };
  });
  return changed ? next : rows;
}

/**
 * Cross-agent inbox for the chat sidebar (T0.2).
 *
 * ``agentKey`` is the inbox *scope* key (``user:<id>`` / ``anon``), not an
 * agent id — switching agents must not change it and must not re-request.
 *
 * Single-source rules (PLAN §6):
 * - agent buckets consume the server's ``has_activity`` verbatim;
 * - session rows go through ``toSession()``, which owns the ``hasActivity``
 *   formula. This hook never recomputes either value.
 */
export function useSessionInbox(agentKey: string): SessionInbox & {
  refresh: () => void;
  loading: boolean;
} {
  const [rows, setRows] = useState<ThreadSummaryRow[]>(() =>
    _cacheKey === agentKey && _cache ? _cache : [],
  );
  const [loading, setLoading] = useState(
    () => !(_cacheKey === agentKey && _cache),
  );

  // Page-entry snapshot: ``agentKey`` is the only dependency, so switching
  // agents / sections / search never re-sends the aggregate request.
  useEffect(() => {
    if (!agentKey) {
      setRows([]);
      setLoading(false);
      return;
    }
    const cached = _cacheKey === agentKey ? _cache : null;
    if (cached) {
      setRows(cached);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void loadSessionInbox(agentKey).then(
      (next) => {
        if (cancelled) return;
        setRows(next);
        setLoading(false);
      },
      () => {
        if (cancelled) return;
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [agentKey]);

  useEffect(
    () =>
      onSessionEvent((event) => {
        if (event.kind !== "sessionDeleted") return;
        setRows((prev) => removeThread(prev, event.sessionId));
      }),
    [],
  );

  const refresh = useCallback(() => {
    if (!agentKey) return;
    setLoading(true);
    void loadSessionInbox(agentKey, { force: true }).then(
      (next) => {
        setRows(next);
        setLoading(false);
      },
      () => setLoading(false),
    );
  }, [agentKey]);

  const patchSession = useCallback(
    (threadId: string, patch: Partial<Session>) => {
      if (!threadId) return;
      setRows((prev) => patchRows(prev, threadId, patch));
    },
    [],
  );

  const inboxByAgent = useMemo<InboxByAgent>(() => {
    const next: InboxByAgent = {};
    for (const row of rows) {
      next[row.agent_id] = {
        agentId: row.agent_id,
        sessionCount: row.session_count,
        hasActivity: row.has_activity,
        lastActive: row.last_active,
        pinned: sortSessions(row.pinned.map((p) => toSession(p))),
      };
    }
    return next;
  }, [rows]);

  const pinnedSessions = useMemo(
    () =>
      sortSessions(rows.flatMap((row) => row.pinned.map((p) => toSession(p)))),
    [rows],
  );

  return { inboxByAgent, pinnedSessions, patchSession, refresh, loading };
}
