/**
 * Remote (cloud-collab) expert helpers: id shape, capability table, grouping.
 *
 * Keep this table in sync with tunnel allowlists. ``peer-only`` surfaces must
 * be gated in the UI instead of failing after the user clicks.
 */
export function isBridgeAgentId(id: string | null | undefined): boolean {
  return Boolean(parseBridgeAgentId(id));
}

export function parseBridgeAgentId(
  agentId: string | null | undefined,
): { connectionId: string; remoteAgentId: string } | null {
  const raw = (agentId ?? "").trim();
  if (!raw.startsWith("bridge:")) return null;
  const rest = raw.slice("bridge:".length);
  const colon = rest.indexOf(":");
  if (colon <= 0 || colon >= rest.length - 1) return null;
  const connectionId = rest.slice(0, colon).trim();
  const remoteAgentId = rest.slice(colon + 1).trim();
  if (!connectionId || !remoteAgentId) return null;
  return { connectionId, remoteAgentId };
}

/** Map a peer-local agent id onto the local Bridge shadow id. */
export function toBridgeShadowAgentId(
  connectionId: string | null | undefined,
  peerAgentId: string | null | undefined,
): string | undefined {
  const cid = (connectionId ?? "").trim();
  const raw = (peerAgentId ?? "").trim();
  if (!raw) return undefined;
  if (parseBridgeAgentId(raw)) return raw;
  if (!cid) return raw;
  return `bridge:${cid}:${raw}`;
}

/** Rewrite a speaker/member id from a peer team room onto the local shadow. */
export function rewritePeerSpeakerId(
  roomAgentId: string | null | undefined,
  speakerId: string | null | undefined,
): string | undefined {
  const parsed = parseBridgeAgentId(roomAgentId);
  if (!parsed) {
    const raw = (speakerId ?? "").trim();
    return raw || undefined;
  }
  return toBridgeShadowAgentId(parsed.connectionId, speakerId);
}

export type RemoteExpertSurface =
  | "chat"
  | "history"
  | "tasks"
  | "workspace"
  | "memory"
  | "tools"
  | "plugins"
  | "channels"
  | "mbti"
  | "subagents"
  | "skillPackages"
  | "acpGlobal"
  | "connectorsManage"
  | "browserHost"
  | "knowledgeManage";

export type RemoteSurfaceMode = "ok" | "limited" | "peer-only";

const SURFACES: Record<RemoteExpertSurface, RemoteSurfaceMode> = {
  chat: "ok",
  history: "ok",
  tasks: "ok",
  workspace: "ok",
  memory: "ok",
  tools: "limited",
  plugins: "limited",
  channels: "limited",
  mbti: "ok",
  subagents: "ok",
  skillPackages: "peer-only",
  acpGlobal: "peer-only",
  connectorsManage: "peer-only",
  browserHost: "peer-only",
  knowledgeManage: "peer-only",
};

export function remoteSurfaceMode(
  surface: RemoteExpertSurface,
): RemoteSurfaceMode {
  return SURFACES[surface];
}

export function isRemotePeerOnly(surface: RemoteExpertSurface): boolean {
  return SURFACES[surface] === "peer-only";
}

export interface RemoteGroupable {
  agent_id: string;
  bridge?: boolean | null;
  bridge_connection_id?: string | null;
  bridge_connection_name?: string | null;
  bridge_connection_icon?: string | null;
  bridge_disconnected?: boolean | null;
}

export interface ExpertConnectionGroup<T extends RemoteGroupable> {
  key: string;
  label: string;
  icon?: string | null;
  disconnected: boolean;
  agents: T[];
}

/** Local experts first, then one group per cloud-collab connection. */
export function groupExpertsByConnection<T extends RemoteGroupable>(
  agents: T[],
  localLabel: string,
): ExpertConnectionGroup<T>[] {
  const local: T[] = [];
  const remoteOrder: string[] = [];
  const remoteByConn = new Map<string, T[]>();
  for (const agent of agents) {
    if (!agent.bridge) {
      local.push(agent);
      continue;
    }
    const key = (agent.bridge_connection_id ?? "").trim() || "_";
    if (!remoteByConn.has(key)) {
      remoteOrder.push(key);
      remoteByConn.set(key, []);
    }
    remoteByConn.get(key)?.push(agent);
  }
  const groups: ExpertConnectionGroup<T>[] = [];
  if (local.length > 0) {
    groups.push({
      key: "local",
      label: localLabel,
      disconnected: false,
      agents: local,
    });
  }
  for (const key of remoteOrder) {
    const list = remoteByConn.get(key) ?? [];
    const head = list[0];
    groups.push({
      key,
      label: (head?.bridge_connection_name ?? "").trim() || key,
      icon: head?.bridge_connection_icon ?? null,
      disconnected: list.every((item) => Boolean(item.bridge_disconnected)),
      agents: list,
    });
  }
  return groups;
}

export interface BridgeShadowAgent {
  agent_id: string;
  bridge?: boolean;
  bridge_connection_id?: string | null;
  bridge_disconnected?: boolean;
  state: string;
}

/**
 * Keep experts from cloud-collab links that dropped this session so the
 * picker can still show them offline instead of jumping to a local expert.
 */
export function retainDisconnectedBridgeAgents<T extends BridgeShadowAgent>(
  prev: T[],
  next: T[],
  liveConnectionIds: ReadonlySet<string>,
): T[] {
  const connectedConnIds = new Set(
    next
      .filter((agent) => agent.bridge && agent.bridge_connection_id)
      .map((agent) => agent.bridge_connection_id as string),
  );
  const nextIds = new Set(next.map((agent) => agent.agent_id));
  const stale = prev
    .filter((agent) => {
      const conn = agent.bridge_connection_id?.trim();
      if (!agent.bridge || !conn) return false;
      if (!liveConnectionIds.has(conn)) return false;
      if (connectedConnIds.has(conn)) return false;
      return !nextIds.has(agent.agent_id);
    })
    .map((agent) => ({
      ...agent,
      bridge_disconnected: true,
      state: "stopped",
    }));
  const locals = next.filter((agent) => !agent.bridge);
  const remotes = next
    .filter((agent) => agent.bridge)
    .map((agent) => ({ ...agent, bridge_disconnected: false }));
  return [...locals, ...remotes, ...stale];
}
