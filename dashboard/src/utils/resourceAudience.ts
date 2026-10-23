import { isRemoteShadowAgent } from "./remoteExpert";
import { isSharedExpertViewer } from "./sharedExpert";

/** Instance resources: everything, ones I own, or ones shared to me. */
export type ResourceAudience = "all" | "local" | "shared";

/** Experts also split local instances from cloud-collab shadows. */
export type ExpertLocationFilter = ResourceAudience | "cloud";

export function matchesResourceAudience(
  filter: ResourceAudience,
  item: { owned: boolean; shared?: boolean | null },
): boolean {
  if (filter === "all") return true;
  if (filter === "shared") return item.shared === true && !item.owned;
  return item.owned;
}

export function matchesExpertLocation(
  agent: {
    bridge?: boolean | null;
    agent_id?: string | null;
    is_shared?: boolean;
    is_owner?: boolean;
  },
  filter: ExpertLocationFilter,
): boolean {
  if (filter === "all") return true;
  if (filter === "shared") return isSharedExpertViewer(agent);
  const remote = isRemoteShadowAgent(agent);
  if (filter === "cloud") return remote;
  return !remote && !isSharedExpertViewer(agent);
}
