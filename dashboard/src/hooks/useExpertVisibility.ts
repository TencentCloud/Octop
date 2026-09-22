import { useEffect, useState } from "react";
import {
  octopSettingsApi,
  type OctopExpertVisibilitySettings,
} from "../api/modules/settings";

/**
 * Expert visibility policy (via GET /api/settings/expert-visibility).
 *
 * ``hide_builtin_experts`` / ``hide_market`` let an admin hide the built-in
 * expert library and the SkillHub expert market from non-admin users. Admins
 * always see everything, and an unset policy keeps the historic behaviour.
 *
 * Cached at module scope with a tiny listener set so every consumer (the
 * Experts tabs and the admin control) stays in sync after an update.
 */
export const EXPERT_VISIBILITY_DEFAULT: OctopExpertVisibilitySettings = {
  hide_builtin_experts: false,
  hide_market: false,
};

function normalize(
  value: Partial<OctopExpertVisibilitySettings> | null | undefined,
): OctopExpertVisibilitySettings {
  return {
    hide_builtin_experts: Boolean(value?.hide_builtin_experts),
    hide_market: Boolean(value?.hide_market),
  };
}

let cache: OctopExpertVisibilitySettings | null = null;
let inflight: Promise<OctopExpertVisibilitySettings> | null = null;
const listeners = new Set<(value: OctopExpertVisibilitySettings) => void>();

function emit(value: OctopExpertVisibilitySettings): void {
  cache = value;
  for (const listener of listeners) listener(value);
}

export async function fetchExpertVisibility(
  force = false,
): Promise<OctopExpertVisibilitySettings> {
  if (!force && cache) return cache;
  if (!inflight) {
    inflight = octopSettingsApi
      .expertVisibility()
      .then((settings) => {
        const next = normalize(settings);
        emit(next);
        return next;
      })
      .catch(() => {
        const next = cache ?? EXPERT_VISIBILITY_DEFAULT;
        emit(next);
        return next;
      })
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Persist a new policy and broadcast it to all consumers. Admin only. */
export async function saveExpertVisibility(
  next: OctopExpertVisibilitySettings,
): Promise<OctopExpertVisibilitySettings> {
  const saved = normalize(await octopSettingsApi.updateExpertVisibility(next));
  emit(saved);
  return saved;
}

export function useExpertVisibility(): {
  hideBuiltinExperts: boolean;
  hideMarket: boolean;
  refresh: () => Promise<OctopExpertVisibilitySettings>;
  save: (
    next: OctopExpertVisibilitySettings,
  ) => Promise<OctopExpertVisibilitySettings>;
} {
  const [value, setValue] = useState<OctopExpertVisibilitySettings>(
    cache ?? EXPERT_VISIBILITY_DEFAULT,
  );

  useEffect(() => {
    const listener = (v: OctopExpertVisibilitySettings) => setValue(v);
    listeners.add(listener);
    void fetchExpertVisibility().then(setValue);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  return {
    hideBuiltinExperts: value.hide_builtin_experts,
    hideMarket: value.hide_market,
    refresh: () => fetchExpertVisibility(true),
    save: saveExpertVisibility,
  };
}
