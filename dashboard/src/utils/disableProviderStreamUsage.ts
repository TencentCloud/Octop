import { request } from "../api/request";
import type { ResolvedModel } from "../api/types";
import { modelOptionValue } from "./modelOptions";

function isExplicitModelRef(
  modelRef: string | null | undefined,
): string | null {
  const key = (modelRef || "").trim();
  if (!key || key.toLowerCase() === "auto") return null;
  return key;
}

/** Resolve the provider row to PATCH for an explicit ``provider/model`` ref. */
export function providerIdForModelRef(
  models: ResolvedModel[],
  modelRef: string | null | undefined,
): number | null {
  const key = isExplicitModelRef(modelRef);
  if (!key) return null;
  const match = models.find((m) => modelOptionValue(m) === key);
  const id = match?.provider_id;
  return typeof id === "number" && id > 0 ? id : null;
}

/**
 * First catalog match among explicit refs (this-turn composer, then defaults).
 * Auto / empty never falls back to the first catalog row.
 */
export function providerIdForTurn(
  models: ResolvedModel[],
  modelRefs: Array<string | null | undefined>,
): number | null {
  for (const ref of modelRefs) {
    const id = providerIdForModelRef(models, ref);
    if (id != null) return id;
  }
  return null;
}

/** Turn off streamed token usage on an existing OpenAI-compatible provider. */
export async function disableProviderStreamUsage(
  providerId: number,
): Promise<void> {
  await request(`/admin/providers/${providerId}`, {
    method: "PATCH",
    body: JSON.stringify({ stream_usage: false }),
  });
}
