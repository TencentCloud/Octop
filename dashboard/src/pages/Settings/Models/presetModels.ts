import type { TFunction } from "i18next";
import type { ProviderModel, ProviderPreset } from "./useProviders";
import { enrichWizardModel } from "./wizardModelMeta";

/** Convert bundled metadata into editable models without losing runtime limits. */
export function modelsFromPreset(
  preset: ProviderPreset,
  t: TFunction,
  enabled = true,
): ProviderModel[] {
  const embeddingLane =
    preset.purpose === "embedding" || preset.provider_variant === "embedding";
  return preset.models.map((model) => {
    const meta = enrichWizardModel(model, t);
    const entry: ProviderModel = {
      id: model.id,
      name: model.name,
      enabled,
      input: meta.input,
      thinking: null,
    };
    if (meta.reasoning) entry.reasoning = true;
    if (model.reasoning_config) entry.reasoning_config = model.reasoning_config;
    if (meta.context_window) entry.context_window = meta.context_window;
    if (model.max_input_tokens) entry.max_input_tokens = model.max_input_tokens;
    const maxOutput = model.max_output_tokens ?? meta.max_tokens;
    if (maxOutput) entry.max_tokens = maxOutput;
    if (embeddingLane || model.embedding || model.task === "embedding") {
      entry.embedding = true;
      entry.task = "embedding";
    }
    return entry;
  });
}

/** Package catalogs are authoritative; other presets only append missing ids. */
export function mergePresetModels(
  models: ProviderModel[],
  preset: ProviderPreset,
  t: TFunction,
): ProviderModel[] {
  if (preset.model_catalog_locked) {
    const existing = new Map(models.map((model) => [model.id, model]));
    const seen = new Set<string>();
    return modelsFromPreset(preset, t, false).flatMap((model) => {
      if (seen.has(model.id)) return [];
      seen.add(model.id);
      return [existing.get(model.id) ?? model];
    });
  }
  const ids = new Set(models.map((model) => model.id));
  const added = modelsFromPreset(preset, t, false).filter((model) => {
    if (ids.has(model.id)) return false;
    ids.add(model.id);
    return true;
  });
  return added.length ? [...models, ...added] : models;
}
