/** Lucide fallback when the cartoon portrait is missing. */
export const TEAM_ICON_NAME = "users";

/** Bundled cartoon portrait, same style as expert avatars. */
export const TEAM_AVATAR_URL = "/experts/avatars/team-host.svg";

/** True when this agent is a team host (group chat), not a solo expert. */
export function isTeamAgent(
  agent: { kind?: string } | null | undefined,
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

/** Team card / chat portrait; falls back to the bundled cartoon. */
export function teamPortraitUrl(iconUrl?: string | null): string {
  const url = iconUrl?.trim() || "";
  if (!url || url === "/experts/avatars/multi-agent-orchestrator.svg") {
    return TEAM_AVATAR_URL;
  }
  return url;
}
