import { useSyncExternalStore } from "react";
import { getToolRendererVersion, subscribeToolRenderers } from "./registry";

/** Re-render when plugin UI modules register/unregister renderers. */
export function useToolRendererVersion(): number {
  return useSyncExternalStore(
    subscribeToolRenderers,
    getToolRendererVersion,
    getToolRendererVersion,
  );
}
