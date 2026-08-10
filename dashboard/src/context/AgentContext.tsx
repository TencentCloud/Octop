import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { setActiveAgentId } from "../api/request";
import { agentApi as legacyAgentApi } from "../api/modules/agent";

/**
 * Multi-Agent navigation state.
 *
 * Plan §14.3: the dashboard fetches the current user's agents on login,
 * stores the list + selected id in this context, persists the selection
 * in ``localStorage`` (``octop:active-agent``), and pipes the selected id
 * into ``api/request.ts`` so every agent-scoped HTTP call gets an
 * ``X-Octop-Agent-Id`` header.
 */

export interface OctopAgent {
  /** Surrogate integer primary key from the database. */
  id: number;
  /** Public agent id used in API paths and ``X-Octop-Agent-Id``. */
  agent_id: string;
  /** Owning user id (present on list responses). */
  user_id?: number | null;
  /** Resolved username for admin list view. */
  owner_username?: string | null;
  name: string;
  description: string | null;
  persona_mbti: string | null;
  default_model: string | null;
  system_prompt: string | null;
  template_name: string | null;
  state: "running" | "stopped" | "failed" | "starting" | "stopping" | string;
  last_error: string | null;
  icon: string | null;
  icon_name: string | null;
  color: string | null;
  max_iters?: number | null;
  max_input_length?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  config: Record<string, unknown>;
  /** Aggregated unread count across all sessions for this agent (current user). */
  unread_count?: number;
  /** True while BOOTSTRAP.md onboarding has not written ``.bootstrapped`` yet. */
  bootstrap_pending?: boolean;
}

interface AgentContextValue {
  /** Latest agents fetched from ``GET /api/agents``. */
  agents: OctopAgent[];
  /** Active agent id, or ``null`` when no agent is selected. */
  activeAgentId: string | null;
  /** Convenience: the full record for ``activeAgentId``. */
  activeAgent: OctopAgent | null;
  /** True while the initial fetch is in flight. */
  loading: boolean;
  /** Last fetch error message, or ``null``. */
  error: string | null;
  /** Switch the active agent (updates context + localStorage + request.ts). */
  setActiveAgent: (id: string | null) => void;
  /** Force a re-fetch of ``/api/agents`` (e.g. after creating one). */
  refresh: (options?: { silent?: boolean; force?: boolean }) => Promise<void>;
}

const STORAGE_KEY = "octop:active-agent";

const defaultValue: AgentContextValue = {
  agents: [],
  activeAgentId: null,
  activeAgent: null,
  loading: false,
  error: null,
  setActiveAgent: () => undefined,
  refresh: async () => undefined,
};

const AgentContext = createContext<AgentContextValue>(defaultValue);

interface ListAgentsResponse {
  // Server returns OctopAgent[]; typed loosely so legacy agent.ts module
  // (which has a different ``agentApi`` shape for finnie endpoints) stays
  // untouched.
  list: () => Promise<OctopAgent[]>;
}

/**
 * Fetch ``/api/agents``. Tries the orca-flavored ``listAll`` method first,
 * falls back to a direct request if the legacy module hasn't been
 * regenerated yet.
 */
async function fetchAgents(): Promise<OctopAgent[]> {
  const candidate = legacyAgentApi as Partial<ListAgentsResponse> &
    Record<string, unknown>;
  if (typeof candidate.list === "function") {
    return candidate.list();
  }
  // Direct fallback so 14.3 doesn't depend on 14.6's API module rewrite.
  const { request } = await import("../api/request");
  return request<OctopAgent[]>("/agents");
}

export function AgentProvider({ children }: { children: ReactNode }) {
  const [agents, setAgents] = useState<OctopAgent[]>([]);
  const [activeAgentId, setActiveAgentIdState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const persistAndApply = useCallback((id: string | null) => {
    setActiveAgentIdState((prev) => {
      // Skip the re-render when the id hasn't changed.
      if (prev === id) return prev;
      if (id) {
        localStorage.setItem(STORAGE_KEY, id);
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
      setActiveAgentId(id); // populates request.ts module-level cache
      return id;
    });
  }, []);

  const refresh = useCallback(
    async (options?: { silent?: boolean; force?: boolean }): Promise<void> => {
      if (!options?.silent) {
        setLoading(true);
      }
      setError(null);
      try {
        const list = await fetchAgents();
        // Only update state when content actually changed, to prevent
        // unnecessary re-renders of every component subscribed to this context
        // (the chat page polls every 10 s to refresh unread badges).
        setAgents((prev) => {
          if (
            !options?.force &&
            prev.length === list.length &&
            prev.every((a, i) => {
              const b = list[i];
              return (
                a.agent_id === b.agent_id &&
                a.state === b.state &&
                a.unread_count === b.unread_count &&
                a.bootstrap_pending === b.bootstrap_pending &&
                a.name === b.name &&
                a.icon === b.icon &&
                a.icon_name === b.icon_name &&
                a.color === b.color
              );
            })
          ) {
            return prev; // nothing changed — keep the same reference
          }
          return list;
        });

        // Reconcile selection with what the server reports.
        const stored = localStorage.getItem(STORAGE_KEY);
        const haveStored = stored && list.some((a) => a.agent_id === stored);
        if (haveStored) {
          persistAndApply(stored);
        } else if (list.length > 0) {
          persistAndApply(list[0].agent_id);
        } else {
          persistAndApply(null);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load agents");
        // On failure, leave whatever previous state was — don't blow away
        // a valid selection just because a fetch hiccuped.
      } finally {
        if (!options?.silent) {
          setLoading(false);
        }
      }
    },
    [persistAndApply],
  );

  // Initial fetch — fire once on mount. Login flow lives elsewhere; this
  // provider sits inside AuthGuard so by the time we mount, the JWT is
  // already in localStorage.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Re-sync agent runtime state when the user returns to the tab (e.g. after
  // stopping an expert on another page).
  useEffect(() => {
    const onFocus = () => void refresh({ silent: true });
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  const activeAgent = useMemo(
    () => agents.find((a) => a.agent_id === activeAgentId) ?? null,
    [agents, activeAgentId],
  );

  const value = useMemo<AgentContextValue>(
    () => ({
      agents,
      activeAgentId,
      activeAgent,
      loading,
      error,
      setActiveAgent: persistAndApply,
      refresh,
    }),
    [
      agents,
      activeAgentId,
      activeAgent,
      loading,
      error,
      persistAndApply,
      refresh,
    ],
  );

  return (
    <AgentContext.Provider value={value}>{children}</AgentContext.Provider>
  );
}

export function useAgent(): AgentContextValue {
  return useContext(AgentContext);
}
