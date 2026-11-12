import { isRemoteShadowAgent } from "../../../utils/remoteExpert";
import { isTeamAgent } from "../../../utils/teamAgent";

/** Classic chat-nav filter under the search box. */
export type ChatNavScope = "experts" | "teams" | "cloud";

export const CHAT_NAV_SCOPES: readonly ChatNavScope[] = [
  "experts",
  "teams",
  "cloud",
];

type NavAgent = {
  kind?: string | null;
  bridge?: boolean | null;
  agent_id?: string | null;
};

/** Open the team tab when the current chat is a team; otherwise experts. */
export function initialChatNavScope(
  agent: { kind?: string | null } | null | undefined,
): ChatNavScope {
  return agent && isTeamAgent(agent) ? "teams" : "experts";
}

/**
 * Experts include cloud experts. Teams include cloud teams.
 * Cloud is every remote shadow, expert or team.
 */
export function matchesChatNavScope(
  agent: NavAgent,
  scope: ChatNavScope,
): boolean {
  if (scope === "cloud") return isRemoteShadowAgent(agent);
  if (scope === "teams") return isTeamAgent(agent);
  return !isTeamAgent(agent);
}
