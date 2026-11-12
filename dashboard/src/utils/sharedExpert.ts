import { isTeamAgent } from "./teamAgent";

export interface SharedExpertAccess {
  is_shared?: boolean;
  is_owner?: boolean;
  /** Owning user id from the agent list. Used when ``is_owner`` is missing or stale. */
  user_id?: number | null;
}

/** Owner or admin. Matches ``assert_agent_owner`` on ``GET /agents/{id}/status``. */
export function canReadAgentRuntimeStatus(
  agent: SharedExpertAccess,
  user: { role?: string } | null | undefined,
): boolean {
  if (user?.role === "admin") return true;
  return agent.is_owner !== false;
}

function sameUserId(
  left: number | null | undefined,
  right: number | null | undefined,
): boolean {
  if (left == null || right == null) return false;
  return Number(left) === Number(right);
}

/**
 * Share-only viewer: the expert is shared and this account does not own it.
 *
 * The owner keeps workspace and file tools after sharing. A matching
 * ``user_id`` counts as ownership even if ``is_owner`` was dropped or false.
 */
export function isSharedExpertViewer(
  agent: SharedExpertAccess,
  viewer?: { id?: number | null } | null,
): boolean {
  if (agent.is_owner === true) return false;
  if (sameUserId(agent.user_id, viewer?.id)) return false;
  return agent.is_shared === true && agent.is_owner === false;
}

/** True when the current user may manage this expert (not a share-only viewer). */
export function isOwnedExpert(agent: SharedExpertAccess): boolean {
  return !isSharedExpertViewer(agent);
}

/**
 * Resolve the expert whose skill catalog can be shown in chat.
 *
 * Shared-expert viewers have read access to the expert's skills; ownership is
 * only required for mutations. Keep readiness/loading as the only UI gates so
 * the composer can inspect and select skills exposed by a shared expert.
 */
export function chatSkillCatalogAgentId(
  agentId: string | null | undefined,
  agentChatReady: boolean,
  agentsLoading: boolean,
): string | null {
  if (!agentChatReady || agentsLoading) return null;
  return agentId ?? null;
}

/** Experts the user owns — for Experts / Personalization / agent bars. */
export function ownedExperts<T extends SharedExpertAccess>(agents: T[]): T[] {
  return agents.filter(isOwnedExpert);
}

/** Owned solo experts — host pickers must not list team hosts. */
export function ownedSoloExperts<
  T extends SharedExpertAccess & { kind?: string },
>(agents: T[]): T[] {
  return ownedExperts(agents).filter((item) => !isTeamAgent(item));
}

/** Owned team hosts — memory / channels pickers. */
export function ownedTeamAgents<
  T extends SharedExpertAccess & { kind?: string },
>(agents: T[]): T[] {
  return ownedExperts(agents).filter(isTeamAgent);
}
