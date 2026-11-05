import type { TFunction } from "i18next";
import { describe, expect, it } from "vitest";
import { mergePresetModels, modelsFromPreset } from "./presetModels";
import type { ProviderModel, ProviderPreset } from "./useProviders";

const t = ((key: string) => key) as TFunction;
const preset: ProviderPreset = {
  id: "tencent-hy-token-plan",
  name: "Tencent Cloud Hy Token Plan",
  base_url: "https://api.lkeap.cloud.tencent.com/plan/v3",
  protocol: "openai",
  api_key_prefix: "sk-tp-",
  models: [
    {
      id: "hy4",
      name: "Hy4",
      context_window: 1_024_000,
      max_input_tokens: 960_000,
      max_output_tokens: 64_000,
      reasoning: true,
      reasoning_config: {
        supported: true,
        toggle: true,
        default_mode: "enabled",
        adapter: "thinking",
      },
    },
    { id: "hy3", name: "Hy3", max_input_tokens: 256_000 },
  ],
};

describe("preset models", () => {
  it("reconciles a package in preset order and removes models from other plans", () => {
    const existing: ProviderModel[] = [
      { id: "hy3", name: "My Hy3", enabled: false },
      { id: "glm-5", name: "Other plan", enabled: true },
    ];
    const merged = mergePresetModels(
      existing,
      { ...preset, model_catalog_locked: true },
      t,
    );
    expect(merged.map((model) => model.id)).toEqual(["hy4", "hy3"]);
    expect(merged[0].enabled).toBe(false);
    expect(merged[1]).toBe(existing[0]);
    expect(existing).toHaveLength(2);
  });
  it("keeps HY4 context, separate token limits, and thinking controls on creation", () => {
    expect(modelsFromPreset(preset, t)[0]).toMatchObject({
      id: "hy4",
      enabled: true,
      input: ["text"],
      context_window: 1_024_000,
      max_input_tokens: 960_000,
      max_tokens: 64_000,
      reasoning: true,
      reasoning_config: preset.models[0].reasoning_config,
    });
  });

  it("appends HY4 disabled while preserving defaults, custom models and disabled choices", () => {
    const existing: ProviderModel[] = [
      { id: "custom", name: "My default", enabled: true, max_tokens: 512 },
      {
        id: "hy3",
        name: "My Hy3",
        enabled: false,
        context_window: 128_000,
        visibility: "groups",
        group_ids: ["team"],
      },
    ];
    const before = structuredClone(existing);
    const merged = mergePresetModels(existing, preset, t);

    expect(merged.slice(0, existing.length)).toEqual(before);
    expect(existing).toEqual(before);
    expect(merged[2]).toMatchObject({
      id: "hy4",
      enabled: false,
      max_tokens: 64_000,
      reasoning_config: preset.models[0].reasoning_config,
    });
    expect(mergePresetModels(merged, preset, t)).toBe(merged);
  });

  it("does not duplicate repeated preset model ids", () => {
    const merged = mergePresetModels(
      [],
      { ...preset, models: [preset.models[0], preset.models[0]] },
      t,
    );
    expect(merged.map((model) => model.id)).toEqual(["hy4"]);
  });

  it("preserves embedding purpose for newly synced models", () => {
    const [model] = mergePresetModels(
      [],
      {
        ...preset,
        purpose: "embedding",
        models: [{ id: "text-embedding", name: "Embedding", max_tokens: 8192 }],
      },
      t,
    );
    expect(model).toMatchObject({
      enabled: false,
      embedding: true,
      task: "embedding",
      max_tokens: 8192,
    });
  });
});
