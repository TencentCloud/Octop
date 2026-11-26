/**
 * Shared git status state for workspace surfaces (tree badges, review panel).
 * Fetching stays silent: non-repo workspaces produce no UI at all.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { gitApi, type GitStatus } from "../../../../api/modules/git";
import { apiErrorMessage } from "../../../../utils/apiError";

export interface UseWorkspaceGitResult {
  status: GitStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  act: (op: (agentId: string) => Promise<unknown>) => Promise<boolean>;
}

export function useWorkspaceGit(
  agentId: string | null | undefined,
  opts: { enabled: boolean; streaming?: boolean; onMutated?: () => void },
): UseWorkspaceGitResult {
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onMutatedRef = useRef(opts.onMutated);
  onMutatedRef.current = opts.onMutated;

  const refresh = useCallback(async () => {
    if (!agentId || !opts.enabled) return;
    setLoading(true);
    try {
      setStatus(await gitApi.status(agentId));
      setError(null);
    } catch (err: unknown) {
      setError(
        apiErrorMessage(
          err,
          err instanceof Error ? err.message : "git status failed",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, [agentId, opts.enabled]);

  useEffect(() => {
    if (!opts.enabled) {
      setStatus(null);
      setError(null);
      return;
    }
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentId, opts.enabled]);

  const prevStreaming = useRef(opts.streaming);
  useEffect(() => {
    const was = prevStreaming.current;
    prevStreaming.current = opts.streaming;
    if (was && !opts.streaming && opts.enabled) {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.streaming]);

  const act = useCallback(
    async (op: (agentId: string) => Promise<unknown>) => {
      if (!agentId) return false;
      try {
        await op(agentId);
        await refresh();
        onMutatedRef.current?.();
        return true;
      } catch {
        return false;
      }
    },
    [agentId, refresh],
  );

  return { status, loading, error, refresh, act };
}

export const GIT_STATUS_LETTER: Record<string, string> = {
  modified: "M",
  added: "A",
  deleted: "D",
  renamed: "R",
  copied: "C",
  typechange: "T",
  untracked: "U",
  conflicted: "!",
};

export interface GitTreeBadges {
  /** workspace path (leading ``/``) → status letter */
  fileStatus: Map<string, string>;
  /** workspace dir path (leading ``/``) with changes inside */
  changedDirs: Set<string>;
}

export function gitTreeBadges(status: GitStatus | null): GitTreeBadges | null {
  if (!status?.is_repo) return null;
  const fileStatus = new Map<string, string>();
  const changedDirs = new Set<string>();
  for (const change of status.files) {
    const rel = change.path.replace(/\/+$/, "");
    if (!rel) continue;
    fileStatus.set(`/${rel}`, GIT_STATUS_LETTER[change.status] ?? "M");
    let parent = rel;
    for (;;) {
      const idx = parent.lastIndexOf("/");
      if (idx < 0) break;
      parent = parent.slice(0, idx);
      if (parent) changedDirs.add(`/${parent}`);
    }
  }
  return { fileStatus, changedDirs };
}
