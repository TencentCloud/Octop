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
import {
  retainDisconnectedBridgeAgents,
  toBridgeShadowAgentId,
} from "../utils/remoteExpert";

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
  /** Whether the owner has shared this expert with other users. */
  is_shared?: boolean;
  /** Whether the current user owns this expert. */
  is_owner?: boolean;
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
  icon_url: string | null;
  color: string | null;
  max_iters?: number | null;
  max_input_length?: number | null;
  temperature?: number | null;
  top_p?: number | null;
  max_tokens?: number | null;
  config: Record<string, unknown>;
  /** Knowledge bases opened by default in new chats with this expert. */
  knowledge_base_ids?: string[];
  /** Connectors opened by default in new chats with this expert. */
  mcp_servers?: string[];
  /** Aggregated unread count across all sessions for this agent (current user). */
  unread_count?: number;
  /** True while BOOTSTRAP.md onboarding has not written ``.bootstrapped`` yet. */
  bootstrap_pending?: boolean;
  /** ``expert`` (default) or ``team`` host. */
  kind?: "expert" | "team" | string;
  /** Member agent ids when ``kind === "team"``. */
  member_ids?: string[];
  welcome_message?: string | null;
  /** True when this row is a remote shadow expert via cloud collab. */
  bridge?: boolean;
  bridge_connection_id?: string | null;
  /** Display name of the cloud-collab link (chat group label). */
  bridge_connection_name?: string | null;
  /** Icon selected for the cloud-collab link (shown on remote expert badges). */
  bridge_connection_icon?: string | null;
  /** True while the cloud-collab link dropped but this shadow is still pinned. */
  bridge_disconnected?: boolean;
  /** True when this shadow arrived via a peer-initiated (inbound) link. */
  bridge_inbound?: boolean;
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

export interface EnabledExpertsOptions {
  /**
   * When ``true`` (opt-in; the default is ``false``), keep the
   * ``resolvedAgentId`` expert in the returned list even if it does not
   * match the predicate. Today every caller passes ``false`` so a disabled
   * expert disappears from the sidebar / @-picker the moment the user stops
   * it, including when it is the currently focused expert. The main panel
   * still renders ``AgentNotReadyScreen`` on the same URL so users get a
   * clear path to ``/experts`` to restart it.
   */
  pinActive?: boolean;
}

const STORAGE_KEY = "octop:active-agent";

/**
 * Pure helper: narrow ``agents`` down to those that are "enabled" for the
 * chat surface (running experts). The same predicate is reused by:
 *   • the chat page left sidebar (``Chat/index.tsx``)
 *   • the minimal-layout records pane (``MinimalRecordsHost`` — non-/chat
 *     routes like ``/experts`` show expert folders here)
 *   • the chat composer's ``@``-mention picker + slash menu
 *
 * Keep this helper in sync with ``isAgentChatReady`` so disabled experts
 * never leak into any chat-side surface.
 */
export function selectEnabledExperts(
  agents: OctopAgent[],
  resolvedAgentId: string | null | undefined,
  options: EnabledExpertsOptions = {},
): OctopAgent[] {
  const { pinActive = false } = options;
  const enabled = agents.filter(
    (a) => a.state === "running" || Boolean(a.bridge_disconnected),
  );
  if (!pinActive || !resolvedAgentId) return enabled;
  if (enabled.some((a) => a.agent_id === resolvedAgentId)) return enabled;
  const pinnedActive = agents.find((a) => a.agent_id === resolvedAgentId);
  if (!pinnedActive) return enabled;
  return [pinnedActive, ...enabled];
}

function sameMemberIds(left?: string[], right?: string[]): boolean {
  const a = left ?? [];
  const b = right ?? [];
  return a.length === b.length && a.every((id, index) => id === b[index]);
}

/**
 * Shared projection used by the chat composer (`ChatInput` /
 * ``composerLookups``). Keeps the lightweight ``ChatAgentOption`` shape
 * consistent across surfaces — name/icon for the chip, shared badge for
 * the picker, owner_username for the current-user indicator.
 */
export function projectChatAgentOption(agent: OctopAgent): {
  agent_id: string;
  name: string;
  icon_name: string | null;
  icon_url: string | null;
  color: string | null;
  is_shared: boolean;
  is_owner: boolean;
  owner_username: string | null;
  bridge: boolean;
  bridge_connection_id: string | null;
  bridge_connection_name: string | null;
  bridge_connection_icon: string | null;
  bridge_disconnected: boolean;
  bridge_inbound: boolean;
} {
  return {
    agent_id: agent.agent_id,
    name: agent.name,
    icon_name: agent.icon_name,
    icon_url: agent.icon_url,
    color: agent.color,
    is_shared: Boolean(agent.is_shared),
    is_owner: Boolean(agent.is_owner),
    owner_username: agent.owner_username ?? null,
    bridge: Boolean(agent.bridge),
    bridge_connection_id: agent.bridge_connection_id ?? null,
    bridge_connection_name: agent.bridge_connection_name ?? null,
    bridge_connection_icon: agent.bridge_connection_icon ?? null,
    bridge_disconnected: Boolean(agent.bridge_disconnected),
    bridge_inbound: Boolean(agent.bridge_inbound),
  };
}

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

interface FetchAgentsResult {
  agents: OctopAgent[];
  liveConnectionIds: Set<string>;
}

/**
 * Fetch ``/api/agents``. Tries the orca-flavored ``listAll`` method first,
 * falls back to a direct request if the legacy module hasn't been
 * regenerated yet.
 */
