/** True when ``url`` points at an uploaded Octop avatar API resource. */
export function isUploadedAvatarUrl(url?: string | null): boolean {
  const text = (url || "").trim().split("?")[0];
  if (!text) return false;
  return /\/avatar\/?$/.test(text);
}

/**
 * Extract a bundled expert/team portrait id from ``/experts/avatars/{id}.svg``.
 * Returns null for empty, uploaded, or non-bundled URLs.
 */
export function presetIdFromExpertAvatarUrl(
  url?: string | null,
): string | null {
  const text = (url || "").trim().split("?")[0];
  const match = /^\/experts\/avatars\/([^/]+)\.svg$/i.exec(text);
  return match?.[1] ?? null;
}

/** Split stored agent ``icon_url`` into upload URL vs preset id for the picker. */
export function splitExpertAvatarUrl(url?: string | null): {
  imageUrl: string | null;
  presetId: string | null;
} {
  const text = url?.trim() || "";
  if (!text) return { imageUrl: null, presetId: null };
  if (isUploadedAvatarUrl(text)) {
    return { imageUrl: text, presetId: null };
  }
  const presetId = presetIdFromExpertAvatarUrl(text);
  if (presetId) {
    return { imageUrl: null, presetId };
  }
  // External or legacy URL — treat as a custom photo.
  return { imageUrl: text, presetId: null };
}
