import type { ProviderModel } from "../../useProviders";

/**
 * The model the provider panel preselects as its "default model" — the one
 * "Test connection" probes when the field is left as-is.
 *
 * Prefer the first enabled model (#2312), falling back to the first entry
 * when all models are disabled, or "" when the list is empty.
 */
export function pickDefaultModelId(
  models: ProviderModel[] | undefined,
): string {
  const list = models ?? [];
  if (!list.length) return "";
  return (list.find((m) => m.enabled !== false) ?? list[0]).id;
}
