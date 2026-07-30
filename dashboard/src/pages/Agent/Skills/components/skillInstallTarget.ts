/** Shared install destination for skill market / URL import UI. */

export type SkillInstallTarget =
  | { type: "agent"; agentId: string }
  | { type: "package"; packageId: string };

export function skillHubRankingsPath(target: SkillInstallTarget): string {
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/rankings?type=all`;
  }
  return `/skill-packages/hub/rankings?type=all`;
}

export function skillHubSearchPath(
  target: SkillInstallTarget,
  query: string,
  limit = 50,
): string {
  const q = encodeURIComponent(query);
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/search?q=${q}&limit=${limit}`;
  }
  return `/skill-packages/hub/search?q=${q}&limit=${limit}`;
}

export function skillHubInstallPath(target: SkillInstallTarget): string {
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills/hub/install`;
  }
  return `/skill-packages/${target.packageId}/skills/hub/install`;
}

export function skillListPath(target: SkillInstallTarget): string {
  if (target.type === "agent") {
    return `/agents/${target.agentId}/skills`;
  }
  return `/skill-packages/${target.packageId}/skills`;
}
