import { useEffect, useState } from "react";
import { projectsApi, type ProjectMember } from "../api/modules/projects";
import { parseApiError } from "../utils/apiError";

export interface UseProjectMembersResult {
  members: ProjectMember[];
  loading: boolean;
  error: string | null;
}

/** Server-localized message when present, otherwise the raw transport error. */
function errorMessageOf(error: unknown): string | null {
  const parsed = parseApiError(error);
  if (parsed?.message?.trim()) return parsed.message;
  if (error instanceof Error && error.message.trim()) return error.message;
  return null;
}

/**
 * Member source for the project-domain pickers (PLAN §8.2 · risk R5).
 *
 * The API only ever returns the **members of this project**, so assignee and
 * PATCH/parent-task pickers must read from here. Reading the global user
 * directory would leak subjects that are not project members — the projects
 * pages and this hook must never call the users-directory endpoint.
 *
 * This hook doubles as the adapter layer required by PLAN §9 (S-11): the
 * project domain may reuse the generic `components/ChatPicker/**` widgets only
 * through a feed like this one, never by importing Chat page internals.
 */
export function useProjectMembers(
  projectId: string | null | undefined,
): UseProjectMembersResult {
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) {
      setMembers([]);
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void projectsApi.listMembers(projectId).then(
      (rows) => {
        // Project switched while the request was in flight — drop the result.
        if (cancelled) return;
        setMembers(rows);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setMembers([]);
        setError(errorMessageOf(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return { members, loading, error };
}
