/** Lucide fallback when the cartoon portrait is missing. */
export const TEAM_ICON_NAME = "users";

/** Bundled cartoon portrait, same style as expert avatars. */
export const TEAM_AVATAR_URL = "/experts/avatars/team-host.svg";

/** True when this agent is a team host (group chat), not a solo expert. */
export function isTeamAgent(
  agent: { kind?: string | null } | null | undefined,
): boolean {
  return agent?.kind === "team";
}

/** Host tokens may be unlabeled or stamped with the room agent id. */
export function isTeamHostSpeaker(
  isTeamRoom: boolean,
  speakerId?: string | null,
  hostId?: string | null,
): boolean {
  if (!isTeamRoom) return false;
  const speaker = (speakerId || "").trim();
  const host = (hostId || "").trim();
  return !speaker || (!!host && speaker === host);
}

/** Roster row returned with a team so viewers can see members they cannot open. */
export interface TeamMemberPublic {
  agent_id: string;
  name: string;
  color?: string | null;
  icon_name?: string | null;
  icon_url?: string | null;
  kind?: string | null;
  is_shared?: boolean;
  user_id?: number | null;
  managed_runner?: string | null;
}

/** Fields chat avatars and @-mentions read from a speaker. */
export interface TeamSpeakerFace {
  agent_id: string;
  name: string;
  color: string | null;
  icon_name: string | null;
  icon_url: string | null;
  kind?: string | null;
  is_shared?: boolean;
  is_owner?: boolean;
  user_id?: number | null;
  owner_username?: string | null;
  config?: Record<string, unknown> | null;
}

export function teamMemberChatOption(member: TeamMemberPublic) {
  return {
    agent_id: member.agent_id,
    name: member.name,
    icon_name: member.icon_name ?? null,
    icon_url: member.icon_url ?? null,
    color: member.color ?? null,
    is_shared: Boolean(member.is_shared),
    is_owner: false,
    owner_username: null,
    bridge: false,
    bridge_connection_id: null,
    bridge_connection_name: null,
    bridge_connection_icon: null,
    bridge_disconnected: false,
    bridge_inbound: false,
    managed_runner: member.managed_runner ?? null,
  };
}

function speakerFromMember(member: TeamMemberPublic): TeamSpeakerFace {
  return {
    agent_id: member.agent_id,
    name: member.name,
    color: member.color ?? null,
    icon_name: member.icon_name ?? null,
    icon_url: member.icon_url ?? null,
    kind: member.kind ?? "expert",
    is_shared: Boolean(member.is_shared),
    is_owner: false,
    user_id: member.user_id ?? null,
    config: member.managed_runner
      ? { managed_runner: member.managed_runner }
      : null,
  };
}

/** Agent list hit, otherwise a roster summary for a member this user cannot open. */
export function resolveSpeakerFace<T extends { agent_id: string }>(
  agents: readonly T[],
  members: readonly TeamMemberPublic[] | undefined,
  speakerId: string | null | undefined,
): T | TeamSpeakerFace | undefined {
  const id = (speakerId || "").trim();
  if (!id) return undefined;
  const found = agents.find((item) => item.agent_id === id);
  if (found) return found;
  const member = members?.find((item) => item.agent_id === id);
  return member ? speakerFromMember(member) : undefined;
}

/** Team card / chat portrait; falls back to the bundled cartoon. */
export function teamPortraitUrl(iconUrl?: string | null): string {
  const url = iconUrl?.trim() || "";
  if (!url || url === "/experts/avatars/multi-agent-orchestrator.svg") {
    return TEAM_AVATAR_URL;
  }
  return url;
}
