/**
 * Bootstrap a dashboard thread for an agent and wire it to the shared chat store.
 * Used by Terminal AI and other embedded chat surfaces (same path as /chat).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { octopThreadsApi, type OctopThread } from "../api/modules/octopThreads";
import { useChat } from "../pages/Chat/hooks/useChat";
import {
  pickPreferredSession,
  toSession,
} from "../pages/Chat/hooks/useSessions";

/**
 * @param options.hitlMode
 *   `ask`        该会话的工具执行需人工审批（云服务器运维专家用）
 *   `allow_all`  默认；嵌入式面板没有审批 UI，必须放行，否则工具会永久挂起
 */
function readSurfaceThread(pinKey: string, agentId: string): string | null {
  try {
    const raw = localStorage.getItem(pinKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    const id = (parsed as Record<string, unknown>)[agentId];
    return typeof id === "string" && id ? id : null;
  } catch {
    return null;
  }
}

function writeSurfaceThread(pinKey: string, agentId: string, threadId: string) {
  try {
    const raw = localStorage.getItem(pinKey);
    const parsed = raw ? (JSON.parse(raw) as unknown) : {};
    const next =
      parsed && typeof parsed === "object" ? { ...(parsed as object) } : {};
    (next as Record<string, string>)[agentId] = threadId;
    localStorage.setItem(pinKey, JSON.stringify(next));
  } catch {
    /* 隐私模式等写不进去时，这次会话仍然可用 */
  }
}

export function useAgentThreadChat(
  agentId: string | null,
  options: {
    hitlMode?: "ask" | "allow_all";
    /**
     * 这个面板自己的会话记忆。设置后不调用 rebind，
     * 避免改掉该专家在对话页或其他页签上的当前会话。
     */
    pinKey?: string;
  } = {},
) {
  const hitlMode = options.hitlMode ?? "allow_all";
  const pinKey = options.pinKey;
  const [threadId, setThreadId] = useState<string | null>(null);
  const [threads, setThreads] = useState<OctopThread[]>([]);
  const [booting, setBooting] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  /** Bumped by ``reload``: re-runs the boot effect after a failure. */
  const [bootNonce, setBootNonce] = useState(0);
  /** Thread the user explicitly picked; boot must not override it. */
  const pinnedRef = useRef<string | null>(null);
  const lastAgentRef = useRef<string | null>(null);
  const lastPinRef = useRef<string | null>(null);
  /**
   * Thread id that belongs to the current agent + pin. Until boot adopts one,
   * the shared chat store must not keep showing the previous expert's thread.
   */
  const boundRef = useRef<{
    agentId: string | null;
    pinKey: string | null;
    threadId: string | null;
  }>({ agentId: null, pinKey: null, threadId: null });
  const pinIdentity = pinKey ?? null;
  const visibleThreadId =
    boundRef.current.agentId === agentId &&
    boundRef.current.pinKey === pinIdentity
      ? threadId
      : null;

  const adoptThread = useCallback(
    (
      nextAgentId: string | null,
      nextPin: string | null,
      nextThreadId: string | null,
    ) => {
      boundRef.current = {
        agentId: nextAgentId,
        pinKey: nextPin,
        threadId: nextThreadId,
      };
      setThreadId(nextThreadId);
    },
    [],
  );

  const {
    messages,
    isStreaming,
    sendMessage,
    cancelStream,
    loadHistory,
    loadMoreHistory,
    historyHasMore,
    resumeHitl,
  } = useChat(visibleThreadId, agentId);

  const refreshThreads = useCallback(async () => {
    if (!agentId) {
      setThreads([]);
      return;
    }
    try {
      setThreads(await octopThreadsApi.list(agentId));
    } catch {
      // Listing is best-effort; the conversation itself still works.
    }
  }, [agentId]);

  useEffect(() => {
    if (!agentId) {
      pinnedRef.current = null;
      lastAgentRef.current = null;
      lastPinRef.current = null;
      adoptThread(null, null, null);
      setThreads([]);
      setBootError(null);
      return;
    }

    // Switching experts (or the panel's own pin) must drop the previous
    // transcript before the async boot adopts a thread for this agent.
    if (
      lastAgentRef.current !== agentId ||
      lastPinRef.current !== pinIdentity
    ) {
      pinnedRef.current = null;
      lastAgentRef.current = agentId;
      lastPinRef.current = pinIdentity;
      adoptThread(agentId, pinIdentity, null);
    }

    let cancelled = false;
    setBooting(true);
    setBootError(null);

    void (async () => {
      try {
        const rows = await octopThreadsApi.list(agentId);
        if (!cancelled) setThreads(rows);

        if (pinnedRef.current) {
          if (!cancelled) adoptThread(agentId, pinIdentity, pinnedRef.current);
          return;
        }

        let tid: string;
        if (pinKey) {
          // 面板自己的会话。没有记录时新建，不占用该专家在对话页的当前会话。
          const remembered = readSurfaceThread(pinKey, agentId);
          if (remembered && rows.some((row) => row.thread_id === remembered)) {
            pinnedRef.current = remembered;
            if (!cancelled) adoptThread(agentId, pinIdentity, remembered);
            return;
          }
          const created = await octopThreadsApi.create(agentId, {
            rebind: false,
          });
          tid = created.thread_id;
          writeSurfaceThread(pinKey, agentId, tid);
          pinnedRef.current = tid;
        } else {
          const preferred = pickPreferredSession(rows.map(toSession));
          tid = preferred?.threadId ?? "";
          if (!tid) {
            const created = await octopThreadsApi.create(agentId);
            tid = created.thread_id;
          }
          await octopThreadsApi.rebind(agentId, tid);
        }

        // 只在会话尚未设置策略时落默认值，不覆盖用户手动改过的设置
        const existing = rows.find((row) => row.thread_id === tid);
        if (!existing?.hitl_policy) {
          try {
            await octopThreadsApi.patch(agentId, tid, {
              hitl_policy: { mode: hitlMode },
            });
          } catch {
            // 设置失败不影响对话，最坏情况是按全局策略走
          }
        }

        if (!cancelled) {
          adoptThread(agentId, pinIdentity, tid);
        }
      } catch (err) {
        if (!cancelled) {
          setBootError(
            err instanceof Error ? err.message : "Failed to load chat thread",
          );
          adoptThread(agentId, pinIdentity, null);
        }
      } finally {
        if (!cancelled) {
          setBooting(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [agentId, hitlMode, bootNonce, pinKey, pinIdentity, adoptThread]);

  useEffect(() => {
    if (visibleThreadId && agentId) {
      void loadHistory(visibleThreadId);
    }
  }, [visibleThreadId, agentId, loadHistory]);

  const send = useCallback(
    (text: string) => {
      const bound = boundRef.current;
      const tid =
        bound.agentId === agentId && bound.pinKey === pinIdentity
          ? bound.threadId
          : null;
      if (!agentId || !tid) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      sendMessage(trimmed, "", agentId, undefined, tid);
    },
    [agentId, pinIdentity, sendMessage],
  );

  /** Start a fresh conversation and pin it so boot won't switch back. */
  const startNewThread = useCallback(async () => {
    if (!agentId) return;
    // 当前会话还没有任何消息时就不必再建一个空壳，
    // 否则每点一次「+」都会在历史列表里留下一条点开是空白的会话。
    const bound = boundRef.current;
    const currentThreadId =
      bound.agentId === agentId && bound.pinKey === pinIdentity
        ? bound.threadId
        : null;
    if (currentThreadId && messages.length === 0) return;
    const created = await octopThreadsApi.create(
      agentId,
      pinKey ? { rebind: false } : undefined,
    );
    if (pinKey) writeSurfaceThread(pinKey, agentId, created.thread_id);
    else await octopThreadsApi.rebind(agentId, created.thread_id);
    pinnedRef.current = created.thread_id;
    adoptThread(agentId, pinIdentity, created.thread_id);
    void refreshThreads();
  }, [
    agentId,
    messages.length,
    refreshThreads,
    pinKey,
    pinIdentity,
    adoptThread,
  ]);

  /** Switch to an existing conversation. */
  const selectThread = useCallback(
    async (id: string) => {
      if (!agentId || !id) return;
      if (pinKey) writeSurfaceThread(pinKey, agentId, id);
      else await octopThreadsApi.rebind(agentId, id);
      pinnedRef.current = id;
      adoptThread(agentId, pinIdentity, id);
    },
    [agentId, pinKey, pinIdentity, adoptThread],
  );

  /** 重新跑一次启动流程（会话列表 / 绑定失败后手动重试）。 */
  const reload = useCallback(() => {
    pinnedRef.current = null;
    setBootNonce((value) => value + 1);
  }, []);

  /** 在对话内直接对挂起的工具调用作出审批决定。 */
  const resolveHitl = useCallback(
    (
      decisions: Array<{ type: string; message?: string }>,
      pendingId?: string,
    ) => {
      resumeHitl(decisions, undefined, undefined, undefined, pendingId);
    },
    [resumeHitl],
  );

  return {
    threadId: visibleThreadId,
    threads,
    booting,
    bootError,
    messages,
    isStreaming,
    historyHasMore,
    loadMoreHistory,
    send,
    cancelStream,
    startNewThread,
    selectThread,
    refreshThreads,
    reload,
    resolveHitl,
  };
}
