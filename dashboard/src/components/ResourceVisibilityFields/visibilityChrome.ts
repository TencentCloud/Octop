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
 * Group names are only needed when the groups radio can appear and there may
 * be groups to list. A single account hides the picker; a known-empty catalog
 * skips the list request.
 */
export function needsGroupCatalog(counts: {
  userCount: number | null;
  groupCount: number | null;
}): boolean {
  if (counts.userCount === 1) return false;
  if (counts.groupCount === 0) return false;
  return true;
}

/** Groups radio is always offered once the multi-user picker is shown. */
export function showGroupVisibilityOption(
  _audience: AudienceSnapshot,
  _visibility: ResourceVisibilityMode,
): boolean {
  return true;
}

/** Hide the whole picker when one account is the only audience. */
export function isVisibilityControlVisible(
  audience: AudienceSnapshot,
  _opts: { allowOwner: boolean; visibility: ResourceVisibilityMode },
): boolean {
  if (audience.status !== "ready") return false;
  if (audience.userCount === 1) return false;
  return true;
}
