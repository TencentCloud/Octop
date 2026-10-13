import { useEffect, useState } from "react";
import {
  searchWorkspaceMentionFiles,
  shouldSearchWorkspaceMentions,
  type WorkspaceMentionFile,
} from "../utils/fileMention";

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
} {
  const [files, setFiles] = useState<WorkspaceMentionFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<"need_agent" | "failed" | null>(null);

  useEffect(() => {
    if (!mentionMenuOpen) {
      setFiles([]);
      setLoading(false);
      setError(null);
      return;
    }
    if (!shouldSearchWorkspaceMentions(mentionQuery)) {
      setFiles([]);
      setLoading(false);
      setError(null);
      return;
    }
    if (!agentId) {
      setFiles([]);
      setLoading(false);
      setError("need_agent");
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setFiles([]);
      setLoading(true);
      setError(null);
      void searchWorkspaceMentionFiles(agentId, mentionQuery, controller.signal)
        .then((hits) => {
          if (controller.signal.aborted) return;
          setFiles(hits);
        })
        .catch((err: unknown) => {
          if (controller.signal.aborted || isAbortError(err)) return;
          setFiles([]);
          setError("failed");
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [mentionMenuOpen, mentionQuery, agentId]);

  return { files, loading, error };
}
