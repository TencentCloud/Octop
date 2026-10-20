/**
 * Session-scoped form drafts for edit drawers.
 *
 * Survives drawer close within the same tab; cleared on successful save
 * or when the page is refreshed (sessionStorage).
 */

const PREFIX = "agentbuddy:form-draft:";

export function draftStorageKey(scope: string): string {
  return `${PREFIX}${scope}`;
}

export function loadFormDraft<T extends Record<string, unknown>>(
  scope: string,
): T | null {
  if (!scope) return null;
  try {
    const raw = sessionStorage.getItem(draftStorageKey(scope));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return parsed as T;
  } catch {
    return null;
  }
}

export function saveFormDraft(
  scope: string,
  values: Record<string, unknown>,
): void {
  if (!scope) return;
  try {
    sessionStorage.setItem(draftStorageKey(scope), JSON.stringify(values));
  } catch {
    /* quota / private mode */
  }
}

export function clearFormDraft(scope: string): void {
  if (!scope) return;
  try {
    sessionStorage.removeItem(draftStorageKey(scope));
  } catch {
    /* ignore */
  }
}
