import type { ComponentType } from "react";
import { ModelKeysPanel } from "../ModelKeys/ModelKeysPanel";

/**
 * Registry of self-service credential tabs.
 *
 * Each credential feature adds one entry. Keep `key` stable: it is used by
 * `?tab=` deep links and must match the standalone route alias. Entries render
 * in array order; keep `models` before `search`.
 */
export interface KeysTab {
  key: string;
  labelKey: string;
  Component: ComponentType;
}

export const KEYS_TABS: KeysTab[] = [
  {
    key: "models",
    labelKey: "nav.modelKeys",
    Component: ModelKeysPanel,
  },
];