async function fetchAgents(): Promise<FetchAgentsResult> {
  const candidate = legacyAgentApi as Partial<ListAgentsResponse> &
    Record<string, unknown>;
  let local: OctopAgent[] = [];
  if (typeof candidate.list === "function") {
    local = await candidate.list();
  } else {
    // Direct fallback so 14.3 doesn't depend on 14.6's API module rewrite.
    const { request } = await import("../api/request");
    local = await request<OctopAgent[]>("/agents");
  }
  const { remote, liveConnectionIds } = await fetchBridgeShadowAgents();
  if (remote.length === 0) {
    return { agents: local, liveConnectionIds };
  }
  const localIds = new Set(local.map((a) => a.agent_id));
  return {
    agents: [...local, ...remote.filter((a) => !localIds.has(a.agent_id))],
    liveConnectionIds,
  };
}

async function fetchBridgeShadowAgents(): Promise<{
  remote: OctopAgent[];
  liveConnectionIds: Set<string>;
}> {
  const empty = {
    remote: [] as OctopAgent[],
    liveConnectionIds: new Set<string>(),
  };
  try {
    const { bridgeApi } = await import("../api/modules/bridge");
    const connections = await bridgeApi.list();
    const liveConnectionIds = new Set(
      connections.map((c) => c.connection_id).filter(Boolean),
    );
    const connected = connections.filter((c) => c.status === "connected");
    if (connected.length === 0) {
      return { remote: [], liveConnectionIds };
    }
    const batches = await Promise.all(
      connected.map(async (conn) => {
        try {
          const agents = await bridgeApi.listAgents(conn.connection_id);
          return agents.map((agent) => mapBridgeAgent(agent, conn));
        } catch {
          return [] as OctopAgent[];
        }
      }),
    );
    return { remote: batches.flat(), liveConnectionIds };
  } catch {
    // Non-admin users or cloud-collab-unavailable installs — ignore.
    return empty;
  }
}

function mapBridgeAgent(
  agent: {
    id?: string;
    agent_id?: string;
    name?: string;
    description?: string | null;
    icon_url?: string | null;
    icon_name?: string | null;
    color?: string | null;
    kind?: string | null;
    state?: string | null;
    member_ids?: unknown;
  },
  conn: {
    connection_id: string;
    display_name: string;
    icon_name?: string | null;
    inbound?: boolean;
    has_password?: boolean;
  },
): OctopAgent {
  const agentId = String(agent.agent_id || agent.id || "");
  const memberIds = Array.isArray(agent.member_ids)
    ? agent.member_ids
        .map((id) =>
          toBridgeShadowAgentId(conn.connection_id, String(id ?? "")),
        )
        .filter((id): id is string => Boolean(id))
    : undefined;
  return {
    id: 0,
    agent_id: agentId,
    name: String(agent.name || agentId),
    description:
      typeof agent.description === "string" ? agent.description : null,
    persona_mbti: null,
    default_model: null,
    system_prompt: null,
    template_name: null,
    state: "running",
    last_error: null,
    icon: null,
    icon_name: typeof agent.icon_name === "string" ? agent.icon_name : null,
    icon_url: typeof agent.icon_url === "string" ? agent.icon_url : null,
    color: typeof agent.color === "string" ? agent.color : null,
    config: {},
    kind: agent.kind === "team" ? "team" : "expert",
    member_ids: memberIds,
    bridge: true,
    is_owner: true,
    is_shared: false,
    bridge_disconnected: false,
    bridge_inbound: Boolean(conn.inbound) || conn.has_password === false,
    bridge_connection_id: conn.connection_id,
    bridge_connection_name: conn.display_name,
    bridge_connection_icon:
      typeof conn.icon_name === "string" && conn.icon_name.trim()
        ? conn.icon_name.trim()
        : null,
  };
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
        const { agents: list, liveConnectionIds } = await fetchAgents();
        // Only update state when content actually changed, to prevent
        // unnecessary re-renders of every component subscribed to this context
        // (the chat page polls every 10 s to refresh unread badges).
        let merged: OctopAgent[] = list;
        setAgents((prev) => {
          merged = retainDisconnectedBridgeAgents(
            prev,
            list,
            liveConnectionIds,
          );
          if (
            !options?.force &&
            prev.length === merged.length &&
            prev.every((a, i) => {
              const b = merged[i];
              return (
                a.agent_id === b.agent_id &&
                a.state === b.state &&
                a.unread_count === b.unread_count &&
                a.bootstrap_pending === b.bootstrap_pending &&
                a.name === b.name &&
                a.icon === b.icon &&
                a.icon_name === b.icon_name &&
                a.icon_url === b.icon_url &&
                a.color === b.color &&
                a.kind === b.kind &&
                a.bridge === b.bridge &&
                a.is_owner === b.is_owner &&
                a.bridge_connection_id === b.bridge_connection_id &&
                a.bridge_connection_name === b.bridge_connection_name &&
                a.bridge_disconnected === b.bridge_disconnected &&
                a.bridge_inbound === b.bridge_inbound &&
                sameMemberIds(a.member_ids, b.member_ids)
              );
            })
          ) {
            merged = prev;
            return prev; // nothing changed — keep the same reference
          }
          return merged;
        });

        // Reconcile selection with what the server reports. Keep a
        // disconnected remote pin instead of jumping to the first local expert.
        const stored = localStorage.getItem(STORAGE_KEY);
        const haveStored = stored && merged.some((a) => a.agent_id === stored);
        if (haveStored) {
          persistAndApply(stored);
        } else if (merged.length > 0) {
          persistAndApply(merged[0].agent_id);
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
