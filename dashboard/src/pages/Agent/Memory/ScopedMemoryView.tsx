/**
 * Container for the T-38 "scope" view: owns the request, hands the result to the
 * presentational `ProjectMemoryPanel`.
 *
 * It lives next to `MemoryPanel` (a page-local hook/container) so that the shared
 * component in `components/` stays fetch-free (``AGENTS.md`` §5).
 *
 * The request *is* the scope: switching to 「团队」 adds ``team_id``, switching to
 * 「项目」 adds ``project_id`` as well. That is what makes the requested namespace
 * change with the switcher (T-38 criterion ①) — the backend never guesses a
 * project layer, it only answers for the contexts it was given.
 *
 * Failure split (T-38 criteria ③ and the task-54 403 rule):
 * * no project chosen yet  → nothing to ask for; the panel's empty state;
 * * HTTP 403               → `denied`, a permission state (non-members must not
 *                            even learn the project's namespace);
 * * anything else          → `error`, shown with a retry.
 */

import { useCallback, useEffect, useState } from "react";

import { teamsApi } from "../../../api/modules/teams";
import ProjectMemoryPanel, {
  type ScopePanelItem,
} from "../../../components/ProjectMemoryPanel";
import {
  fetchMemoryScopes,
  isPermissionDenied,
  type MemoryScopeGroup,
  type MemorySourceLayer,
} from "./memoryScopes";

export interface ScopedMemoryViewProps {
  agentId: string;
  /** Which layer the switcher is focused on (`team` or `project`). */
  scope: Exclude<MemorySourceLayer, "agent">;
  /** Required for `scope === "project"`; absent means "pick a project first". */
  projectId?: string | null;
  /** Team host agent id; resolved from the team list when omitted. */
  teamId?: string | null;
  /**
   * T-50: forwarded verbatim to ``ProjectMemoryPanel``. This view stays
   * write-free on purpose — it never issues the write itself, the host injects
   * the callback (``ProjectMemoryPanel``'s contract, and the T-38 guard that
   * scans this file for write verbs stays true).
   */
  onRecordToProject?: (item: ScopePanelItem) => void;
  /** Why the write affordance is unavailable / what it needs. Display text. */
  recordToProjectHint?: string | null;
  /** Bump to refetch after the host performed a write elsewhere. */
  reloadKey?: number;
}

export default function ScopedMemoryView({
  agentId,
  scope,
  projectId = null,
  teamId = null,
  onRecordToProject,
  recordToProjectHint = null,
  reloadKey: hostReloadKey = 0,
}: ScopedMemoryViewProps) {
  const [groups, setGroups] = useState<MemoryScopeGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [hostTeamId, setHostTeamId] = useState<string | null>(teamId);

  // `team_id` is the *team host* agent id, not this agent's id, so it cannot be
  // assumed. Without it the backend never opens a team namespace and the 团队
  // tab would silently always look empty — so resolve it from the team list.
  useEffect(() => {
    if (teamId) {
      setHostTeamId(teamId);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const teams = await teamsApi.list();
        const hit = teams.find(
          (team) =>
            team.agent_id === agentId ||
            (team.member_ids ?? []).includes(agentId),
        );
        if (!cancelled) setHostTeamId(hit?.agent_id ?? null);
      } catch {
        // A team lookup failure must not break the agent/project scopes.
        if (!cancelled) setHostTeamId(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [agentId, teamId]);

  const needsProject = scope === "project" && !projectId;

  useEffect(() => {
    if (needsProject) {
      // Nothing to request: the project layer is never guessed.
      setGroups([]);
      setLoading(false);
      setDenied(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setDenied(false);
    setError(null);
    (async () => {
      try {
        const res = await fetchMemoryScopes(agentId, {
          projectId: scope === "project" ? projectId : null,
          teamId: hostTeamId,
        });
        if (cancelled) return;
        setGroups(res.groups ?? []);
      } catch (err) {
        if (cancelled) return;
        setGroups([]);
        if (isPermissionDenied(err)) {
          setDenied(true);
        } else {
          // Deliberately no `t(...)` here: this effect must not depend on the
          // translation function's identity, or a per-render `t` re-triggers the
          // fetch on every render. The panel owns the localized copy.
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    agentId,
    scope,
    projectId,
    hostTeamId,
    needsProject,
    reloadKey,
    hostReloadKey,
  ]);

  const retry = useCallback(() => setReloadKey((k) => k + 1), []);

  return (
    <ProjectMemoryPanel
      groups={groups}
      scope={scope}
      loading={loading}
      denied={denied}
      error={error}
      onRetry={retry}
      onRecordToProject={onRecordToProject}
      recordToProjectHint={recordToProjectHint}
    />
  );
}
