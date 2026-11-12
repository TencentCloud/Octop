import { useEffect, useMemo, useState } from "react";
import {
  cachedWorkspaceMentionIndex,
  isPathLikeMentionQuery,
  loadWorkspaceMentionIndex,
  rankWorkspaceMentionFiles,
  searchWorkspaceMentionFiles,
  shouldSearchWorkspaceMentions,
  type WorkspaceMentionEntry,
  type WorkspaceMentionFile,
} from "../utils/fileMention";

const TRUNCATED_GLOB_DEBOUNCE_MS = 250;

function isAbortError(err: unknown): boolean {
  return (
    (err instanceof DOMException && err.name === "AbortError") ||
    (err instanceof Error && err.name === "AbortError")
  );
}

export function useWorkspaceFileMention(
  agentId: string | null | undefined,
  mentionMenuOpen: boolean,
  mentionQuery: string,
): {
  files: WorkspaceMentionFile[];
  loading: boolean;
  error: "need_agent" | "failed" | null;
  truncated: boolean;
} {
  const [index, setIndex] = useState<{
    agentId: string;
    paths: WorkspaceMentionEntry[];
    truncated: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<"need_agent" | "failed" | null>(null);
  const [globEntries, setGlobEntries] = useState<WorkspaceMentionEntry[]>([]);
  const [globLoading, setGlobLoading] = useState(false);

  useEffect(() => {
    if (!mentionMenuOpen) {
      setLoading(false);
      setError(null);
      return;
    }
    if (!agentId) {
      setLoading(false);
      return;
    }

    const cached = cachedWorkspaceMentionIndex(agentId);
    if (cached) {
      setIndex({ agentId, paths: cached.paths, truncated: cached.truncated });
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void loadWorkspaceMentionIndex(agentId, controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setIndex({
          agentId,
          paths: loaded.paths,
          truncated: loaded.truncated,
        });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || isAbortError(err)) return;
        setIndex({ agentId, paths: [], truncated: false });
        setError("failed");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [mentionMenuOpen, agentId]);

  const ready = index && agentId && index.agentId === agentId ? index : null;
  const truncated = Boolean(ready?.truncated);
  const supplement =
    mentionMenuOpen &&
    Boolean(agentId) &&
    truncated &&
    isPathLikeMentionQuery(mentionQuery) &&
    shouldSearchWorkspaceMentions(mentionQuery);

  useEffect(() => {
    if (!supplement || !agentId) {
      setGlobEntries([]);
      setGlobLoading(false);
      return;
    }

    const controller = new AbortController();
    setGlobLoading(true);
    const timer = window.setTimeout(() => {
      void searchWorkspaceMentionFiles(agentId, mentionQuery, controller.signal)
        .then((entries) => {
          if (controller.signal.aborted) return;
          setGlobEntries(entries);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || isAbortError(err)) return;
          setGlobEntries([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setGlobLoading(false);
        });
    }, TRUNCATED_GLOB_DEBOUNCE_MS);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
      setGlobLoading(false);
    };
  }, [supplement, agentId, mentionQuery]);

  useEffect(() => {
    if (!mentionMenuOpen || agentId) return;
    setError(shouldSearchWorkspaceMentions(mentionQuery) ? "need_agent" : null);
  }, [mentionMenuOpen, agentId, mentionQuery]);

  const files = useMemo(() => {
    if (!ready || !shouldSearchWorkspaceMentions(mentionQuery)) return [];
    const entries = supplement ? [...ready.paths, ...globEntries] : ready.paths;
    return rankWorkspaceMentionFiles(entries, mentionQuery);
  }, [ready, mentionQuery, supplement, globEntries]);

  const searching = shouldSearchWorkspaceMentions(mentionQuery);
  const waiting =
    (loading || (supplement && globLoading)) && files.length === 0;
  return {
    files,
    loading: searching && waiting,
    error: searching ? error : null,
    truncated: searching && truncated,
  };
}
