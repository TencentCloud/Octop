import {
  octopThreadsApi,
  type OctopThread,
} from "../../../api/modules/octopThreads";

export function firstUnreadThreadId(
  threads: readonly Pick<OctopThread, "thread_id" | "unread_count">[],
): string | null {
  return (
    threads.find((thread) => (thread.unread_count ?? 0) > 0)?.thread_id ?? null
  );
}

export async function fetchFirstUnreadThreadId(
  agentId: string,
): Promise<string | null> {
  const threads = await octopThreadsApi.list(agentId, 100);
  return firstUnreadThreadId(threads);
}
