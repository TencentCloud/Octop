/**
 * useListOrder - per-user localStorage persistence for manual sidebar
 * ordering + pinning of experts / expert teams.
 *
 * Mirrors the hiddenExpertsPrefs pattern: key is namespaced per user so two
 * accounts on the same browser don't share arrangements. An all-empty state
 * removes the key entirely (most users never touch this feature).
 */

import { useCallback, useEffect, useState } from "react";
import { useCurrentUser } from "./useCurrentUser";
import {
  EMPTY_LIST_ORDER,
  parseListOrder,
  togglePinned,
  type ListOrderState,
} from "../utils/listOrder";

export const SIDEBAR_AGENT_ORDER_STORAGE_KEY = "octop:sidebar-agent-order";

export function sidebarAgentOrderStorageKey(userId?: number | null): string {
  return userId == null || userId <= 0
    ? SIDEBAR_AGENT_ORDER_STORAGE_KEY
    : `${SIDEBAR_AGENT_ORDER_STORAGE_KEY}:${userId}`;
}

export function readListOrder(userId?: number | null): ListOrderState {
  try {
    return parseListOrder(
      localStorage.getItem(sidebarAgentOrderStorageKey(userId)),
    );
  } catch {
    return { ...EMPTY_LIST_ORDER };
  }
}

export function writeListOrder(
  state: ListOrderState,
  userId?: number | null,
): void {
  try {
    const key = sidebarAgentOrderStorageKey(userId);
    if (state.pinned.length === 0 && state.order.length === 0) {
      localStorage.removeItem(key);
      return;
    }
    localStorage.setItem(
      key,
      JSON.stringify({ pinned: state.pinned, order: state.order }),
    );
  } catch {
    // quota / private mode — ordering simply won't persist
  }
}

/**
 * State + mutators for the current user's manual list order.
 *
 * - ``move(id, delta)``: menu 上移/下移 (clamped by caller via canMove).
 * - ``relocate(id, targetId, placement)``: drag & drop.
 * - ``togglePin(id)``: pin/unpin membership.
 * - ``applyOrder(items, getId)``: convenience wrapper over applyListOrder.
 */
export function useListOrder() {
  const userId = useCurrentUser()?.id ?? null;
  const [state, setState] = useState<ListOrderState>(() =>
    readListOrder(userId),
  );

  useEffect(() => {
    setState(readListOrder(userId));
  }, [userId]);

  const commit = useCallback(
    (next: ListOrderState) => {
      writeListOrder(next, userId);
      setState(next);
    },
    [userId],
  );

  const move = useCallback(
    (seq: string[], id: string, delta: number) => {
      const from = seq.indexOf(id);
      if (from < 0) return;
      const to = from + delta;
      if (to < 0 || to >= seq.length) return;
      const next = [...seq];
      next.splice(from, 1);
      next.splice(to, 0, id);
      commit({ ...state, order: next });
    },
    [commit, state],
  );

  const relocate = useCallback(
    (seq: string[], id: string, targetId: string, placement: "before" | "after") => {
      if (id === targetId) return;
      const from = seq.indexOf(id);
      if (from < 0) return;
      const next = seq.filter((_, i) => i !== from);
      let to = next.indexOf(targetId);
      if (to < 0) return;
      if (placement === "after") to += 1;
      next.splice(to, 0, id);
      commit({ ...state, order: next });
    },
    [commit, state],
  );

  const togglePin = useCallback(
    (id: string) => {
      commit({ ...state, pinned: togglePinned(state.pinned, id) });
    },
    [commit, state],
  );

  return {
    state,
    move,
    relocate,
    togglePin,
    write: commit,
  };
}
