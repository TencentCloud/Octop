export interface SharedExpertAccess {
  is_shared?: boolean;
  is_owner?: boolean;
}

export function isSharedExpertViewer(agent: SharedExpertAccess): boolean {
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
