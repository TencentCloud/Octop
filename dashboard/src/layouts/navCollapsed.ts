/** Desktop left-nav collapse preference. */
export const NAV_COLLAPSED_KEY = "octop:sidebar:collapsed";

export function readNavCollapsed(): boolean {
  try {
    return localStorage.getItem(NAV_COLLAPSED_KEY) === "true";
  } catch {
    return false;
  }
}

export function writeNavCollapsed(collapsed: boolean): void {
  try {
    localStorage.setItem(NAV_COLLAPSED_KEY, String(collapsed));
  } catch {
    /* ignore */
  }
}
