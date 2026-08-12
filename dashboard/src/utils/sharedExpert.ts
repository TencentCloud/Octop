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

/** Experts the user owns — for Experts / Personalization / agent bars. */
export function ownedExperts<T extends SharedExpertAccess>(agents: T[]): T[] {
  return agents.filter(isOwnedExpert);
}
