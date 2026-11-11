import type { ResourceVisibilityMode } from "../../api/modules/userGroups";

/** Loaded sharing context for the who-can-use picker. */
export type AudienceSnapshot = {
  status: "loading" | "ready";
  /** Enabled accounts. ``null`` when the count could not be loaded. */
  userCount: number | null;
  /** User groups. ``null`` when the count could not be loaded. */
  groupCount: number | null;
  /** Group catalog loaded successfully (may still be empty). */
  groupsLoaded: boolean;
  groupCountFromList: number;
};

/**
 * Group names are only needed when the groups radio can appear.
 * A single account hides the picker; zero groups hides that radio.
 */
export function needsGroupCatalog(counts: {
  userCount: number | null;
  groupCount: number | null;
}): boolean {
  if (counts.userCount === 1) return false;
  if (counts.groupCount === 0) return false;
  return true;
}

export function showGroupVisibilityOption(
  audience: AudienceSnapshot,
  visibility: ResourceVisibilityMode,
): boolean {
  if (visibility === "groups") return true;
  if (audience.groupCount === 0) return false;
  if (audience.groupCount != null && audience.groupCount > 0) return true;
  if (audience.groupsLoaded) return audience.groupCountFromList > 0;
  return true;
}

/** Hide the whole picker when one account is the only audience, or when a single remaining choice would be "everyone". */
export function isVisibilityControlVisible(
  audience: AudienceSnapshot,
  opts: { allowOwner: boolean; visibility: ResourceVisibilityMode },
): boolean {
  if (audience.status !== "ready") return false;
  if (audience.userCount === 1) return false;
  const groups = showGroupVisibilityOption(audience, opts.visibility);
  const choices = (opts.allowOwner ? 1 : 0) + 1 + (groups ? 1 : 0);
  return choices > 1;
}
