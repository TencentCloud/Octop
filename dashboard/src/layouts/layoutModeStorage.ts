/** App chrome layout: classic (dual rail) vs minimal (single nav with settings/records). */
export type LayoutMode = "classic" | "minimal";

/** Minimal-mode lower pane: merged settings nav vs agent/session records. */
export type MinimalNavPane = "settings" | "records";

export const LAYOUT_MODE_KEY = "octop:layout-mode";
/** v2: default pane is records (primary). */
export const MINIMAL_NAV_PANE_KEY = "octop:sidebar-minimal-pane-v2";

export function loadLayoutMode(): LayoutMode {
  try {
    const raw = localStorage.getItem(LAYOUT_MODE_KEY);
    if (raw === "minimal" || raw === "classic") return raw;
  } catch {
    /* ignore */
  }
  return "classic";
}

export function saveLayoutMode(mode: LayoutMode): void {
  try {
    localStorage.setItem(LAYOUT_MODE_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function loadMinimalNavPane(): MinimalNavPane {
  try {
    const raw = localStorage.getItem(MINIMAL_NAV_PANE_KEY);
    // Accept briefly-shipped chat/nav aliases if present.
    if (raw === "settings" || raw === "nav") return "settings";
    if (raw === "records" || raw === "chat") return "records";
  } catch {
    /* ignore */
  }
  return "records";
}

export function saveMinimalNavPane(pane: MinimalNavPane): void {
  try {
    localStorage.setItem(MINIMAL_NAV_PANE_KEY, pane);
  } catch {
    /* ignore */
  }
}
