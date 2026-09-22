/** Cross-tab signal when installed plugins change (market install / uninstall). */

export const PLUGINS_CHANGED_EVENT = "octop-plugins-changed";

export function notifyPluginsChanged(): void {
  window.dispatchEvent(new Event(PLUGINS_CHANGED_EVENT));
}
