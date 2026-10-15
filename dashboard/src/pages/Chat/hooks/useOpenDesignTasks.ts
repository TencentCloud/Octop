import { useCallback, useEffect, useState } from "react";
import {
  openDesignApi,
  type DesignTask,
} from "../../../api/modules/openDesign";

/** One live subscription per conversation, shared by all turn cards. */
export function useOpenDesignTasks(agentId?: string | null, threadId?: string) {
  const [snapshot, setSnapshot] = useState<{
    scope: string;
    tasks: DesignTask[];
  }>({ scope: "", tasks: [] });
  const [disconnected, setDisconnected] = useState(false);
  const scope = `${agentId}:${threadId}`;
  useEffect(() => {
    setDisconnected(false);
    if (!agentId || !threadId) return;
    const controller = new AbortController();
    let retry: ReturnType<typeof setTimeout>;
    const connect = async () => {
      try {
        await openDesignApi.watch(
          agentId,
          threadId,
          (tasks) => {
            if (!controller.signal.aborted) {
              setSnapshot({ scope, tasks });
              setDisconnected(false);
            }
          },
          controller.signal,
        );
      } catch {
        if (controller.signal.aborted) return;
      }
      if (!controller.signal.aborted) {
        setDisconnected(true);
        retry = setTimeout(() => void connect(), 5000);
      }
    };
    void connect();
    return () => {
      controller.abort();
      clearTimeout(retry);
    };
  }, [agentId, threadId, scope]);
  const setTasks = useCallback(
    (tasks: DesignTask[]) => {
      setSnapshot((previous) =>
        previous.scope === scope ? { scope, tasks } : previous,
      );
    },
    [scope],
  );
  return {
    tasks: snapshot.scope === scope ? snapshot.tasks : [],
    disconnected,
    setTasks,
  };
}
