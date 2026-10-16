/**
 * useListOrder - manual sidebar ordering + pinning for experts / teams.
 *
 * The source of truth is the per-user backend table ``user_agent_prefs``
 * (schema v21, cross-device). The hook derives its ``state`` from the
 * ``AgentContext`` agents (which carry ``pinned`` / ``sort_order`` once
 * loaded) and routes every mutation through the context actions
 * (``pinAgent`` / ``reorderAgents`` → ``POST /agents/{id}/pin`` +
 * ``PUT /agents/order``).
 *
 * No local mirror: localStorage is **not** a source of truth here — keeping
 * one would let an offline tab drift out of sync with the server and the
 * two copies could never be reconciled deterministically. Before agents have
 * loaded, the derived state is intentionally empty so the sidebar falls back
 * to its default ordering rather than presenting stale local data as truth.
 */

import { useCallback, useMemo } from "react";
import { useAgent } from "../context/AgentContext";
import type { OctopAgent } from "../context/AgentContext";
import {
  EMPTY_LIST_ORDER,
  togglePinned,
  type ListOrderState,
} from "../utils/listOrder";

/**
 * Derive the ``{pinned, order}`` view state from the loaded agents.
 *
 * - ``pinned``: agent_ids whose server flag is true (membership list).
 * - ``order``: only the manually-ordered agents (``sort_order >= 0``),
 *   ascending — items with ``sort_order == -1`` are left out so
 *   ``applyListOrder`` keeps them in default position (backend "no backfill"
 *   semantics: a fresh upgrade shows the exact pre-upgrade order).
 *
 * Bridge shadow agents (no ``pinned`` / ``sort_order``) fall through to the
 * default tail, matching their server-side treatment.
 */
export function deriveListOrderFromAgents(
  agents: readonly OctopAgent[],
): ListOrderState {
  const pinned: string[] = [];
  for (const a of agents) if (a.pinned) pinned.push(a.agent_id);
  const order = agents
    .filter((a) => (a.sort_order ?? -1) >= 0)
    .sort((x, y) => (x.sort_order ?? 0) - (y.sort_order ?? 0))
    .map((a) => a.agent_id);
  return { pinned, order };
}

export interface UseListOrder {
  /** Current server-derived order state (empty before agents load). */
  state: ListOrderState;
  /** True until the backend list has been fetched at least once. */
  loading: boolean;
  /** Whether a pending mutation is in flight (optimistic, not yet confirmed). */
  pending: boolean;
  /**
   * Persist a full manual sequence (drag & drop / move up / down).
   * Propagates the underlying failure so the caller can surface it —
   * the context rolls back the optimistic patch on rejection.
   */
  write: (next: ListOrderState) => Promise<void>;
  /**
   * Flip the pin membership of one agent. Propagates the underlying failure
   * so the caller can surface it.
   */
  togglePin: (id: string) => Promise<void>;
}

/**
 * State + mutators for the current user's manual list order.
 *
 * All mutations are optimistically applied by the context (which patches the
 * live ``agents`` list) and persisted through the backend; on failure the
 * context re-syncs from the server, so the UI never lingers on a fake
 * arrangement. The hook itself holds no state — it just projects the live
 * agents into a ``{pinned, order}`` shape.
 */
export function useListOrder(): UseListOrder {
  const { agents, loading, pinAgent, reorderAgents } = useAgent();

  const state = useMemo<ListOrderState>(
    () => (agents.length > 0 ? deriveListOrderFromAgents(agents) : EMPTY_LIST_ORDER),
    [agents],
  );

  const write = useCallback(
    async (next: ListOrderState) => {
      // Reorder only when there is an actual manual sequence to send; a
      // fully-default list (no pinned / no order) carries nothing to persist.
      if (next.order.length === 0) return;
      await reorderAgents(next.order);
    },
    [reorderAgents],
  );

  const togglePin = useCallback(
    async (id: string) => {
      const nextPinned = togglePinned(state.pinned, id);
      await pinAgent(id, nextPinned.includes(id));
    },
    [state, pinAgent],
  );

  return { state, loading, pending: false, write, togglePin };
}
